"""Synthetic negative and acceptance contract for read-only prospective PIT diagnostics."""
import hashlib
import json
import sqlite3

import pytest

from hbi.core_pit_roster_verification import audit_file, parse_time

R='RIKSTOTO:S2_NR_2026-10-30:1'
REF='S2_NR_2026-10-30'
T='2026-10-30T14:54:00+00:00'
LATER='2026-10-30T14:59:00+00:00'


def fixture_db(tmp_path, *, raw_time=T, source_start='2026-10-30T15:00:00+00:00',
               stable_id=True, market_extra=None, raw_changed=False):
    path=tmp_path/'hbi.sqlite'; c=sqlite3.connect(path)
    c.executescript('''
    CREATE TABLE races(race_id TEXT,race_date TEXT,country TEXT,track TEXT,race_no INT,start_time_utc TEXT,discipline TEXT);
    CREATE TABLE provider_race_refs(race_id TEXT,provider TEXT,provider_raceday_key TEXT,discovered_at_utc TEXT);
    CREATE TABLE provider_payloads(payload_id TEXT,provider TEXT,category TEXT,provider_raceday_key TEXT,race_number INT,observed_at_utc TEXT,source_uri TEXT,payload_json TEXT);
    CREATE TABLE runners(race_id TEXT,selection_id TEXT,scratched INT,horse_name TEXT);
    CREATE TABLE runner_fundamental_snapshots(race_id TEXT,selection_id TEXT,observed_at_utc TEXT,feature_as_of_utc TEXT,full_field_history_complete INT,history_total_starts INT,history_total_wins INT,source_uri TEXT,scratched INT);
    CREATE TABLE provider_market_snapshots(race_id TEXT,selection_key TEXT,product TEXT,observed_at_utc TEXT,provider_updated_at_utc TEXT,odds_decimal REAL);
    ''')
    c.execute('insert into races values (?,?,?,?,?,?,?)',(R,'2026-10-30','SE','Synthetic',1,'2026-10-30T15:00:00+00:00','trot'))
    c.execute('insert into provider_race_refs values (?,?,?,?)',(R,'rikstoto',REF,'2026-10-30T13:00:00+00:00'))
    starts=[];ident=[]
    for number in [1,2,3]:
        sid=str(number);scratch=number==3;name=f'Horse{number}'
        starts.append({'raceNumber':1,'startNumber':number,'horseRegistrationNumber':f'TMP-{number}','horseName':name,'driverName':'Driver','extraDistance':0,'raceKey':f'{REF}#1','isScratched':scratch})
        c.execute('insert into runners values (?,?,?,?)',(R,sid,int(scratch),name+'-CHANGED' if raw_changed else name))
        c.execute('insert into runner_fundamental_snapshots values (?,?,?,?,?,?,?,?,?)',(R,sid,raw_time,raw_time,1,12,3,'test://history',int(scratch)))
        c.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',(R,sid,'V',raw_time,None,-0.02 if scratch else 2.5))
        if not scratch:ident.append({'selection_id':sid,'horse_name':name,'match_method':'UNIQUE_NAME_AND_PROGRAM_NUMBER','schema_ok':True,'reason':None,'provider_horse_id':number if stable_id else None})
    if market_extra is not None:
        c.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',(R,'99','V',raw_time,None,market_extra))
    starts_payload=json.dumps({'result':{'1':starts}})
    atg_payload=json.dumps({'passed':True,'probe_only':False,'active_runners':2,'matched_complete_runners':2,
                              'active_selections':['1','2'],'runners':ident,'race_start_utc':source_start,
                              'timestamp_basis':'FETCH_COMPLETED','source_published_at_utc':None})
    c.execute('insert into provider_payloads values (?,?,?,?,?,?,?,?)',('raw-1','rikstoto','RACEDAY_STARTS',REF,1,raw_time,'test://starts',starts_payload))
    c.execute('insert into provider_payloads values (?,?,?,?,?,?,?,?)',('atg-1','atg','FULL_FIELD_ONLY_V1',R,1,raw_time,'test://atg',atg_payload))
    c.commit();c.close();return path


def run(path, asof='2026-10-30T15:10:00+00:00'):
    return audit_file(path,[R],asof=asof)['races'][0]


def change(path, sql, args=()):
    with sqlite3.connect(path) as c:c.execute(sql,args)


def test_happy_path_source_observed_but_no_full_pit_certification(tmp_path):
    r=run(fixture_db(tmp_path))
    assert r['raw_input_ready_at_cutoff']
    assert r['status']=='SOURCE_OBSERVED_UNATTESTED'
    assert not r['source_publication_proven'] and not r['pit_certified']
    assert r['raw_active_count']==2


def test_clock_earlier_than_mutable_race_start_blocks_late_inputs(tmp_path):
    r=run(fixture_db(tmp_path,source_start='2026-10-30T14:57:00+00:00'))
    assert r['clock_disagreement_seconds']==180
    assert r['conservative_cutoff_utc']=='2026-10-30T14:53:00+00:00'
    assert not r['raw_input_ready_at_cutoff']
    assert 'NO_PRE_CUTOFF_RIKSTOTO_STARTS' in r['blockers']


