"""P0 read-only original Champion replay: fail-closed per-runner admission."""
from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from hbi.fundamental import MarketFreeFundamentalChampionV1

mod = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "scripts/weekend_champion_research_readonly.py"
))
_time, _verified, _canonical = mod["_time"], mod["_verified_bytes"], mod["_canonical"]


def _leg():
    return {
        "physical_race_id": "RIKSTOTO:S1_NR_2026-11-07:5",
        "race_no": 5, "active_runners": 2,
        "runners": [
            {"number": 1, "name": "A", "horse_registration": "TMP-A", "active": True},
            {"number": 2, "name": "B", "horse_registration": "TMP-B", "active": True},
        ],
    }


def _starts():
    return [
        {"startNumber": n, "raceKey": "S1_NR_2026-11-07#5", "raceNumber": 5,
         "horseRegistrationNumber": f"TMP-{name}", "horseName": name, "isScratched": False}
        for n, name in [(1, "A"), (2, "B")]
    ]


def test_source_utc_must_be_aware():
    with pytest.raises(ValueError, match="ORIGINAL_SOURCE_UTC_NOT_AWARE"):
        _time("2026-11-06T15:30:00")
    assert _time("2026-11-06T15:30:00+00:00").isoformat().endswith("+00:00")


def test_unmodified_original_sha_required(tmp_path):
    raw = b'{"races":[]}'
    sha = hashlib.sha256(raw).hexdigest()
    (tmp_path / f"{sha}.json").write_bytes(raw)
    assert _verified(tmp_path, sha, sha + ".json") == raw
    (tmp_path / f"{sha}.json").write_bytes(b'{"races":[0]}')
    with pytest.raises(ValueError, match="ORIGINAL_SHA_MISMATCH"):
        _verified(tmp_path, sha, sha + ".json")


def test_exact_canonical_roster_accepts_original_and_blocks_relabels():
    active, scratched = _canonical(_starts(), [], _leg())
    assert len(active) == 2 and scratched == set()
    altered = _starts()
    altered[0]["horseName"] = "B"
    with pytest.raises(ValueError, match="REPORTED_ROSTER_NOT_ORIGINAL"):
        _canonical(altered, [], _leg())


def test_new_scratch_without_authentic_matching_receipt_rejected():
    starts = _starts()
    starts[0]["isScratched"] = True
    with pytest.raises(ValueError, match="ORIGINAL_SCRATCH_CONFLICT"):
        _canonical(starts, [], _leg())


def test_duplicate_provider_registration_does_not_pass():
    starts = _starts()
    starts[1]["horseRegistrationNumber"] = starts[0]["horseRegistrationNumber"]
    with pytest.raises(ValueError, match="DUPLICATE_RIKSTOTO_REGISTRATION"):
        _canonical(starts, [], _leg())


def test_unmodified_model_is_shadow_only_and_has_no_market_features():
    model = MarketFreeFundamentalChampionV1()
    assert model.VERSION == "FUNDAMENTAL_CHAMPION_V1_1"
    assert model.CALIBRATION_VERSION == "UNVALIDATED_SHADOW_V1_1"
    assert model.ROLE.value == "SHADOW_CHAMPION"


def test_no_synthetic_probability_for_failed_full_field():
    source = Path(__file__).resolve().parents[1] / "scripts/weekend_champion_research_readonly.py"
    text = source.read_text()
    assert "if len(matched) == len(active) and evidence[\"passed\"] is True:" in text
    assert "model.estimate(" in text
    assert '"bet_authority": False' in text
    assert '"v85_system_ev": "NOT_ESTABLISHED"' in text
    assert "name_key" not in text  # No ad-hoc suffix removal or fuzzy name matching
    assert "market_free_model_executed" in text


def test_reject_falsely_approved_original_status(tmp_path):
    # Missing originals are never replaced by remembered runner counts.
    original = tmp_path / "original-capture"
    atg = tmp_path / "atg"
    original.mkdir()
    atg.mkdir()
    (original / "weekend-race-intelligence.json").write_text(json.dumps(
        {"schema": "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1",
         "bet_authority": True, "new_model_invocations": 0}
    ))
    (atg / "atg-readiness.json").write_text(json.dumps(
        {"schema": "WEEKEND_ATG_AUTHENTIC_SOURCE_DIAGNOSTIC_V1",
         "bet_authority": False, "model_invocations": 0, "pit_certified": False}
    ))
    with pytest.raises(ValueError, match="UNQUALIFIED_ORIGINAL_REPORT"):
        mod["audit"](original, atg)
