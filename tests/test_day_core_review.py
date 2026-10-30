from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from hbi.day_core_review import analyze_day, main, write_day_report
from hbi.day_fixture_extract import extract_day_fixture
from test_race_core_review import fixture, RACE

ARCHIVE = Path(os.environ.get('HBI_CORE_002_ARCHIVE',
    Path(__file__).resolve().parents[1] / 'reports/core_002_28oct_fixture.sqlite'))
FULL_SOURCE = Path(os.environ.get('HBI_CORE_002_SOURCE', '/nonexistent'))


def load(path: Path = ARCHIVE) -> sqlite3.Connection:
    conn = sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro&immutable=1', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture(scope='module')
def archived():
    if not ARCHIVE.exists():
        pytest.skip('Local historical miniature fixture unavailable; supply HBI_CORE_002_ARCHIVE')
    conn = load()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope='module')
def day(archived):
    return analyze_day(archived, race_date='2026-10-28')


def test_full_day_covers_all_inventory_refs(day):
    assert day['summary']['races_in_inventory'] == 50
    assert len(day['races']) == 50
    assert len({r['race_id'] for r in day['races']}) == 50


def test_eligible_physical_races(day):
    s = day['summary']
    assert s['attempted_races'] == 31
    assert s['skipped_discipline'] == 7
    assert s['skipped_composite'] == 8
    assert s['skipped_duplicate_references'] == 4
    assert s['full_baseline_races'] == 9
    assert s['blocked_races'] == 22
    assert s['fundamental_only_races'] == 0


def test_whole_day_horse_denominator_is_known_not_guessed(day):
    s = day['summary']
    assert s['roster_active_attempted'] == 201
    assert s['runners_with_p_win'] == 93
    assert s['runners_with_model_ev'] == 93
    assert s['runner_rows_exported'] == 213
    assert s['runner_p_coverage_pct'] == pytest.approx(100 * 93 / 201)


def test_no_bet_output(day):
    assert day['summary']['real_bet_count'] == 0
    assert not any(h['status'] == 'BET' for h in day['runner_rows'])
    assert day['authority'] == 'RESEARCH_ONLY_NO_REAL_BET'
    assert day['summary']['watch_runners'] == 47


def test_each_ready_race_has_full_field_probabilities(day):
    ids = {r['race_id'] for r in day['races'] if r['stage'] == 'FULL_BASELINE'}
    assert len(ids) == 9
    for race_id in ids:
        horses = [h for h in day['runner_rows'] if h['race_id'] == race_id]
        assert sum(h['p_win'] or 0 for h in horses) == pytest.approx(1.0)
        assert all(h['p_win'] is None if h['scratched'] else h['p_win'] > 0
                   for h in horses)
        assert all(h['fair_odds'] == pytest.approx(1/h['p_win']) for h in horses if h['p_win'])
        assert all(h['theoretical_ev'] == pytest.approx(h['p_win']*h['available_odds']-1)
                   for h in horses if h['p_win'])


def test_no_future_snapshots_used(day):
    races = {r['race_id']: r for r in day['races']}
    for h in day['runner_rows']:
        r = races[h['race_id']]
        assert datetime.fromisoformat(h['decision_at_utc']) < datetime.fromisoformat(r['race_start_time_utc'])


def test_all_exported_runner_keys_unique(day):
    keys = [(h['race_id'], h['selection_id']) for h in day['runner_rows']]
    assert len(keys) == len(set(keys))


def test_separate_skipped_races_not_exported_as_horses(day):
    skipped = {r['race_id'] for r in day['races'] if r['stage'].startswith('SKIPPED')}
    assert not any(h['race_id'] in skipped for h in day['runner_rows'])


def test_skipped_duplicate_mapped_to_kept_ref(day):
    races = {r['race_id']: r for r in day['races']}
    for r in day['races']:
        if r['stage'] == 'SKIPPED_DUPLICATE_REFERENCE':
            assert r['duplicate_reference_of'] in races
            assert races[r['duplicate_reference_of']]['stage'] != 'SKIPPED_DUPLICATE_REFERENCE'
            assert races[r['duplicate_reference_of']]['track'] == r['track']
            assert races[r['duplicate_reference_of']]['race_no'] == r['race_no']


def test_block_reasons_are_aggregated(day):
    assert day['blocker_counts']['NO_FUNDAMENTAL_COHORT_AS_OF'] == 20
    assert day['blocker_counts']['NO_CANONICAL_ROSTER'] == 12
    assert day['blocker_counts']['LOW_HISTORY_COVERAGE'] == 2


