"""CORE-003: recover documented *market-free* current-year signals from raw snapshots.

A read-only sidecar: does not modify Champion, database, calibration, or BET logic.
Never fills year-wins/records if ATG does not provide them. Only the exact
pre-cutoff, full-field-verified snapshot cohort can supply derived features.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .day_core_review import analyze_day
from .race_core_review import _cohort


def extract_year_features(row: dict[str,Any], decision_at: str) -> dict[str,Any] | None:
    """Conservatively recover year starts/earnings from snapshotted JSON only."""
    if not bool(row.get('full_field_history_complete')):
        return None
    raw=row.get('raw_json')
    if not raw or not isinstance(raw,str):
        return None
    try:
        data=json.loads(raw)
        atg=data.get('atg_market_free')
        if not isinstance(atg,dict):return None
        years=atg.get('yearCrosscheck')
        if not isinstance(years,dict):return None
        year=str(datetime.fromisoformat(decision_at).year)
        record=years.get(year)
        if not isinstance(record,dict):return None
        starts=record.get('starts'); earnings=record.get('earnings')
        # Booleans are NOT valid counters; no casting estimates from strings.
        if type(starts) is not int or starts<0:return None
        if type(earnings) not in (int,float) or not 0<=earnings<1e20:return None
        lifetime=row.get('history_total_starts')
        if lifetime is not None and starts>int(lifetime):return None
    except (TypeError,ValueError,OverflowError,KeyError):
        return None
    return {'current_year_starts':starts,'current_year_earnings_source_units':float(earnings),
            'source':'ATG_YEAR_CROSSCHECK_IN_VERIFIED_PRE_CUTOFF_RAW_JSON',
            'source_snapshot_at_utc':row['observed_at_utc'],
            'decision_at_utc':decision_at,'derived_not_used_by_champion':True}


def build_feature_sidecar(conn:sqlite3.Connection,*,race_date:str,
                          cutoff_minutes:float=4.)->dict[str,Any]:
    day=analyze_day(conn,race_date=race_date,cutoff_minutes=cutoff_minutes)
    rows=[]; counts=Counter();active=0
    for race in day['races']:
        if str(race['stage']).startswith('SKIPPED'):continue
        cutoff=str(race['decision_at_utc'])
        cohort,_=_cohort(conn,'runner_fundamental_snapshots',str(race['race_id']),cutoff)
        for record in sorted(cohort,key=lambda x:(int(x['selection_id']) if str(x['selection_id']).isdigit() else 10**9,str(x['selection_id']))):
            if bool(record.get('scratched')):continue
            active+=1
            fields=extract_year_features(record,cutoff)
            if fields:
                counts['current_year_starts']+=1
                counts['current_year_earnings_source_units']+=1
                rows.append({'race_id':race['race_id'],
                            'selection_id':record['selection_id'],
                            'horse_name':record.get('horse_name'),**fields})
    return {'schema_version':'CORE_003_YEAR_FEATURE_SIDECAR_V1',
            'authority':'RESEARCH_ONLY_NO_MODEL_CHANGES',
            'race_date':race_date,'eligible_fundamental_cohort_active':active,
            'recovered_rows':len(rows),'recovered_feature_counts':dict(counts),
            'rows':rows,'limitations':[
                'Only starts and earnings are present in retained yearCrosscheck; wins and record_auto/volt remain unavailable.',
                'Earnings are preserved in source-native units; no currency conversion or NOK interpretation is justified.',
                'No correction to historical p(win), EV or CORE-002 T-4 coverage.',
                'Crosscheck is a snapshotted observed value, not independently proven source publication.',
                'Only full-field verified snapshots at or before archive cutoff are eligible.']}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='CORE-003 recover observed year starts/earnings (read-only)')
    p.add_argument('--db',required=True);p.add_argument('--date',required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args(argv)
    path=Path(args.db).resolve()
    if not path.is_file():p.error('Missing DB')
    c=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    try:r=build_feature_sidecar(c,race_date=args.date)
    finally:c.close()
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rows_recovered':r['recovered_rows'],'path':str(output)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
