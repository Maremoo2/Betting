"""MVP-019B authenticated disjoint-source reconciliation, no PIT or BET."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp019_source_readiness import (
    build_operational_readiness,
    operational_from_originals,
)

PIN = {
    "scorecard": "6ec0392fd9620b41be90610b5348a019e0a9e43a975562960f8f04d2cbd61a9a",
    "source": "ab5a773ef530b061659d2ff2ee78f16806fd97637be6c57f29768d9c51cad560",
    "cohort": "f3af0f08f203044b0cede78ca41b395828144aad794ec21ace3ef4520541dec7",
    "manifest": "a9b5c7efa0a35191f4693658df58161d553556f3dcc4e1ecc638a2c8b0c4a01e",
}


def _original():
    root = os.getenv("MVP019_OPERATIONAL_ORIGINAL_ROOT")
    if not root:
        pytest.skip("41879063497 authentic four originals only in PR CI")
    base = Path(root)
    paths = {
        "scorecard": base / "scorecard/index.json",
        "source": base / "source/core003-pilot-report.json",
        "cohort": base / "cohort/cohort-index.json",
        "manifest": base / "manifest/manifest.json",
    }
    docs = {}
    for name, path in paths.items():
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == PIN[name]
        docs[name] = json.loads(raw)
    return paths, docs


def _evaluate(docs):
    return build_operational_readiness(
        scorecard=docs["scorecard"], source=docs["source"],
        cohort=docs["cohort"], coverage=docs["manifest"],
        original_sha256={
            "cumulative_scorecard_index": PIN["scorecard"],
            "current_core003_source_report": PIN["source"],
            "current_model_cohort_index": PIN["cohort"],
            "cumulative_dev011_manifest": PIN["manifest"],
        },
        github_run_id=41879063497,
    )


def test_true_original_cohort_not_indexed_yet_is_kept_outside_benchmark():
    paths, docs = _original()
    report = _evaluate(docs)
    assert report["cumulative_benchmark_physical_races"] == 79
    assert report["current_source_physical_races"] == 7
    assert report["source_only_not_yet_cumulative"] == [
        "RIKSTOTO:S3_NR_2026-11-04:4"
    ]
    assert report["union_unique_physical_races_not_benchmark_denominator"] == 80
    assert report["current_model_processed_research_only"] == 6
    assert report["current_collector_model_input_approved"] == 0
    assert report["cumulative_benchmark_stages"] == {
        "ORIGINAL_PHYSICAL_COHORT": 79,
        "FROZEN_COMPLETE_FULL_FIELD": 31,
        "OFFICIAL_RESULT_SCORED": 20,
        "SAME_FREEZE_WIN_TRIPLE": 19,
    }
    assert report["bet_authority"] is False
    assert report["prospective_pit_certified"] == 0
    assert report["new_model_freezes_created"] == 0
    assert sum(report["current_status_counts"].values()) == 7
    source_only = next(
        r for r in report["races"]
        if r["race_id"] == "RIKSTOTO:S3_NR_2026-11-04:4"
    )
    assert source_only["current_source_cohort"] is True
    assert source_only["cumulative_scorecard_member"] is False
    assert source_only["cumulative_win_triple"] is None
    assert source_only["current_research_model_processed"] is True
    assert source_only["registered_runner_ids_independently_attested"] is False
    assert source_only["collector_model_input_approved"] is False
    assert all(r["bet_authority"] is False and r["pit_certified"] is False
               for r in report["races"])
    direct = operational_from_originals(
        scorecard_index=paths["scorecard"], source_report=paths["source"],
        model_cohort_index=paths["cohort"],
        coverage_manifest=paths["manifest"], github_run_id=41879063497,
    )
    assert direct["source_join_sha256"]["cumulative_scorecard_index"] == PIN["scorecard"]
    assert direct["source_only_not_yet_cumulative"] == report["source_only_not_yet_cumulative"]


@pytest.mark.parametrize("mutation", [
    "bad_model_cohort_source_sha", "duplicate_current",
    "missing_current_readiness", "invent_pit", "bad_inventory",
    "invent_pair_count", "duplicate_scorecard_race",
    "invalid_run_id", "fail_open_original_inventory",
])
def test_original_contract_tampering_must_block(mutation):
    _, original_docs = _original()
    docs = copy.deepcopy(original_docs)
    kwargs = {}
    if mutation == "bad_model_cohort_source_sha":
        docs["cohort"]["source_report_sha256"] = "0" * 64
    elif mutation == "duplicate_current":
        docs["cohort"]["original_cohort"][0] = docs["cohort"]["original_cohort"][1]
    elif mutation == "missing_current_readiness":
        docs["source"]["race_readiness_after"].pop()
    elif mutation == "invent_pit":
        docs["cohort"]["pit_certified"] = True
    elif mutation == "bad_inventory":
        docs["manifest"]["github_artifact_inventory_sha256"] = "0" * 64
    elif mutation == "invent_pair_count":
        docs["scorecard"]["counts"]["paired_champion_core004"] += 1
    elif mutation == "duplicate_scorecard_race":
        docs["scorecard"]["records"][0]["race_id"] = (
            docs["scorecard"]["records"][1]["race_id"]
        )
    elif mutation == "invalid_run_id":
        kwargs["github_run_id"] = -1
    else:
        docs["manifest"]["missing_originals"].append({
            "reason": "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"
        })
    with pytest.raises(ValueError):
        build_operational_readiness(
            scorecard=docs["scorecard"], source=docs["source"],
            cohort=docs["cohort"], coverage=docs["manifest"],
            original_sha256={
                "cumulative_scorecard_index": PIN["scorecard"],
                "current_core003_source_report": PIN["source"],
                "current_model_cohort_index": PIN["cohort"],
                "cumulative_dev011_manifest": PIN["manifest"],
            },
            **kwargs,
        )
