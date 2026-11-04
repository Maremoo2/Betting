"""MVP-019 test of source gate, clock, identity and authenticated replay."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp016_research_status import summarize
from hbi.mvp019_source_readiness import build_readiness, main


def _fixture():
    return {
        "schema": "MVP016_CUMULATIVE_RESEARCH_STATUS_V1",
        "research_only": True, "bet_authority": False,
        "pit_certification_performed": False,
        "source_clocks": {"current_core003_finished_at_utc": "2026-11-04T16:00:00+00:00"},
        "source_sha256": {
            "cumulative_scorecard_index": "a" * 64,
            "current_core003_source_report": "b" * 64,
            "current_model_cohort_index": "c" * 64,
            "cumulative_dev011_manifest": "d" * 64,
        },
        "counts": {
            "physical_races": 2, "complete_prediction_fields": 1,
            "paired_champion_core004": 1, "triple_evaluable": 1,
            "current_source_fixed_cohort": 1, "current_source_model_processed": 0,
        },
        "per_physical_race": [
            {
                "race_id": "RIKSTOTO:S1_NR_2026-11-03:1", "track": "S1",
                "date": "2026-11-03", "race_no": 1, "model_full_field": True,
                "model_frozen_sha256": "1" * 64,
                "alternative_original_freezes": [{
                    "selected_benchmark_reference": True, "eligible_pre_t4": True,
                    "model_sha256": "1" * 64,
                }],
                "official_result_verified": True,
                "research_status": "EVALUABLE_RESEARCH_ONLY",
                "benchmark_status": "TRIPLE_EVALUABLE",
                "win_market_on_reference_freeze": True,
            },
            {
                "race_id": "RIKSTOTO:F1_NR_2026-11-04:2", "track": "F1",
                "date": "2026-11-04", "race_no": 2, "model_full_field": False,
                "alternative_original_freezes": [], "official_result_verified": False,
                "benchmark_status": "NOT_EVALUABLE",
                "current_source_readiness": {
                    "start_utc": "2026-11-04T18:00:00+00:00",
                    "t4_cutoff_utc": "2026-11-04T17:56:00+00:00",
                    "source_as_of_utc": "2026-11-04T15:59:00+00:00",
                    "collector_source_sha256": "e" * 64,
                    "collector_model_input_approved": False,
                    "all_fundamentals_complete": False,
                    "admission_status": "COLLECTOR_RESEARCH_MODEL_GATE_NOT_VERIFIED",
                    "admission_blockers": ["IDENTITY_CROSS_PROVIDER_NOT_ATTESTED"],
                },
            },
        ],
    }


def test_identity_and_historical_receipts_not_promoted():
    report = build_readiness(_fixture(), github_run_id=41832416078)
    assert report["current_status_counts"] == {"BLOCKED_IDENTITY": 1}
    assert report["historical_without_current_source"] == 1
    assert report["new_model_freezes_created"] == 0
    assert report["prospective_pit_certified"] == 0
    assert report["bet_authority"] is False
    active = next(r for r in report["races"] if r["current_source_cohort"])
    assert active["t4_still_possible"] is True
    assert active["stable_runner_identities"] is None
    assert active["collector_startlist_sha256"] == "e" * 64
    assert "independent_per_runner_registered_identity_original" in active["missing_original_evidence"]
    historic = next(r for r in report["races"] if not r["current_source_cohort"])
    assert historic["status"] == "HISTORICAL_ONLY_NO_CURRENT_SOURCE_RECEIPT"
    assert historic["source_observed_at_utc"] is None


def test_cutoff_expires_without_overwriting_source_blocker():
    doc = _fixture()
    a = build_readiness(doc, evaluation_at_utc="2026-11-04T18:05:00+00:00")
    assert a["current_status_counts"] == {"BLOCKED_IDENTITY": 1}
    assert next(r for r in a["races"] if r["current_source_cohort"])["t4_still_possible"] is False
    doc["per_physical_race"][1]["current_source_readiness"]["admission_blockers"] = []
    b = build_readiness(doc, evaluation_at_utc="2026-11-04T18:05:00+00:00")
    assert b["current_status_counts"] == {"PAST_CUTOFF": 1}


@pytest.mark.parametrize("mutation", ["bad_sha", "duplicate", "fake_pit", "bad_clock", "run"])
def test_invalid_originals_fail_closed(mutation):
    doc = copy.deepcopy(_fixture())
    kwargs = {}
    if mutation == "bad_sha":
        doc["source_sha256"]["current_core003_source_report"] = "BAD"
    elif mutation == "duplicate":
        doc["per_physical_race"][1]["race_id"] = doc["per_physical_race"][0]["race_id"]
    elif mutation == "fake_pit":
        doc["pit_certification_performed"] = True
    elif mutation == "bad_clock":
        doc["per_physical_race"][1]["current_source_readiness"]["t4_cutoff_utc"] = "BAD"
    else:
        kwargs["github_run_id"] = -1
    with pytest.raises(ValueError):
        build_readiness(doc, **kwargs)


def test_authentic_four_original_67_race_replay(tmp_path):
    root = os.getenv("MVP018_FUNNEL_ORIGINAL_ROOT")
    if not root:
        pytest.skip("Original bytes available only in PR GitHub CI")
    d = Path(root)
    paths = {
        "scorecard": d / "scorecard/index.json",
        "source": d / "source/core003-pilot-report.json",
        "cohort": d / "cohort/cohort-index.json",
        "manifest": d / "manifest/manifest.json",
    }
    expected = {
        "scorecard": "a4a667bd596bde42b9e3dbed6d96247731067fe76f82b33ea816194fa68b5ff7",
        "source": "b75eb90a215ef1fe251da9d0d8df630cece2c7c003e2659a69a259390e67cb58",
        "cohort": "5a39954a79ca2e4d765092bfef64386eb8d77d5c9fb6685645306911c008de04",
        "manifest": "67a2ca0296c5fd571fa58c4b3a90f13d5155cb03228866bd8e0062a737951f33",
    }
    for key, path in paths.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected[key]
    joined = summarize(
        scorecard_index=paths["scorecard"], source_report=paths["source"],
        model_cohort_index=paths["cohort"], coverage_manifest=paths["manifest"],
    )
    report = build_readiness(joined, github_run_id=41832416078)
    assert report["physical_races"] == 67
    assert report["current_source_races"] == 3
    assert report["historical_without_current_source"] == 64
    assert report["cumulative_benchmark_stages"]["SAME_FREEZE_WIN_TRIPLE"] == 14
    assert sum(report["current_status_counts"].values()) == 3
    assert all(not row["pit_certified"] and not row["bet_authority"] for row in report["races"])
    assert main([
        "--scorecard-index", str(paths["scorecard"]),
        "--source-report", str(paths["source"]),
        "--model-cohort-index", str(paths["cohort"]),
        "--coverage-manifest", str(paths["manifest"]),
        "--output-dir", str(tmp_path / "matrix"),
    ]) == 0
    assert json.loads((tmp_path / "matrix/index.json").read_text())["bet_authority"] is False
