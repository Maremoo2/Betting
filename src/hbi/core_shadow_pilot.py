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
    RESEARCH_MARKET_PRIORITY,
    _atg_history_source_diagnostic,
    _market_complete,
    _prefetch_source_clock,
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



def _selected_cohort_timestamp_problems(
    rows: list[dict[str, Any]], cutoff: datetime, *, market: bool,
) -> list[str]:
    """Prevent lexical SQLite ISO comparison from admitting future snapshots.

    This checks the rows actually selected by the legacy read-only research
    cohort query, without changing that helper or frozen Champion formulas.
    Missing source clock evidence never becomes a PIT certification.
    """
    prefix = "WIN_MARKET" if market else "FUNDAMENTAL"
    fields = (
        ("observed_at_utc", "provider_updated_at_utc")
        if market else ("observed_at_utc", "feature_as_of_utc")
    )
    problems: set[str] = set()
    for row in rows:
        for field in fields:
            value = row.get(field)
            if market and field == "provider_updated_at_utc" and value is None:
                continue
            try:
                if not isinstance(value, str):
                    raise TypeError("Source clock must be ISO text")
                observed = _utc(value).astimezone(UTC)
                if observed > cutoff:
                    problems.add(f"{prefix}_{field.upper()}_AFTER_CUTOFF")
            except (TypeError, ValueError, OverflowError):
                problems.add(f"{prefix}_{field.upper()}_INVALID")
    return sorted(problems)


def _readiness(conn: sqlite3.Connection, race_id: str, as_of: datetime) -> dict[str, Any]:
    """Source-evidence diagnostic, NOT an executable model or PIT roster proof."""
    info = _rows(conn, "SELECT start_time_utc FROM races WHERE race_id = ?", (race_id,))
    if len(info) != 1:
        raise ValueError("Race missing from source inventory")
    start = _utc(str(info[0]["start_time_utc"])).astimezone(UTC)
    canonical_t4 = start - timedelta(minutes=4)
    conservative_t4, source_diagnostic = _prefetch_source_clock(
        conn, race_id, start, as_of.astimezone(UTC),
    )
    earliest = source_diagnostic.get("earliest_retained_source_start_utc") if source_diagnostic else None
    source_start = _utc(earliest).astimezone(UTC) if earliest else None
    cutoff = min(as_of.astimezone(UTC), conservative_t4)
    # At the strict T−4 boundary, a snapshot is already too late.
    snapshot_cutoff = min(cutoff, conservative_t4 - timedelta(microseconds=1))
    rows = _rows(conn, "SELECT selection_id, scratched FROM runners WHERE race_id = ?", (race_id,))
    fundamentals, fundamental_at = _cohort(
        conn, "runner_fundamental_snapshots", race_id, snapshot_cutoff.isoformat()
    )
    market, market_at = _cohort(
        conn, "provider_market_snapshots", race_id, snapshot_cutoff.isoformat(), product="V"
    )
    full_history, verified_active = _verified_fundamentals(fundamentals, rows)
    market_complete = _market_complete(market, rows) if rows else False
    selected_timestamp_problems = (
        _selected_cohort_timestamp_problems(fundamentals, snapshot_cutoff, market=False)
        + _selected_cohort_timestamp_problems(market, snapshot_cutoff, market=True)
    )
    if selected_timestamp_problems:
        # The underlying read-only _cohort uses lexical SQLite filtering;
        # this research-only veto must never miscount UTC-future inputs.
        full_history = False
        market_complete = False
    if source_diagnostic and not source_diagnostic["full_field_gate_passed"]:
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
        "selected_snapshot_timestamp_problems": selected_timestamp_problems,
        "selected_source_clock_guard_passed": not selected_timestamp_problems,
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


