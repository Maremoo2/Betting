"""Read-only descriptive sensitivity checks; not prospective model validation.

Reuses an EXISTING frozen-decision descriptive CSV. Never imports features,
trains weights, reclassifies legacy replay failures or issues betting decisions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from urllib.parse import quote

LEGACY_RACES = {
    'RIKSTOTO:S2_NR_2026-10-09:5',
    'RIKSTOTO:MO_NR_2026-10-17:10',
    'RIKSTOTO:S4_NR_2026-10-21:9',
    'RIKSTOTO:S2_NR_2026-10-22:5',
    'RIKSTOTO:S3_NR_2026-10-25:11',
}


def _summary(rows):
    if not rows:
        return {'n': 0, 'status': 'NO_EVIDENCE'}
    delta=[float(x['combined_logloss'])-float(x['market_logloss']) for x in rows]
    return {'n': len(rows),
            'mean_combined_minus_market_logloss': fmean(delta),
            'median_combined_minus_market_logloss': sorted(delta)[len(delta)//2],
            'market_better_race_fraction': sum(d>0 for d in delta)/len(delta),
            'mean_combined_minus_market_brier': fmean(
                float(x['combined_brier'])-float(x['market_brier']) for x in rows),
            'mean_fundamental_minus_market_logloss': fmean(
                float(x['fundamental_logloss'])-float(x['market_logloss']) for x in rows)}


def _day_cluster_interval(rows, *, samples=2400, seed=2112):
    days=defaultdict(list)
    for x in rows:days[x['race_day']].append(x)
    if len(days)<3: return None
    keys=sorted(days)
    rnd=random.Random(seed)
    boot=[]
    for _ in range(samples):
        selected=[row for day in rnd.choices(keys,k=len(keys)) for row in days[day]]
        boot.append(fmean(float(x['combined_logloss'])-float(x['market_logloss']) for x in selected))
    boot.sort()
    return [boot[int(0.025*(len(boot)-1))], boot[int(0.975*(len(boot)-1))]]


def evaluate(csv_path, db_path):
    with csv_path.open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    ids=[x['race_id'] for x in rows]
    if not ids or len(ids)!=len(set(ids)):
        raise ValueError('Duplicate/empty race_ids: cannot treat as paired race cohort')
    # Read ONLY. No implication that SQLite's current race metadata proves PIT.
    uri='file:'+quote(str(db_path.resolve()))+'?mode=ro&immutable=1'
    con=sqlite3.connect(uri,uri=True)
    try:
        mapping={row[0]:row[1] for row in con.execute('SELECT race_id,country FROM races')}
    finally:con.close()
    by_country=defaultdict(list);by_size=defaultdict(list);by_status=defaultdict(list)
    missing=[]
    for x in rows:
        for k in ['combined_logloss','market_logloss','combined_brier','market_brier','fundamental_logloss']:
            if not math.isfinite(float(x[k])): raise ValueError('Nonfinite paired historical scores')
        c=mapping.get(x['race_id'])
        if c is None:missing.append(x['race_id']);c='UNKNOWN'
        by_country[c].append(x)
        n=int(x['selection_count'])
        by_size['2-7' if n<=7 else '8-11' if n<=11 else '12+'].append(x)
        by_status[x['status']].append(x)
    without_legacy=[x for x in rows if x['race_id'] not in LEGACY_RACES]
    return {
        'schema':'BETTING_P1_RETROSPECTIVE_SENSITIVITY_V1',
        'evidence_level':'RETROSPECTIVE_DESCRIPTIVE_NOT_OOS_NOT_PROMOTION',
        'data_csv_sha256':hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        'total_scored':len(rows),'missing_race_metadata':len(missing),
        'overall':_summary(rows),
        'day_cluster_bootstrap_95pct':_day_cluster_interval(rows),
        'by_country':{k:_summary(v) for k,v in sorted(by_country.items())},
        'by_field_size':{k:_summary(v) for k,v in sorted(by_size.items())},
        'by_decision_status':{k:_summary(v) for k,v in sorted(by_status.items())},
        'excluding_five_legacy_races':_summary(without_legacy),
        'legacy_races_present':sorted(set(ids)&LEGACY_RACES),
        'date_blocks':len(set(x['race_day'] for x in rows)),
        'interpretation':'Descriptive sample conditioned on recorded decisions: cannot validate edge or support model promotion.',
        'betting_authority':False,'model_promotion_authority':False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--paired-csv',type=Path,required=True)
    p.add_argument('--db',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=evaluate(args.paired_csv,args.db)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps({'n':result['total_scored'],'day_blocks':result['date_blocks'],
          'countries':result['by_country'],'overall':result['overall'],
          'bootstrap':result['day_cluster_bootstrap_95pct']},indent=2))

if __name__=='__main__':main()
