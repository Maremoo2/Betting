"""MVP-016 read-only operational research status from four EXISTING originals.

The scorecard is already the immutable prediction/outcome judge. This consumer
only cross-checks source joins and reports coverage; it never reruns models,
fetches providers, repairs history, performs settlement or awards BET/PIT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

SCHEMA = "MVP016_CUMULATIVE_RESEARCH_STATUS_V1"
RACE_ID = re.compile(r"RIKSTOTO:([^:]+)_NR_(\d{4}-\d{2}-\d{2}):(\d+)\Z")


def _load(path: Path) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("RESEARCH_INPUT_MISSING_OR_UNSAFE")
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("RESEARCH_INPUT_NOT_JSON") from exc
    if not isinstance(parsed, dict):
        raise TypeError("RESEARCH_INPUT_NOT_OBJECT")
    return parsed, hashlib.sha256(raw).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _uncertainty(rows: list[dict], a: str, b: str, measure: str, min_n: int) -> dict:
    diffs = [float(r["score"][f"{a}_{measure}"]) -
             float(r["score"][f"{b}_{measure}"]) for r in rows]
    _require(all(math.isfinite(x) for x in diffs), "NONFINITE_SCORE_DIFFERENCE")
    n = len(diffs)
    mean = statistics.fmean(diffs) if diffs else None
    sd = statistics.stdev(diffs) if n >= 2 else None
    se = sd / math.sqrt(n) if sd is not None else None
    return {
        "n_distinct_physical_races": n,
        "mean_first_minus_second": mean,
        "sample_standard_deviation": sd,
        "standard_error_descriptive": se,
        "approximate_95_percent_interval": (
            [mean - 1.96 * se, mean + 1.96 * se]
            if n >= min_n and se is not None else None
        ),
        "interpretation": (
            "EXPLORATORY_INSUFFICIENT_DISTINCT_RACES"
            if n < min_n else "APPROXIMATE_IID_RACE_ASSUMPTION_UNVALIDATED"
        ),
        "first": a, "second": b, "metric": measure,
    }


def summarize(
    *,
    scorecard_index: Path, source_report: Path, model_cohort_index: Path,
    coverage_manifest: Path,
) -> dict:
    """Fail closed on inconsistent original joins; preserve physical denominator."""
    scorecard, score_sha = _load(scorecard_index)
    source, source_sha = _load(source_report)
    cohort, cohort_sha = _load(model_cohort_index)
    coverage, coverage_sha = _load(coverage_manifest)
    _require(
        scorecard.get("schema") == "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
        and scorecard.get("authority") == "READ_ONLY_RESEARCH_SCORECARD"
        and scorecard.get("model_originals_verified_by_sha") is True
        and scorecard.get("bet_authority") is False
        and scorecard.get("v33_evaluator_called") is False,
        "SCORECARD_SOURCE_CONTRACT_INVALID",
    )
    _require(
        source.get("schema_version") == "CORE_003_SHADOW_PILOT_V1"
        and source.get("bet_count") == 0
        and source.get("prospective_t4_success_proven") is False,
        "CORE003_NOT_SOURCE_ONLY",
    )
    _require(
        cohort.get("schema") == "BET_MVP_002_FIXED_COHORT_INDEX_V1"
        and cohort.get("bet_authority") is False
        and cohort.get("pit_certified") is False
        and cohort.get("source_report_sha256") == source_sha,
        "CURRENT_ORIGINAL_COHORT_SOURCE_SHA_MISMATCH",
    )
    _require(
        coverage.get("schema") == "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1"
        and coverage.get("bet_authority") is False
        and coverage.get("pit_certification_performed") is False
        and coverage.get("github_artifact_inventory_sha256")
        == (scorecard.get("cumulative_original_inventory") or {}).get(
            "github_artifact_inventory_sha256"
        ),
        "CUMULATIVE_COVERAGE_ORIGINAL_MISMATCH",
    )
    current = cohort.get("original_cohort")
    _require(
        isinstance(current, list)
        and len(current) == len(set(current))
        and current == source.get("races_in_fixed_cohort"),
        "CURRENT_SOURCE_COHORT_IDENTITY_MISMATCH",
    )
    _require(isinstance(cohort.get("not_processed"), list)
             and isinstance(cohort.get("processed"), list), "COHORT_MEMBERS_INVALID")
    processed = {r.get("race_id"): r for r in cohort["processed"]}
    blocked = {r.get("race_id"): r for r in cohort["not_processed"]}
    _require(
        len(processed) == len(cohort["processed"])
        and len(blocked) == len(cohort["not_processed"])
        and not (set(processed) & set(blocked))
        and set(processed) | set(blocked) == set(current),
        "CURRENT_COHORT_MEMBER_CONFLICT",
    )
    readiness = source.get("race_readiness_after")
    _require(isinstance(readiness, list), "CURRENT_SOURCE_READINESS_MISSING")
    ready = {r.get("race_id"): r for r in readiness}
    _require(
        len(ready) == len(readiness) and set(ready) == set(current),
        "CURRENT_SOURCE_READINESS_CONFLICT",
    )
    original_handoff = cohort.get("collector_handoff") or []
    _require(isinstance(original_handoff, list), "COLLECTOR_HANDOFF_FORMAT_INVALID")
    handoff = {r.get("race_id"): r for r in original_handoff}
    _require(len(handoff) == len(original_handoff)
             and set(handoff) <= set(current), "COLLECTOR_HANDOFF_IDENTITY_CONFLICT")
    records = scorecard.get("records")
    counts = scorecard.get("counts")
    _require(isinstance(records, list) and isinstance(counts, dict),
             "SCORECARD_ROWS_OR_COUNTS_MISSING")
    names = [r.get("race_id") for r in records]
    _require(
        len(names) == len(set(names)) == counts.get("physical_races"),
        "SCORECARD_PHYSICAL_DENOMINATOR_INVALID",
    )
    # Current source captures can precede their immutable model/result archive.
    # Keep those physical races entirely outside the cumulative scorecard
    # denominator, never invent a benchmark row or a post-hoc prediction.
    source_only = sorted(set(current) - set(names))
    paired = [r for r in records if r.get("status") == "EVALUABLE_RESEARCH_ONLY"]
    triple = [r for r in paired if r.get("benchmark_status") == "TRIPLE_EVALUABLE"]
    _require(
        len(paired) == counts.get("paired_champion_core004")
        and len(triple) == counts.get("triple_evaluable")
        and len(paired) - len(triple) == counts.get("model_pair_only")
        and sum(r.get("complete_active_field") is True for r in records)
        == counts.get("complete_prediction_fields")
        and all(r.get("bet_authority") is False for r in records),
        "SCORECARD_QUALITY_COUNTS_INVALID",
    )
    for row in paired:
        _require(
            isinstance(row.get("score"), dict)
            and len(row.get("original_result_receipts") or []) >= 2
            and row.get("winner_selection_id") is not None,
            "EVALUABLE_ROW_LACKS_ORIGINAL_OUTCOME",
        )
    for row in triple:
        _require(
            row.get("market_baseline_available") is True
            and row["score"].get("market_log_loss") is not None
            and row["score"].get("market_multiclass_brier") is not None,
            "TRIPLE_ROW_LACKS_WIN_SOURCE",
        )
    min_n = (scorecard.get("calibration") or {}).get("min_distinct_races")
    _require(type(min_n) is int and min_n >= 30,
             "CALIBRATION_MINIMUM_UNVERIFIED")
    per_race = []
    per_track: dict[str, Counter] = {}
    per_date: dict[str, Counter] = {}
    primary_blockers: Counter = Counter()
    for row in sorted(records, key=lambda x: x["race_id"]):
        rid = row["race_id"]
        match = RACE_ID.fullmatch(rid)
        _require(match is not None, "PHYSICAL_RACE_ID_FORMAT_INVALID")
        track, day, race_no = match.groups()
        is_paired = row in paired
        is_triple = row in triple
        reasons = row.get("reasons") or []
        if not is_paired:
            primary_blockers[reasons[0] if reasons else "UNCLASSIFIED_NOT_EVALUABLE"] += 1
        facts = {
            "race_id": rid, "track": track, "date": day,
            "race_no": int(race_no),
            "model_full_field": row.get("complete_active_field") is True,
            "model_frozen_sha256": row.get("source_model_original_sha256"),
            "active_model_runners": row.get("active_runners"),
            "model_as_of_utc": row.get("model_as_of_utc"),
            "reference_created_at_utc": row.get("model_created_at_utc"),
            "alternative_original_freezes": row.get("original_freeze_history") or [],
            "win_market_on_reference_freeze": row.get("market_baseline_available") is True,
            "official_result_verified": is_paired,
            "original_result_receipts": row.get("original_result_receipts") or [],
            "benchmark_status": row.get("benchmark_status") or "NOT_EVALUABLE",
            "research_status": row.get("status"),
            "score": row.get("score"),
            "primary_blocker": reasons[0] if reasons else None,
            "all_blockers": reasons,
            "pit_certified": False,
            "bet_authority": False,
        }
        if rid in ready:
            src = ready[rid]
            importer = handoff.get(rid)
            admission = blocked.get(rid) or processed.get(rid)
            facts["current_source_readiness"] = {
                "start_utc": src.get("canonical_start_utc"),
                "t4_cutoff_utc": src.get("t4_cutoff_utc"),
                "source_as_of_utc": src.get("evidence_as_of_utc"),
                "observed_roster_rows": src.get("roster_rows"),
                "observed_active_runners": src.get("active_runners_known"),
                "verified_fundamentals": src.get("verified_active_history"),
                "all_fundamentals_complete": src.get("history_complete_as_of_t4") is True,
                "win_complete_as_of_t4": src.get("win_market_complete_as_of_t4") is True,
                "collector_model_input_approved": (
                    importer.get("model_input_approved") is True if importer else False
                ),
                "collector_source_sha256": (
                    (importer.get("model_input_sources") or {}).get(
                        "collector_starts_sha256"
                    ) if importer else None
                ),
                "admission_blockers": (admission or {}).get("collector_blockers", []),
                "admission_status": (admission or {}).get("reason", "PROCESSED"),
            }
        per_race.append(facts)
        for counter in (per_track.setdefault(track, Counter()),
                        per_date.setdefault(day, Counter())):
            counter["physical_races"] += 1
            counter["complete_model_full_fields"] += bool(facts["model_full_field"])
            counter["scored_original_model_pairs"] += is_paired
            counter["triple_win_benchmarks"] += is_triple
    comparisons = {}
    for cohort_name, cohort_rows in (("triple_same_races", triple), ("model_pairs", paired)):
        first = (
            [("champion", "core004"), ("champion", "market"), ("core004", "market")]
            if cohort_name == "triple_same_races" else [("champion", "core004")]
        )
        comparisons[cohort_name] = {
            f"{a}_minus_{b}_{measure}": _uncertainty(cohort_rows, a, b, measure, min_n)
            for a, b in first for measure in ("log_loss", "multiclass_brier")
        }
    market_avg = statistics.fmean(r["score"]["market_log_loss"] for r in triple) if triple else None
    reported_market_avg = (scorecard.get("metrics") or {}).get("market_log_loss")
    if market_avg is not None:
        _require(
            type(reported_market_avg) in (int, float)
            and math.isclose(market_avg, reported_market_avg, rel_tol=0, abs_tol=1e-9),
            "MARKET_METRIC_COHORT_MISMATCH",
        )
    return {
        "schema": SCHEMA,
        "research_only": True,
        "bet_authority": False,
        "model_refit_performed": False,
        "pit_certification_performed": False,
        "source_sha256": {
            "cumulative_scorecard_index": score_sha,
            "current_core003_source_report": source_sha,
            "current_model_cohort_index": cohort_sha,
            "cumulative_dev011_manifest": coverage_sha,
        },
        "source_clocks": {
            "current_core003_finished_at_utc": source.get("finished_at_utc"),
            "current_model_index_written_at_utc": cohort.get("index_written_at_utc"),
            "cumulative_scorecard_generated_at_utc": scorecard.get("generated_at_utc"),
        },
        "coverage_status": (
            "INCOMPLETE_ORIGINAL_COVERAGE" if coverage.get("coverage_complete") is not True
            else "ORIGINAL_COVERAGE_COMPLETE_RESEARCH_ONLY"
        ),
        "counts": {
            **counts,
            "current_source_fixed_cohort": len(current),
            "current_source_only_unscored": len(source_only),
            "current_source_model_processed": len(processed),
            "current_source_rejected": len(blocked),
            "current_source_verified_full_fundamentals": sum(
                r.get("history_complete_as_of_t4") is True for r in readiness
            ),
            "current_source_complete_win": sum(
                r.get("win_market_complete_as_of_t4") is True for r in readiness
            ),
            "cumulative_archive_errors": len(scorecard.get("archive_errors") or []),
            "cumulative_missing_or_conflicting_originals": len(
                coverage.get("missing_originals") or []
            ),
        },
        "primary_rejection_reasons": dict(sorted(primary_blockers.items())),
        "current_not_processed": cohort["not_processed"],
        "current_source_only_not_in_benchmark": [
            {"race_id": rid, "status": "SOURCE_ONLY_NOT_BENCHMARKED",
             "pit_certified": False, "bet_authority": False}
            for rid in source_only
        ],
        "missing_originals": coverage.get("missing_originals") or [],
        "per_track": {k: dict(v) for k, v in sorted(per_track.items())},
        "per_date": {k: dict(v) for k, v in sorted(per_date.items())},
        "pairwise_model_differences": comparisons,
        "min_distinct_races_before_calibration": min_n,
        "market_calibration_status": (scorecard.get("calibration") or {}).get("status"),
        "per_physical_race": per_race,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scorecard-index", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--model-cohort-index", type=Path, required=True)
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = summarize(
        scorecard_index=args.scorecard_index,
        source_report=args.source_report,
        model_cohort_index=args.model_cohort_index,
        coverage_manifest=args.coverage_manifest,
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "index.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
