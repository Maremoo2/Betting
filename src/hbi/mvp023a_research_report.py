"""MVP-023A: combined read-only historical research audit report (NO BET).

Consumes four separately produced, source-bounded reports. Never fetches,
trains, opens 2025 labels, invents missing years, or merges incompatible
research denominators.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .research_lab import digest

SCHEMA = "MVP023A_CONSOLIDATED_RESEARCH_REPORT_V1"
COMPONENTS = {
    "coverage": "MVP023A_HISTORICAL_COVERAGE_V1",
    "features": "MVP023A_HISTORICAL_FEATURE_AUDIT_V1",
    "dataset": "MVP023A_RESEARCH_DATASET_PARTITION_V1",
    "benter": "MVP023A_BENTER_READINESS_V1",
}


def _read(path: Path, kind: str) -> tuple[dict, str]:
    if path.is_symlink():
        raise ValueError("SYMLINKED_RESEARCH_REPORT_REFUSED")
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise TypeError("RESEARCH_REPORT_OBJECT_REQUIRED")
    if doc.get("schema") != COMPONENTS[kind] or doc.get("bet_authority") is not False:
        raise ValueError("RESEARCH_REPORT_SCHEMA_OR_BET_AUTHORITY_INVALID:" + kind)
    if doc.get("training_performed") is not False:
        raise ValueError("RESEARCH_TRAINING_UNEXPECTED:" + kind)
    return doc, hashlib.sha256(raw).hexdigest()


def _quality(coverage: dict, features: dict, dataset: dict, benter: dict) -> None:
    rows = coverage.get("by_race")
    if (
        coverage.get("historical_not_prospective") is not True
        or not isinstance(rows, list)
        or coverage.get("data_sha256") != digest(rows)
        or coverage.get("readiness", {}).get("pit_model_eligible") != 0
        or coverage.get("readiness", {}).get("lockbox_2025_accessed_for_tuning") is not False
        or len({r.get("race_id") for r in rows}) != len(rows)
    ):
        raise ValueError("COVERAGE_ORIGINAL_BASIS_OR_PIT_CLAIM_INVALID")
    feature_rows = features.get("by_race")
    if (
        not isinstance(feature_rows, list)
        or features.get("feature_audit_sha256") != digest(feature_rows)
        or features.get("physical_races") != len(feature_rows)
        or features.get("training_ready_races") != 0
        or features.get("lockbox_2025_opened") is not False
    ):
        raise ValueError("HISTORICAL_FEATURE_ORIGINAL_BASIS_INVALID")
    for group, key in (("by_year", "date"), ("by_country", "country")):
        expected = {}
        for row in feature_rows:
            if not isinstance(row, dict) or not isinstance(row.get(key), str):
                raise TypeError("FEATURE_RACE_DIMENSION_INVALID")
            name = row[key][:4] if key == "date" else row[key]
            if name not in expected:
                expected[name] = Counter()
            expected[name]["races"] += 1
            expected[name]["active_runners"] += row.get("active_runners", 0)
        actual = features.get(group)
        if (
            not isinstance(actual, dict) or set(actual) != set(expected)
            or any(
                actual[name].get("races") != count["races"]
                or actual[name].get("active_runners") != count["active_runners"]
                for name, count in expected.items()
            )
        ):
            raise ValueError("FEATURE_" + group.upper() + "_DENOMINATOR_CONFLICT")
    if (
        dataset.get("model_training_eligible") != 0
        or dataset.get("benter_fit_eligible") != 0
        or dataset.get("2025_candidate_lockbox_opened") is not False
        or dataset.get("label_separated_from_fundamentals") is not True
        or dataset.get("readiness") != "BLOCKED_SOURCE"
        or not isinstance(dataset.get("partitions"), dict)
        or any(
            not isinstance(part, dict)
            or not isinstance(part.get("race_ids"), list)
            or part.get("count") != len(part["race_ids"])
            or part.get("sha256") != digest(part["race_ids"])
            for part in dataset["partitions"].values()
        )
    ):
        raise ValueError("DATASET_PARTITION_OR_LOCKBOX_CONTRACT_INVALID")
    if (
        benter.get("fit_readiness") != "NOT_READY"
        or benter.get("training_performed") is not False
        or benter.get("weight_estimation_performed") is not False
        or benter.get("2025_lockbox_used_for_tuning") is not False
        or benter.get("combination_fit_ready") is not False
        or benter.get("economic_ev_ready") is not False
    ):
        raise ValueError("BENTER_PREMATURE_FIT_OR_EV_CLAIM")
    totals = coverage.get("counts") or {}
    if totals.get("physical_races", 0) != len(rows):
        raise ValueError("COVERAGE_RACE_DENOMINATOR_CONFLICT")
    if any(int(year) not in range(2015, 2027) for year in coverage.get("by_year", {})):
        raise ValueError("COVERAGE_YEAR_OUTSIDE_REGISTERED_RANGE")
    physical_by_year = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("INVALID_PHYSICAL_RACE_ROW")
        rid = row.get("race_id")
        if not isinstance(rid, str):
            raise TypeError("INVALID_PHYSICAL_RACE_ID")
        match = re.fullmatch(
            r"RIKSTOTO:[A-Z0-9]+_NR_(20\d{2})-\d{2}-\d{2}:[1-9]\d*", rid
        )
        if match is None or row.get("year") != int(match.group(1)):
            raise ValueError("COVERAGE_RACE_ID_YEAR_CONFLICT")
        physical_by_year[match.group(1)] += 1
    declared_years = coverage.get("by_year", {})
    if set(declared_years) != set(physical_by_year):
        raise ValueError("COVERAGE_YEAR_DENOMINATOR_MISSING_OR_INVENTED")
    if any(
        values.get("physical_races") != physical_by_year[year]
        or values.get("coverage_denominator") != physical_by_year[year]
        for year, values in declared_years.items()
    ):
        raise ValueError("COVERAGE_YEAR_DENOMINATOR_MISMATCH")
    if any(int(year) not in range(2015, 2027) for year in features.get("by_year", {})):
        raise ValueError("FEATURE_YEAR_OUTSIDE_REGISTERED_RANGE")


def build_consolidated_report(
    *, coverage: dict, features: dict, dataset: dict, benter: dict,
    input_sha256: dict[str, str],
) -> dict:
    _quality(coverage, features, dataset, benter)
    if (set(input_sha256) != set(COMPONENTS)
            or any(not isinstance(value, str)
                   or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in input_sha256.values())):
        raise ValueError("RESEARCH_REPORT_INPUT_HASH_SET_INCOMPLETE")
    years = []
    for year in range(2015, 2027):
        key = str(year)
        observed = coverage.get("by_year", {}).get(key)
        feature = features.get("by_year", {}).get(key)
        withheld = year == 2025
        years.append({
            "year": year,
            "data_scope": (
                "CANDIDATE_2025_LOCKBOX_RESULTS_WITHHELD" if withheld
                else "OBSERVED_ARCHIVE_SUBSET" if observed is not None
                else "NOT_MEASURED_NO_ORIGINAL_ARCHIVE"
            ),
            "discovered_physical": observed.get("physical_races") if observed else None,
            "source_archived": observed.get("SOURCE_ARCHIVED", 0) if observed else None,
            "full_field_verified": observed.get("FULL_FIELD_VERIFIED", 0) if observed else None,
            "independent_identity_verified": observed.get("IDENTITY_VERIFIED", 0) if observed else None,
            "official_result_verified": (
                None if withheld else observed.get("RESULT_VERIFIED", 0) if observed else None
            ),
            "win_market_complete": observed.get("MARKET_COMPLETE", 0) if observed else None,
            "market_pre_t4_verified": observed.get("MARKET_PRE_RACE_VERIFIED", 0) if observed else None,
            "pit_model_eligible": observed.get("PIT_MODEL_ELIGIBLE", 0) if observed else None,
            "coverage_denominator": observed.get("coverage_denominator") if observed else None,
            "m5_feature_audit_races_separate_cohort": feature.get("races") if feature else None,
            "m5_active_runners_separate_cohort": feature.get("active_runners") if feature else None,
            "historical_training_admitted": False,
        })
    feature_rows = {
        name: {
            "status_counts": data.get("status_counts", {}),
            "qualified_races": data.get("eligible_races"),
            "qualified_runners": data.get("eligible_runners"),
            "m5_active_runner_denominator": data.get("denominator_active_runners"),
            "qualified_runner_coverage_rate": data.get("qualified_runner_coverage_rate"),
            "by_year": data.get("by_year", {}),
            "by_country": data.get("by_country", {}),
            "main_blocker": data.get("main_blocker"),
            "observed_value_types": data.get("observed_value_types", {}),
            "source_time_field": data.get("source_time_field"),
            "historical_event_time_field": data.get("historical_event_time_field"),
            "availability_time_field": data.get("availability_time_field"),
            "identity_integrity_requirement": data.get("identity_requirement"),
            "time_integrity": "NOT_PIT_CERTIFIED",
            "leakage_risk": data.get("leakage_risk", "NOT_REVIEWED"),
            "scope": "M5_DIAGNOSTIC_COHORT_NOT_JOINED_TO_COVERAGE",
        }
        for name, data in sorted(features.get("features", {}).items())
    }
    return {
        "schema": SCHEMA, "research_only": True, "bet_authority": False,
        "training_performed": False, "model_promotion": False,
        "raw_source_scope": "SELECTED_LOCAL_ARCHIVES_ONLY",
        "input_report_sha256": dict(sorted(input_sha256.items())),
        "years": years,
        "coverage_original_physical_races": coverage.get("counts", {}).get("physical_races", 0),
        "m5_feature_audit_races_separate_cohort": features.get("physical_races"),
        "m5_dataset_races_separate_cohort": dataset.get("races"),
        "countries_coverage_scope": coverage.get("by_country", {}),
        "countries_m5_feature_scope": features.get("by_country", {}),
        "features": feature_rows,
        "registered_chronological_partitions": dataset.get("partitions"),
        "benter": {
            "fit_readiness": "NOT_READY",
            "blocker_counts": benter.get("blocker_counts", {}),
            "fundamental_dataset_ready": False,
            "oos_fundamental_predictions_ready": False,
            "pre_race_market_ready": False,
            "same_race_alignment_structure_only": benter.get(
                "same_race_alignment_structure_ready", False
            ),
            "combination_fit_ready": False,
            "independent_validation_ready": False,
            "economic_ev_ready": False,
        },
        "readiness": {
            "fundamental_training": "BLOCKED_SOURCE",
            "benter_weight_fit": "BLOCKED_SOURCE",
            "economic_ev": "BLOCKED_TIME",
            "production_betting_ready": False,
        },
        "2025_lockbox_opened": False,
        "report_sha256": digest({
            "years": years, "features": feature_rows, "input_report_sha256": input_sha256,
        }),
        "limitations": [
            "Empty years mean NOT_MEASURED, never no races.",
            "M5, cumulative historical and current source cohorts have separate denominators.",
            "A later archive capture does not prove historical pre-race publication.",
            "Provider temporary IDs do not attest independent horse identity.",
            "No historical Benter weights, predictive superiority or economic edge established.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in COMPONENTS:
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    inputs = {
        key: _read(getattr(args, key), key)
        for key in COMPONENTS
    }
    result = build_consolidated_report(
        **{key: item[0] for key, item in inputs.items()},
        input_sha256={key: item[1] for key, item in inputs.items()},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
