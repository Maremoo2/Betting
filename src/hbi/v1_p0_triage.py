"""Read-only V1 P0 triage: immutable original replay and unsettled paper tickets.

This is NOT a second settlement engine and does not change the existing
replay/settlement FAIL, edit source facts or authorize any betting activity.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from .legacy_provenance import classify_legacy_replay

SCHEMA = "HBI_V1_P0_READ_ONLY_TRIAGE_V1"


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    return result.astimezone(UTC) if result.utcoffset() is not None else None


def _selection(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        items = json.loads(value)
    except (ValueError, TypeError):
        return None
    return str(items[0]) if (
        isinstance(items, list) and len(items) == 1
        and type(items[0]) in (int, str)
        and str(items[0])
    ) else None


def inspect_unsettled_outcomes(
    database: Path,
    *,
    now: datetime,
    grace_hours: float = 24.0,
) -> dict[str, object]:
    """Inspect ONLY the stored metadata behind the V1 settlement integrity fail.

    An outcomes row is not original official complete-results or published
    winner-dividend evidence. Do not infer an amount or a loss/refund from it.
    """
    if now.utcoffset() is None or not math.isfinite(grace_hours) or grace_hours < 0:
        raise ValueError("Require timezone-aware now and nonnegative finite grace")
    uri = "file:" + quote(str(database.resolve(strict=True))) + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT t.ticket_id, t.race_id, t.status, t.product, "
            "t.selections_json, t.provider_raceday_key, t.stake_nok, "
            "r.race_no, r.start_time_utc, "
            "o.winner_selection_id, o.settled_at_utc AS outcome_recorded_at_utc "
            "FROM shadow_tickets t "
            "LEFT JOIN races r ON r.race_id=t.race_id "
            "JOIN outcomes o ON o.race_id=t.race_id "
            "WHERE t.status NOT IN ('SETTLED','NOT_EXECUTABLE') "
            "ORDER BY t.ticket_id"
        ).fetchall()
    unresolved = []
    not_yet_due = 0
    malformed_time = 0
    for row in rows:
        started = _utc_time(row["start_time_utc"])
        if started is None:
            malformed_time += 1
            due = True  # Missing original clock cannot become success.
        else:
            due = started + timedelta(hours=grace_hours) <= now.astimezone(UTC)
        if not due:
            not_yet_due += 1
            continue
        selection = _selection(row["selections_json"])
        unresolved.append({
            "ticket_id": row["ticket_id"],
            "race_id": row["race_id"],
            "product": row["product"],
            "ticket_status": row["status"],
            "provider_raceday_key": row["provider_raceday_key"],
            "race_number": row["race_no"],
            "race_start_utc": row["start_time_utc"],
            "outcome_recorded_at_utc": row["outcome_recorded_at_utc"],
            "selected_runner": selection,
            "winner_from_stored_outcome": row["winner_selection_id"],
            "stored_winner_matches_selection": (
                selection == str(row["winner_selection_id"])
                if selection is not None and row["product"] == "V" else None
            ),
            "original_complete_result_attested_by_this_report": False,
            "original_dividend_attested_by_this_report": False,
            "settlement_or_refund_authorized": False,
            "cause": "UNRESOLVED_REQUIRES_ORIGINAL_OFFICIAL_FINISH_AND_DIVIDEND_REVIEW",
            "scope": (
                "Stored outcome proves only a winner was recorded; original "
                "finish, scratch/disqualification status and dividend remain "
                "to be independently checked before any settlement."
            ),
        })
    return {
        "status": "UNRESOLVED_OFFICIAL_SOURCE_SETTLEMENT_P0" if unresolved else "NO_OVERDUE_TICKET_IN_STORED_OUTCOME_SUBSET",
        "overdue_unsettled_with_stored_outcome": len(unresolved),
        "not_yet_due_with_stored_outcome": not_yet_due,
        "malformed_original_race_clock": malformed_time,
        "tickets": unresolved,
        "stored_outcome_is_payout_evidence": False,
        "money_movement_performed": False,
    }


def build_triage(
    database: Path,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Audit a finished, checkpointed source DB without modifying a single byte."""
    database = database.resolve(strict=True)
    if not database.is_file():
        raise ValueError("Original HBI state must be a local SQLite file")
    before = _hash_file(database)
    legacy = classify_legacy_replay(database)
    settlement = inspect_unsettled_outcomes(
        database, now=now or datetime.now(UTC),
    )
    after = _hash_file(database)
    if before != after or legacy["source_database_sha256"] != before:
        raise RuntimeError("Original HBI state changed during forensic read")
    counts = Counter(
        item["classification"] for item in legacy["exceptions"]
    )
    if sum(counts.values()) != len(legacy["exceptions"]):
        raise ValueError("Legacy exceptions denominator mismatch")
    return {
        "schema": SCHEMA,
        "status": "DIAGNOSTIC_ONLY_P0_NOT_CLEARED",
        "source_database_sha256": before,
        "source_database_unchanged": True,
        "replay": {
            "source_diagnostic_schema": legacy["schema_version"],
            "total_decisions": legacy["total_decisions"],
            "provenance_eligible_checked": legacy["provenance_eligible_checked"],
            "saved_provenance_replay_pass": legacy["saved_provenance_replay_pass"],
            "legacy_late_attachment_original_source_reconstructed": (
                legacy["legacy_source_reconstructed"]
            ),
            "historical_replay_unreconciled": legacy["unreconciled"],
            "incomplete_provenance_skipped": legacy["incomplete_provenance_skipped"],
            "exception_classification_counts": dict(counts),
            "exceptions": legacy["exceptions"],
            "original_v1_audit_overridden": False,
            "frozen_probabilities_or_policies_modified": False,
        },
        "settlement": settlement,
        "snapshot_rewritten": False,
        "v1_system_audit_failure_overridden": False,
        "prospective_pit_validated": False,
        "model_or_bet_authority": False,
        "next_actions": [
            "For each legacy mismatch: reconcile exact frozen provider odds and original decision timestamp, preserve immutable rows, and separately authorize any historical correction plan.",
            "For each overdue shadow ticket: inspect ORIGINAL official complete-results and final winner dividends, then apply existing conservative settlement engine only when proven.",
            "Re-run unchanged V1 system audit and independently review exact source evidence; do not treat this diagnostic as a PASS.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_triage(args.db)
    raw = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(raw)
    print(raw)


if __name__ == "__main__":
    main()
