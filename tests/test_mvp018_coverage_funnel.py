"""MVP-018 source-provenance funnel: no invented historical source transitions."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp018_coverage_funnel import build_funnel, main

ORIGINAL_SHA = {
    "scorecard": "a4a667bd596bde42b9e3dbed6d96247731067fe76f82b33ea816194fa68b5ff7",
    "source": "b75eb90a215ef1fe251da9d0d8df630cece2c7c003e2659a69a259390e67cb58",
    "cohort": "5a39954a79ca2e4d765092bfef64386eb8d77d5c9fb6685645306911c008de04",
    "manifest": "67a2ca0296c5fd571fa58c4b3a90f13d5155cb03228866bd8e0062a737951f33",
}


def _joined():
    return {
        "schema": "MVP016_CUMULATIVE_RESEARCH_STATUS_V1",
        "bet_authority": False, "pit_certification_performed": False,
        "research_only": True, "source_sha256": {
            "cumulative_scorecard_index": "a" * 64,
            "current_core003_source_report": "b" * 64,
            "current_model_cohort_index": "c" * 64,
            "cumulative_dev011_manifest": "d" * 64,
        },
        "counts": {
            "physical_races": 2, "complete_prediction_fields": 1,
            "paired_champion_core004": 1, "triple_evaluable": 1,
            "current_source_fixed_cohort": 1,
            "current_source_verified_full_fundamentals": 0,
            "current_source_complete_win": 0,
        },
        "primary_rejection_reasons": {"NO_VERIFIED_FROZEN_MODEL": 1},
        "per_physical_race": [
            {
                "race_id": "RIKSTOTO:S1_NR_2026-11-03:1",
                "model_full_field": True,
                "model_frozen_sha256": "1" * 64,
                "alternative_original_freezes": [{
                    "selected_benchmark_reference": True,
                    "eligible_pre_t4": True, "model_sha256": "1" * 64,
                }],
                "official_result_verified": True,
                "research_status": "EVALUABLE_RESEARCH_ONLY",
                "benchmark_status": "TRIPLE_EVALUABLE",
                "win_market_on_reference_freeze": True,
            },
            {
                "race_id": "RIKSTOTO:F1_NR_2026-11-04:2",
                "model_full_field": False,
                "alternative_original_freezes": [],
                "official_result_verified": False,
                "benchmark_status": "NOT_EVALUABLE",
                "current_source_readiness": {
                    "collector_source_sha256": "e" * 64,
                    "collector_model_input_approved": False,
                    "admission_status": "COLLECTOR_RESEARCH_MODEL_GATE_NOT_VERIFIED",
                    "admission_blockers": ["IDENTITY_CROSS_PROVIDER_NOT_ATTESTED"],
                },
            },
        ],
    }


def test_disjoint_current_and_cumulative_funnel_no_promotion():
    report = build_funnel(_joined())
    assert list(report["current_cohort_stages"].values()) == [1, 1, 0, 0]
    assert list(report["cumulative_benchmark_stages"].values()) == [2, 1, 1, 1]
    assert report["current_cohort_blockers_nonexclusive"] == {
        "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED": 1,
    }
    assert report["qualified_historical_freezes_created"] == 0
    assert report["bet_authority"] is False
    assert report["operational_pit_certified"] == 0
    assert "UNKNOWN" in report["data_limitation"]


@pytest.mark.parametrize(("mutation", "expected"), [
    ("duplicate_race", "PHYSICAL_RACE_DENOMINATOR_CONFLICT"),
    ("invent_result", "OFFICIAL_RESULT_WITHOUT_VERIFIED_MODEL"),
    ("invent_triple", "WIN_TRIPLE_WITHOUT_SAME_FREEZE_RESULT"),
    ("change_model_sha", "QUALIFIED_FULL_FIELD_WITHOUT_ORIGINAL_FREEZE"),
    ("uncorroborated_admission", "SOURCE_MODEL_APPROVED_WITHOUT_COLLECTOR_SHA"),
    ("change_counts", "FUNNEL_OR_SCORECARD_STAGE_CONFLICT"),
    ("invent_bet", "MVP016_SOURCE_JOIN_NOT_VERIFIED"),
])
def test_invalid_originally_joined_research_is_fail_closed(mutation, expected):
    doc = copy.deepcopy(_joined())
    if mutation == "duplicate_race":
        doc["per_physical_race"][1]["race_id"] = doc["per_physical_race"][0]["race_id"]
    elif mutation == "invent_result":
        doc["per_physical_race"][1]["official_result_verified"] = True
    elif mutation == "invent_triple":
        doc["per_physical_race"][1]["benchmark_status"] = "TRIPLE_EVALUABLE"
    elif mutation == "change_model_sha":
        doc["per_physical_race"][0]["model_frozen_sha256"] = "9" * 64
    elif mutation == "uncorroborated_admission":
        src = doc["per_physical_race"][1]["current_source_readiness"]
        src["collector_source_sha256"] = None
        src["collector_model_input_approved"] = True
    elif mutation == "change_counts":
        doc["counts"]["complete_prediction_fields"] = 2
    elif mutation == "invent_bet":
        doc["bet_authority"] = True
    with pytest.raises(ValueError, match=expected):
        build_funnel(doc)


def test_real_four_git_originals_and_zero_false_source_admission(tmp_path):
    root = os.environ.get("MVP018_FUNNEL_ORIGINAL_ROOT")
    if not root:
        pytest.skip("Original GitHub source set provided only by PR CI")
    folder = Path(root)
    paths = {
        "scorecard": folder / "scorecard/index.json",
        "source": folder / "source/core003-pilot-report.json",
        "cohort": folder / "cohort/cohort-index.json",
        "manifest": folder / "manifest/manifest.json",
    }
    for key, path in paths.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == ORIGINAL_SHA[key]
    assert main([
        "--scorecard-index", str(paths["scorecard"]),
        "--source-report", str(paths["source"]),
        "--model-cohort-index", str(paths["cohort"]),
        "--coverage-manifest", str(paths["manifest"]),
        "--output-dir", str(tmp_path / "report"),
    ]) == 0
    report = json.loads((tmp_path / "report/index.json").read_text())
    assert list(report["current_cohort_stages"].values()) == [3, 3, 0, 0]
    assert list(report["cumulative_benchmark_stages"].values()) == [67, 24, 16, 14]
    assert report["current_source_history_complete"] == 2
    assert report["current_source_win_complete"] == 0
    assert report["bet_authority"] is False
    assert report["qualified_historical_freezes_created"] == 0
    assert len(report["physical_race_ids_per_cumulative_stage"]["SAME_FREEZE_WIN_TRIPLE"]) == 14
