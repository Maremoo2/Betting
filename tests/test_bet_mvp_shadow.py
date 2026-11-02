"""BET-MVP-001 read-only integration contract, including genuine archival data."""
from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.bet_mvp_shadow import (
    NO_BET_AUTHORITY, PINNED_UPSTREAM, SCHEMA,
    analyze, aware, select_next_race, sha256, write_frozen,
)
from hbi.core_multifactor_research import ExperimentalCoefficients
from hbi.race_core_review import historical_win_prior

REAL = os.getenv("BET_MVP_REAL_DB")
PILOT = os.getenv("BET_MVP_PILOT_DB")


def connection(path: str):
    c = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro&immutable=1", uri=True)
    c.row_factory = sqlite3.Row
    return c


def test_schema_and_model_weights_are_unchanged():
    assert SCHEMA == "BET_MVP_001_FROZEN_SHADOW_V1"
    assert PINNED_UPSTREAM == "deec4e240293f43261d368c546faa6437f912472"
    assert NO_BET_AUTHORITY == "RESEARCH_ONLY_NEVER_BET"
    assert ExperimentalCoefficients().__dict__ == {"top3": 0.2, "earnings_per_start": 0.1, "experience": 0.05}


def test_source_model_champion_prior_sums_to_one():
    prior, n = historical_win_prior([
        {"selection_id": "1", "scratched": 0,"history_total_starts": 20,"history_total_wins": 3},
        {"selection_id": "2", "scratched": 0,"history_total_starts": 10,"history_total_wins": 1},
        {"selection_id": "3", "scratched": 1,"history_total_starts": 10,"history_total_wins": 10},
    ])
    assert set(prior) == {"1","2"} and n == 2
    assert abs(sum(prior.values())-1) < 1e-12


@pytest.mark.parametrize('value', ['2026-10-17T14:00:00','not-a-time'])
def test_naive_or_invalid_clock_never_accepted(value):
    with pytest.raises(ValueError): aware(value)


def test_empty_race_returns_none_on_discovery():
    with sqlite3.connect(':memory:') as c:
        c.row_factory=sqlite3.Row
        c.execute('CREATE TABLE races(race_id TEXT,track TEXT,race_no INT,start_time_utc TEXT,discipline TEXT)')
        assert select_next_race(c,datetime(2026,11,2,tzinfo=UTC)) is None


def test_frozen_reports_are_never_overwritten(tmp_path):
    report={
        'race':{'track':'T','race_no':1,'race_date':'2026-10-01','start_time_utc':'2026-10-01T12:00:00+00:00','race_id':'T:1'},
        'analysis_status':'SOURCE_BLOCKED','pit_status':'PIT_NOT_CERTIFIED','as_of_utc':'2026-10-01T11:00:00+00:00',
        'model_versions':{'champion':'C','core004':'M'},'active_runners':0,'field_size':0,'champion_p_sum':None,'core004_p_sum':None,
        'source_database_sha256':'0'*64,'source_audit':{'fundamental_observed_at_utc':None,'market_observed_at_utc':None},
        'source_blocks':['NO_CANONICAL_ROSTER'],'runners':[],
    }
    target=tmp_path/'frozen'
    hashes=write_frozen(report,target)
    assert set(hashes)=={'shadow.json','shadow.md','runners.csv'}
    assert all(len(v)==64 for v in hashes.values())
    original=target.joinpath('shadow.json').read_bytes()
    with pytest.raises(FileExistsError,match='NO_OVERWRITE'):
        write_frozen(report,target)
    assert target.joinpath('shadow.json').read_bytes()==original


