"""Authentic, read-only M5 source acceptance for MVP-023A integration (NO BET).

This is NOT the 2015-2024 historical native archive, and it does not synthesize
coverage or a Benter fitted model. It uses ONLY the verified M4 truth regression
archive from 2026, runs M5 importer -> P1-B -> P1-C and reports missing gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hbi.backfill import run_batch
from hbi.mvp023a_dataset_partitions import build_partitioned_dataset
from hbi.mvp023a_feature_audit import audit_feature_dataset

REPO = Path(__file__).resolve().parents[1]
ORIGINAL = REPO / "tests/fixtures/rikstoto-historical-truth.json"
MANIFEST = REPO / "examples/backfill/m4-regression.json"
EXPECTED_SHA = "8086ec016e8e4f9cda7d9ad36abe44df1e09e3c2e387a9ed6c612fa61a0f8953"


def execute(output: Path) -> dict:
    observed_sha = hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    if observed_sha != EXPECTED_SHA:
        raise ValueError("AUTHENTIC_M4_ORIGINAL_SHA_MISMATCH")
    output.mkdir(parents=True, exist_ok=False)
    imported = run_batch(MANIFEST, output / "m5")
    features = audit_feature_dataset(output / "m5")
    dataset, inputs, labels = build_partitioned_dataset(output / "m5")
    if (
        imported["races"] != len(inputs) or len(inputs) != len(labels)
        or features["physical_races"] != len(inputs)
        or features["source_dataset_sha256"] != dataset["source_m5_dataset_sha256"]
        or features["source_manifest_sha256"] != dataset["source_m5_manifest_sha256"]
        or {row["race_id"] for row in inputs} != {row["race_id"] for row in features["by_race"]}
    ):
        raise ValueError("AUTHENTIC_M5_CROSS_MODULE_SOURCE_OR_COHORT_CONFLICT")
    months = imported["per_month"]
    if not months or {month[:4] for month in months} != {"2026"}:
        raise ValueError("UNEXPECTED_DATA_ROLE_OR_LOCKBOX_EXPOSURE")
    if imported["races"] != 39:
        raise ValueError("M4_REGRESSION_RACE_BASELINE_CHANGED")
    if features["training_ready_races"] or dataset["model_training_eligible"]:
        raise ValueError("UNAUTHORISED_PIT_OR_TRAINING_PROMOTION")
    feature_details = {}
    for name, info in sorted(features["features"].items()):
        feature_details[name] = {
            "m5_active_runner_denominator": info["denominator_active_runners"],
            "status_counts": info["status_counts"],
            "observed_value_types": info["observed_value_types"],
            "qualified_runner_count": info["eligible_runners"],
            "main_blocker": info["main_blocker"],
        }
    observed_result_races = sum(m["result_verified_races"] for m in months.values())
    counters = {
        "original_race_records_m5": imported["races"],
        "unique_physical_races_m5": len(inputs),
        "imported_runners_m5": imported["imported_runners"],
        "full_field_identity_verification_m5": sum(
            m["full_field_identity_verified_races"] for m in months.values()
        ),
        "provider_identity_verified_runners_m5": sum(
            m["identity_verified_runners"] for m in months.values()
        ),
        "result_verified_races_m5": observed_result_races,
        "raw_retrospective_label_rows_m5": sum(
            m["result_label_rows"] for m in months.values()
        ),
        "history_performance_features_pit_verified": 0,
        "fundamental_training_eligible": 0,
        "benter_combination_eligible": 0,
        "complete_pre_t4_win_market": None,
    }
    report = {
        "schema": "MVP023A_REAL_SOURCE_PARTIAL_ACCEPTANCE_V1",
        "research_only": True, "bet_authority": False,
        "authentic_source_scope": "M4_TRUTH_REGRESSION_ONLY_EXPOSED_2026",
        "source_original_path": ORIGINAL.relative_to(REPO).as_posix(),
        "source_original_sha256": observed_sha,
        "source_input_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "m5_import_report_sha256": hashlib.sha256(
            (output / "m5/model-readiness.json").read_bytes()
        ).hexdigest(),
        "m5_dataset_sha256": features["source_dataset_sha256"],
        "m5_feature_report_sha256": hashlib.sha256(
            json.dumps(features, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "m5_partition_manifest_sha256": hashlib.sha256(
            json.dumps(dataset, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "data_role": "2026_PREVIOUSLY_EXPOSED_NOT_BLIND_OOS",
        "source_years": sorted({month[:4] for month in months}),
        "source_months": sorted(months),
        "counters": counters,
        "features": feature_details,
        "module_execution": {
            "historical_coverage": "BLOCKED_NO_NATIVE_2015_2024_ORIGINAL_ARCHIVE",
            "m5_source_import": "PASS_AUTHENTIC_SHA_REPLAYED",
            "feature_audit": "PASS_RESEARCH_ONLY",
            "dataset_partitions": "PASS_RESEARCH_ONLY",
            "benter_readiness": "BLOCKED_NO_AUTHENTIC_FITTED_FUNDAMENTAL_MODEL",
            "consolidated_real_five_stage": "BLOCKED_NO_ALL_FOUR_SAME_SCOPE_ORIGINAL_REPORTS",
            "five_module_schema_test": "SEPARATE_TEST_ONLY_CI",
        },
        "2025_lockbox_accessed": False,
        "fundamental_model_training_performed": False,
        "benter_weight_fitting_performed": False,
        "economic_ev_ready": False,
        "production_betting_ready": False,
        "limitations": [
            "This is authentic exposed 2026 M4/M5 regression source, NOT the complete 2015-24 archive.",
            "Native Historical Coverage cannot be run on M4 truth JSON as if it were archival envelopes.",
            "No actual historical pre-T4 WIN data or trained model artifact in this cohort.",
            "Retrospective historical labels are held separate from fundamental input.",
            "Unknown native coverage or executable market counts are NULL, not invented zero.",
        ],
    }
    target = output / "real-source-acceptance.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = execute(args.output)
    print(json.dumps({
        "schema": report["schema"], "source_sha256": report["source_original_sha256"],
        "counters": report["counters"], "module_execution": report["module_execution"],
    }, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
