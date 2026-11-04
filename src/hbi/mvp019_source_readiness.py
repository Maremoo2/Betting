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

from .mvp016_research_status import summarize
from .mvp018_coverage_funnel import build_funnel

SCHEMA = "MVP019_SOURCE_READINESS_MATRIX_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _clock(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("SOURCE_CLOCK_TYPE_INVALID")
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
        raise ValueError("SOURCE_CLOCKS_INVALID")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for field in ("scorecard-index", "source-report", "model-cohort-index",
                  "coverage-manifest", "output-dir"):
        parser.add_argument("--" + field, required=True, type=Path)
    parser.add_argument("--evaluation-at-utc")
    parser.add_argument("--github-run-id", type=int)
    args = parser.parse_args(argv)
    joined = summarize(
        scorecard_index=args.scorecard_index, source_report=args.source_report,
        model_cohort_index=args.model_cohort_index,
        coverage_manifest=args.coverage_manifest,
    )
    result = build_readiness(
        joined, evaluation_at_utc=args.evaluation_at_utc, github_run_id=args.github_run_id
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "index.json").write_text(
        json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
