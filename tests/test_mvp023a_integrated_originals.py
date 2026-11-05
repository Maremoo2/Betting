"""MVP-023A FINAL INTEGRATION: real M4/M5 2026 original versus synthetic adapters.

AUTHENTIC_SCOPE: SHA-pinned tests/fixtures/rikstoto-historical-truth.json
(2026, 39 physical races; M4 verified regression originals, NOT 2015-2024).
TEST_ONLY_SCOPE: coverage fixture and Benter readiness fixture used solely to
prove all five wire-format interfaces. NEVER report the hybrid as real full E2E.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hbi.backfill import run_batch
from hbi.mvp023a_benter_readiness import inspect_benter_readiness
from hbi.mvp023a_dataset_partitions import build_partitioned_dataset
from hbi.mvp023a_feature_audit import audit_feature_dataset
from hbi.mvp023a_historical_coverage import build_coverage
from hbi.mvp023a_research_report import build_consolidated_report, main as report_cli
from hbi.research_lab import digest
from test_mvp023a_benter_readiness import _bundle
from test_mvp023a_historical_coverage import fixture as synthetic_coverage_fixture

ROOT = Path(__file__).resolve().parents[1]
M4_MANIFEST = ROOT / "examples" / "backfill" / "m4-regression.json"
M4_RAW_SOURCE = ROOT / "tests" / "fixtures" / "rikstoto-historical-truth.json"
M4_ORIGINAL_SHA = "8086ec016e8e4f9cda7d9ad36abe44df1e09e3c2e387a9ed6c612fa61a0f8953"


def _real_m5(tmp_path):
    # This importer rejects source SHA mismatch; source was previously audited
    # as M4 historical truth. It is not a complete provider monthly archive.
    assert hashlib.sha256(M4_RAW_SOURCE.read_bytes()).hexdigest() == M4_ORIGINAL_SHA
    output = tmp_path / "m5-2026-regression"
    original = run_batch(M4_MANIFEST, output)
    assert original["schema"] == "HBI_RESEARCH_DATASET_V1"
    assert original["cohort"] == "M4_REGRESSION_ONLY"
    assert original["races"] == 39
    assert original["imported_runners"] == 393
    assert sum(s["result_verified_races"] for s in original["per_month"].values()) == 4
    assert set(month[:4] for month in original["per_month"]) == {"2026"}
    return output, original


def test_real_2026_m4_source_runs_m5_feature_audit_and_dataset_builder(tmp_path):
    root, original = _real_m5(tmp_path)
    features = audit_feature_dataset(root)
    partitions, inputs, labels = build_partitioned_dataset(root)
    assert features["schema"] == "MVP023A_HISTORICAL_FEATURE_AUDIT_V1"
    assert partitions["schema"] == "MVP023A_RESEARCH_DATASET_PARTITION_V1"
    assert features["physical_races"] == partitions["races"] == original["races"] == 39
    assert features["source_dataset_sha256"] == partitions["source_m5_dataset_sha256"]
    assert features["source_manifest_sha256"] == partitions["source_m5_manifest_sha256"]
    assert {r["race_id"] for r in features["by_race"]} == {
        r["race_id"] for r in inputs
    } == {r["race_id"] for r in labels}
    assert sum(p["count"] for p in partitions["partitions"].values()) == 39
    assert set(partitions["partitions"]) == {"EXPOSED_RESEARCH_2026_NOT_BLIND_OOS"}
    assert partitions["model_training_eligible"] == 0
    assert partitions["benter_fit_eligible"] == 0
    assert features["training_ready_races"] == 0
    assert all(r["market_input"] is None for r in inputs)
    assert all(r["model_eligible"] is False for r in inputs)
    assert all("labels" not in r and "results" not in r for r in inputs)
    assert all(r["training_feature_input"] is False for r in labels)
    assert original["dataset_sha256"] == partitions["source_m5_dataset_sha256"]


def test_hybrid_five_module_json_schema_only_does_not_falsely_merge_cohorts(tmp_path):
    # Historical coverage and Benter inputs here are TEST_ONLY fixtures.
    # Real raw monthly 2015-24 archive and empirically fitted model unavailable.
    native = tmp_path / "synthetic-historic-coverage"
    synthetic_coverage_fixture(native)
    coverage = build_coverage(native)
    m5_dir, original = _real_m5(tmp_path)
    features = audit_feature_dataset(m5_dir)
    dataset, inputs, labels = build_partitioned_dataset(m5_dir)
    benter = inspect_benter_readiness(_bundle())
    assert coverage["counts"]["physical_races"] == 1  # TEST_ONLY, not real!
    assert original["races"] == features["physical_races"] == dataset["races"] == 39
    assert benter["fit_readiness"] == "NOT_READY"
    references = {
        "coverage": coverage, "features": features,
        "dataset": dataset, "benter": benter,
    }
    paths = {}
    hashes = {}
    for name, report in references.items():
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        paths[name] = path
    combined = build_consolidated_report(**references, input_sha256=hashes)
    assert combined["coverage_original_physical_races"] == 1
    assert combined["m5_feature_audit_races_separate_cohort"] == 39
    assert combined["m5_dataset_races_separate_cohort"] == 39
    assert next(y for y in combined["years"] if y["year"] == 2026)[
        "m5_feature_audit_races_separate_cohort"
    ] == 39
    assert next(y for y in combined["years"] if y["year"] == 2026)[
        "discovered_physical"
    ] is None  # No native 2026 census supplied.
    assert next(y for y in combined["years"] if y["year"] == 2025)[
        "official_result_verified"
    ] is None
    assert combined["readiness"]["economic_ev"] == "BLOCKED_TIME"
    assert combined["bet_authority"] is False
    assert combined["2025_lockbox_opened"] is False
    assert all("results" not in r for r in inputs)
    report_path = tmp_path / "report-out.json"
    args = [item for name in ("coverage", "features", "dataset", "benter")
            for item in ("--" + name, str(paths[name]))]
    args += ["--output", str(report_path)]
    assert report_cli(args) == 0
    assert json.loads(report_path.read_text()) == combined


def test_cross_original_m5_mismatch_is_rejected_even_if_each_report_is_valid(tmp_path):
    root, _ = _real_m5(tmp_path)
    features = audit_feature_dataset(root)
    dataset, _, _ = build_partitioned_dataset(root)
    coverage_root = tmp_path / "synthetic-root"
    synthetic_coverage_fixture(coverage_root, market=False)
    coverage = build_coverage(coverage_root)
    benter = inspect_benter_readiness(_bundle())
    references = {key: "b" * 64 for key in ("coverage", "features", "dataset", "benter")}
    dataset["source_m5_manifest_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="M5_FEATURE_PARTITION_ORIGINAL_PROVENANCE_CONFLICT"):
        build_consolidated_report(
            coverage=coverage, features=features, dataset=dataset,
            benter=benter, input_sha256=references,
        )