@pytest.mark.skipif(not REAL,reason='Set BET_MVP_REAL_DB to exact historical SQLite')
def test_real_archived_fullfield_models_and_market():
    with connection(REAL) as db:
        result=analyze(db,race_id='RIKSTOTO:S1_NR_2026-10-17:6',as_of='2026-10-17T13:18:00+00:00',archive_sha=None)
    assert result['analysis_status']=='RESEARCH_READY'
    assert result['active_runners']==15
    assert len(result['runners'])==15
    assert abs(result['champion_p_sum']-1)<1e-12
    assert abs(result['core004_p_sum']-1)<1e-12
    assert abs(result['normalized_market_p_sum']-1)<1e-12
    assert all(r['champion_p_win'] is not None and r['core004_p_win'] is not None for r in result['runners'])
    assert all(r['history_source_uri'] for r in result['runners'])
    assert sum(r['research_status']=='WATCH' for r in result['runners'])==5
    assert all(r['bet_authority'] is False for r in result['runners'])
    assert result['pit_status']=='PIT_NOT_CERTIFIED' and result['bet_authority'] is False
    assert result['frozen_outcome'] is None


@pytest.mark.skipif(not REAL,reason='Set BET_MVP_REAL_DB to exact historical SQLite')
def test_real_archived_atg_clock_blocks_core004():
    with connection(REAL) as db:
        result=analyze(db,race_id='RIKSTOTO:S2_NR_2026-10-30:7',as_of='2026-10-30T16:45:00+00:00',archive_sha=None)
    assert result['active_runners']==14
    assert result['champion_p_sum']==pytest.approx(1)
    assert result['core004_p_sum'] is None
    assert 'ASOF_AFTER_EARLIEST_SOURCE_T4' in result['source_blocks']
    assert result['analysis_status']=='SOURCE_BLOCKED'
    assert all(r['research_status']=='BLOCKED' for r in result['runners'] if not r['scratched'])
    assert all(r['research_status']=='PASS' for r in result['runners'] if r['scratched'])


@pytest.mark.skipif(not REAL,reason='Set BET_MVP_REAL_DB to exact historical SQLite')
def test_real_scratch_excluded_from_probability_denominator():
    with connection(REAL) as db:
        result=analyze(db,race_id='RIKSTOTO:S1_NR_2026-10-20:4',as_of='2026-10-20T11:22:00+00:00',archive_sha=None)
    assert result['analysis_status']=='RESEARCH_READY'
    assert result['field_size']==15 and result['active_runners']==13
    scratched=[r for r in result['runners'] if r['scratched']]
    assert len(scratched)==2
    assert all(r['research_status']=='PASS' and r['champion_p_win'] is None and r['core004_p_win'] is None for r in scratched)
    assert result['champion_p_sum']==pytest.approx(1)
    assert result['core004_p_sum']==pytest.approx(1)


@pytest.mark.skipif(not REAL,reason='Set BET_MVP_REAL_DB to exact historical SQLite')
def test_real_archive_before_source_cannot_use_future_snapshots():
    with connection(REAL) as db:
        result=analyze(db,race_id='RIKSTOTO:S1_NR_2026-10-17:6',as_of='2026-10-17T12:00:00+00:00',archive_sha=None)
    assert result['analysis_status']=='SOURCE_BLOCKED'
    assert result['champion_p_sum'] is None
    assert result['core004_p_sum'] is None
    assert all(r['win_odds'] is None for r in result['runners'])


@pytest.mark.skipif(not PILOT,reason='Set BET_MVP_PILOT_DB to actual CORE-003 pilot SQLite')
def test_genuine_prestart_core003_capture_has_both_model_distributions_but_no_market():
    with connection(PILOT) as db:
        result=analyze(db,race_id='RIKSTOTO:S1_NR_2026-11-02:1',as_of='2026-11-02T10:08:40+00:00',archive_sha=None)
    assert result['race']['track']=='Årjäng'
    assert result['active_runners']==10
    assert result['champion_p_sum']==pytest.approx(1)
    assert result['core004_p_sum']==pytest.approx(1)
    assert result['analysis_status']=='SOURCE_BLOCKED'
    assert result['pit_status']=='PIT_NOT_CERTIFIED'
    assert 'NO_WIN_MARKET_AS_OF' in result['source_blocks']
    assert all(r['research_status']=='BLOCKED' and r['win_odds'] is None for r in result['runners'])
    assert result['bet_authority'] is False


