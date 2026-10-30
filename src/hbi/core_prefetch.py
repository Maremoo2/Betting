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

SCHEMA = 'CORE_003_PREFETCH_V1'
REQUIRED_HISTORY_RATIO = 0.8


@dataclass(frozen=True)
class PrefetchTask:
    race_id: str
    track: str
    race_no: int
    provider_raceday_key: str
    race_start_utc: str
    minutes_to_start: float
    action: str
    reason: str
    phase: str
    urgency: int
    roster_count: int
    verified_history_count: int
    market_count: int
    issued_at_utc: str


def _verified_fundamentals(fund: list[dict[str, Any]], roster: list[dict[str, Any]]) -> tuple[bool, int]:
    ids = {str(r['selection_id']) for r in roster}
    fids = {str(r['selection_id']) for r in fund}
    if not ids or len(fids) != len(fund) or ids != fids:
        return False, 0
    verified = sum(bool(r.get('full_field_history_complete'))
                   and r.get('history_total_starts') is not None
                   and r.get('history_total_wins') is not None
                   and r.get('source_uri')
                   and not bool(r.get('scratched')) for r in fund)
    active = sum(not bool(r.get('scratched')) for r in fund)
    # Existing Champion's full-field gate requires all active history *verified*.
    return active >= 2 and verified == active, verified


def _market_complete(market: list[dict[str, Any]], roster: list[dict[str, Any]]) -> bool:
    mids = [str(r['selection_key']) for r in market]
    if not mids or len(mids) != len(set(mids)):
        return False
    if set(mids) != {str(r['selection_id']) for r in roster}:
        return False
    for row in market:
        if str(row['selection_key']) not in {str(r['selection_id']) for r in roster if not r['scratched']}:
            continue
        try:
            odds = float(row['odds_decimal'])
        except (TypeError, ValueError):
            return False
        if not math.isfinite(odds) or odds <= 1:
            return False
    return True


def plan_prefetch(conn: sqlite3.Connection, *, now: str, horizon_minutes: float = 90.0,
                  lead_minutes: float = 4.0, market_window_minutes: float = 12.0,
                  max_tasks: int | None = None) -> dict[str, Any]:
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
    refs = _rows(conn, """select r.race_id,r.track,r.race_no,r.start_time_utc,r.discipline,
                               p.provider_raceday_key,p.provider,p.race_number
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
    # Avoid probable product duplicates in a single future discovery batch.
    # Same track/number within ten minutes is only a research heuristic.
    selected: list[tuple[dict[str, Any], float]] = []
    for r, minutes in sorted(candidates, key=lambda x: (x[1], str(x[0]['race_id']))):
        if any(r['track'] == existing['track'] and r['race_no'] == existing['race_no']
               and abs(minutes - before) <= 10 for existing, before in selected):
            continue
        selected.append((r, minutes))

    for r, minutes in selected:
        race_id = str(r['race_id'])
        eligible_races.add(race_id)
        roster = _rows(conn, 'select selection_id,scratched from runners where race_id=?', (race_id,))
        fund, fundamental_at = _cohort(conn, 'runner_fundamental_snapshots', race_id, current.isoformat())
        market, market_at = _cohort(conn, 'provider_market_snapshots', race_id, current.isoformat(), product='V')
        complete_fund, verified = _verified_fundamentals(fund, roster)
        complete_market = _market_complete(market, roster)
        if not roster:
            why = 'MISSING_STARTLIST'
        elif not fund:
            why = 'MISSING_HORSE_HISTORY'
        elif not complete_fund:
            why = 'INCOMPLETE_FULL_FIELD_HISTORY'
        elif minutes <= 8 and fundamental_at and (current-_utc(fundamental_at)).total_seconds()>3*60:
            why = 'REFRESH_VERIFIED_FUNDAMENTALS_NEAR_START'
        else:
            why = ''
        phase = 'EARLY' if minutes > market_window_minutes else 'NEAR_START'
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            tasks.append(PrefetchTask(race_id,str(r['track']),int(r['race_no']),
                str(r['provider_raceday_key']),start.isoformat(),round(minutes,3),
                'COLLECT_FUNDAMENTALS',why,phase,0 if minutes <= 12 else 1,
                len(roster),verified,len(market),current.isoformat()))
        market_stale = (complete_market and market_at is not None and minutes <= 8 and
                        (current-_utc(market_at)).total_seconds()>2*60)
        if minutes <= market_window_minutes and (not complete_market or market_stale):
            market_reason = ('REFRESH_WIN_MARKET_NEAR_START' if market_stale else
                             'MISSING_OR_INCOMPLETE_WIN_MARKET')
            reasons[market_reason] = reasons.get(market_reason,0)+1
            tasks.append(PrefetchTask(race_id,str(r['track']),int(r['race_no']),
                str(r['provider_raceday_key']),start.isoformat(),round(minutes,3),
                'COLLECT_WIN_MARKET',market_reason,phase,0,
                len(roster),verified,len(market),current.isoformat()))
    # For near-start races collect missing fundamentals ahead of price capture.
    tasks.sort(key=lambda t:(t.urgency,t.minutes_to_start,
                            0 if t.action=='COLLECT_FUNDAMENTALS' else 1,t.race_id))
    chosen = tasks if max_tasks is None else tasks[:max_tasks]
    return {'schema_version':SCHEMA,'authority':'SHADOW_RESEARCH_ONLY',
            'as_of_utc':current.isoformat(),'horizon_minutes':horizon_minutes,
            'lead_minutes':lead_minutes,'market_window_minutes':market_window_minutes,
            'races_considered':len(eligible_races),'tasks_available':len(tasks),
            'tasks_returned':len(chosen),'truncated':len(chosen)<len(tasks),
            'reason_counts':dict(sorted(reasons.items())),
            'tasks':[asdict(t) for t in chosen]}


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
        actual = _utc(clock().isoformat()).astimezone(UTC)
        if actual >= stamp - timedelta(minutes=float(plan['lead_minutes'])):
            events.append({'race_id':task['race_id'],'action':task['action'],'status':'TOO_LATE_TO_PREFETCH'})
            continue
        if task['action']=='COLLECT_FUNDAMENTALS':
            try:
                inserted, fetched, uri = collector.collect_fundamentals(
                    raceday_key=task['provider_raceday_key'], race_number=task['race_no'],
                    race_id=task['race_id'], observed_at=actual)
                status='FETCHED_NOT_PROVEN_COMPLETE' if fetched else 'SOURCE_UNAVAILABLE'
                events.append({'race_id':task['race_id'],'action':task['action'],
                               'status':status,'rows_inserted':inserted,'source_uri':uri})
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                events.append({'race_id':task['race_id'],'action':task['action'],
                               'status':'PROVIDER_EXCEPTION','exception_type':type(exc).__name__})
        elif task['action']=='COLLECT_WIN_MARKET':
            try:
                inserted, failures = collector.collect_market(
                    raceday_key=task['provider_raceday_key'], race_number=task['race_no'],
                    race_id=task['race_id'],observed_at=actual,products={'V'})
                events.append({'race_id':task['race_id'],'action':task['action'],
                               'status':'FETCHED_NOT_PROVEN_COMPLETE' if failures==0 else 'SOURCE_UNAVAILABLE',
                               'rows_inserted':inserted,'fetch_failures':failures})
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                events.append({'race_id':task['race_id'],'action':task['action'],
                               'status':'PROVIDER_EXCEPTION','exception_type':type(exc).__name__})
        else:
            raise ValueError('unexpected action')
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