def test_field_missing_features_prioritized(day):
    assert day['missing_feature_counts']['history_total_starts'] == 108
    assert day['eligible_feature_denominators']['history_total_starts'] == 201
    assert day['missing_feature_counts']['current_year_starts'] == 201


def test_complete_roster_gaps_for_blocked_race(day):
    r = next(x for x in day['races'] if x['track']=='Solvalla' and x['race_no']==6)
    assert r['stage'] == 'BLOCKED'
    assert r['roster_active'] == 15
    assert len(r['missing_fundamental_ids']) == 15
    assert len(day['missing_by_race'][r['race_id']]) == 15


def test_solvalla_is_entire_track_card(archived):
    d = analyze_day(archived,race_date='2026-10-28',track='Solvalla')
    s = d['summary']
    assert s['attempted_races'] == 10
    assert s['full_baseline_races'] == 4
    assert s['roster_active_attempted'] == 65
    assert s['runners_with_p_win'] == 40
    assert s['watch_runners'] == 19
    assert s['runner_p_coverage_pct'] == pytest.approx(100*40/65)


def test_all_solvalla_races_included_even_empty(archived):
    d = analyze_day(archived,race_date='2026-10-28',track='Solvalla')
    assert {r['race_no'] for r in d['races']} == set(range(1,11))
    for n in (1,2,5,9):
        r = next(x for x in d['races'] if x['race_no']==n)
        assert r['stage']=='BLOCKED'
        assert 'NO_CANONICAL_ROSTER' in r['blocks']


def test_full_day_include_duplicates_increases_attempted(archived):
    d = analyze_day(archived,race_date='2026-10-28',deduplicate_physical=False)
    assert d['summary']['attempted_races'] == 35
    assert d['summary']['full_baseline_races'] == 9
    assert d['summary']['skipped_duplicate_references'] == 0


def test_full_day_include_composite_increases_attempted(archived):
    d = analyze_day(archived,race_date='2026-10-28',exclude_composite=False)
    assert d['summary']['attempted_races'] == 39
    assert d['summary']['skipped_composite'] == 0


def test_gallop_separate_discipline(archived):
    d = analyze_day(archived,race_date='2026-10-28', discipline='gallop')
    assert d['summary']['attempted_races'] == 7
    assert d['summary']['skipped_discipline'] == 43


def test_missing_track_raises(archived):
    with pytest.raises(ValueError, match='No race records'):
        analyze_day(archived,race_date='2026-10-28',track='NONEXISTENT')


@pytest.mark.parametrize('cutoff', [0,-1,121, float('nan'),float('inf')])
def test_invalid_cutoff_rejected(archived,cutoff):
    with pytest.raises(ValueError,match='cutoff_minutes'):
        analyze_day(archived,race_date='2026-10-28',cutoff_minutes=cutoff)


def test_invalid_date_rejected(archived):
    with pytest.raises(ValueError):
        analyze_day(archived,race_date='not a date')


def test_synthetic_fundamental_only_without_market():
    db = fixture()
    try:
        db.execute('delete from provider_market_snapshots')
        d=analyze_day(db,race_date='2026-10-28',cutoff_minutes=3.9)
        assert d['summary']['fundamental_only_races'] == 1
        assert d['summary']['runners_with_p_win'] == 2
        assert d['summary']['runners_with_model_ev'] == 0
        assert d['summary']['watch_runners'] == 0
        assert all(h['status'] == 'PASS' for h in d['runner_rows'])
    finally:db.close()


def test_synthetic_missing_fundamental_is_blocked():
    db = fixture()
    try:
        db.execute('delete from runner_fundamental_snapshots')
        d=analyze_day(db,race_date='2026-10-28',cutoff_minutes=3.9)
        assert d['summary']['blocked_races'] == 1
        assert d['summary']['roster_active_attempted'] == 2
        assert d['summary']['runners_with_p_win'] == 0
        assert d['summary']['watch_runners'] == 0
    finally:db.close()


def test_synthetic_complete_baseline_and_scratched():
    db = fixture()
    try:
        d=analyze_day(db,race_date='2026-10-28',cutoff_minutes=3.9)
        assert d['summary']['full_baseline_races'] == 1
        assert d['summary']['roster_active_attempted'] == 2
        assert len(d['runner_rows']) == 3
        assert d['summary']['runners_with_p_win'] == 2
        assert sum(h['scratched'] for h in d['runner_rows']) == 1
    finally:db.close()


