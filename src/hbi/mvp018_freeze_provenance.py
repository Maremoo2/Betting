"""MVP-018: source-attested explanations for absent prospective model freezes.

Pure read-only diagnostics. All model/market/result numbers stay untouched.
An old original cohort index is evidence of an ATTEMPT, never a reconstructed
model freeze or proof of PIT. Missing sources remain UNKNOWN, not invented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCORECARD = "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
COHORT = "BET_MVP_002_FIXED_COHORT_INDEX_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RACE = re.compile(r"RIKSTOTO:[A-Za-z0-9]+_NR_\d{4}-\d{2}-\d{2}:\d+\Z")
RESEARCH_SCHEMA = "MVP018_MISSING_MODEL_FREEZE_SOURCE_TRACE_V1"


def _clock(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("ORIGINAL_CLOCK_MISSING")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ORIGINAL_CLOCK_INVALID") from exc
    if instant.utcoffset() is None:
        raise ValueError("ORIGINAL_CLOCK_NOT_AWARE")
    return instant.astimezone(UTC)


def _original(path: Path, expected_sha: str) -> dict:
    if (not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha)
            or path.is_symlink() or not path.is_file()):
        raise ValueError("SOURCE_FILE_OR_PIN_INVALID")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("ORIGINAL_SHA256_MISMATCH")
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("ORIGINAL_JSON_INVALID") from exc
    if not isinstance(decoded, dict):
        raise TypeError("ORIGINAL_JSON_NOT_OBJECT")
    return decoded


def _members(index: dict) -> tuple[list[str], dict[str, dict], dict[str, dict]]:
    if (index.get("schema") != COHORT or index.get("bet_authority") is not False
            or index.get("pit_certified") is not False):
        raise ValueError("COHORT_ORIGINAL_CONTRACT_INVALID")
    cohort = index.get("original_cohort")
    if (not isinstance(cohort, list)
            or any(not isinstance(rid, str) or not RACE.fullmatch(rid) for rid in cohort)
            or len(set(cohort)) != len(cohort)):
        raise ValueError("ORIGINAL_PHYSICAL_COHORT_INVALID")
    processed, rejected = index.get("processed"), index.get("not_processed")
    if not isinstance(processed, list) or not isinstance(rejected, list):
        raise ValueError("ORIGINAL_COHORT_MEMBERS_MISSING")
    def lookup(rows: list[dict]) -> dict[str, dict]:
        values: dict[str, dict] = {}
        for item in rows:
            if not isinstance(item, dict):
                raise ValueError("ORIGINAL_COHORT_MEMBER_INVALID")
            rid = item.get("race_id")
            if not isinstance(rid, str) or not RACE.fullmatch(rid) or rid in values:
                raise ValueError("ORIGINAL_COHORT_MEMBER_DUPLICATED")
            values[rid] = item
        return values
    done, blocked = lookup(processed), lookup(rejected)
    if set(done) & set(blocked) or set(done) | set(blocked) != set(cohort):
        raise ValueError("COHORT_MEMBER_DENOMINATOR_CONFLICT")
    _clock(index.get("as_of_utc"))
    _clock(index.get("index_written_at_utc"))
    if _clock(index["index_written_at_utc"]) < _clock(index["as_of_utc"]):
        raise ValueError("COHORT_WRITTEN_BEFORE_ASOF")
    return cohort, done, blocked


def _blocker(rejection: dict | None, handoff: dict | None, processed: dict | None) -> tuple[str, str]:
    if processed is not None:
        return "UNRESOLVED", "INDEX_PROCESSED_MODEL_REQUIRES_INDEPENDENT_MODEL_SHA_REPLAY"
    if rejection is None:
        return "UNRESOLVED", "NO_PROSPECTIVE_DECISION_IN_SOURCE"
    reason = rejection.get("reason")
    if reason == "NOT_BEFORE_CONSERVATIVE_T4":
        return "MODEL_GATE_REJECTED", "CONSERVATIVE_T4_ALREADY_REACHED"
    if reason == "MODEL_REPORT_EXECUTION_ERROR":
        return "FREEZE_EXECUTION_FAILED", "ORIGINAL_MODEL_EXECUTION_ERROR"
    if reason != "COLLECTOR_RESEARCH_MODEL_GATE_NOT_VERIFIED":
        return "MODEL_GATE_REJECTED", str(reason or "NO_DECLARED_REASON")
    blockers = set(rejection.get("collector_blockers") or [])
    if handoff is not None:
        blockers.update(handoff.get("blockers") or [])
    if "COLLECTOR_PDF_FIELD_MISMATCH" in blockers:
        return "SOURCE_CONFLICT", "PDF_FIELD_MISMATCH_IN_ORIGINAL_RUN"
    if "COLLECTOR_PDF_START_CLOCK_CONFLICT" in blockers:
        return "SOURCE_CONFLICT", "ORIGINAL_PDF_START_CLOCK_CONFLICT"
    if any(x in blockers for x in (
        "COLLECTOR_SQLITE_FIELD_MISMATCH",
        "COLLECTOR_LIVE_ROSTER_REVISION_CONFLICT",
        "COLLECTOR_RETAINED_ROSTER_REVISION_CONFLICT",
        "COLLECTOR_ATG_ATG_ACTIVE_SET_MISMATCH",
    )):
        return "SOURCE_CONFLICT", "ACTIVE_FIELD_OR_ROSTER_REVISION_CONFLICT"
    if any(x in blockers for x in (
        "COLLECTOR_ATG_ATG_FULL_FIELD_GATE_NOT_PASSED",
        "COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE",
    )):
        return "MODEL_GATE_REJECTED", "ATG_FULL_FIELD_OR_FUNDAMENTALS_INCOMPLETE"
    if any("IDENTITY" in x or "TMP_" in x for x in blockers):
        return "IDENTITY_NOT_VERIFIED", "INDEPENDENT_REGISTRATION_OR_ATG_IDENTITY_MISSING"
    return "UNRESOLVED", "COLLECTOR_REASON_NOT_EXPLAINED_BY_ORIGINAL"


def explain(scorecard: dict, supplied: list[dict]) -> dict:
    """Never infer no-source from a partial archive sample."""
    records = scorecard.get("records")
    counts = scorecard.get("counts")
    if (scorecard.get("schema") != SCORECARD
            or scorecard.get("model_originals_verified_by_sha") is not True
            or scorecard.get("bet_authority") is not False
            or not isinstance(records, list) or not isinstance(counts, dict)):
        raise ValueError("SCORECARD_ORIGINAL_CONTRACT_INVALID")
    ids = [r.get("race_id") if isinstance(r, dict) else None for r in records]
    if (any(not isinstance(rid, str) or not RACE.fullmatch(rid) for rid in ids)
            or len(ids) != len(set(ids))
            or len(ids) != counts.get("physical_races")):
        raise ValueError("SCORECARD_ORIGINAL_RACE_DENOMINATOR_CONFLICT")
    missing = {
        r["race_id"]: r for r in records
        if r.get("status") == "NOT_EVALUABLE"
        and (r.get("reasons") or [None])[0] == "NO_VERIFIED_FROZEN_MODEL"
    }
    by_race: dict[str, list[dict]] = {rid: [] for rid in missing}
    seen_origins: set[tuple[int, int]] = set()
    if not isinstance(supplied, list):
        raise TypeError("ORIGINAL_COHORT_SOURCES_NOT_LIST")
    for spec in supplied:
        if not isinstance(spec, dict):
            raise TypeError("ORIGINAL_SOURCE_SPEC_INVALID")
        run_id, artifact_id = spec.get("run_id"), spec.get("artifact_id")
        if (type(run_id) is not int or run_id <= 0
                or type(artifact_id) is not int or artifact_id <= 0
                or (run_id, artifact_id) in seen_origins):
            raise ValueError("ORIGINAL_RUN_ARTIFACT_ID_INVALID_OR_DUPLICATE")
        seen_origins.add((run_id, artifact_id))
        index = _original(Path(spec["path"]), spec.get("sha256"))
        members, processed, rejected = _members(index)
        handoffs = index.get("collector_handoff")
        if not isinstance(handoffs, list):
            raise ValueError("ORIGINAL_COLLECTOR_HANDOFF_INVALID")
        handoff: dict[str, dict] = {}
        for item in handoffs:
            if not isinstance(item, dict) or not isinstance(item.get("race_id"), str):
                raise ValueError("ORIGINAL_HANDOFF_ENTRY_INVALID")
            rid = item["race_id"]
            if rid in handoff or rid not in members:
                raise ValueError("ORIGINAL_HANDOFF_RACE_CONFLICT")
            handoff[rid] = item
        for rid in members:
            if rid not in missing:
                continue
            p, n = processed.get(rid), rejected.get(rid)
            category, reason = _blocker(n, handoff.get(rid), p)
            by_race[rid].append({
                "source_run_id": run_id,
                "source_artifact_id": artifact_id,
                "cohort_index_sha256": spec["sha256"],
                "source_report_sha256": index.get("source_report_sha256"),
                "original_as_of_utc": _clock(index["as_of_utc"]).isoformat(),
                "original_index_written_at_utc": index.get("index_written_at_utc"),
                "model_was_processed": p is not None,
                "processed_model_status": p.get("model_status") if p else None,
                "original_not_processed_reason": n.get("reason") if n else None,
                "original_collector_blockers": sorted(set(
                    (n.get("collector_blockers") or []) if n else []
                ) | set((handoff.get(rid) or {}).get("blockers") or [])),
                "category": category,
                "specific_reason": reason,
            })
    rows = []
    for rid in sorted(missing):
        versions = sorted(by_race[rid], key=lambda x: (
            x["original_as_of_utc"], x["source_run_id"],
            x["cohort_index_sha256"],
        ))
        chosen = versions[-1] if versions else None
        rows.append({
            "race_id": rid,
            "scorecard_original_model_sha256": missing[rid].get(
                "source_model_original_sha256"
            ),
            "historical_original_cohort_observed": bool(versions),
            "observations_in_supplied_origins": len(versions),
            "chosen_latest_observation": chosen,
            "category": chosen["category"] if chosen else "UNRESOLVED",
            "specific_reason": (
                chosen["specific_reason"] if chosen
                else "NO_COHORT_ORIGINAL_SUPPLIED_NOT_PROOF_OF_NO_CAPTURE"
            ),
            "all_supplied_originals": versions,
            "model_recomputed": False,
            "retrospective_pit_certified": False,
        })
    categories = Counter(x["category"] for x in rows)
    return {
        "schema": RESEARCH_SCHEMA,
        "source_scope": "EXACT_SUPPLIED_SHA_PINNED_ARCHIVES_NOT_COMPLETE_INVENTORY",
        "physical_races_in_cumulative_scorecard": len(records),
        "original_scorecard_model_pairs": counts.get("paired_champion_core004"),
        "original_scorecard_win_triples": counts.get("triple_evaluable"),
        "original_no_freeze_target_count": len(missing),
        "target_races_found_in_supplied_cohort_originals": sum(
            r["historical_original_cohort_observed"] for r in rows
        ),
        "target_races_without_supplied_original": sum(
            not r["historical_original_cohort_observed"] for r in rows
        ),
        "counts_by_category": dict(sorted(categories.items())),
        "races": rows,
        "frozen_models_reconstructed_or_promoted": 0,
        "pit_certification_performed": False,
        "bet_authority": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--scorecard-sha256", required=True)
    parser.add_argument("--original-cohorts-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.original_cohorts_manifest.is_symlink():
        raise ValueError("COHORT_SPEC_SYMLINK_NOT_ADMITTED")
    manifest = json.loads(args.original_cohorts_manifest.read_bytes())
    if not isinstance(manifest, dict) or manifest.get("schema") != (
        "MVP018_SHA_PINNED_COHORT_INPUTS_V1"
    ):
        raise ValueError("COHORT_SPEC_CONTRACT_INVALID")
    output = explain(
        _original(args.scorecard, args.scorecard_sha256),
        manifest.get("archives"),
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "index.json").write_text(
        json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
