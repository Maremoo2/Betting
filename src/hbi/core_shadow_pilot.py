"""CORE-003 isolated, source-only prospective Shadow pilot.

Produces comparable readiness snapshots for the same upcoming races before and
after provider fetches. Does not call a probability model or place a wager.
Its SQLite database must be separate from the production hbi-state artifact.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .core_prefetch import (
    _market_complete,
    _verified_fundamentals,
    execute_prefetch,
    plan_prefetch,
)
from .race_core_review import _cohort, _rows, _utc

SCHEMA = "CORE_003_SHADOW_PILOT_V1"


def _pilot_race_ids(conn: sqlite3.Connection, *, now: datetime, horizon: float) -> list[str]:
    """Stable, explicitly known eligible race cohort, without invented starters."""
    candidates = _rows(conn, """
        SELECT r.race_id, r.track, r.race_no, r.start_time_utc
        FROM races r
        JOIN provider_race_refs p ON p.race_id = r.race_id
        WHERE p.provider = 'rikstoto' AND lower(r.discipline) = 'trot'
        ORDER BY r.start_time_utc, r.race_id
    """)
    selected: list[tuple[dict[str, Any], float]] = []
    for row in candidates:
        if "/" in str(row["track"]):
            continue
        minutes = (_utc(str(row["start_time_utc"])) - now).total_seconds() / 60
        if minutes <= 4 or minutes > horizon:
            continue
        if any(
            row["track"] == other["track"]
            and row["race_no"] == other["race_no"]
            and abs(minutes - earlier) <= 10
            for other, earlier in selected
        ):
            continue
        selected.append((row, minutes))
    return [str(row["race_id"]) for row, _ in selected]



def _atg_history_source_diagnostic(
    conn: sqlite3.Connection, *, race_id: str, cutoff: datetime,
) -> dict[str, Any] | None:
    """Latest observed ATG full-field evidence, with explicit runner blockers.

    Read-only optional diagnostic: source evidence is not guaranteed to exist in
    synthetic fixtures or historical databases. Never infer validity from a
    mutable roster or from an ATG payload recorded after the decision cutoff.
    """
    has_payloads = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_payloads'"
    ).fetchone()
    if has_payloads is None:
        return None
    rows = _rows(conn, """
        SELECT p.payload_json, p.observed_at_utc
        FROM provider_payloads p
        WHERE p.provider='atg' AND p.category='FULL_FIELD_ONLY_V1'
          AND p.race_number = (SELECT race_no FROM races WHERE race_id = ?)
          AND (p.provider_raceday_key = ? OR p.provider_raceday_key IN (
              SELECT provider_raceday_key FROM provider_race_refs WHERE race_id = ?
          ))
        ORDER BY p.observed_at_utc DESC
    """, (race_id, race_id, race_id))
    eligible_rows = [
        row for row in rows if _utc(str(row['observed_at_utc'])) <= cutoff
    ]
    eligible = eligible_rows[0] if eligible_rows else None
    if eligible is None:
        return None
    try:
        evidence = json.loads(str(eligible['payload_json']))
    except (ValueError, TypeError):
        return None
    if not isinstance(evidence, dict):
        return None
    # Earliest archived source-stated off-time is a conservative bound, never
    # a certification of the actual off-time or source publication instant.
    source_clocks = []
    invalid_clock = False
    for archived in eligible_rows:
        try:
            payload = json.loads(str(archived['payload_json']))
            candidate = payload.get('race_start_utc')
            if candidate is None:
                continue
            source_clocks.append(_utc(str(candidate)).astimezone(UTC))
        except (ValueError, TypeError, AttributeError):
            invalid_clock = True
    runner_issues = []
    for runner in evidence.get('runners', []):
        if not isinstance(runner, dict):
            continue
        if runner.get('reason') or runner.get('schema_ok') is False:
            runner_issues.append({
                'selection_id': str(runner.get('selection_id')),
                'horse_name': runner.get('horse_name'),
                'reason': runner.get('reason') or 'UNVERIFIED_RUNNER_SCHEMA',
            })
    return {
        'observed_at_utc': eligible['observed_at_utc'],
        'full_field_gate_passed': bool(evidence.get('passed')),
        'matched_complete_runners': evidence.get('matched_complete_runners'),
        'active_runners': evidence.get('active_runners'),
        'source_reasons': evidence.get('reasons', []),
        'source_race_start_utc': evidence.get('race_start_utc'),
        'earliest_retained_source_start_utc': (
            min(source_clocks).isoformat() if source_clocks else None
        ),
        'source_clock_invalid': invalid_clock,
        'source_published_at_utc': evidence.get('source_published_at_utc'),
        'runner_issues': runner_issues,
    }


def _readiness(conn: sqlite3.Connection, race_id: str, as_of: datetime) -> dict[str, Any]:
    """Source-evidence diagnostic, NOT an executable model or PIT roster proof."""
    info = _rows(conn, "SELECT start_time_utc FROM races WHERE race_id = ?", (race_id,))
    if len(info) != 1:
        raise ValueError("Race missing from source inventory")
    start = _utc(str(info[0]["start_time_utc"])).astimezone(UTC)
    canonical_t4 = start - timedelta(minutes=4)
    canonical_cutoff = min(as_of.astimezone(UTC), canonical_t4)
    source_diagnostic = _atg_history_source_diagnostic(
        conn, race_id=race_id, cutoff=canonical_cutoff,
    )
    earliest = (
        source_diagnostic.get("earliest_retained_source_start_utc")
        if source_diagnostic else None
    )
    source_start = _utc(earliest).astimezone(UTC) if earliest else None
    effective_start = min(start, source_start) if source_start else start
    conservative_t4 = effective_start - timedelta(minutes=4)
    cutoff = min(as_of.astimezone(UTC), conservative_t4)
    rows = _rows(conn, "SELECT selection_id, scratched FROM runners WHERE race_id = ?", (race_id,))
    fundamentals, fundamental_at = _cohort(
        conn, "runner_fundamental_snapshots", race_id, cutoff.isoformat()
    )
    market, market_at = _cohort(
        conn, "provider_market_snapshots", race_id, cutoff.isoformat(), product="V"
    )
    full_history, verified_active = _verified_fundamentals(fundamentals, rows)
    market_complete = _market_complete(market, rows) if rows else False
    if source_diagnostic and source_diagnostic["source_clock_invalid"]:
        full_history = False
        market_complete = False
    return {
        "race_id": race_id,
        "canonical_t4_cutoff_utc": canonical_t4.isoformat(),
        "t4_cutoff_utc": conservative_t4.isoformat(),
        "canonical_start_utc": start.isoformat(),
        "earliest_retained_source_start_utc": (
            source_start.isoformat() if source_start else None
        ),
        "start_clock_disagreement_seconds": (
            abs((start - source_start).total_seconds()) if source_start else None
        ),
        "source_clock_conservative_guard_applied": (
            source_start is not None and source_start < start
        ),
        "evidence_as_of_utc": cutoff.isoformat(),
        "roster_rows": len(rows),
        "active_runners_known": sum(not bool(row["scratched"]) for row in rows),
        "verified_active_history": verified_active,
        "fundamental_cohort_at_utc": fundamental_at,
        "win_market_cohort_at_utc": market_at,
        "history_complete_as_of_t4": full_history,
        "win_market_complete_as_of_t4": market_complete,
        "all_inputs_complete_as_of_t4": full_history and market_complete,
        "atg_history_source_diagnostic": source_diagnostic,
    }


def _aggregate(readiness: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "races_checked": len(readiness),
        "races_with_roster": sum(r["roster_rows"] > 0 for r in readiness),
        "active_runners_known": sum(r["active_runners_known"] for r in readiness),
        "active_horses_with_verified_history": sum(r["verified_active_history"] for r in readiness),
        "races_full_history": sum(r["history_complete_as_of_t4"] for r in readiness),
        "races_full_win_market": sum(r["win_market_complete_as_of_t4"] for r in readiness),
        "races_full_sources": sum(r["all_inputs_complete_as_of_t4"] for r in readiness),
        "races_with_earlier_source_clock": sum(
            r["source_clock_conservative_guard_applied"] for r in readiness
        ),
    }


def run_pilot(
    *, store: Any, collector: Any, now: datetime, clock: Callable[[], datetime],
    horizon_minutes: float = 90.0, max_tasks: int = 4,
    market_window_minutes: float = 30.0, discover: bool = True,
    execute: bool = False,
) -> dict[str, Any]:
    """One bounded measurement tick; identical race universe before and after."""
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not 4 <= horizon_minutes <= 1440:
        raise ValueError("horizon_minutes must be 4..1440")
    if type(max_tasks) is not int or not 1 <= max_tasks <= 12:
        raise ValueError("max_tasks must be integer 1..12")
    started = now.astimezone(UTC)
    discovered = collector.discover(now) if discover and execute else []
    with store.connect() as conn:
        plan = plan_prefetch(
            conn, now=started.isoformat(), horizon_minutes=horizon_minutes,
            max_tasks=max_tasks, market_window_minutes=market_window_minutes,
        )
        race_ids = _pilot_race_ids(conn, now=started, horizon=horizon_minutes)
        before = [_readiness(conn, race_id, started) for race_id in race_ids]
    events = execute_prefetch(plan, collector, now=started, clock=clock) if execute else []
    finished = clock().astimezone(UTC) if execute else started
    with store.connect() as conn:
        after = [_readiness(conn, race_id, finished) for race_id in race_ids]
    a, b = _aggregate(before), _aggregate(after)
    differences = {key: b[key] - a[key] for key in a}
    return {
        "schema_version": SCHEMA,
        "authority": "SHADOW_RESEARCH_ONLY_NO_MODEL_NO_BET",
        "mode": "FETCH_SOURCES" if execute else "PREVIEW_NO_PROVIDER_CALLS",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "discovered_races": len(discovered),
        "races_in_fixed_cohort": race_ids,
        "tasks_available": plan["tasks_available"],
        "tasks_selected": plan["tasks_returned"],
        "tasks_attempted": len(events),
        "task_reason_counts": plan["reason_counts"],
        "provider_event_statuses": dict(sorted(Counter(e["status"] for e in events).items())),
        "provider_events": events,
        "before": a,
        "after": b,
        "delta": differences,
        "race_readiness_before": before,
        "race_readiness_after": after,
        "roster_pit_verified": False,
        "prospective_t4_success_proven": False,
        "bet_count": 0,
        "model_invocations": 0,
        "caveat": (
            "Evidence timestamps are capped at T-4; the mutable runners roster "
            "has no historical timestamp proof. These counts measure source "
            "readiness in an isolated Shadow database, not validated betting eligibility."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated CORE-003 source-readiness pilot")
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--horizon-minutes", type=float, default=90.0)
    parser.add_argument("--max-tasks", type=int, default=4)
    parser.add_argument("--market-window-minutes", type=float, default=30.0)
    parser.add_argument("--execute", action="store_true", help="Fetch real source data, no bets")
    args = parser.parse_args(argv)
    path = Path(args.db)
    if not path.is_file():
        parser.error("Pilot SQLite database missing; initialize isolated DB first")
    from .storage import SQLiteStore

    store = SQLiteStore(path)
    collector = None
    if args.execute:
        from .rikstoto_collector import RikstotoCollector

        collector = RikstotoCollector(store)
    result = run_pilot(
        store=store, collector=collector, now=datetime.now(UTC),
        clock=lambda: datetime.now(UTC), horizon_minutes=args.horizon_minutes,
        max_tasks=args.max_tasks, market_window_minutes=args.market_window_minutes,
        execute=args.execute,
    )
    if args.execute:
        store.checkpoint()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "mode": result["mode"], "races": result["before"]["races_checked"],
        "source_deltas": result["delta"], "bet_count": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
