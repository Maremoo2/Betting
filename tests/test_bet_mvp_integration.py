"""BET-MVP-001 additive status/provenance checks using real, immutable race data."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from hbi.bet_mvp_shadow import analyze, sha256

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path(os.environ.get('BET_MVP_REAL_DB', ''))
PILOT = Path(os.environ.get('BET_MVP_PILOT_DB', ''))
SOURCE = Path(os.environ.get('BET_MVP_CORE003_REPORT', ''))
FROZEN = Path(os.environ['BET_MVP_FROZEN_REPORTS']) if os.getenv('BET_MVP_FROZEN_REPORTS') else None


def connection(path):
    db = sqlite3.connect(f'file:{path.resolve()}?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    return db


@pytest.mark.skipif(not ORIGINAL.is_file(), reason='Original HBI SQLite unavailable')
def test_real_fullfield_statuses_coexist_with_pit_not_certified():
    with connection(ORIGINAL) as db:
        result = analyze(db, race_id='RIKSTOTO:S1_NR_2026-10-17:6',
                         as_of='2026-10-17T13:18:00+00:00', archive_sha=sha256(ORIGINAL))
    assert result['analysis_status'] == 'RESEARCH_READY'
    assert result['status_dimensions'] == {
        'model':'MODEL_READY','market':'MARKET_READY','pit':'PIT_NOT_CERTIFIED',
        'bet':'NOT_ELIGIBLE_FOR_REAL_BETTING',
    }
    assert len(result['runners']) == 15
    assert result['model_blockers'] == []
    assert result['market_blockers'] == []
    assert all(row['model_status'] == 'MODEL_READY' and row['pit_status'] == 'PIT_NOT_CERTIFIED'
               for row in result['runners'])
    assert all(row['bet_authority'] is False for row in result['runners'])


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(), reason='Real CORE003 data unavailable')
def test_real_core003_model_ready_market_blocked_is_not_model_failure():
    evidence = json.loads(SOURCE.read_text())
    with connection(PILOT) as db:
        result = analyze(db, race_id='RIKSTOTO:S1_NR_2026-11-02:1',
                         as_of='2026-11-02T10:21:36+00:00', archive_sha=sha256(PILOT),
                         source_report=evidence, source_report_sha256=sha256(SOURCE))
    assert result['status_dimensions'] == {
        'model':'MODEL_READY','market':'MARKET_BLOCKED','pit':'PIT_NOT_CERTIFIED',
        'bet':'NOT_ELIGIBLE_FOR_REAL_BETTING',
    }
    assert result['analysis_status'] == 'SOURCE_BLOCKED'
    assert result['model_blockers'] == []
    assert 'NO_WIN_MARKET_AS_OF' in result['market_blockers']
    assert result['champion_p_sum'] == pytest.approx(1)
    assert result['core004_p_sum'] == pytest.approx(1)
    assert len(result['runners']) == 10
    assert all(row['research_status'] == 'BLOCKED' and row['model_status'] == 'MODEL_READY'
               and row['market_status'] == 'MARKET_BLOCKED' and row['win_odds'] is None
               for row in result['runners'])
    assert result['collector_source_evidence']['sha256'] == sha256(SOURCE)
    assert result['collector_source_evidence']['finished_at_utc'] == '2026-11-02T10:08:39.302286+00:00'
    assert result['collector_source_evidence']['independent_pit_certified'] is False
    assert (datetime.fromisoformat(result['analysis_started_at_utc'])
            <= datetime.fromisoformat(result['model_calculated_at_utc'])
            <= datetime.fromisoformat(result['report_created_at_utc']))


@pytest.mark.skipif(not ORIGINAL.is_file(), reason='Original HBI SQLite unavailable')
def test_real_skive_partial_model_not_called_fully_ready():
    with connection(ORIGINAL) as db:
        r = analyze(db, race_id='RIKSTOTO:S2_NR_2026-10-30:7',
                    as_of='2026-10-30T16:45:00+00:00', archive_sha=None)
    assert r['model_status'] == 'MODEL_PARTIAL'
    assert r['champion_p_sum'] == pytest.approx(1)
    assert r['core004_p_sum'] is None
    assert 'ASOF_AFTER_EARLIEST_SOURCE_T4' in r['model_blockers']
    assert r['bet_authority'] is False


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(), reason='Original source unavailable')
@pytest.mark.parametrize(('field', 'value', 'blocker'), [
    ('races_in_fixed_cohort', ['WRONG_RACE'], 'CORE003_REPORT_RACE_NOT_IN_FIXED_COHORT'),
    ('finished_at_utc', '2026-11-02T10:21:37+00:00', 'CORE003_CAPTURE_FINISHED_AFTER_ANALYSIS_AS_OF'),
    ('started_at_utc', 'not-an-instant', 'CORE003_CAPTURE_CLOCK_INVALID'),
])
def test_untrusted_core003_report_never_promotes_model(field, value, blocker):
    source = json.loads(SOURCE.read_text())
    source[field] = value
    with connection(PILOT) as db:
        r = analyze(db, race_id='RIKSTOTO:S1_NR_2026-11-02:1',
                    as_of='2026-11-02T10:21:36+00:00', archive_sha=None,
                    source_report=source, source_report_sha256='0'*64)
    assert blocker in r['source_blocks']
    assert r['model_status'] == 'MODEL_BLOCKED'
    assert r['bet_authority'] is False


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(), reason='Real source unavailable')
def test_real_source_cli_writes_frozen_statuses_and_rejects_second_write(tmp_path):
    target = tmp_path / 'new-frozen-report'
    command = [sys.executable, '-m', 'hbi.bet_mvp_shadow',
               '--db', str(PILOT), '--source-report', str(SOURCE),
               '--race-id', 'RIKSTOTO:S1_NR_2026-11-02:1',
               '--as-of', '2026-11-02T10:21:36+00:00', '--out', str(target),
               '--run-kind', 'ARCHIVED_REPLAY']
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
    run = subprocess.run(command, check=False, cwd=ROOT, env=env, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    report = json.loads((target / 'shadow.json').read_text())
    assert report['status_dimensions']['model'] == 'MODEL_READY'
    assert report['status_dimensions']['market'] == 'MARKET_BLOCKED'
    assert 'MODEL_READY' in (target / 'shadow.md').read_text()
    assert 'MARKET_BLOCKED' in (target / 'shadow.md').read_text()
    assert sha256(target / 'shadow.json') == json.loads(run.stdout)['output_sha256']['shadow.json']
    again = subprocess.run(command, check=False, cwd=ROOT, env=env, text=True, capture_output=True)
    assert again.returncode != 0
    assert 'FROZEN_SHADOW_OUTPUT_DIRECTORY_EXISTS_NO_OVERWRITE' in again.stderr


@pytest.mark.skipif(not PILOT.is_file() or not ORIGINAL.is_file() or FROZEN is None,
                    reason='Original frozen reports / SQLite unavailable')
@pytest.mark.parametrize(('source', 'race', 'as_of', 'dirname'), [
    (ORIGINAL, 'RIKSTOTO:S1_NR_2026-10-17:6', '2026-10-17T13:18:00+00:00', 'archived_gavle_final'),
    (ORIGINAL, 'RIKSTOTO:S1_NR_2026-10-20:4', '2026-10-20T11:22:00+00:00', 'archived_scratched_final'),
    (ORIGINAL, 'RIKSTOTO:S2_NR_2026-10-30:7', '2026-10-30T16:45:00+00:00', 'archived_skive_final'),
    (PILOT, 'RIKSTOTO:S1_NR_2026-11-02:1', '2026-11-02T10:21:36+00:00', 'prospective_final_attested'),
])
def test_four_original_frozen_races_have_same_probabilities_and_market(source, race, as_of, dirname):
    old = json.loads((FROZEN / dirname / 'shadow.json').read_text())
    original_sha = hashlib.sha256((FROZEN / dirname / 'shadow.json').read_bytes()).hexdigest()
    with connection(source) as db:
        new = analyze(db, race_id=race, as_of=as_of, archive_sha=sha256(source))
    assert new['field_size'] == old['field_size']
    assert new['active_runners'] == old['active_runners']
    a = {r['selection_id']:r for r in new['runners']}
    for previous in old['runners']:
        updated = a[previous['selection_id']]
        for key in ('scratched','champion_p_win','core004_p_win',
                    'normalized_market_p','win_odds','champion_theoretical_ev_uncalibrated',
                    'core004_minus_champion_pp','historical_starts','historical_wins'):
            assert updated[key] == previous[key], (race, previous['selection_id'], key)
    assert old['champion_p_sum'] == new['champion_p_sum']
    assert old['core004_p_sum'] == new['core004_p_sum']
    assert original_sha == hashlib.sha256((FROZEN / dirname / 'shadow.json').read_bytes()).hexdigest()


@pytest.mark.skipif(FROZEN is None, reason='Original frozen reports unavailable')
def test_two_original_aerjang_freeze_times_and_original_report_bytes_are_preserved():
    snapshots = [("prospective_genuine_frozen", '2026-11-02T10:13:28.941818+00:00', '2026-11-02T10:08:40+00:00'),
                 ("prospective_final_attested", '2026-11-02T10:21:37.216488+00:00', '2026-11-02T10:21:36+00:00')]
    original_sha = []
    for dirname, created, cutoff in snapshots:
        p = FROZEN / dirname / 'shadow.json'
        old = json.loads(p.read_text())
        assert old['report_created_at_utc'] == created
        assert old['as_of_utc'] == cutoff
        assert old['source_database_sha256'] == '9c9a7021d15648db355fb320c51def268e5ffd34dc78ebef1cd95a6f5b7794ef'
        assert old['source_audit']['fundamental_observed_at_utc'] == '2026-11-02T10:08:39.259317+00:00'
        assert old['model_versions']['champion'] == 'FUNDAMENTAL_CHAMPION_V1_1'
        assert old['model_versions']['core004'] == 'CORE_004_EXPLORATORY_MULTIFACTOR_V0_NOT_FITTED'
        assert old.get('model_calculated_at_utc') is None  # never retroactively invent a clock
        original_sha.append(hashlib.sha256(p.read_bytes()).hexdigest())
    assert original_sha == [
        '97a79b8d8344d56340b886811187cd92dd63e718f209e9acf5f11f7f90cf9428',
        'c685b107639d4cdb2a6d4371e5514c8a92f30b51c19998d856c0e6793dbf74f6',
    ]
