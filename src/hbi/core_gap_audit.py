"""CORE-003 archival source-availability audit, no after-cutoff backfill.

Answers whether provider payloads were actually observed before the recorded T-4
cutoff. The audit does not try to change a historical p(win) or produce bets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from .day_core_review import analyze_day
from .race_core_review import _rows


def _payload_times(db: sqlite3.Connection, *, race_id: str, raceday_key: str,
                   race_no: int, category: str) -> list[str]:
    if category == 'RACEDAY_STARTS':
        rows=_rows(db,"""select observed_at_utc from provider_payloads
                          where category=? and provider='rikstoto'
                          and provider_raceday_key=? and race_number=?
                          order by observed_at_utc""", (category,raceday_key,race_no))
    elif category == 'FULL_FIELD_ONLY_V1':
        rows=_rows(db,"""select observed_at_utc from provider_payloads
                          where category=? and provider='atg'
                          and provider_raceday_key=? and race_number=?
                          order by observed_at_utc""", (category,race_id,race_no))
    else:
        raise ValueError('Unsupported raw source category')
    return [str(x['observed_at_utc']) for x in rows]


def _source_observation(timestamps: list[str], cutoff: str) -> dict[str, Any]:
    pre=[t for t in timestamps if datetime.fromisoformat(t.replace('Z','+00:00')) <=
          datetime.fromisoformat(cutoff.replace('Z','+00:00'))]
    return {'events_total':len(timestamps), 'events_pre_cutoff':len(pre),
            'latest_pre_cutoff_utc':pre[-1] if pre else None,
            'first_after_cutoff_utc':next((t for t in timestamps if t not in pre),None),
            'status':'BEFORE_CUTOFF' if pre else ('ONLY_AFTER_CUTOFF' if timestamps else 'NO_ARCHIVED_PAYLOAD')}


def audit_day_sources(db: sqlite3.Connection, *,race_date: str,cutoff_minutes: float=4.,
                      track: str | None=None) -> dict[str,Any]:
    day=analyze_day(db,race_date=race_date,track=track,cutoff_minutes=cutoff_minutes)
    availability=[];counts=Counter()
    for r in day['races']:
        if str(r['stage']).startswith('SKIPPED'):
            continue
        ref=_rows(db,"""select provider_raceday_key from provider_race_refs
                           where provider='rikstoto' and race_id=? limit 1""",(r['race_id'],))
        key=str(ref[0]['provider_raceday_key']) if ref else None
        raw={}
        for category in ('RACEDAY_STARTS','FULL_FIELD_ONLY_V1'):
            raw[category]=_source_observation(
                _payload_times(db,race_id=r['race_id'],raceday_key=key,
                               race_no=int(r['race_no']),category=category) if key else [],
                str(r['decision_at_utc']))
        diagnosis=[]
        if r['stage']=='BLOCKED':
            if raw['RACEDAY_STARTS']['status']=='NO_ARCHIVED_PAYLOAD':
                diagnosis.append('NO_ARCHIVED_STARTS_ATTEMPT')
            elif raw['RACEDAY_STARTS']['status']=='ONLY_AFTER_CUTOFF':
                diagnosis.append('STARTS_CAPTURED_TOO_LATE')
            elif r['roster_runners']==0:
                diagnosis.append('EARLY_STARTS_PAYLOAD_NO_CANONICAL_ROSTER')
            if raw['FULL_FIELD_ONLY_V1']['status']=='NO_ARCHIVED_PAYLOAD':
                diagnosis.append('NO_ARCHIVED_HISTORY_ATTEMPT')
            elif raw['FULL_FIELD_ONLY_V1']['status']=='ONLY_AFTER_CUTOFF':
                diagnosis.append('HISTORY_CAPTURED_TOO_LATE')
            elif 'LOW_HISTORY_COVERAGE' in r['blocks'] or 'FULL_FIELD_HISTORY_NOT_VERIFIED' in r['blocks']:
                diagnosis.append('HISTORY_PRESENT_BUT_NOT_VERIFIED')
            if not diagnosis:
                diagnosis.append('OTHER_MODEL_OR_MARKET_BLOCK')
            counts.update(diagnosis)
        availability.append({'race_id':r['race_id'],'track':r['track'],'race_no':r['race_no'],
                             'stage':r['stage'],'cutoff_utc':r['decision_at_utc'],
                             'roster_runners_archived':r['roster_runners'],
                             'blocks':r['blocks'],'raw_sources':raw,'diagnosis':diagnosis})
    return {'schema_version':'CORE_003_SOURCE_AUDIT_V1','authority':'ARCHIVAL_RESEARCH_ONLY',
            'race_date':race_date,'cutoff_minutes':cutoff_minutes,
            'baseline_summary':day['summary'],
            'blocker_diagnoses':dict(sorted(counts.items())),
            'race_sources':availability,
            'caveats':[
                'Archive contains only retained provider payloads, not proof no upstream data existed.',
                'A provider response observed after T-4 cannot be used to backfill T-4 predictions.',
                'Mutable runner lists and recorded start times may have been updated after cutoff.',
                'A raw response observed before T-4 may still lack full-field identity or history validation.',
                'No provider fetched and no production changes made.']}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='CORE-003 sources behind CORE-002 gaps')
    p.add_argument('--db',required=True);p.add_argument('--date',required=True)
    p.add_argument('--track');p.add_argument('--cutoff-minutes',type=float,default=4.)
    p.add_argument('--out',required=True)
    args=p.parse_args(argv)
    path=Path(args.db).resolve()
    if not path.is_file():p.error('Missing DB')
    db=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:report=audit_day_sources(db,race_date=args.date,cutoff_minutes=args.cutoff_minutes,track=args.track)
    finally:db.close()
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'blocked':report['baseline_summary']['blocked_races'],
                      'diagnoses':report['blocker_diagnoses'],'out':str(out)},ensure_ascii=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
