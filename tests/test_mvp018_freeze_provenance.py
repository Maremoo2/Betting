"""MVP-018 strict original-backed explanations; never reconstruct a model freeze."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp018_freeze_provenance import _original, explain

RACE = "RIKSTOTO:F1_NR_2026-11-03:6"
MODEL_SHA = "a" * 64
ORIGINAL_SHA = {
    41689647527: "ff60ace9f57c3c1193b9024ae48012f12349d4cecc0b7d75f0cc6bd5fcaaf552",
    41710594697: "5cc2a0d920e4dd8db9b0100a9554af79e9941e53dc74ea11bab8d6a0578c1596",
    41665938596: "a371cfd49e21eb8cf70abdf0be3923e19a21e3161f4ede87467d23c8ba2c4a8e",
    41826490000: "87e8cd9751a9987e49180c95c62d16ea418767fdbecaff3345c634f409c5dae4",
    41811192493: "afb2f64cccbaf89837ef22c2368468fff36538b2ce1ece70fb46db34ecadb49a",
}
BASELINE_SCORECARD_SHA = "a7cc16d026ea08e0042dc4d6c5c2d75d3212bfd5fb00203dbbbbc36455f11d2b"


def _write(path: Path, obj: dict) -> str:
    raw = json.dumps(obj, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _scorecard() -> dict:
    return {
        "schema": "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1",
        "model_originals_verified_by_sha": True,
        "bet_authority": False,
        "counts": {"physical_races": 1, "paired_champion_core004": 0,
                   "triple_evaluable": 0},
        "records": [{
            "race_id": RACE, "status": "NOT_EVALUABLE",
            "reasons": ["NO_VERIFIED_FROZEN_MODEL"],
            "source_model_original_sha256": None, "score": None,
        }],
    }


def _cohort(*, reason: str = "COLLECTOR_PDF_FIELD_MISMATCH") -> dict:
    return {
        "schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1",
        "bet_authority": False, "pit_certified": False,
        "as_of_utc": "2026-11-03T15:01:00+00:00",
        "index_written_at_utc": "2026-11-03T15:01:01+00:00",
        "original_cohort": [RACE],
        "processed": [],
        "not_processed": [{
            "race_id": RACE,
            "reason": "COLLECTOR_RESEARCH_MODEL_GATE_NOT_VERIFIED",
            "collector_blockers": [reason],
        }],
        "collector_handoff": [{
            "race_id": RACE, "blockers": [reason],
            "research_model_eligible": False,
            "model_input_approved": False,
        }],
    }


def _spec(tmp_path: Path, obj: dict | None = None, *, run=1, artifact=2) -> dict:
    root = tmp_path / f"{run}"
    root.mkdir()
    path = root / "cohort-index.json"
    sha = _write(path, obj or _cohort())
    return {"path": str(path), "sha256": sha, "run_id": run,
            "artifact_id": artifact}


def test_source_conflict_classified_without_any_model_promotion(tmp_path):
    result = explain(_scorecard(), [_spec(tmp_path)])
    assert result["original_no_freeze_target_count"] == 1
    assert result["target_races_found_in_supplied_cohort_originals"] == 1
    assert result["counts_by_category"] == {"SOURCE_CONFLICT": 1}
    row = result["races"][0]
    assert row["category"] == "SOURCE_CONFLICT"
    assert row["chosen_latest_observation"]["source_report_sha256"] is None
    assert row["scorecard_original_model_sha256"] is None
    assert result["frozen_models_reconstructed_or_promoted"] == 0
    assert result["bet_authority"] is False
    assert result["pit_certification_performed"] is False


def test_no_original_source_is_unknown_not_proof_of_schedule_failure():
    result = explain(_scorecard(), [])
    assert result["target_races_without_supplied_original"] == 1
    assert result["races"][0]["specific_reason"] == (
        "NO_COHORT_ORIGINAL_SUPPLIED_NOT_PROOF_OF_NO_CAPTURE"
    )


def test_multiple_originals_latest_asof_chosen_independent_of_outcome(tmp_path):
    original = _spec(tmp_path, _cohort(reason="COLLECTOR_ATG_ATG_IDENTITY_UNVERIFIED"))
    later = _cohort()
    later["as_of_utc"] = "2026-11-03T15:03:00+00:00"
    later["index_written_at_utc"] = "2026-11-03T15:03:01+00:00"
    second = _spec(tmp_path, later, run=2, artifact=3)
    score = _scorecard()
    score["records"][0]["winner_selection_id"] = "5"
    first = explain(score, [second, original])
    score["records"][0]["winner_selection_id"] = "1"
    after = explain(score, [original, second])
    assert first["races"][0]["category"] == after["races"][0]["category"] == "SOURCE_CONFLICT"
    assert first["races"][0]["chosen_latest_observation"]["source_run_id"] == 2


@pytest.mark.parametrize("bad,reason", [
    ("duplicate", "ORIGINAL_PHYSICAL_COHORT_INVALID"),
    ("hidden", "COHORT_MEMBER_DENOMINATOR_CONFLICT"),
    ("retro", "COHORT_WRITTEN_BEFORE_ASOF"),
    ("pit", "COHORT_ORIGINAL_CONTRACT_INVALID"),
])
def test_nonmatching_or_unsafe_original_rejected(tmp_path, bad, reason):
    obj = _cohort()
    if bad == "duplicate":
        obj["original_cohort"] = [RACE, RACE]
    elif bad == "hidden":
        obj["not_processed"] = []
    elif bad == "retro":
        obj["index_written_at_utc"] = "2026-11-03T14:59:59+00:00"
    elif bad == "pit":
        obj["bet_authority"] = True
    with pytest.raises(ValueError, match=reason):
        explain(_scorecard(), [_spec(tmp_path, obj)])


def test_modified_original_sha_rejected_and_duplicate_run_blocked(tmp_path):
    spec = _spec(tmp_path)
    with pytest.raises(ValueError, match="ORIGINAL_SHA256_MISMATCH"):
        explain(_scorecard(), [{**spec, "sha256": "0" * 64}])
    with pytest.raises(ValueError, match="ORIGINAL_RUN_ARTIFACT_ID_INVALID_OR_DUPLICATE"):
        explain(_scorecard(), [spec, spec])


def test_unverified_model_report_never_made_into_a_frozen_prediction(tmp_path):
    obj = _cohort()
    obj["processed"] = [{
        "race_id": RACE, "model_status": "MODEL_READY",
        "report_sha256": MODEL_SHA, "directory": "bet-mvp-shadow/race-001",
    }]
    obj["not_processed"] = []
    res = explain(_scorecard(), [_spec(tmp_path, obj)])
    row = res["races"][0]
    assert row["category"] == "UNRESOLVED"
    assert "REQUIRES_INDEPENDENT_MODEL_SHA_REPLAY" in row["specific_reason"]
    assert res["frozen_models_reconstructed_or_promoted"] == 0


def test_original_github_five_root_causes():
    root = os.environ.get("MVP018_SOURCE_ORIGINAL_ROOT")
    if not root:
        pytest.skip("Authentic GitHub original cohort index is available only in PR CI")
    path = Path(root)
    scorecard_path = path / "scorecard/index.json"
    scorecard = _original(scorecard_path, BASELINE_SCORECARD_SHA)
    artifacts = {
        41689647527: 13257326927,
        41710594697: 13267848493,
        41665938596: 13245606773,
        41826490000: 13319117566,
        41811192493: 13311119836,
    }
    specs = [{
        "run_id": run,
        "artifact_id": artifact,
        "path": str(path / f"run-{run}/cohort-index.json"),
        "sha256": ORIGINAL_SHA[run],
    } for run, artifact in artifacts.items()]
    result = explain(scorecard, specs)
    assert result["physical_races_in_cumulative_scorecard"] == 65
    assert result["original_no_freeze_target_count"] == 27
    assert result["original_scorecard_model_pairs"] == 16
    assert result["original_scorecard_win_triples"] == 14
    by_race = {row["race_id"]: row for row in result["races"]}
    expected = {
        "RIKSTOTO:BJ_NR_2026-11-03:2": ("IDENTITY_NOT_VERIFIED",
                                         "INDEPENDENT_REGISTRATION_OR_ATG_IDENTITY_MISSING"),
        "RIKSTOTO:BJ_NR_2026-11-03:8": ("SOURCE_CONFLICT",
                                         "ACTIVE_FIELD_OR_ROSTER_REVISION_CONFLICT"),
        "RIKSTOTO:F1_NR_2026-11-03:6": ("SOURCE_CONFLICT",
                                         "PDF_FIELD_MISMATCH_IN_ORIGINAL_RUN"),
        "RIKSTOTO:F1_NR_2026-11-04:1": ("MODEL_GATE_REJECTED",
                                         "CONSERVATIVE_T4_ALREADY_REACHED"),
        "RIKSTOTO:F2_NR_2026-11-04:2": ("MODEL_GATE_REJECTED",
                                         "ATG_FULL_FIELD_OR_FUNDAMENTALS_INCOMPLETE"),
    }
    for rid, (category, reason) in expected.items():
        assert by_race[rid]["category"] == category
        assert by_race[rid]["specific_reason"] == reason
        assert by_race[rid]["chosen_latest_observation"]["cohort_index_sha256"] in ORIGINAL_SHA.values()
    assert result["bet_authority"] is False
    assert result["pit_certification_performed"] is False
    assert result["frozen_models_reconstructed_or_promoted"] == 0
