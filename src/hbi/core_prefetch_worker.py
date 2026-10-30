"""CORE-003 opt-in acquisition tick using EXISTING RikstotoCollector.

This worker fetches research inputs only. It neither invokes Champion nor the
shadow decision engine and it is not installed into any production workflow.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from .core_prefetch import execute_prefetch, plan_prefetch


def run_tick(*, store: Any, collector: Any, now: datetime, clock: Callable[[], datetime],
             horizon_minutes: float = 90., max_tasks: int = 12,
             discover: bool = True) -> dict:
    """Discover -> fetch missing prestart fields -> report latest source readiness.

    Collector is injected for deterministic offline tests. Returned results never
    claim a model prediction, a placed bet, or successful upstream completeness.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must carry timezone')
    observed_discoveries = collector.discover(now) if discover else []
    with store.connect() as conn:
        before = plan_prefetch(conn, now=now.isoformat(),horizon_minutes=horizon_minutes,
                               max_tasks=max_tasks)
    events = execute_prefetch(before, collector, now=now, clock=clock)
    after_time = clock().astimezone(UTC)
    with store.connect() as conn:
        after=plan_prefetch(conn,now=after_time.isoformat(),horizon_minutes=horizon_minutes,
                            max_tasks=max_tasks)
    return {'schema_version':'CORE_003_TICK_V1','authority':'SHADOW_RESEARCH_ONLY',
            'logical_start_utc':now.astimezone(UTC).isoformat(),
            'verified_at_utc':after_time.isoformat(),
            'discovered':len(observed_discoveries),
            'races_considered':before['races_considered'],
            'tasks_prepared':before['tasks_available'],
            'tasks_attempted':len(events),
            'provider_events':events,
            'tasks_still_needed':after['tasks_available'],
            'plan_before':before,'plan_after':after,
            'model_invocations':0,'real_bet_count':0}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='CORE-003 research source collector, manual opt-in')
    p.add_argument('--db',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--horizon-minutes',type=float,default=90.)
    p.add_argument('--max-tasks',type=int,default=12)
    p.add_argument('--execute',action='store_true',help='Actually contact configured providers and update the chosen DB')
    args=p.parse_args(argv)
    db=Path(args.db).resolve()
    if not db.exists():p.error('database does not exist')
    if args.max_tasks<1:p.error('max-tasks must be >=1')
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    if args.execute:
        from .storage import SQLiteStore
        from .rikstoto_collector import RikstotoCollector
        store=SQLiteStore(str(db));collector=RikstotoCollector(store)
        result=run_tick(store=store,collector=collector,now=datetime.now(UTC),
                        clock=lambda:datetime.now(UTC),horizon_minutes=args.horizon_minutes,
                        max_tasks=args.max_tasks)
    else:
        import sqlite3
        conn=sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True)
        conn.row_factory=sqlite3.Row
        try:
            plan=plan_prefetch(conn,now=datetime.now(UTC).isoformat(),
                               horizon_minutes=args.horizon_minutes,max_tasks=args.max_tasks)
        finally:conn.close()
        result={'schema_version':'CORE_003_DRY_RUN_V1','plan':plan,
                'provider_calls':0,'real_bet_count':0}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'mode':'EXECUTE_PROVIDER_INPUTS' if args.execute else 'DRY_RUN',
                      'path':str(output),'bet_count':0},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
