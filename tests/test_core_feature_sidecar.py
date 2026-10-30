from pathlib import Path
import json
import sqlite3

import pytest

from hbi.core_feature_sidecar import build_feature_sidecar, extract_year_features

CUTOFF='2026-10-28T18:35:00+00:00'


def row(data, *, complete=1, total=20):
    return {'selection_id':'1','full_field_history_complete':complete,
            'history_total_starts':total,'observed_at_utc':'2026-10-28T18:30:00+00:00',
            'raw_json':json.dumps({'atg_market_free':{'yearCrosscheck':data}})}


def test_year_extracted_only_if_verified():
    r=extract_year_features(row({'2026':{'starts':8,'earnings':1200}}),CUTOFF)
    assert r['current_year_starts']==8 and r['current_year_earnings_source_units']==1200
    assert r['derived_not_used_by_champion']


def test_no_verified_field_no_recovery():
    assert extract_year_features(row({'2026':{'starts':8,'earnings':1200}},complete=0),CUTOFF) is None


def test_no_current_year_no_fabrication():
    assert extract_year_features(row({'2025':{'starts':8,'earnings':1200}}),CUTOFF) is None


def test_no_wins_invented():
    assert 'current_year_wins' not in extract_year_features(
        row({'2026':{'starts':8,'earnings':1200}}),CUTOFF)


@pytest.mark.parametrize('data',[{'2026':{'starts':True,'earnings':1200}},
                                  {'2026':{'starts':21,'earnings':1200}},
                                  {'2026':{'starts':-1,'earnings':100}},
                                  {'2026':{'starts':1,'earnings':-1}},
                                  {'2026':{'starts':1,'earnings':'100'}},
                                  {'2026':{'starts':1}},
                                  {},[]])
def test_invalid_features_return_none(data):
    assert extract_year_features(row(data),CUTOFF) is None


def test_invalid_json_is_none():
    x=row({'2026':{'starts':2,'earnings':5}});x['raw_json']='{bad'
    assert extract_year_features(x,CUTOFF) is None


def test_archival_features_from_compact_fixture():
    path=Path(__file__).resolve().parents[1]/'reports/core_003_day_fixture.sqlite'
    conn=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    try:r=build_feature_sidecar(conn,race_date='2026-10-28')
    finally:conn.close()
    assert r['recovered_rows']==93
    assert r['recovered_feature_counts']['current_year_starts']==93
    assert all('current_year_wins' not in s for s in r['rows'])
