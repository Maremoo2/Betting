"""Self-contained offline tests. Repo-wide CI is NOT claimed by these tests."""
from __future__ import annotations

import importlib.util
import json
import math
import sqlite3
from datetime import UTC
from pathlib import Path

import pytest

from hbi.legacy_provenance import _exact_active_market

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('betting_milestone_audit',BASE/'scripts/betting_milestone_audit.py')
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def market(rows,active):
    return audit.active_market_cohort([{'selection_key':k,'odds_decimal':v} for k,v in rows],set(active))


def test_frozen_original_with_inactive_sentinel_accepted():
    m,e=market([('1',2.),('2',3.),('3',-.02)],{'1','2'})
    assert e is None and m['excluded_unpriced_keys']==['3']
    assert math.isclose(sum(audit.norm_odds(m['odds']).values()),1.0)

@pytest.mark.parametrize('rows,active,reason',[
    ([('1',2.0)],{'1','2'},'MISSING_ACTIVE_PRICE'),
    ([('1',2.),('2',.9)],{'1','2'},'INVALID_ACTIVE_PRICE'),
    ([('1',2.),('2',2.),('3',10.)],{'1','2'},'EXTRA_PRICE_OR_UNKNOWN_MARKER'),
    ([('1',2.),('2',2.),('3',-0.01)],{'1','2'},'EXTRA_PRICE_OR_UNKNOWN_MARKER'),
    ([('1',2.),('2',2.),('2',2.)],{'1','2'},'DUPLICATE_SELECTION'),
    ([('1',2.),('2',None)],{'1','2'},'UNKNOWN_ODDS_VALUE'),
    ([('1',2.),('2',float('nan'))],{'1','2'},'NONFINITE_ODDS'),
    ([('1',-.02),('2',2.)],{'1','2'},'INVALID_ACTIVE_PRICE'),
    ([('1',2.),('2',2.)],set(),'EXTRA_PRICE_OR_UNKNOWN_MARKER'),
])
def test_market_failclosed(rows,active,reason):
    m,e=market(rows,active)
    assert m is None and e==reason


def test_naive_date_rejected():
    assert audit.stamp('2026-10-28T11:00:00') is None
    assert audit.stamp('2026-10-28T11:00:00+00:00').tzinfo==UTC


def test_champion_market_free_and_normalized():
    f=[{'selection_id':'1','history_total_starts':10,'history_total_wins':2,
        'full_field_history_complete':1,'source_uri':'evidence:test'},
       {'selection_id':'2','history_total_starts':20,'history_total_wins':2,
        'full_field_history_complete':1,'source_uri':'evidence:test'}]
    got=audit.champion_baseline(f,{'1','2'})
    assert set(got)=={'1','2'} and math.isclose(sum(got.values()),1.0,abs_tol=1e-12)
    assert got['1']>got['2']


def test_missing_history_fails_closed():
    f=[{'selection_id':'1','history_total_starts':10,'history_total_wins':2,
        'full_field_history_complete':1,'source_uri':'evidence:test'}]
    assert audit.champion_baseline(f,{'1','2'}) is None


def test_invalid_probabilities_failclosed():
    assert audit._parse_distribution('{"1":0.9,"2":0.9}') is None
    assert audit._parse_distribution('{"1":0.6,"2":0.4}') is not None
    assert audit._parse_distribution('{"1":1.0,"2":0.0}') is None


def test_readonly_database_uri_rejects_write(tmp_path):
    p=tmp_path/'db.sqlite'
    with sqlite3.connect(p) as conn: conn.execute('create table x(n integer)')
    before=audit.sha256(p)
    with audit.db_open(p) as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute('insert into x values(1)')
    assert audit.sha256(p)==before


def test_real_archive_replay_and_coverage():
    db=Path('/mnt/data/p0_integrity/live_state/data/hbi.sqlite')
    if not db.is_file():pytest.skip('Actual rolling HBI archive not installed; not PASS for archive E2E')
    with audit.db_open(db) as conn:
        replay=audit.audit_replay(conn)
        assert len(replay)==5
        assert sum(r['classification']=='SOURCE_RECONSTRUCTED_LEGACY_ATTACHMENT_MISMATCH' for r in replay)==5
        assert sum(bool(r['excluded_unpriced_original_keys']) for r in replay)==3
        days,_rows,examples=audit.audit_card(conn,['2026-10-28','2026-10-29'],audit.DEFAULT_END)
        assert days[0]['physically_distinct_heuristic']==31
        assert days[0]['both_t4']==9
        assert days[1]['both_t4']==8
        assert len(examples)==17
        assert all(abs(sum(ex['champion_pwin'].values())-1)<1e-12 for ex in examples)
        assert all(ex['roster_pit_attested'] is False for ex in examples)
        ticket=audit.audit_settlement(conn)
        assert ticket['action']=='BLOCKED_READ_ONLY_NO_SETTLEMENT'
        assert ticket['cached_winner']=='5'
        metrics, paired=audit.audit_paired(conn,audit.DEFAULT_END)
        assert metrics['races']==len(paired)==297
        assert metrics['mean_logloss']['market'] < metrics['mean_logloss']['combined']
        assert metrics['betting_authority'] is False