@pytest.mark.skipif(not PILOT,reason='Set BET_MVP_PILOT_DB to actual CORE-003 pilot SQLite')
def test_pilot_before_fetch_has_no_future_lookahead():
    with connection(PILOT) as db:
        result=analyze(db,race_id='RIKSTOTO:S1_NR_2026-11-02:1',as_of='2026-11-02T10:08:34+00:00',archive_sha=None)
    assert result['champion_p_sum'] is None and result['core004_p_sum'] is None
    assert result['analysis_status']=='SOURCE_BLOCKED'
    assert len(result['runners'])==10
    assert 'NO_FUNDAMENTAL_SNAPSHOT_BEFORE_AS_OF' in result['source_blocks']


@pytest.mark.skipif(not PILOT,reason='Set BET_MVP_PILOT_DB to actual CORE-003 pilot SQLite')
def test_pilot_discovery_returns_real_upcoming_race():
    with connection(PILOT) as db:
        selected=select_next_race(db,datetime.fromisoformat('2026-11-02T10:07:29+00:00'))
    assert selected['race_id']=='RIKSTOTO:S1_NR_2026-11-02:1'


@pytest.mark.skipif(not PILOT,reason='Set BET_MVP_PILOT_DB to actual CORE-003 pilot SQLite')
def test_prospective_future_asof_is_rejected_even_if_calendar_is_future():
    with connection(PILOT) as db:
        with pytest.raises(ValueError,match='PROSPECTIVE_AS_OF_IN_FUTURE'):
            analyze(db,race_id='RIKSTOTO:S1_NR_2026-11-02:1',as_of='2026-11-02T11:19:59+00:00',archive_sha=None,run_kind='PROSPECTIVE_ATTEMPT')


@pytest.mark.skipif(not REAL,reason='Set BET_MVP_REAL_DB to exact historical SQLite')
def test_readonly_source_has_not_been_mutated():
    assert sha256(Path(REAL))=='30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0'

@pytest.mark.skipif(not PILOT, reason='Set BET_MVP_PILOT_DB to actual CORE-003 pilot SQLite')
def test_rejected_atg_source_in_isolated_copy_vetoes_research(tmp_path):
    """Synthetic tamper of a *copy* of the genuine pilot, not the real archive."""
    target = tmp_path / 'tampered-pilot.sqlite'
    source = connection(PILOT)
    with sqlite3.connect(target) as dest:
        source.backup(dest)
    source.close()
    with sqlite3.connect(target) as db:
        matches = db.execute("""
          SELECT payload_id FROM provider_payloads
          WHERE provider='atg' AND category='FULL_FIELD_ONLY_V1'
          AND provider_raceday_key=? AND race_number=1
          AND observed_at_utc <= ?
          ORDER BY observed_at_utc DESC
        """, ('RIKSTOTO:S1_NR_2026-11-02:1', '2026-11-02T10:08:40+00:00')).fetchall()
        assert matches
        db.execute('UPDATE provider_payloads SET payload_json=? WHERE payload_id=?',
                   ('{"passed": false,"matched_complete_runners":0,"active_runners":10,"reasons":["PROVIDER_REJECTED"],"runners":[]}',matches[0][0]))
        db.commit()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.close()  # immutable=1 readers deliberately ignore pending WAL frames
    with connection(str(target)) as db:
        report=analyze(db,race_id='RIKSTOTO:S1_NR_2026-11-02:1',as_of='2026-11-02T10:08:40+00:00',archive_sha=None)
    assert report['analysis_status']=='SOURCE_BLOCKED'
    assert 'ATG_FULL_FIELD_SOURCE_EXPLICITLY_REJECTED' in report['source_blocks']
    assert all(r['bet_authority'] is False for r in report['runners'])