def test_late_only_payload_does_not_backfill(tmp_path):
    r=run(fixture_db(tmp_path,raw_time=LATER))
    assert not r['raw_input_ready_at_cutoff']
    assert r['source_snapshots']['rikstoto_starts']['observed_at_utc'] is None


def test_race_not_yet_at_t4_is_future(tmp_path):
    r=run(fixture_db(tmp_path),asof='2026-10-30T14:40:00+00:00')
    assert r['status']=='FUTURE' and 'TMINUS4_NOT_OBSERVED' in r['blockers']


def test_unverified_provider_horse_id_fails(tmp_path):
    r=run(fixture_db(tmp_path,stable_id=False))
    assert not r['identity_matched_at_source_time']
    assert 'ATG_IDENTITY_UNVERIFIED' in r['blockers']


def test_current_mutable_roster_difference_is_exposed(tmp_path):
    r=run(fixture_db(tmp_path,raw_changed=True))
    assert not r['mutable_roster_agrees_now'] and 'MUTABLE_ROSTER_DIFFERS_FROM_RAW' in r['blockers']


def test_off_field_unpriced_sentinel_allowed_only_when_exact(tmp_path):
    assert run(fixture_db(tmp_path))['win_market_complete_at_cutoff'] is True


@pytest.mark.parametrize('price', [5.0,-0.01,float('nan')])
def test_off_field_priced_or_unrecognized_marker_blocks(tmp_path,price):
    assert not run(fixture_db(tmp_path,market_extra=price))['win_market_complete_at_cutoff']


def test_duplicate_start_number_blocks(tmp_path):
    path=fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        r=c.execute("select payload_json from provider_payloads where payload_id='raw-1'").fetchone()
        payload=json.loads(r[0]); payload['result']['1'].append(dict(payload['result']['1'][0]))
        c.execute('update provider_payloads set payload_json=? where payload_id=?',(json.dumps(payload),'raw-1'))
    assert 'DUPLICATE_START_NUMBER' in run(path)['blockers']


def test_ambiguous_scratch_blocks(tmp_path):
    path=fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        d=json.loads(c.execute("select payload_json from provider_payloads where payload_id='raw-1'").fetchone()[0]);d['result']['1'][0]['isScratched']=None
        c.execute("update provider_payloads set payload_json=? where payload_id='raw-1'",(json.dumps(d),))
    assert 'MALFORMED_START_ROW' in run(path)['blockers']


def test_wrong_race_key_blocks(tmp_path):
    path=fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        d=json.loads(c.execute("select payload_json from provider_payloads where payload_id='raw-1'").fetchone()[0]);d['result']['1'][0]['raceKey']='OTHER#1'
        c.execute("update provider_payloads set payload_json=? where payload_id='raw-1'",(json.dumps(d),))
    assert 'RACE_KEY_MISMATCH' in run(path)['blockers']


def test_unknown_fundamental_asof_blocks(tmp_path):
    path=fixture_db(tmp_path)
    change(path,"update runner_fundamental_snapshots set feature_as_of_utc='2026-10-30T15:01:00+00:00'")
    assert not run(path)['fundamental_complete_at_cutoff']


def test_future_provider_market_update_blocks(tmp_path):
    path=fixture_db(tmp_path)
    change(path,"update provider_market_snapshots set provider_updated_at_utc='2026-10-30T15:01:00+00:00'")
    assert not run(path)['win_market_complete_at_cutoff']


def test_duplicate_price_selection_blocks(tmp_path):
    path=fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',(R,'1','V',T,None,5.5))
    assert not run(path)['win_market_complete_at_cutoff']


def test_reject_mixed_provider_identity_keys(tmp_path):
    path=fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        d=json.loads(c.execute("select payload_json from provider_payloads where payload_id='atg-1'").fetchone()[0]);d['active_selections']=['1','3']
        c.execute("update provider_payloads set payload_json=? where payload_id='atg-1'",(json.dumps(d),))
    assert 'ATG_ACTIVE_SET_MISMATCH' in run(path)['blockers']


def test_original_db_sha_unchanged(tmp_path):
    path=fixture_db(tmp_path);h=hashlib.sha256(path.read_bytes()).hexdigest()
    report=audit_file(path,[R],asof='2026-10-30T15:10:00+00:00')
    assert report['total']==1
    assert hashlib.sha256(path.read_bytes()).hexdigest()==h


def test_source_datetime_requires_offset():
    assert parse_time('2026-10-30T14:45:00') is None


def test_missing_db_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):audit_file(tmp_path/'absent.sqlite',[R],asof='2026-10-30T15:10:00+00:00')


def test_null_extra_market_price_is_rejected(tmp_path):
    path=fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',(R,'99','V',T,None,None))
    assert not run(path)['win_market_complete_at_cutoff']
