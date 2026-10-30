"""Deterministic descriptive stats; guard against false OOS/promotion claims."""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPT))
from retrospective_sensitivity import _day_cluster_interval, _summary, evaluate


def rows():
    return [dict(race_id=f'R{i}',race_day=f'2026-10-{i+1:02d}',
        selection_count='5',status='WATCH',fundamental_logloss='1.6',
        market_logloss='1.0',combined_logloss=str(1.0+i/10),
        combined_brier='0.8',market_brier='0.7') for i in range(5)]


def write_fixture(tmp_path,lines):
    p=tmp_path/'pairs.csv'
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(lines[0]));w.writeheader();w.writerows(lines)
    db=tmp_path/'db.sqlite'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE races(race_id TEXT, country TEXT)')
        for i in range(5):c.execute('INSERT INTO races VALUES (?,?)',(f'R{i}','SE' if i%2 else 'NO'))
    return p,db


def test_mean_and_day_bootstrap_repeatable(tmp_path):
    p,db=write_fixture(tmp_path,rows())
    first=evaluate(p,db);second=evaluate(p,db)
    assert first==second
    assert first['total_scored']==5
    assert first['overall']['mean_combined_minus_market_logloss']==pytest.approx(.2)
    assert first['day_cluster_bootstrap_95pct'] is not None
    assert not first['betting_authority'] and not first['model_promotion_authority']
    assert first['by_country']['SE']['n']==2


def test_duplicate_race_observations_do_not_count_as_two(tmp_path):
    duplicate=rows();duplicate[1]['race_id']=duplicate[0]['race_id']
    p,db=write_fixture(tmp_path,duplicate)
    with pytest.raises(ValueError,match='Duplicate/empty'):
        evaluate(p,db)


def test_nonfinite_scores_fail_closed(tmp_path):
    data=rows();data[2]['market_logloss']='nan'
    p,db=write_fixture(tmp_path,data)
    with pytest.raises(ValueError,match='Nonfinite'):
        evaluate(p,db)


def test_bootstrap_does_not_claim_interval_for_only_one_day():
    data=rows()
    for x in data:x['race_day']='2026-10-29'
    assert _day_cluster_interval(data) is None


def test_no_evidence_is_not_zero_loss_or_perfect_market():
    assert _summary([])=={'n':0,'status':'NO_EVIDENCE'}
