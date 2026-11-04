"""MVP-019: read-only, original-backed prospective source readiness diagnostics.

Never infer independent registration IDs, scratch receipts, PIT or BET from an
old model freeze, collector name match or a cumulative outcome scorecard.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .mvp016_research_status import _load
from .mvp018_coverage_funnel import build_funnel

SCHEMA = "MVP019_SOURCE_READINESS_MATRIX_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _clock(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("SOURCE_CLOCK_TYPE_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("SOURCE_CLOCK_INVALID") from exc
    if parsed.utcoffset() is None:
        raise ValueError("SOURCE_CLOCK_NOT_AWARE")
    return parsed.astimezone(UTC)


def _blocker(blockers: list[str]) -> str | None:
    raw = " ".join(blockers).upper()
    if "IDENTITY" in raw or "TMP_" in raw:
        return "BLOCKED_IDENTITY"
    if "CLOCK_CONFLICT" in raw or "START_CLOCK" in raw:
        return "BLOCKED_CLOCK_CONFLICT"
    if "SCRATCH" in raw or "STRYK" in raw:
        return "BLOCKED_SCRATCH_SOURCE"
    if "ATG_FULL_FIELD" in raw or "FUNDAMENTAL_COHORT" in raw:
        return "BLOCKED_ATG_FULL_FIELD"
    if any(k in raw for k in ("ROSTER", "ACTIVE_SET", "FIELD_MISMATCH", "SQLITE_FIELD")):
        return "BLOCKED_ACTIVE_FIELD"
    if "NOT_BEFORE_CONSERVATIVE_T4" in raw:
        return "PAST_CUTOFF"
    if "EXECUTION_ERROR" in raw or "VALIDATION_ERROR" in raw:
        return "BLOCKED_IMPLEMENTATION"
    if "TIMING" in raw or "OBSERVATION_CLOCK" in raw:
        return "BLOCKED_SOURCE_TIMING"
    return "BLOCKED_SOURCE_ATTESTATION" if blockers else None


def build_readiness(
    joined: dict, *, evaluation_at_utc: str | None = None,
    github_run_id: int | None = None,
) -> dict:
    """Use source-only admission records, not retrospective model scores."""
    funnel = build_funnel(joined)  # validates hashes, cohort identity, original outcomes
    if github_run_id is not None and (type(github_run_id) is not int or github_run_id <= 0):
        raise ValueError("GITHUB_RUN_ID_CLAIM_INVALID")
    source_clocks = joined.get("source_clocks") or {}
    if not isinstance(source_clocks, dict):
        raise TypeError("SOURCE_CLOCKS_INVALID")
    at = _clock(
        evaluation_at_utc if evaluation_at_utc is not None
        else source_clocks.get("current_core003_finished_at_utc")
    )
    current_ids = set(funnel["current_source_race_ids"])
    counts = Counter()
    rows = []
    for old in sorted(joined["per_physical_race"], key=lambda row: row["race_id"]):
        rid = old["race_id"]
        current = rid in current_ids
        source = old.get("current_source_readiness") if current else None
        if current and not isinstance(source, dict):
            raise ValueError("CURRENT_RACE_SOURCE_MISSING")
        source = source or {}
        start = _clock(source.get("start_utc"))
        cutoff = _clock(source.get("t4_cutoff_utc"))
        observed = _clock(source.get("source_as_of_utc"))
        if start is not None and cutoff is not None and cutoff >= start:
            raise ValueError("CUTOFF_CLOCK_CONFLICT")
        blockers = source.get("admission_blockers") or []
        if not isinstance(blockers, list) or any(not isinstance(b, str) for b in blockers):
            raise ValueError("SOURCE_BLOCKERS_INVALID")
        blockers = sorted(set(blockers))
        sha = source.get("collector_source_sha256")
        captured = isinstance(sha, str) and SHA.fullmatch(sha) is not None
        after_cutoff = observed is not None and cutoff is not None and observed >= cutoff
        expired = at is not None and cutoff is not None and at >= cutoff
        missing = []
        if current:
            if not captured:
                missing.append("collector_startlist_original_sha256")
            if start is None:
                missing.append("independent_official_start_clock_original")
            if observed is None:
                missing.append("source_observation_clock")
            if cutoff is None:
                missing.append("conservative_t4_clock")
            if source.get("all_fundamentals_complete") is not True:
                missing.append("complete_atg_fundamentals")
            if source.get("collector_model_input_approved") is not True:
                missing.append("collector_model_input_approval")
            # The four-original research join DOES NOT independently attest these.
            missing.extend((
                "independent_per_runner_registered_identity_original",
                "time_qualified_official_scratch_original",
            ))
            status = (
                _blocker(blockers)
                or ("BLOCKED_SOURCE_TIMING" if after_cutoff else None)
                or ("PAST_CUTOFF" if expired else None)
                or "BLOCKED_SOURCE_ATTESTATION"
            )
            counts[status] += 1
        else:
            status = "HISTORICAL_ONLY_NO_CURRENT_SOURCE_RECEIPT"
            missing = ["contemporaneous_collector_evidence_chain_not_in_four_originals"]
        rows.append({
            "race_id": rid, "track": old["track"], "date": old["date"],
            "race_no": old["race_no"], "current_source_cohort": current,
            "status": status, "original_gate_blockers": blockers,
            "collector_run_id_claim": github_run_id if current else None,
            "collector_startlist_sha256": sha if captured else None,
            "source_observed_at_utc": observed.isoformat() if observed else None,
            "canonical_start_at_utc": start.isoformat() if start else None,
            "official_clock_independently_attested": False,
            "conservative_t4_at_utc": cutoff.isoformat() if cutoff else None,
            "t4_still_possible": at < cutoff if current and at and cutoff else None,
            "source_observed_after_t4": after_cutoff if current else None,
            "roster_rows": source.get("observed_roster_rows") if current else None,
            "active_runners": source.get("observed_active_runners") if current else None,
            "atg_verified_active_histories": (
                source.get("verified_fundamentals") if current else None
            ),
            "atg_full_field": (
                source.get("all_fundamentals_complete") is True if current else None
            ),
            "stable_runner_identities": None,
            "cross_provider_identity": "NOT_ATTESTED_IN_FOUR_ORIGINAL_JOIN",
            "official_scratch_original_qualified": None,
            "collector_model_input_approved": (
                source.get("collector_model_input_approved") is True if current else None
            ),
            "current_model_admission": source.get("admission_status") if current else None,
            "cumulative_model_full_field": old.get("model_full_field") is True,
            "cumulative_result_scored": old.get("official_result_verified") is True,
            "cumulative_win_triple": old.get("benchmark_status") == "TRIPLE_EVALUABLE",
            "missing_original_evidence": missing,
            "pit_certified": False, "bet_authority": False,
        })
    if sum(counts.values()) != len(current_ids):
        raise ValueError("READINESS_CURRENT_DENOMINATOR_INVALID")
    return {
        "schema": SCHEMA, "research_only": True, "bet_authority": False,
        "pit_certification_performed": False, "new_model_freezes_created": 0,
        "prospective_pit_certified": 0, "readiness_granting_authority": "NONE",
        "source_join_sha256": funnel["original_source_sha256"],
        "github_run_id_claim_not_authenticated": github_run_id,
        "evaluation_at_utc": at.isoformat() if at else None,
        "physical_races": len(rows), "current_source_races": len(current_ids),
        "historical_without_current_source": len(rows) - len(current_ids),
        "current_status_counts": dict(sorted(counts.items())),
        "cumulative_benchmark_stages": funnel["cumulative_benchmark_stages"],
        "limitation": (
            "Four originals lack independent stable IDs and timed official "
            "scratches; cumulative models do not prove current source readiness."
        ),
        "races": rows,
    }



def build_operational_readiness(
    *, scorecard: dict, source: dict, cohort: dict, coverage: dict,
    original_sha256: dict[str, str], evaluation_at_utc: str | None = None,
    github_run_id: int | None = None,
) -> dict:
    """Use disjoint current-source and cumulative scorecard denominators.

    The current run's cohort may contain a newly processed race before its
    model archive is uploaded or indexed by the cumulative scorecard. Never
    fabricate a cumulative result row to make the join succeed.
    """
    if github_run_id is not None and (type(github_run_id) is not int or github_run_id <= 0):
        raise ValueError("GITHUB_RUN_ID_CLAIM_INVALID")
    required_hashes = {
        "cumulative_scorecard_index", "current_core003_source_report",
        "current_model_cohort_index", "cumulative_dev011_manifest",
    }
    if (set(original_sha256) != required_hashes
            or any(SHA.fullmatch(value) is None for value in original_sha256.values())):
        raise ValueError("ORIGINAL_SHA_ANCHORS_INVALID")
    if (scorecard.get("schema") != "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
            or scorecard.get("authority") != "READ_ONLY_RESEARCH_SCORECARD"
            or scorecard.get("model_originals_verified_by_sha") is not True
            or scorecard.get("v33_evaluator_called") is not False
            or scorecard.get("bet_authority") is not False
            or scorecard.get("pit_certification_performed") is not False):
        raise ValueError("SCORECARD_NOT_AUTHENTICATED_RESEARCH_ONLY")
    if (source.get("schema_version") != "CORE_003_SHADOW_PILOT_V1"
            or source.get("bet_count") != 0
            or source.get("prospective_t4_success_proven") is not False):
        raise ValueError("CORE003_SOURCE_ORIGINAL_INVALID")
    if (cohort.get("schema") != "BET_MVP_002_FIXED_COHORT_INDEX_V1"
            or cohort.get("bet_authority") is not False
            or cohort.get("pit_certified") is not False
            or cohort.get("source_report_sha256")
            != original_sha256["current_core003_source_report"]):
        raise ValueError("CURRENT_COHORT_SOURCE_SHA_INVALID")
    if (coverage.get("schema") != "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1"
            or coverage.get("bet_authority") is not False
            or coverage.get("pit_certification_performed") is not False
            or coverage.get("github_artifact_inventory_sha256") is None
            or coverage.get("github_artifact_inventory_sha256")
            != (scorecard.get("cumulative_original_inventory") or {}).get(
                "github_artifact_inventory_sha256"
            )):
        raise ValueError("CUMULATIVE_INVENTORY_SOURCE_CONFLICT")
    if any(
        isinstance(item, dict)
        and item.get("reason") == "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"
        for item in (coverage.get("missing_originals") or [])
    ):
        raise ValueError("CUMULATIVE_ORIGINAL_INVENTORY_UNAVAILABLE")
    records = scorecard.get("records")
    metrics = scorecard.get("counts")
    if not isinstance(records, list) or not isinstance(metrics, dict):
        raise ValueError("CUMULATIVE_SCORECARD_MISSING")
    historical = {}
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("race_id"), str):
            raise ValueError("PHYSICAL_RACE_ROW_INVALID")
        rid = item["race_id"]
        if rid in historical or item.get("bet_authority") is not False:
            raise ValueError("CUMULATIVE_PHYSICAL_ID_OR_AUTHORITY_CONFLICT")
        historical[rid] = item
    pairs = {rid for rid, item in historical.items()
             if item.get("status") == "EVALUABLE_RESEARCH_ONLY"}
    triples = {rid for rid in pairs
               if historical[rid].get("benchmark_status") == "TRIPLE_EVALUABLE"}
    full = {rid for rid, item in historical.items()
            if item.get("complete_active_field") is True}
    if (len(historical) != metrics.get("physical_races")
            or len(full) != metrics.get("complete_prediction_fields")
            or len(pairs) != metrics.get("paired_champion_core004")
            or len(triples) != metrics.get("triple_evaluable")
            or len(pairs) - len(triples) != metrics.get("model_pair_only")
            or metrics.get("pit_certified_paired") != 0
            or any(rid not in full for rid in pairs)):
        raise ValueError("CUMULATIVE_SCORECARD_DENOMINATOR_CONFLICT")
    current = cohort.get("original_cohort")
    if (not isinstance(current, list) or not all(isinstance(r, str) for r in current)
            or len(current) != len(set(current))
            or current != source.get("races_in_fixed_cohort")):
        raise ValueError("CURRENT_SOURCE_COHORT_IDENTITY_CONFLICT")
    current_ids = set(current)

    def keyed(items: object, name: str) -> dict:
        if not isinstance(items, list):
            raise ValueError(name + "_NOT_LIST")
        result = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("race_id"), str):
                raise ValueError(name + "_ROW_INVALID")
            rid = item["race_id"]
            if rid in result:
                raise ValueError(name + "_DUPLICATE_PHYSICAL_ID")
            result[rid] = item
        return result

    processed = keyed(cohort.get("processed"), "PROCESSED")
    not_processed = keyed(cohort.get("not_processed"), "NOT_PROCESSED")
    readiness = keyed(source.get("race_readiness_after"), "SOURCE_READINESS")
    handoff = keyed(cohort.get("collector_handoff") or [], "COLLECTOR_HANDOFF")
    if (set(processed) & set(not_processed)
            or set(processed) | set(not_processed) != current_ids
            or set(readiness) != current_ids
            or not set(handoff) <= current_ids):
        raise ValueError("CURRENT_SOURCE_MEMBERSHIP_CONFLICT")
    at = _clock(
        evaluation_at_utc if evaluation_at_utc is not None
        else source.get("finished_at_utc")
    )
    statuses = Counter()
    rows = []
    for rid in sorted(set(historical) | current_ids):
        historical_row = historical.get(rid)
        active = rid in current_ids
        current_src = readiness[rid] if active else {}
        raw_handoff = handoff.get(rid, {})
        blocked = not_processed.get(rid, {})
        observed = _clock(current_src.get("evidence_as_of_utc"))
        start = _clock(current_src.get("canonical_start_utc"))
        t4 = _clock(current_src.get("t4_cutoff_utc"))
        if start is not None and t4 is not None and t4 >= start:
            raise ValueError("CURRENT_SOURCE_CUTOFF_INVALID")
        original_starts_sha = (raw_handoff.get("model_input_sources") or {}).get(
            "collector_starts_sha256"
        )
        sha_valid = (isinstance(original_starts_sha, str)
                     and SHA.fullmatch(original_starts_sha) is not None)
        blockers = sorted(set(
            list(raw_handoff.get("blockers") or [])
            + list(blocked.get("collector_blockers") or [])
        ))
        if any(not isinstance(value, str) for value in blockers):
            raise ValueError("COLLECTOR_BLOCKER_TYPE_INVALID")
        dimensions = sorted({_blocker([reason]) for reason in blockers} - {None})
        missing = []
        if active:
            if not sha_valid:
                missing.append("collector_original_startlist_sha256")
            if start is None or t4 is None:
                missing.append("independent_official_start_and_conservative_t4")
            if observed is None:
                missing.append("source_observation_clock")
            if current_src.get("history_complete_as_of_t4") is not True:
                missing.append("active_full_field_atg_fundamentals")
            if current_src.get("win_market_complete_as_of_t4") is not True:
                missing.append("time_qualified_win_source")
            if raw_handoff.get("model_input_approved") is not True:
                missing.append("independent_collector_model_approval")
            # Names / start numbers and the copied Rikstoto registration
            # CANNOT certify an independent ATG registration crosswalk.
            missing += [
                "independent_per_runner_registered_identity_original",
                "time_qualified_official_scratch_original",
            ]
            status = (
                "BLOCKED_ACTIVE_FIELD" if "BLOCKED_ACTIVE_FIELD" in dimensions
                else "BLOCKED_ATG_FULL_FIELD" if "BLOCKED_ATG_FULL_FIELD" in dimensions
                else "BLOCKED_IDENTITY" if "BLOCKED_IDENTITY" in dimensions
                else dimensions[0] if dimensions else "BLOCKED_SOURCE_ATTESTATION"
            )
            statuses[status] += 1
        else:
            status = "HISTORICAL_ONLY_NO_CURRENT_SOURCE_RECEIPT"
            missing = ["contemporaneous_collector_source_chain_unavailable"]
        rows.append({
            "race_id": rid,
            "current_source_cohort": active,
            "cumulative_scorecard_member": historical_row is not None,
            "status": status,
            "blocking_dimensions": dimensions,
            "underlying_original_gate_blockers": blockers,
            "collector_original_starts_sha256": original_starts_sha if sha_valid else None,
            "source_observed_at_utc": observed.isoformat() if observed else None,
            "canonical_start_at_utc": start.isoformat() if start else None,
            "conservative_t4_at_utc": t4.isoformat() if t4 else None,
            "t4_still_possible": at < t4 if active and at and t4 else None,
            "official_clock_independently_attested": False,
            "source_full_active_atg": (
                current_src.get("history_complete_as_of_t4") is True if active else None
            ),
            "verified_active_atg_histories": (
                current_src.get("verified_active_history") if active else None
            ),
            "active_runners": (
                current_src.get("active_runners_known") if active else None
            ),
            "win_market_complete_as_of_t4": (
                current_src.get("win_market_complete_as_of_t4") is True
                if active else None
            ),
            "registered_runner_ids_independently_attested": False if active else None,
            "official_scratch_as_of_t4_attested": None,
            "frozen_roster_reported_scratches": [
                {"start_number": runner.get("start_number"),
                 "horse_name": runner.get("horse_name")}
                for runner in (raw_handoff.get("runners") or [])
                if isinstance(runner, dict) and runner.get("scratched") is True
            ] if active else None,
            "current_research_model_processed": rid in processed if active else None,
            "collector_model_input_approved": (
                raw_handoff.get("model_input_approved") is True if active else None
            ),
            "current_research_model_eligible": (
                raw_handoff.get("research_model_eligible") is True if active else None
            ),
            "cumulative_full_frozen_model": (
                historical_row.get("complete_active_field") is True
                if historical_row else None
            ),
            "cumulative_scored_model_pair": (
                rid in pairs if historical_row else None
            ),
            "cumulative_win_triple": (
                rid in triples if historical_row else None
            ),
            "missing_original_evidence": missing,
            "bet_authority": False, "pit_certified": False,
        })
    if sum(statuses.values()) != len(current_ids):
        raise ValueError("CURRENT_SOURCE_COUNT_CONFLICT")
    return {
        "schema": SCHEMA,
        "research_only": True, "bet_authority": False,
        "pit_certification_performed": False, "new_model_freezes_created": 0,
        "prospective_pit_certified": 0, "readiness_granting_authority": "NONE",
        "source_join_sha256": dict(sorted(original_sha256.items())),
        "github_run_id_claim_not_authenticated": github_run_id,
        "evaluation_at_utc": at.isoformat() if at else None,
        "cumulative_benchmark_physical_races": len(historical),
        "current_source_physical_races": len(current_ids),
        "source_only_not_yet_cumulative": sorted(current_ids - set(historical)),
        "union_unique_physical_races_not_benchmark_denominator": len(rows),
        "cumulative_benchmark_stages": {
            "ORIGINAL_PHYSICAL_COHORT": len(historical),
            "FROZEN_COMPLETE_FULL_FIELD": len(full),
            "OFFICIAL_RESULT_SCORED": len(pairs),
            "SAME_FREEZE_WIN_TRIPLE": len(triples),
        },
        "current_model_processed_research_only": len(processed),
        "current_collector_model_input_approved": sum(
            handoff.get(rid, {}).get("model_input_approved") is True
            for rid in current_ids
        ),
        "current_status_counts": dict(sorted(statuses.items())),
        "limitation": (
            "Historical scorecard and current source have disjoint horizons. "
            "Source-only races are NOT benchmark model/results, and copied "
            "registration numbers cannot certify independent identities."
        ),
        "races": rows,
    }


def operational_from_originals(
    *, scorecard_index: Path, source_report: Path, model_cohort_index: Path,
    coverage_manifest: Path, evaluation_at_utc: str | None = None,
    github_run_id: int | None = None,
) -> dict:
    scorecard, score_sha = _load(scorecard_index)
    source, source_sha = _load(source_report)
    cohort, cohort_sha = _load(model_cohort_index)
    coverage, coverage_sha = _load(coverage_manifest)
    return build_operational_readiness(
        scorecard=scorecard, source=source, cohort=cohort, coverage=coverage,
        original_sha256={
            "cumulative_scorecard_index": score_sha,
            "current_core003_source_report": source_sha,
            "current_model_cohort_index": cohort_sha,
            "cumulative_dev011_manifest": coverage_sha,
        },
        evaluation_at_utc=evaluation_at_utc, github_run_id=github_run_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for field in ("scorecard-index", "source-report", "model-cohort-index",
                  "coverage-manifest", "output-dir"):
        parser.add_argument("--" + field, required=True, type=Path)
    parser.add_argument("--evaluation-at-utc")
    parser.add_argument("--github-run-id", type=int)
    args = parser.parse_args(argv)
    result = operational_from_originals(
        scorecard_index=args.scorecard_index, source_report=args.source_report,
        model_cohort_index=args.model_cohort_index,
        coverage_manifest=args.coverage_manifest,
        evaluation_at_utc=args.evaluation_at_utc, github_run_id=args.github_run_id,
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "index.json").write_text(
        json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
