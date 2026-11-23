"""PREWATCH-004: source-only, read-optimized full-race intelligence packs.

Uses the existing CLOUD-RUN-002 original-archive and official-field verifier.
This module NEVER scores Champion, calls a model/provider, freezes Phase A,
writes a production ledger, or grants model/PIT/BET authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .cloud_run002_import import SourceRace, prepare_source
from .collector_handoff import OriginalArchive, name_key

SCHEMA = "PREWATCH004_RACE_INTELLIGENCE_SOURCE_V1"
DRAFT_SCHEMA = "PREWATCH004_PHASE_A_DRAFT_V1"
UNKNOWN = "UNKNOWN"
SCORE_BOUNDS = {
    "data_25": 25, "shape_20": 20, "mispricing_30": 30,
    "liquidity_15": 15, "today_fit_10": 10,
}
FORBIDDEN = frozenset({
    "odds", "win_odds", "winodds", "v_percent", "collective_share",
    "market_probability", "expected_value", "bet_authorized", "stake_nok",
})


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_row(row: dict[str, Any]) -> dict[str, Any]:
    """A parsed PDF history line is NOT a verified result or negative event."""
    raw = row.get("raw_text")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("PREWATCH004_HISTORY_RAW_TEXT_MISSING")
    candidate_date = row.get("date")
    return {
        "raw_text": raw,
        "raw_sha256": digest(raw.encode("utf-8")),
        "date_candidate": (
            candidate_date if isinstance(candidate_date, str) and candidate_date
            else UNKNOWN
        ),
        "date_semantics": "SOURCE_EXTRACTED_UNVERIFIED",
        "result": UNKNOWN,
        "placing": UNKNOWN,
        "gallop": UNKNOWN,
        "disqualification": UNKNOWN,
        "official_result_verified": False,
        "model_feature_eligible": False,
    }


def _snapshot_diff(before: dict[str, Any] | None, after: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic source comparison only; not a live roster certification."""
    if before is None:
        return {"status": "NO_PRIOR_PACK", "changes": []}
    if before.get("schema") != SCHEMA or before.get("race_id") != after["race_id"]:
        raise ValueError("PREWATCH004_PREVIOUS_PACK_IDENTITY_CONFLICT")
    old_when = datetime.fromisoformat(before["source"]["observed_at_utc"])
    new_when = datetime.fromisoformat(after["source"]["observed_at_utc"])
    if old_when.utcoffset() is None or new_when.utcoffset() is None or old_when > new_when:
        raise ValueError("PREWATCH004_NONMONOTONIC_SOURCE_CLOCK")
    changes = []
    for field in ("start_time_utc", "distance_m", "start_method"):
        old_value = before["race"][field]
        new_value = after["race"][field]
        if old_value != new_value:
            changes.append({"field": field, "before": old_value, "after": new_value})
    old = {x["selection_id"]: x for x in before["runners"]}
    new = {x["selection_id"]: x for x in after["runners"]}
    for number in sorted(set(old) | set(new), key=int):
        for field in ("horse_name", "scratched", "post_position", "driver"):
            was = old.get(number, {}).get(field, "NOT_PRESENT")
            now = new.get(number, {}).get(field, "NOT_PRESENT")
            if was != now:
                changes.append({
                    "selection_id": number, "field": field,
                    "before": was, "after": now,
                })
    return {
        "status": "CHANGED" if changes else "UNCHANGED_AS_OF_CAPTURE",
        "previous_run_id": before["source"]["run_id"],
        "changes": changes,
    }


