"""MVP-018: explicit source-backed physical-race research coverage funnel.

Consumes the already validated MVP-016 four-original join; never reclassifies
a historical original, creates a freeze, evaluates the model, or authorizes bets.
Current fixed-cohort stages and cumulative outcome stages are deliberately
separate: there are no longitudinal source receipts for all cumulative races.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path

from .mvp016_research_status import summarize

SCHEMA = "MVP018_PHYSICAL_RACE_COVERAGE_FUNNEL_V1"
CURRENT_STAGES = (
    "FIXED_PHYSICAL_COHORT",
    "COLLECTOR_SOURCE_SHA_PRESENT",
    "SOURCE_MODEL_INPUT_APPROVED",
    "ELIGIBLE_FROZEN_AND_INDEXED",
    "OFFICIAL_RESULT_SCORED",
    "SAME_FREEZE_WIN_TRIPLE",
)
CUMULATIVE_STAGES = (
    "ORIGINAL_PHYSICAL_COHORT",
    "FROZEN_COMPLETE_FULL_FIELD",
    "OFFICIAL_RESULT_SCORED",
    "SAME_FREEZE_WIN_TRIPLE",
)


def build_funnel(joined: dict) -> dict:
    """Preserve unknown evidence; do not infer 67 full source capture chains."""
    if (not isinstance(joined, dict)
            or joined.get("schema") != "MVP016_CUMULATIVE_RESEARCH_STATUS_V1"
            or joined.get("bet_authority") is not False
            or joined.get("research_only") is not True
            or joined.get("pit_certification_performed") is not False):
        raise ValueError("MVP016_SOURCE_JOIN_NOT_VERIFIED")
    rows = joined.get("per_physical_race")
    counts = joined.get("counts")
    original_hashes = joined.get("source_sha256")
    if (not isinstance(rows, list) or not isinstance(counts, dict)
            or not isinstance(original_hashes, dict)
            or set(original_hashes) != {
                "cumulative_scorecard_index", "current_core003_source_report",
                "current_model_cohort_index", "cumulative_dev011_manifest"
            }
            or any(not isinstance(value, str) or len(value) != 64
                   or any(c not in "0123456789abcdef" for c in value)
                   for value in original_hashes.values())):
        raise ValueError("SOURCE_JOIN_RECEIPTS_OR_ROWS_MISSING")
    ids = [r.get("race_id") for r in rows if isinstance(r, dict)]
    if (len(ids) != len(rows) or len(set(ids)) != len(ids)
            or len(ids) != counts.get("physical_races")):
        raise ValueError("PHYSICAL_RACE_DENOMINATOR_CONFLICT")
    current = [r for r in rows if "current_source_readiness" in r]
    current_ids = {r["race_id"] for r in current}
    current_capture = set()
    current_approved = set()
    full_field = set()
    scored = set()
    triple = set()
    current_blocks = Counter()
    for r in rows:
        rid = r["race_id"]
        history = r.get("alternative_original_freezes") or []
        if not isinstance(history, list):
            raise TypeError("FROZEN_HISTORY_NOT_LIST")
        selected = [v for v in history if v.get("selected_benchmark_reference") is True]
        if len(selected) > 1:
            raise ValueError("MULTIPLE_SELECTED_BENCHMARK_FREEZES")
        if r.get("model_full_field") is True:
            if (len(selected) != 1 or selected[0].get("eligible_pre_t4") is not True
                    or selected[0].get("model_sha256") != r.get("model_frozen_sha256")):
                raise ValueError("QUALIFIED_FULL_FIELD_WITHOUT_ORIGINAL_FREEZE")
            full_field.add(rid)
        if r.get("official_result_verified") is True:
            if rid not in full_field or r.get("research_status") != "EVALUABLE_RESEARCH_ONLY":
                raise ValueError("OFFICIAL_RESULT_WITHOUT_VERIFIED_MODEL")
            scored.add(rid)
        if r.get("benchmark_status") == "TRIPLE_EVALUABLE":
            if rid not in scored or r.get("win_market_on_reference_freeze") is not True:
                raise ValueError("WIN_TRIPLE_WITHOUT_SAME_FREEZE_RESULT")
            triple.add(rid)
        if rid not in current_ids:
            continue
        src = r["current_source_readiness"]
        if not isinstance(src, dict):
            raise TypeError("CURRENT_SOURCE_READINESS_INVALID")
        sha = src.get("collector_source_sha256")
        if isinstance(sha, str) and len(sha) == 64 and all(
            c in "0123456789abcdef" for c in sha
        ):
            current_capture.add(rid)
        if src.get("collector_model_input_approved") is True:
            if rid not in current_capture:
                raise ValueError("SOURCE_MODEL_APPROVED_WITHOUT_COLLECTOR_SHA")
            current_approved.add(rid)
        if src.get("admission_status") != "PROCESSED":
            for reason in src.get("admission_blockers") or []:
                current_blocks[str(reason)] += 1
    current_frozen = current_ids & full_field
    current_scored = current_ids & scored
    current_triple = current_ids & triple
    current_counts = [
        len(current_ids), len(current_capture), len(current_approved),
        len(current_frozen), len(current_scored), len(current_triple)
    ]
    cumulative_counts = [len(ids), len(full_field), len(scored), len(triple)]
    if (any(a < b for a, b in pairwise(current_counts))
            or any(a < b for a, b in pairwise(cumulative_counts))
            or cumulative_counts[1] != counts.get("complete_prediction_fields")
            or cumulative_counts[2] != counts.get("paired_champion_core004")
            or cumulative_counts[3] != counts.get("triple_evaluable")
            or len(current_ids) != counts.get("current_source_fixed_cohort")):
        raise ValueError("FUNNEL_OR_SCORECARD_STAGE_CONFLICT")
    return {
        "schema": SCHEMA,
        "research_only": True,
        "bet_authority": False,
        "pit_certification_performed": False,
        "qualified_historical_freezes_created": 0,
        "original_source_sha256": dict(sorted(original_hashes.items())),
        "current_cohort_stages": dict(zip(CURRENT_STAGES, current_counts)),
        "cumulative_benchmark_stages": dict(zip(CUMULATIVE_STAGES, cumulative_counts)),
        "current_cohort_blockers_nonexclusive": dict(sorted(current_blocks.items())),
        "current_source_history_complete": counts.get(
            "current_source_verified_full_fundamentals"
        ),
        "current_source_win_complete": counts.get("current_source_complete_win"),
        "cumulative_primary_blockers": joined.get("primary_rejection_reasons"),
        "physical_race_ids_per_cumulative_stage": {
            "FROZEN_COMPLETE_FULL_FIELD": sorted(full_field),
            "OFFICIAL_RESULT_SCORED": sorted(scored),
            "SAME_FREEZE_WIN_TRIPLE": sorted(triple),
        },
        "current_source_race_ids": sorted(current_ids),
        "data_limitation": (
            "Cumulative source-captured and validated counts are UNKNOWN: "
            "the four originals only attest those transitions for the latest "
            "fixed cohort; do not infer a historical funnel from outcome rows."
        ),
        "current_workflow_code_sha": None,
        "operational_pit_certified": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scorecard-index", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--model-cohort-index", type=Path, required=True)
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    joined = summarize(
        scorecard_index=args.scorecard_index, source_report=args.source_report,
        model_cohort_index=args.model_cohort_index,
        coverage_manifest=args.coverage_manifest,
    )
    report = build_funnel(joined)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "index.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
