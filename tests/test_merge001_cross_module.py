"""Cross-PR contract and fail-closed safety regression; test data is synthetic."""
import hashlib

import pytest

from hbi.benchmark003_framework import validate
from hbi.data009_prospective_bridge import audit
from hbi.merge001_shadow_handoff import preview_handoff
from hbi.model003_shadow_research import candidate_features


def fixture(tmp_path):
    rid = "TEST:2026-11-09:1"
    source = {}
    for role in ("PROGRAM", "ROSTER", "WIN", "MODEL", "RESULT", "SETTLEMENT"):
        raw = ("synthetic:" + role).encode()
        p = tmp_path / (role + ".bin")
        p.write_bytes(raw)
        source[role] = {
            "race_id": rid, "member": p.name,
            "source_hash": hashlib.sha256(raw).hexdigest(),
            "observed_at": (
                "2026-11-09T20:05:00+00:00" if role in ("RESULT", "SETTLEMENT")
                else "2026-11-09T19:55:00+00:00"
            ),
        }
    return {
        "race_id": rid, "scheduled_start_at": "2026-11-09T20:00:00+00:00",
        "decision_cutoff": "2026-11-09T19:56:00+00:00",
        "sources": source, "active_field": ["1", "2"],
        "model_probabilities": {"1": .55, "2": .45},
        "win_odds": {"1": 2., "2": 3.},
        "scratches_independently_verified": True,
        "actual_start_independently_verified": True,
        "source_publication_or_asof_attested": True,
        "provider_identity_verified": True,
        "winner_selection_id": "1", "model_version": "SHADOW_TEST_ONLY",
    }


def test_cross_module_preview_is_structurally_valid_but_never_scored(tmp_path):
    race = fixture(tmp_path)
    result = preview_handoff(race, tmp_path, race_date="2026-11-09")
    assert result["status"] == "SCHEMA_COMPATIBLE_NOT_SCORE_AUTHORIZED"
    assert result["benchmark_eligible"] is False
    assert result["pit_evidence_status"] == "PIT_UNPROVEN"
    assert result["bet_authority"] is False
    assert "NORMALIZED_WIN_PREVIEW" not in result


def test_changed_source_and_late_win_fail_closed_across_modules(tmp_path):
    race = fixture(tmp_path)
    (tmp_path / "WIN.bin").write_bytes(b"changed")
    out = preview_handoff(race, tmp_path, race_date="2026-11-09")
    assert out["status"] == "BLOCKED_SOURCE_AUDIT"
    assert "WIN:SOURCE_BYTES_SHA_CONFLICT" in out["blockers"]
    race = fixture(tmp_path)
    race["sources"]["WIN"]["observed_at"] = "2026-11-09T19:58:00+00:00"
    out = preview_handoff(race, tmp_path, race_date="2026-11-09")
    assert "WIN:SOURCE_OBSERVED_AFTER_CUTOFF" in out["blockers"]


def test_direct_data009_is_not_a_benchmark_certificate(tmp_path):
    result = audit(fixture(tmp_path), tmp_path)
    assert result["evaluation_eligible"] is False
    with pytest.raises(ValueError, match="INVALID_EVIDENCE_SCOPE"):
        validate(result)


def test_pit_claim_needs_certificate_even_on_structural_example():
    bad = {
        "race_id": "TEST", "race_date": "2026-11-09", "scope": "PIT_CERTIFIED",
        "active_field": ["1", "2"],
        "probabilities": {"A": {"1": .6, "2": .4}},
        "winner_selection_id": "1", "race_start_at": "2026-11-09T20:00:00Z",
        "decision_cutoff": "2026-11-09T19:56:00Z",
        "pit_evidence_status": "PIT_UNPROVEN",
    }
    with pytest.raises(ValueError, match="PIT_CLAIM_WITHOUT_CERTIFICATE"):
        validate(bad)


def test_model003_provisional_history_never_becomes_active_feature():
    result = candidate_features(
        target_date="2026-11-09", horse_id="TEST-ONLY",
        identity_status="PROVISIONAL_MATCH", starts=[],
    )
    assert result["status"] == "NOT_TESTABLE"
    assert result["features"] == {}
    assert result["bet_authority"] is False


def test_missing_model_version_stays_blocked(tmp_path):
    race = fixture(tmp_path)
    race.pop("model_version")
    out = preview_handoff(race, tmp_path, race_date="2026-11-09")
    assert out["status"] == "BLOCKED_MODEL_VERSION_UNATTESTED"
    assert out["benchmark_eligible"] is False