def build_race_pack(
    receipt: dict[str, Any], item: SourceRace, doc: dict[str, Any],
    *, previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Use ONLY canonical entrants admitted by the verified original importer."""
    race = item.card.race
    rid = str(race["race_id"])
    if (doc.get("race", {}).get("meeting_id") != item.meeting_id
            or doc["race"].get("race_number") != item.race_no
            or item.payload.get("race_id") != rid
            or item.payload.get("source_ready_snapshot") is not True):
        raise ValueError("PREWATCH004_RACE_IDENTITY_OR_SOURCE_INVALID")
    original = doc.get("entrants")
    if not isinstance(original, list):
        raise ValueError("PREWATCH004_PDF_RUNNERS_MISSING")
    by_number: dict[str, dict] = {}
    for entry in original:
        if not isinstance(entry, dict) or type(entry.get("program_number")) is not int:
            raise ValueError("PREWATCH004_PDF_SELECTION_INVALID")
        number = str(entry["program_number"])
        if number in by_number:
            raise ValueError("PREWATCH004_DUPLICATE_PDF_SELECTION")
        by_number[number] = entry

    rows = []
    for canonical in sorted(item.card.runners, key=lambda r: int(str(r["selection_id"]))):
        number = str(canonical["selection_id"])
        parsed = by_number.get(number)
        if parsed is None or name_key(parsed.get("name", "")) != name_key(canonical["horse_name"]):
            raise ValueError("PREWATCH004_FULL_FIELD_MISMATCH")
        history = parsed.get("past_starts")
        if not isinstance(history, list):
            raise ValueError("PREWATCH004_HISTORY_SHAPE_INVALID")
        source_rows = [_source_row(row) for row in history]
        rows.append({
            "selection_id": number,
            "horse_name": str(canonical["horse_name"]),
            "scratched": bool(canonical["scratched"]),
            "post_position": (
                canonical["post_position"]
                if type(canonical.get("post_position")) is int else UNKNOWN
            ),
            "driver": canonical.get("driver_or_jockey") or UNKNOWN,
            "trainer": UNKNOWN,
            "extra_distance_m": UNKNOWN,
            "source_history": source_rows,
            "conservative_form": {
                "source_history_rows": len(source_rows),
                "source_date_candidates": sum(
                    x["date_candidate"] != UNKNOWN for x in source_rows
                ),
                "officially_verified_result_rows": 0,
                "last_5_verified_form": UNKNOWN,
                "last_10_verified_form": UNKNOWN,
                "verified_gallop_rate": UNKNOWN,
                "verified_disqualification_rate": UNKNOWN,
                "class_adjusted_strength": UNKNOWN,
                "distance_start_method_strength": UNKNOWN,
            },
            "history_status": "RAW_PDF_LINES_NOT_SEMANTIC_GOLD",
        })
    if set(by_number) != {r["selection_id"] for r in rows}:
        raise ValueError("PREWATCH004_FULL_FIELD_MISMATCH")

    pack: dict[str, Any] = {
        "schema": SCHEMA,
        "record_type": "SOURCE_ONLY_DRAFT_INPUT",
        "race_id": rid,
        "date_oslo": race["race_date"],
        "race": {
            "track": race["track"],
            "country": race["country"],
            "race_number": item.race_no,
            "start_time_utc": race["start_time_utc"],
            "distance_m": race["distance_m"],
            "start_method": race.get("start_method") or UNKNOWN,
            "race_class": UNKNOWN,
        },
        "source": {
            "run_id": receipt["run_id"],
            "archive_sha256": item.payload["archive_sha256"],
            "manifest_sha256": item.payload["manifest_sha256"],
            "starts_original_sha256": item.payload["starts_original_sha256"],
            "program_pdf_original_sha256": item.payload["program_pdf_original_sha256"],
            "structured_program_sha256": item.payload["structured_program_sha256"],
            "observed_at_utc": item.received_at.isoformat(),
            "source_uri": item.source_uri,
            "status": "VERIFIED_AS_OF_SOURCE_CAPTURE",
            "day_denominator_independently_verified": False,
            "official_driver_changes_verified_by_this_stage": False,
        },
        "listed_count": len(rows),
        "active_count": sum(not r["scratched"] for r in rows),
        "scratched_numbers": [r["selection_id"] for r in rows if r["scratched"]],
        "runners": rows,
        "quality": {
            "full_official_pdf_field_match": True,
            "history_semantics_accepted": False,
            "permanent_horse_identity_attested": False,
            "missing_or_unverified": [
                "HISTORY_SEMANTIC_GOLD", "PERMANENT_HORSE_ID",
                "DRIVER_CHANGES_INDEPENDENT_CURRENT_CHECK",
                "TRAINER", "EQUIPMENT", "EXTRA_DISTANCE_VERIFIED",
                "FORM_AND_PACE_STATISTICS",
            ],
        },
        "phase_a_status": "NOT_RUN",
        "phase_b_status": "NOT_RUN",
        "model_ready": False,
        "pit_certified": False,
        "bet_authorized": False,
    }
    pack["snapshot_diff"] = _snapshot_diff(previous, pack)
    return pack


def validate_phase_a_draft(draft: dict[str, Any], pack: dict[str, Any]) -> None:
    """Validate an untrusted AI draft's structure without approving a freeze."""
    if (draft.get("schema") != DRAFT_SCHEMA
            or draft.get("status") != "DRAFT"
            or draft.get("race_id") != pack.get("race_id")
            or draft.get("source_run_id") != pack.get("source", {}).get("run_id")):
        raise ValueError("PREWATCH004_DRAFT_IDENTITY_OR_STATUS_INVALID")
    runners = draft.get("runners")
    if not isinstance(runners, list) or len(runners) != pack["active_count"]:
        raise ValueError("PREWATCH004_DRAFT_FULL_FIELD_MISSING")
    expected = {r["selection_id"] for r in pack["runners"] if not r["scratched"]}
    observed = [str(r.get("selection_id")) for r in runners if isinstance(r, dict)]
    if len(set(observed)) != len(observed) or set(observed) != expected:
        raise ValueError("PREWATCH004_DRAFT_RUNNER_ID_MISMATCH")
    for runner in runners:
        if any(
            not isinstance(runner.get(k), str) or not runner[k].strip()
            for k in ("assessment", "strengths", "weaknesses", "evidence")
        ):
            raise ValueError("PREWATCH004_DRAFT_EVIDENCE_MISSING")
    for key in ("race_shape", "candidate", "counterargument", "uncertainty"):
        if not isinstance(draft.get(key), str) or not draft[key].strip():
            raise ValueError("PREWATCH004_DRAFT_REASONING_MISSING")
    scores = draft.get("champion_provisional")
    if scores is not None:
        if not isinstance(scores, dict) or set(scores) != set(SCORE_BOUNDS):
            raise ValueError("PREWATCH004_DRAFT_SCORE_FIELDS_INVALID")
        for key, bound in SCORE_BOUNDS.items():
            value = scores[key]
            if type(value) is not int or not 0 <= value <= bound:
                raise ValueError("PREWATCH004_DRAFT_SCORE_BOUNDS_INVALID")
    if set(draft) & FORBIDDEN or draft.get("bet_authorized", False) is not False:
        raise ValueError("PREWATCH004_DRAFT_MARKET_OR_BET_FIELD_FORBIDDEN")


def _write_once(path: Path, raw: bytes) -> None:
    if path.is_symlink():
        raise ValueError("PREWATCH004_OUTPUT_SYMLINK")
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("PREWATCH004_IMMUTABLE_OUTPUT_CONFLICT")
        return
    with path.open("xb") as out:
        out.write(raw)
    if path.read_bytes() != raw:
        raise ValueError("PREWATCH004_READBACK_MISMATCH")


def make_day_packs(
    archive: Path, checksum: Path, dest: Path, *,
    date_oslo: str | None = None, previous_dir: Path | None = None,
) -> dict[str, Any]:
    """End-to-end original-backed offline output; no external network/Sheets."""
    receipt, races = prepare_source(archive, checksum, date_oslo=date_oslo)
    original = OriginalArchive(archive)
    index: dict[tuple[str, int], dict] = {}
    for meeting_id in {r.meeting_id for r in races}:
        path = f"{original.prefix}meetings/{meeting_id}/structured_program.json"
        raw = original.read(path)
        expected = {r.payload["structured_program_sha256"] for r in races if r.meeting_id == meeting_id}
        if expected != {digest(raw)}:
            raise ValueError("PREWATCH004_STRUCTURED_SOURCE_SHA_MISMATCH")
        docs = json.loads(raw)["races"]
        for doc in docs:
            key = (meeting_id, doc["race"]["race_number"])
            if key in index:
                raise ValueError("PREWATCH004_DUPLICATE_PHYSICAL_RACE")
            index[key] = doc
    assembled = []
    for item in races:
        filename = f"race_pack_{item.meeting_id}_{item.race_no}.json"
        previous = None
        if previous_dir is not None and (previous_dir / filename).exists():
            prior_path = previous_dir / filename
            if prior_path.is_symlink():
                raise ValueError("PREWATCH004_PRIOR_SYMLINK")
            previous = json.loads(prior_path.read_text(encoding="utf-8"))
        key = (item.meeting_id, item.race_no)
        if key not in index:
            raise ValueError("PREWATCH004_PHYSICAL_RACE_MISSING")
        pack = build_race_pack(receipt, item, index[key], previous=previous)
        raw = (json.dumps(pack, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        assembled.append((filename, raw, pack))
    dest.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        raise ValueError("PREWATCH004_OUTPUT_DIR_SYMLINK")
    report = {
        "schema": "PREWATCH004_SOURCE_COVERAGE_V1",
        "date_oslo": receipt["date_oslo"],
        "source_run_id": receipt["run_id"],
        "source_discovered_physical_races": len(assembled),
        "listed_runners": sum(p["listed_count"] for _, _, p in assembled),
        "active_runners": sum(p["active_count"] for _, _, p in assembled),
        "source_packs": [
            {"race_id": p["race_id"], "file": name, "sha256": digest(raw),
             "active_count": p["active_count"],
             "history_semantics_accepted": False}
            for name, raw, p in assembled
        ],
        "independent_whole_day_denominator_verified": False,
        "actual_phase_a_completed": 0,
        "bet_authorized": False,
    }
    for name, raw, _ in assembled:
        _write_once(dest / name, raw)
    _write_once(dest / "coverage.json", (json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="PREWATCH-004 original-backed source packs (NO BET)")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--checksum", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--date-oslo")
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    report = make_day_packs(args.archive, args.checksum, args.output,
                            date_oslo=args.date_oslo, previous_dir=args.previous)
    print(json.dumps({k: v for k, v in report.items() if k != "source_packs"}, sort_keys=True))


if __name__ == "__main__":
    main()
