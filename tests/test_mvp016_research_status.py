"""MVP-016: one read-only original-joined operational status, not a model.

Real GitHub corpus checks run in PR CI with exact four original SHA256 values.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp016_research_status import summarize

R1 = "RIKSTOTO:S1_NR_2026-11-03:1"
R2 = "RIKSTOTO:F2_NR_2026-11-04:3"
ORIGINAL_SHAS = {
    "scorecard": "62b0d78ca75847d2f2bfe895af240e45eada96a7719aefe4f880c1da02cbe178",
    "source": "151168c074b7d1f0c92bb1c568f70bd23d2669a8903540a26c9b97f32121a7d7",
    "cohort": "3b804af346a340c6713b64319fd4201881040a264360e4a014069bb60c3e7cd0",
    "manifest": "ecb4477a0ec5fc9c954862943ab8b39876d7b13c6adf701bf4e777eaa9f9df33",
}


def _write(path: Path, body: dict) -> str:
    raw = json.dumps(body, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _seed(tmp_path: Path) -> dict:
    x = {"scorecard": tmp_path / "score.json",
         "source": tmp_path / "source.json",
         "cohort": tmp_path / "cohort.json",
         "manifest": tmp_path / "manifest.json"}
    source = {
        "schema_version": "CORE_003_SHADOW_PILOT_V1",
        "bet_count": 0, "prospective_t4_success_proven": False,
        "races_in_fixed_cohort": [R2],
        "race_readiness_after": [{
            "race_id": R2, "roster_rows": 9, "active_runners_known": 9,
            "verified_active_history": 0, "history_complete_as_of_t4": False,
            "win_market_complete_as_of_t4": False,
        }],
    }
    source_sha = _write(x["source"], source)
    cohort = {
        "schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1",
        "bet_authority": False, "pit_certified": False,
        "source_report_sha256": source_sha, "original_cohort": [R2],
        "processed": [], "not_processed": [{"race_id": R2, "reason": "SOURCE_BLOCKED"}],
        "collector_handoff": [],
    }
    _write(x["cohort"], cohort)
    inventory_sha = "a" * 64
    _write(x["manifest"], {
        "schema": "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1",
        "bet_authority": False, "pit_certification_performed": False,
        "coverage_complete": False,
        "github_artifact_inventory_sha256": inventory_sha,
        "missing_originals": [{"reason": "ORIGINAL_UNINDEXED"}],
    })
    records = [
        {
            "race_id": R1, "status": "EVALUABLE_RESEARCH_ONLY",
            "benchmark_status": "TRIPLE_EVALUABLE",
            "bet_authority": False, "complete_active_field": True,
            "market_baseline_available": True,
            "source_model_original_sha256": "b" * 64,
            "winner_selection_id": "1",
            "original_result_receipts": [{"role": "complete"}, {"role": "raceday"}],
            "score": {
                "champion_log_loss": 1.8, "core004_log_loss": 1.6,
                "market_log_loss": 2.4,
                "champion_multiclass_brier": .9,
                "core004_multiclass_brier": .8,
                "market_multiclass_brier": 1.1,
            },
            "reasons": [],
        },
        {
            "race_id": R2, "status": "NOT_EVALUABLE",
            "bet_authority": False, "complete_active_field": False,
            "market_baseline_available": False, "reasons": ["NO_VERIFIED_FROZEN_MODEL"],
        },
    ]
    _write(x["scorecard"], {
        "schema": "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1",
        "authority": "READ_ONLY_RESEARCH_SCORECARD",
        "model_originals_verified_by_sha": True,
        "bet_authority": False, "v33_evaluator_called": False,
        "cumulative_original_inventory": {
            "github_artifact_inventory_sha256": inventory_sha,
        },
        "calibration": {"min_distinct_races": 30, "status": "INSUFFICIENT_DISTINCT_RACES"},
        "metrics": {"market_log_loss": 2.4},
        "counts": {
            "physical_races": 2, "complete_prediction_fields": 1,
            "paired_champion_core004": 1, "triple_evaluable": 1,
            "model_pair_only": 0, "pit_certified_paired": 0,
        },
        "records": records,
    })
    return x


def _evaluate(paths: dict) -> dict:
    return summarize(
        scorecard_index=paths["scorecard"], source_report=paths["source"],
        model_cohort_index=paths["cohort"],
        coverage_manifest=paths["manifest"],
    )


def test_source_join_and_same_race_metrics(tmp_path):
    output = _evaluate(_seed(tmp_path))
    assert output["research_only"] and output["bet_authority"] is False
    assert output["counts"]["physical_races"] == 2
    assert output["counts"]["triple_evaluable"] == 1
    assert output["counts"]["current_source_fixed_cohort"] == 1
    assert output["counts"]["current_source_rejected"] == 1
    assert output["primary_rejection_reasons"] == {"NO_VERIFIED_FROZEN_MODEL": 1}
    assert len(output["per_physical_race"]) == 2
    assert output["per_track"]["S1"]["triple_win_benchmarks"] == 1
    current = next(r for r in output["per_physical_race"] if r["race_id"] == R2)
    assert current["current_source_readiness"]["collector_model_input_approved"] is False
    delta = output["pairwise_model_differences"]["triple_same_races"]["champion_minus_market_log_loss"]
    assert delta["mean_first_minus_second"] == pytest.approx(-.6)
    assert delta["approximate_95_percent_interval"] is None
    assert delta["interpretation"] == "EXPLORATORY_INSUFFICIENT_DISTINCT_RACES"


def test_changed_source_original_rejected_without_backdating(tmp_path):
    paths = _seed(tmp_path)
    source = json.loads(paths["source"].read_text())
    source["race_readiness_after"][0]["verified_active_history"] = 9
    _write(paths["source"], source)
    with pytest.raises(ValueError, match="CURRENT_ORIGINAL_COHORT_SOURCE_SHA_MISMATCH"):
        _evaluate(paths)


@pytest.mark.parametrize("mutated_file,change,error", [
    ("scorecard", "duplicate", "SCORECARD_PHYSICAL_DENOMINATOR_INVALID"),
    ("scorecard", "invent_bet", "SCORECARD_SOURCE_CONTRACT_INVALID"),
    ("scorecard", "invent_score", "SCORECARD_QUALITY_COUNTS_INVALID"),
    ("manifest", "invent_inventory", "CUMULATIVE_COVERAGE_ORIGINAL_MISMATCH"),
    ("cohort", "invent_hidden_race", "CURRENT_COHORT_MEMBER_CONFLICT"),
])
def test_mismatched_original_input_fail_closed(tmp_path, mutated_file, change, error):
    paths = _seed(tmp_path)
    doc = json.loads(paths[mutated_file].read_text())
    if change == "duplicate":
        doc["records"].append(doc["records"][0])
    elif change == "invent_bet":
        doc["bet_authority"] = True
    elif change == "invent_score":
        doc["counts"]["triple_evaluable"] = 2
    elif change == "invent_inventory":
        doc["github_artifact_inventory_sha256"] = "f" * 64
    elif change == "invent_hidden_race":
        doc["not_processed"] = []
    _write(paths[mutated_file], doc)
    with pytest.raises(ValueError, match=error):
        _evaluate(paths)


def test_exact_original_four_artifact_replay_with_63_physical_races():
    root = os.environ.get("MVP016_RESEARCH_ORIGINAL_ROOT")
    if not root:
        pytest.skip("SHA-pinned original research bundle is available only in PR CI")
    folder = Path(root)
    files = {
        "scorecard": folder / "scorecard/index.json",
        "source": folder / "source/core003-pilot-report.json",
        "cohort": folder / "cohort/cohort-index.json",
        "manifest": folder / "manifest/manifest.json",
    }
    for key, path in files.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == ORIGINAL_SHAS[key]
    output = _evaluate(files)
    assert output["counts"]["physical_races"] == 63
    assert output["counts"]["paired_champion_core004"] == 16
    assert output["counts"]["triple_evaluable"] == 14
    assert output["counts"]["model_pair_only"] == 2
    assert output["counts"]["current_source_fixed_cohort"] == 2
    assert output["counts"]["current_source_rejected"] == 2
    assert output["counts"]["pit_certified_paired"] == 0
    assert output["coverage_status"] == "INCOMPLETE_ORIGINAL_COVERAGE"
    assert output["pairwise_model_differences"]["triple_same_races"]["champion_minus_market_log_loss"]["n_distinct_physical_races"] == 14
    assert all(r["bet_authority"] is False for r in output["per_physical_race"])
