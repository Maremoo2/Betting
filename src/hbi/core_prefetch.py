"""CORE-003: source-first *research* acquisition queue for all known upcoming races.

This module does not modify Champion, bet rules or the production Watcher. It can
call existing RikstotoCollector methods when explicitly invoked by a caller.
Inventory is authoritative only for the current scheduling pass; roster timestamps
are not proven by a mutable archived `runners` table.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .race_core_review import _cohort, _rows, _utc
from .source_identity import is_generic_horse_identity

SCHEMA = 'CORE_003_PREFETCH_V1'
REQUIRED_HISTORY_RATIO = 0.8
RESEARCH_MARKET_PRIORITY = {'NO': 0, 'SE': 0, 'DK': 1, 'FR': 2}


@dataclass(frozen=True)
class PrefetchTask:
    race_id: str
    track: str
    race_no: int
    provider_raceday_key: str
    race_start_utc: str
    cutoff_at_utc: str
    minutes_to_start: float
    action: str
    reason: str
    phase: str
    urgency: int
    roster_count: int
    verified_history_count: int
    market_count: int
    issued_at_utc: str


def _scratch_state(value: Any) -> int | None:
    """Only explicit 0/1 source states count; NULL is never an active runner."""
    return value if type(value) is int and value in (0, 1) else None


def _roster_states(roster: list[dict[str, Any]]) -> dict[str, int] | None:
    if any(is_generic_horse_identity(r.get('horse_name')) for r in roster):
        return None
    ids = [str(r['selection_id']) for r in roster]
    if (len(ids) < 2 or len(ids) != len(set(ids))
            or any(not key or key == 'None' for key in ids)):
        return None
    states = {str(r['selection_id']): _scratch_state(r['scratched']) for r in roster}
    return states if all(state is not None for state in states.values()) else None


def _verified_fundamentals(fund: list[dict[str, Any]], roster: list[dict[str, Any]]) -> tuple[bool, int]:
    states = _roster_states(roster)
    if states is None:
        return False, 0
    fids = [str(r['selection_id']) for r in fund]
    if len(fids) != len(set(fids)) or set(fids) != set(states):
        return False, 0
    if any(_scratch_state(r['scratched']) != states[str(r['selection_id'])] for r in fund):
        return False, 0
    active = [r for r in fund if states[str(r['selection_id'])] == 0]
    verified = sum(
        r.get('full_field_history_complete') == 1
        and type(r.get('history_total_starts')) is int
        and type(r.get('history_total_wins')) is int
        and 0 <= r['history_total_wins'] <= r['history_total_starts']
        and isinstance(r.get('source_uri'), str) and bool(r['source_uri'].strip())
        for r in active
    )
    # Research-only source freshness, never immutable roster/PIT certification.
    return len(active) >= 2 and verified == len(active), verified


def _market_complete(market: list[dict[str, Any]], roster: list[dict[str, Any]]) -> bool:
    states = _roster_states(roster)
    if states is None:
        return False
    mids = [str(r['selection_key']) for r in market]
    if not mids or len(mids) != len(set(mids)) or set(mids) != set(states):
        return False
    for row in market:
        if states[str(row['selection_key'])] != 0:
            continue  # Scratched runners have no required WIN quote.
        try:
            odds = float(row['odds_decimal'])
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(odds) or odds <= 1:
            return False
    return True


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
    eligible_rows = []
    invalid_observation_clock = False
    for row in rows:
        try:
            observed = _utc(str(row["observed_at_utc"])).astimezone(UTC)
        except (TypeError, ValueError, AttributeError):
            # A malformed clock cannot prove a source was available before
            # cutoff. Do not choose a convenient later revision instead.
            invalid_observation_clock = True
            continue
        if observed <= cutoff:
            eligible_rows.append((observed, row))
    if not eligible_rows and not invalid_observation_clock:
        return None
    # SQL's TEXT ordering of timestamps is not chronological for different
    # offset spellings. Normalize to aware UTC instants before comparing.
    if eligible_rows:
        latest = max(observed for observed, _ in eligible_rows)
        newest = [row for observed, row in eligible_rows if observed == latest]
        eligible = min(newest, key=lambda row: str(row["payload_json"]))
    else:
        eligible = None
    payloads_at_time = {}
    for observed, row in eligible_rows:
        payloads_at_time.setdefault(observed, set()).add(
            str(row["payload_json"])
        )
    # A collision at ANY previously observed instant cannot be resolved by
    # choosing a revised later source, even when the latest row is unique.
    source_cohort_ambiguous = any(
        len(bodies) > 1 for bodies in payloads_at_time.values()
    )
    try:
        evidence = json.loads(str(eligible["payload_json"])) if eligible is not None else {}
    except (ValueError, TypeError):
        evidence = {}
        source_cohort_ambiguous = True
    if not isinstance(evidence, dict):
        evidence = {}
        source_cohort_ambiguous = True
    # Earliest archived source-stated off-time is a conservative bound, never
    # a certification of the actual off-time or source publication instant.
    source_clocks = []
    invalid_clock = False
    for _, archived in eligible_rows:
        try:
            payload = json.loads(str(archived['payload_json']))
            candidate = payload.get('race_start_utc')
            if candidate is None:
                continue
            source_clocks.append(_utc(str(candidate)).astimezone(UTC))
        except (ValueError, TypeError, AttributeError):
            invalid_clock = True
    source_runners = evidence.get("runners", [])
    runner_list_invalid = not isinstance(source_runners, list)
    runner_issues = []
    for runner in source_runners if isinstance(source_runners, list) else []:
        if not isinstance(runner, dict):
            runner_list_invalid = True
            continue
        if runner.get('reason') or runner.get('schema_ok') is False:
            runner_issues.append({
                'selection_id': str(runner.get('selection_id')),
                'horse_name': runner.get('horse_name'),
                'reason': runner.get('reason') or 'UNVERIFIED_RUNNER_SCHEMA',
            })
    declared_reasons = evidence.get("reasons", [])
    declared_reasons_valid = (
        isinstance(declared_reasons, list)
        and all(isinstance(reason, str) for reason in declared_reasons)
    )
    matched = evidence.get("matched_complete_runners")
    active = evidence.get("active_runners")
    totals_invalid = (
        type(matched) is not int or type(active) is not int
        or active < 2 or matched < 0 or matched > active
    )
    totals_conflict = (
        type(matched) is int and type(active) is int and matched != active
    )
    full_field_reasons = (
        (["ATG_FULL_FIELD_GATE_NOT_PASSED"] if evidence.get("passed") is not True else [])
        + (["ATG_FULL_FIELD_RUNNER_TOTALS_INVALID"] if totals_invalid else [])
        + (["ATG_FULL_FIELD_RUNNER_COUNT_CONFLICT"] if totals_conflict else [])
        + (["ATG_FULL_FIELD_RUNNER_SCHEMA_REJECTED"] if runner_issues else [])
        + (["ATG_FULL_FIELD_RUNNER_LIST_INVALID"] if runner_list_invalid else [])
        + (["ATG_FULL_FIELD_PROVIDER_REASONS_PRESENT"]
           if declared_reasons_valid and declared_reasons else [])
        + (["ATG_FULL_FIELD_PROVIDER_REASONS_INVALID"]
           if not declared_reasons_valid else [])
    )
    return {
        'observed_at_utc': eligible['observed_at_utc'] if eligible is not None else None,
        'full_field_gate_passed': (
            not full_field_reasons
            and not source_cohort_ambiguous
            and not invalid_observation_clock
            and not invalid_clock
        ),
        'full_field_rejection_reasons': full_field_reasons,
        'source_cohort_ambiguous': source_cohort_ambiguous,
        'invalid_observation_clock': invalid_observation_clock,
        'matched_complete_runners': evidence.get('matched_complete_runners'),
        'active_runners': evidence.get('active_runners'),
        'source_reasons': (
            (declared_reasons if declared_reasons_valid else [])
            + full_field_reasons
            + (['CONFLICTING_SAME_INSTANT_ATG_FULL_FIELD_SOURCES']
               if source_cohort_ambiguous else [])
            + (['ATG_SOURCE_OBSERVATION_CLOCK_INVALID']
               if invalid_observation_clock else [])
        ),
        'source_race_start_utc': evidence.get('race_start_utc'),
        'earliest_retained_source_start_utc': (
            min(source_clocks).isoformat() if source_clocks else None
        ),
        'source_clock_invalid': invalid_clock,
        'source_published_at_utc': evidence.get('source_published_at_utc'),
        'runner_issues': runner_issues,
    }


def _prefetch_source_clock(conn, race_id, canonical_start, now, *, lead_minutes=4.0):
    """Use only the retained CORE-003 source clocks available by canonical T−4."""
    diagnostic = _atg_history_source_diagnostic(
        conn, race_id=race_id, cutoff=min(now, canonical_start - timedelta(minutes=4)),
    )
    earliest = diagnostic.get("earliest_retained_source_start_utc") if diagnostic else None
    source_start = _utc(earliest).astimezone(UTC) if earliest else canonical_start
    cutoff = min(canonical_start, source_start) - timedelta(minutes=lead_minutes)
    return cutoff, diagnostic


def _source_observation_as_of(value: str | None, cutoff: datetime) -> bool:
    """Never treat a malformed or UTC-future selected cohort as available."""
    if not isinstance(value, str):
        return False
    try:
        return _utc(value).astimezone(UTC) <= cutoff
    except (TypeError, ValueError, OverflowError):
        return False


def plan_prefetch(conn: sqlite3.Connection, *, now: str, horizon_minutes: float = 90.0,
                  lead_minutes: float = 4.0, market_window_minutes: float = 12.0,
                  max_tasks: int | None = None, nordic_first: bool = False) -> dict[str, Any]:
    """Create work for missing fundamental/market data for *future* trot races.

    Only snapshots observed <= now are considered. No provider call and no DB writes.
    Includes actionable reason and source ref; never claims a later snapshot was PIT.
    """
    current = _utc(now).astimezone(UTC)
    if not 4 <= horizon_minutes <= 1440 or not math.isfinite(horizon_minutes):
        raise ValueError('horizon_minutes must be 4..1440')
    if not 1 <= lead_minutes <= 60 or not math.isfinite(lead_minutes):
        raise ValueError('lead_minutes must be 1..60')
    if not lead_minutes < market_window_minutes <= horizon_minutes or not math.isfinite(market_window_minutes):
        raise ValueError('market_window_minutes must be > lead_minutes and <= horizon_minutes')
    if max_tasks is not None and (type(max_tasks) is not int or max_tasks < 1):
        raise ValueError('max_tasks must be positive integer')
    country_column = ", r.country" if nordic_first else ""
    refs = _rows(conn, f"""select r.race_id,r.track,r.race_no,r.start_time_utc,r.discipline,
                               p.provider_raceday_key,p.provider,p.race_number {country_column}
                        from races r join provider_race_refs p on r.race_id=p.race_id
                        where p.provider='rikstoto' order by r.start_time_utc,r.race_id""")
    candidates = []
    reasons: dict[str, int] = {}
    for row in refs:
        if str(row['discipline']).lower() != 'trot' or '/' in str(row['track']):
            continue
        start = _utc(str(row['start_time_utc'])).astimezone(UTC)
        minutes = (start - current).total_seconds() / 60
        if minutes <= lead_minutes or minutes > horizon_minutes:
            continue
        candidates.append((row, minutes))
    tasks: list[PrefetchTask] = []
    eligible_races = set()
    source_priority = {}
    # Avoid probable product duplicates in a single future discovery batch.
    # Same track/number within ten minutes is only a research heuristic.
    selected: list[tuple[dict[str, Any], float]] = []
    for r, minutes in sorted(candidates, key=lambda x: (x[1], str(x[0]['race_id']))):
        if any(r['track'] == existing['track'] and r['race_no'] == existing['race_no']
               and abs(minutes - before) <= 10 for existing, before in selected):
            continue
        selected.append((r, minutes))

    clock_exclusions = []
    for r, minutes in selected:
        race_id = str(r['race_id'])
        start = _utc(str(r['start_time_utc'])).astimezone(UTC)
        cutoff, diagnostic = _prefetch_source_clock(
            conn, race_id, start, current, lead_minutes=lead_minutes,
        )
        if diagnostic and any(diagnostic[k] for k in (
            "source_clock_invalid", "invalid_observation_clock", "source_cohort_ambiguous",
        )):
            reason = "SOURCE_START_CLOCK_CONFLICT"
        elif current >= cutoff:
            reason = "TOO_LATE_TO_PREFETCH"
        else:
            reason = None
        if reason:
            clock_exclusions.append({
                "race_id": race_id, "race_start_utc": start.isoformat(),
                "cutoff_at_utc": cutoff.isoformat(), "reason": reason,
            })
            continue
        eligible_races.add(race_id)
        minutes = (cutoff + timedelta(minutes=lead_minutes) - current).total_seconds() / 60
        roster = _rows(conn, 'select selection_id,scratched,horse_name from runners where race_id=?', (race_id,))
        fund, fundamental_at = _cohort(conn, 'runner_fundamental_snapshots', race_id, current.isoformat())
        market, market_at = _cohort(conn, 'provider_market_snapshots', race_id, current.isoformat(), product='V')
        roster_ready = _roster_states(roster) is not None
        complete_fund, verified = _verified_fundamentals(fund, roster)
        complete_market = _market_complete(market, roster)
        # _cohort's legacy SQLite text comparison can admit a timestamp
        # whose true UTC instant is AFTER current, or an invalid ISO clock.
        # Keep the collection queue fail-closed rather than crashing/stopping.
        fundamental_clocks_valid = (
            _source_observation_as_of(fundamental_at, current)
            and all(
                _source_observation_as_of(row.get("observed_at_utc"), current)
                and _source_observation_as_of(row.get("feature_as_of_utc"), current)
                for row in fund
            )
        )
        market_clocks_valid = (
            _source_observation_as_of(market_at, current)
            and all(
                _source_observation_as_of(row.get("observed_at_utc"), current)
                and (row.get("provider_updated_at_utc") is None
                     or _source_observation_as_of(
                         row["provider_updated_at_utc"], current
                     ))
                for row in market
            )
        )
        if not fundamental_clocks_valid:
            complete_fund = False
            verified = 0
        if not market_clocks_valid:
            complete_market = False
        if nordic_first:
            source_priority[race_id] = (
                RESEARCH_MARKET_PRIORITY.get(str(r['country']).upper(), 3),
                not roster_ready,
                not complete_fund,
            )
        if not roster:
            why = 'MISSING_STARTLIST'
        elif any(is_generic_horse_identity(row.get('horse_name')) for row in roster):
            why = 'UNRESOLVED_PLACEHOLDER_ROSTER_IDENTITY'
        elif _roster_states(roster) is None:
            why = 'UNVERIFIED_ROSTER_SCRATCH_OR_ID'
        elif not fund:
            why = 'MISSING_HORSE_HISTORY'
        elif not complete_fund:
            why = 'INCOMPLETE_FULL_FIELD_HISTORY'
        elif minutes <= 8 and fundamental_at and (current-_utc(fundamental_at).astimezone(UTC)).total_seconds()>3*60:
            why = 'REFRESH_VERIFIED_FUNDAMENTALS_NEAR_START'
        else:
            why = ''
        phase = 'EARLY' if minutes > market_window_minutes else 'NEAR_START'
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            tasks.append(PrefetchTask(race_id,str(r['track']),int(r['race_no']),
                str(r['provider_raceday_key']),start.isoformat(),cutoff.isoformat(),round(minutes,3),
                'COLLECT_FUNDAMENTALS',why,phase,0 if minutes <= 12 else 1,
                len(roster),verified,len(market),current.isoformat()))
        market_stale = (complete_market and market_at is not None and minutes <= 8 and
                        (current-_utc(market_at).astimezone(UTC)).total_seconds()>2*60)
        if minutes <= market_window_minutes and (not complete_market or market_stale):
            market_reason = ('REFRESH_WIN_MARKET_NEAR_START' if market_stale else
                             'MISSING_OR_INCOMPLETE_WIN_MARKET')
            reasons[market_reason] = reasons.get(market_reason,0)+1
            tasks.append(PrefetchTask(race_id,str(r['track']),int(r['race_no']),
                str(r['provider_raceday_key']),start.isoformat(),cutoff.isoformat(),round(minutes,3),
                'COLLECT_WIN_MARKET',market_reason,phase,0,
                len(roster),verified,len(market),current.isoformat()))
    # For near-start races collect missing fundamentals ahead of price capture.
    tasks.sort(key=lambda t: (
        source_priority[t.race_id][0] if nordic_first else 0,
        t.urgency,
        source_priority[t.race_id][1:] if nordic_first else (),
        t.minutes_to_start,
        0 if t.action == 'COLLECT_FUNDAMENTALS' else 1,
        t.race_id,
    ))
    chosen = tasks if max_tasks is None else tasks[:max_tasks]
    return {'schema_version':SCHEMA,'authority':'SHADOW_RESEARCH_ONLY',
            'as_of_utc':current.isoformat(),'horizon_minutes':horizon_minutes,
            'lead_minutes':lead_minutes,'market_window_minutes':market_window_minutes,
            'races_considered':len(eligible_races),'tasks_available':len(tasks),
            'tasks_returned':len(chosen),'truncated':len(chosen)<len(tasks),
            'reason_counts':dict(sorted(reasons.items())),
            'clock_exclusions':clock_exclusions,
            'tasks':[asdict(t) for t in chosen],
            'deferred_tasks':[asdict(t) for t in tasks[len(chosen):]]}


def execute_prefetch(plan: dict[str, Any], collector: Any, *, now: datetime,
                     clock: Callable[[], datetime] | None = None) -> list[dict[str, Any]]:
    """Invoke existing collector entrypoints; NO model or betting decisions.

    The caller owns the store and is responsible for a single process. Execution
    reports what the provider returned, not proof of full-field readiness.
    """
    _utc(now.isoformat())  # Validate aware timestamp
    clock = clock or (lambda: datetime.now(UTC))
    events = []
    if plan.get('schema_version') != SCHEMA or plan.get('authority') != 'SHADOW_RESEARCH_ONLY':
        raise ValueError('wrong or untrusted prefetch plan')
    for task in plan['tasks']:
        stamp = _utc(str(task['race_start_utc'])).astimezone(UTC)
        canonical_cutoff = stamp - timedelta(minutes=float(plan['lead_minutes']))
        cutoff = min(_utc(task.get('cutoff_at_utc', canonical_cutoff.isoformat())), canonical_cutoff)
        actual = _utc(clock().isoformat()).astimezone(UTC)
        details = {'race_id': task['race_id'], 'action': task['action'],
                   'cutoff_at_utc': cutoff.isoformat(), 'checked_at_utc': actual.isoformat()}
        if actual >= cutoff:
            events.append({**details, 'status': 'TOO_LATE_TO_PREFETCH'})
            continue
        if task['action']=='COLLECT_FUNDAMENTALS':
            try:
                inserted, fetched, uri = collector.collect_fundamentals(
                    raceday_key=task['provider_raceday_key'], race_number=task['race_no'],
                    race_id=task['race_id'], observed_at=actual)
                status='FETCHED_NOT_PROVEN_COMPLETE' if fetched else 'SOURCE_UNAVAILABLE'
                events.append({**details,
                               'status':status,'rows_inserted':inserted,'source_uri':uri})
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                events.append({**details,
                               'status':'PROVIDER_EXCEPTION','exception_type':type(exc).__name__})
        elif task['action']=='COLLECT_WIN_MARKET':
            try:
                inserted, failures = collector.collect_market(
                    raceday_key=task['provider_raceday_key'], race_number=task['race_no'],
                    race_id=task['race_id'],observed_at=actual,products={'V'}, record_response_time=True)
                events.append({**details,
                               'status':'FETCHED_NOT_PROVEN_COMPLETE' if failures==0 else 'SOURCE_UNAVAILABLE',
                               'rows_inserted':inserted,'fetch_failures':failures})
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                events.append({**details,
                               'status':'PROVIDER_EXCEPTION','exception_type':type(exc).__name__})
        else:
            raise ValueError('unexpected action')
        finished = _utc(clock().isoformat()).astimezone(UTC)
        events[-1]["finished_at_utc"] = finished.isoformat()
        if finished >= cutoff and events[-1]["status"] == "FETCHED_NOT_PROVEN_COMPLETE":
            events[-1]["status"] = "COLLECTION_FINISHED_AT_OR_AFTER_CUTOFF"
    return events


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description='CORE-003 research prefetch queue (read-only plan)')
    p.add_argument('--db',required=True)
    p.add_argument('--now',required=True,help='ISO timestamp with UTC offset')
    p.add_argument('--out',required=True)
    p.add_argument('--horizon-minutes',type=float,default=90)
    p.add_argument('--market-window-minutes',type=float,default=12)
    p.add_argument('--max-tasks',type=int)
    args=p.parse_args(argv)
    db=Path(args.db).resolve()
    if not db.is_file():p.error('Missing database')
    conn=sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    try:
        report=plan_prefetch(conn,now=args.now,horizon_minutes=args.horizon_minutes,
                            market_window_minutes=args.market_window_minutes,max_tasks=args.max_tasks)
    finally:conn.close()
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'races':report['races_considered'],'tasks':report['tasks_returned'],
                      'plan':str(output)},ensure_ascii=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