def plan_t4_source_receipts(
    conn: sqlite3.Connection, *, now: datetime,
    horizon_minutes: float = 8.0, max_races: int = 2,
) -> dict[str, Any]:
    """Race-relative source receipts; NOT a change to prefetch/model admission.

    All candidates and capacity exclusions are retained. The caller must fetch
    original bytes and verify source identity; no mutable roster is trusted.
    """
    if now.utcoffset() is None or not 1 <= horizon_minutes <= 15 or max_races < 1:
        raise ValueError("INVALID_T4_PLAN_ARGUMENTS")
    now_utc = now.astimezone(UTC)
    candidates = _rows(conn, """
        SELECT r.race_id, r.track, r.country, r.race_no, r.start_time_utc,
               r.discipline, p.provider_raceday_key, p.discovered_at_utc
        FROM races r JOIN provider_race_refs p ON p.race_id=r.race_id
        WHERE p.provider='rikstoto' AND lower(r.discipline)='trot'
        ORDER BY r.start_time_utc, r.race_id
    """)
    by_race: dict[str, list[dict[str, Any]]] = {}
    for record in candidates:
        by_race.setdefault(str(record["race_id"]), []).append(record)
    selected = []
    excluded = []
    for race_id, matches in by_race.items():
        row = matches[0]
        try:
            start = _utc(str(row["start_time_utc"])).astimezone(UTC)
        except (ValueError, TypeError):
            excluded.append({"race_id": race_id, "reason": "UNVERIFIED_START_CLOCK"})
            continue
        minutes = (start - timedelta(minutes=4) - now_utc).total_seconds() / 60
        if minutes < -2 or minutes > horizon_minutes:
            continue
        refs = {str(m["provider_raceday_key"]) for m in matches}
        if len(refs) != 1 or not next(iter(refs)):
            excluded.append({"race_id": race_id, "reason": "AMBIGUOUS_RACE_REFERENCE"})
            continue
        if not any(
            (stamp := _safe_aware(m.get("discovered_at_utc"))) is not None
            and stamp <= now_utc for m in matches
        ):
            excluded.append({"race_id": race_id, "reason": "RACE_NOT_DISCOVERED_AS_OF"})
            continue
        diagnostic = _atg_history_source_diagnostic(
            conn, race_id=race_id, cutoff=min(now_utc, start - timedelta(minutes=4))
        )
        if diagnostic and (
            diagnostic.get("source_clock_invalid")
            or diagnostic.get("invalid_observation_clock")
            or diagnostic.get("source_cohort_ambiguous")
        ):
            excluded.append({"race_id": race_id, "reason": "SOURCE_START_CLOCK_CONFLICT"})
            continue
        earliest = diagnostic.get("earliest_retained_source_start_utc") if diagnostic else None
        source_start = _safe_aware(earliest) if earliest else None
        effective_start = min(start, source_start) if source_start else start
        t4 = effective_start - timedelta(minutes=4)
        delta = (t4 - now_utc).total_seconds()
        if delta < 0:
            status = "MISSED_T4"
        else:
            status = "DUE"
        selected.append({
            "race_id": race_id, "raceday_key": next(iter(refs)),
            "race_number": row["race_no"], "country": row["country"],
            "canonical_start_utc": start.isoformat(),
            "earliest_source_start_utc": source_start.isoformat() if source_start else None,
            "effective_t4_utc": t4.isoformat(), "seconds_to_t4": delta,
            "status": status,
        })
    selected.sort(key=lambda item: (
        RESEARCH_MARKET_PRIORITY.get(str(item["country"]).upper(), 3),
        item["effective_t4_utc"], item["race_id"],
    ))
    eligible = [r for r in selected if r["status"] == "DUE"]
    for item in selected:
        if item["status"] == "MISSED_T4":
            excluded.append({"race_id": item["race_id"], "reason": "MISSED_T4"})
    for item in eligible[max_races:]:
        excluded.append({"race_id": item["race_id"], "reason": "NOT_PROCESSED_CAPACITY"})
    return {
        "schema": "CORE003_T4_SOURCE_PLAN_V1",
        "planned_at_utc": now_utc.isoformat(),
        "eligible": eligible[:max_races],
        "excluded": excluded,
        "bet_authority": False,
    }


def _safe_aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return _utc(value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


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
            max_tasks=max_tasks, market_window_minutes=market_window_minutes, nordic_first=True,
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
        "queue_selected": plan["tasks"],
        "queue_deferred_capacity": plan["deferred_tasks"],
        "queue_clock_exclusions": plan["clock_exclusions"],
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