def _patch_filter():
    """Read the actual integrated helper rather than a local patch file."""
    return _exact_active_market


def test_repo_patch_helper_reconstructs_real_five_snapshots():
    helper=_patch_filter()
    db=Path('/mnt/data/p0_integrity/live_state/data/hbi.sqlite')
    if not db.is_file():pytest.skip('Historical real archive absent')
    with audit.db_open(db) as conn:
        for rid in sorted(audit.P0_RACES):
            d=conn.execute('''SELECT d.source_market_observed_at_utc,d.product,
                  d.fundamental_probabilities_json FROM shadow_decision_runs d
                  WHERE d.race_id=?''',(rid,)).fetchone()
            original=conn.execute('''SELECT selection_key,odds_decimal
                    FROM provider_market_snapshots WHERE race_id=? AND product=?
                    AND observed_at_utc=?''',(rid,d['product'],d['source_market_observed_at_utc'])).fetchall()
            expected=set(json.loads(d['fundamental_probabilities_json']))
            m,unused=helper(original,expected)
            assert set(m)==expected and len(m)>=2
            assert all(x not in m for x in unused)


def test_repo_patch_helper_is_failclosed_against_injected_rows():
    helper=_patch_filter();active={'1','2'}
    original=[{'selection_key':'1','odds_decimal':2.0},
              {'selection_key':'2','odds_decimal':3.0}]
    assert len(helper(original,active)[0])==2
    for extra in [
        {'selection_key':'3','odds_decimal':7.0},
        {'selection_key':'3','odds_decimal':-0.01},
        {'selection_key':'1','odds_decimal':2.5}]:
        assert helper(original+[extra],active)[0]=={}
    assert helper(original[:1],active)[0]=={}
    assert helper(original+[{'selection_key':'3','odds_decimal':-0.02}],active)[1]==['3']


def test_tminus4_raw_source_does_not_use_later_capture():
    conn=sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE provider_payloads(provider text,category text,provider_raceday_key text,race_number integer,observed_at_utc text)')
    conn.execute("INSERT INTO provider_payloads VALUES ('rikstoto','RACEDAY_STARTS','XX',1,'2026-10-28T13:57:00+00:00')")
    conn.execute("INSERT INTO provider_payloads VALUES ('atg','FULL_FIELD_ONLY_V1','TEST:1',1,'2026-10-28T13:57:00+00:00')")
    cutoff=audit.stamp('2026-10-28T13:56:00+00:00')
    result=audit.raw_source_status(conn,race_id='TEST:1',cutoff=cutoff,race_no=1,raceday_key='XX')
    assert all(v['pre_t4_events']==0 for v in result.values())
    assert all(v['status']=='FIRST_OBSERVED_ONLY_AFTER_T4' for v in result.values())


def test_cohort_newer_partial_is_not_replaced_with_older_full():
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE runner_fundamental_snapshots(race_id text, selection_id text, observed_at_utc text, feature_as_of_utc text)')
    for sid in ['1','2']:
        conn.execute('INSERT INTO runner_fundamental_snapshots VALUES (?,?,?,?)',
                     ('TEST:1',sid,'2026-10-28T13:40:00+00:00','2026-10-28T13:40:00+00:00'))
    conn.execute('INSERT INTO runner_fundamental_snapshots VALUES (?,?,?,?)',
                 ('TEST:1','1','2026-10-28T13:55:00+00:00','2026-10-28T13:55:00+00:00'))
    rows,ts=audit.latest_cohort(conn,'runner_fundamental_snapshots','TEST:1',audit.stamp('2026-10-28T13:56:00+00:00'))
    assert len(rows)==1 and {x['selection_id'] for x in rows}=={'1'}
    assert ts=='2026-10-28T13:55:00+00:00'


def test_future_feature_in_cohort_hard_blocks():
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE runner_fundamental_snapshots(race_id text,selection_id text,observed_at_utc text,feature_as_of_utc text)')
    conn.execute('INSERT INTO runner_fundamental_snapshots VALUES (?,?,?,?)',
                 ('TEST:1','1','2026-10-28T13:50:00+00:00','2026-10-28T14:05:00+00:00'))
    rows,ts=audit.latest_cohort(conn,'runner_fundamental_snapshots','TEST:1',audit.stamp('2026-10-28T13:56:00+00:00'))
    assert rows==[] and ts=='2026-10-28T13:50:00+00:00'