def test_duplicate_reference_prefers_nonempty_roster():
    db = fixture()
    try:
        alt = 'RIKSTOTO:OTHER:1'
        db.execute('insert into races values(?,?,?,?,?,?,?,?,?)',
                   (alt,'2026-10-28','SE','Synthetic',1,'2026-10-28T18:28:00+00:00','trot',2140,'Volt'))
        d = analyze_day(db,race_date='2026-10-28',cutoff_minutes=3.9)
        assert d['summary']['attempted_races'] == 1
        assert d['summary']['skipped_duplicate_references'] == 1
        assert next(r for r in d['races'] if r['race_id']==alt)['duplicate_reference_of']==RACE
    finally:db.close()


def test_outfile_json_csv_md_and_rows(day,tmp_path):
    write_day_report(day,tmp_path)
    for name in ['day_core.json','day_core.md','races.csv','runners.csv']:
        assert (tmp_path/name).exists()
    assert json.loads((tmp_path/'day_core.json').read_text()) == day
    with (tmp_path/'races.csv').open() as f:
        assert len(list(csv.DictReader(f)))==50
    with (tmp_path/'runners.csv').open() as f:
        assert len(list(csv.DictReader(f)))==213
    md=(tmp_path/'day_core.md').read_text()
    assert '9/31' in md
    assert '93/201' in md
    assert 'NO_FUNDAMENTAL_COHORT_AS_OF' in md


def test_cli_generates_all_per_race_reports(tmp_path):
    assert main(['--db',str(ARCHIVE),'--date','2026-10-28',
                 '--track','Solvalla','--out',str(tmp_path),'--details']) == 0
    assert len(list((tmp_path/'races').glob('*/race_core.md'))) == 10
    assert (tmp_path/'day_core.json').exists()


def test_repeated_runs_identical(archived):
    one=analyze_day(archived,race_date='2026-10-28')
    two=analyze_day(archived,race_date='2026-10-28')
    assert one==two


def test_fixture_contains_only_relevant_tables(archived):
    tables={r[0] for r in archived.execute("select name from sqlite_master where type='table'")}
    assert tables == {'races','runners','runner_fundamental_snapshots',
                      'provider_market_snapshots','fundamental_model_runs'}
    assert archived.execute('select count(*) from races').fetchone()[0]==50
    assert archived.execute('select count(*) from provider_market_snapshots').fetchone()[0]==238


def test_fixture_latest_market_time_pre_cutoff(archived):
    sql='''select m.observed_at_utc,m.provider_updated_at_utc,r.start_time_utc from
    provider_market_snapshots m join races r on r.race_id=m.race_id'''
    for row in archived.execute(sql):
        t=datetime.fromisoformat(row[2])-timedelta(minutes=4)
        assert datetime.fromisoformat(row[0]) <= t
        if row[1]: assert datetime.fromisoformat(row[1]) <= t


def test_fixture_latest_fundamental_time_pre_cutoff(archived):
    sql='''select m.observed_at_utc,m.feature_as_of_utc,r.start_time_utc from
    runner_fundamental_snapshots m join races r on r.race_id=m.race_id'''
    for row in archived.execute(sql):
        t=datetime.fromisoformat(row[2])-timedelta(minutes=4)
        assert datetime.fromisoformat(row[0]) <= t
        assert datetime.fromisoformat(row[1]) <= t


def test_extractor_refuses_missing_source_or_overwrite(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_day_fixture(tmp_path/'missing.sqlite',tmp_path/'out.sqlite','2026-10-28')
    existing=tmp_path/'existing.sqlite';existing.touch()
    with pytest.raises(FileExistsError):
        extract_day_fixture(ARCHIVE,existing,'2026-10-28')


def test_extractor_from_small_fixture_identical_replay(tmp_path):
    dst=tmp_path/'small.sqlite'
    stats=extract_day_fixture(ARCHIVE,dst,'2026-10-28',track='Solvalla')
    assert stats['races']==10
    c1=load();c2=load(dst)
    try:
        assert analyze_day(c1,race_date='2026-10-28',track='Solvalla') == analyze_day(c2,race_date='2026-10-28',track='Solvalla')
    finally: c1.close();c2.close()


@pytest.mark.skipif(not FULL_SOURCE.exists(), reason='Optional large original source not mounted')
def test_original_archive_replay_identical_to_compact_fixture(archived):
    full=load(FULL_SOURCE)
    try:
        assert analyze_day(full,race_date='2026-10-28') == analyze_day(archived,race_date='2026-10-28')
    finally:full.close()
