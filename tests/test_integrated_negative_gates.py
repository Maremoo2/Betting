"""Targeted fail-closed source/identity/protocol regressions for integration QA.

Only synthetic provider bytes; never requires live access or changes canonical HBI.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from test_pit_roster_verification import R, T, fixture_db, run
from test_prospective_eval_gate import row

from hbi.core_pit_roster_verification import audit_file
from hbi.prospective_eval_gate import validate_cohort, validate_one


def _duplicate_payload(path, provider, category, *, mutate=False):
    with sqlite3.connect(path) as db:
        before = db.execute(
            "SELECT payload_id,provider,category,provider_raceday_key,race_number,"
            "observed_at_utc,source_uri,payload_json FROM provider_payloads "
            "WHERE provider=? AND category=?", (provider, category),
        ).fetchone()
        assert before
        clone = list(before)
        clone[0] = f"another-{provider}"
        if mutate:
            data = json.loads(clone[-1])
            if category == "RACEDAY_STARTS":
                data['result']['1'][0]['horseName'] = 'CONFLICT'
            else:
                data['runners'][0]['horse_name'] = 'CONFLICT'
            clone[-1] = json.dumps(data)
        db.execute("INSERT INTO provider_payloads VALUES (?,?,?,?,?,?,?,?)", clone)


@pytest.mark.parametrize('provider,category,reason', [
    ('rikstoto','RACEDAY_STARTS','CONFLICTING_SAME_INSTANT_RAW_STARTS'),
    ('atg','FULL_FIELD_ONLY_V1','CONFLICTING_SAME_INSTANT_ATG_CLOCK_SOURCE'),
])
def test_conflicting_same_timestamp_source_fails_closed(tmp_path,provider,category,reason):
    p=fixture_db(tmp_path)
    _duplicate_payload(p,provider,category,mutate=True)
    outcome=run(p)
    assert outcome['status']=='BLOCKED'
    assert reason in outcome['blockers']
    assert outcome['raw_input_ready_at_cutoff'] is False
    assert outcome['pit_certified'] is False


@pytest.mark.parametrize('provider,category', [
    ('rikstoto','RACEDAY_STARTS'),('atg','FULL_FIELD_ONLY_V1'),
])
def test_identical_duplicate_source_payload_is_deterministic(tmp_path,provider,category):
    p=fixture_db(tmp_path)
    _duplicate_payload(p,provider,category,mutate=False)
    outcome=run(p)
    assert outcome['raw_input_ready_at_cutoff'] is True
    assert outcome['status']=='SOURCE_OBSERVED_UNATTESTED'


def test_duplicate_stable_provider_horse_id_fails(tmp_path):
    p=fixture_db(tmp_path)
    with sqlite3.connect(p) as db:
        d=json.loads(db.execute("SELECT payload_json FROM provider_payloads WHERE provider='atg'").fetchone()[0])
        d['runners'][1]['provider_horse_id'] = d['runners'][0]['provider_horse_id']
        db.execute("UPDATE provider_payloads SET payload_json=? WHERE provider='atg'",(json.dumps(d),))
    outcome=run(p)
    assert 'ATG_DUPLICATED_PROVIDER_HORSE_ID' in outcome['blockers']
    assert not outcome['raw_input_ready_at_cutoff']


@pytest.mark.parametrize('bad_id',[True,0,'not-numeric','0',None,[],{}])
def test_unstable_provider_horse_id_fails(tmp_path,bad_id):
    p=fixture_db(tmp_path)
    with sqlite3.connect(p) as db:
        d=json.loads(db.execute("SELECT payload_json FROM provider_payloads WHERE provider='atg'").fetchone()[0])
        d['runners'][0]['provider_horse_id']=bad_id
        db.execute("UPDATE provider_payloads SET payload_json=? WHERE provider='atg'",(json.dumps(d),))
    outcome=run(p)
    assert not outcome['identity_matched_at_source_time']
    assert outcome['status']=='BLOCKED'


def test_duplicate_physical_race_ids_are_invalid_denominator(tmp_path):
    p=fixture_db(tmp_path)
    with pytest.raises(ValueError,match='Duplicate race IDs'):
        audit_file(p,[R,R],asof='2026-10-30T15:10:00+00:00')


def test_empty_denominator_is_not_a_successful_audit(tmp_path):
    p=fixture_db(tmp_path)
    with pytest.raises(ValueError,match='NO_EVIDENCE'):
        audit_file(p,[],asof='2026-10-30T15:10:00+00:00')


def test_naive_asof_fails_before_sql(tmp_path):
    p=fixture_db(tmp_path)
    with pytest.raises(ValueError,match='Aware asof'):
        audit_file(p,[R],asof='2026-10-30T15:10:00')


@pytest.mark.parametrize('bad_hash',['z'*64,'1'*63,'1'*65,None,42,''])
def test_fake_or_malformed_protocol_hash_cannot_be_admitted(bad_hash):
    with pytest.raises(ValueError,match='SHA-256'):
        validate_cohort([row()],experiment_id='future-protocol',frozen_protocol_hash=bad_hash)


def test_empty_future_experiment_reports_no_evidence_not_pass():
    report=validate_cohort([],experiment_id='future-protocol',frozen_protocol_hash='0'*64)
    assert report['status']=='NO_EVIDENCE'
    assert report['count']==report['admitted']==0
    assert report['model_promotion_authority'] is False


@pytest.mark.parametrize('bad_id',[None,0,{},' ',''])
def test_invalid_experiment_id_blocked(bad_id):
    with pytest.raises(ValueError,match='Nonempty experiment'):
        validate_cohort([row()],experiment_id=bad_id,frozen_protocol_hash='0'*64)


def test_nondict_records_cannot_be_admitted():
    with pytest.raises(ValueError,match='mappings'):
        validate_cohort([row(),None],experiment_id='future-protocol',frozen_protocol_hash='0'*64)


def test_user_claimed_booleans_are_not_external_attestation():
    # A synthetically self-attested happy path cannot prove actual preregistration.
    report=validate_cohort([row()],experiment_id='future-protocol',frozen_protocol_hash='0'*64)
    assert report['status']=='UNATTESTED_CLAIMS_ONLY'
    assert report['admitted']==1
    assert not report['model_promotion_authority']
    assert not report['betting_authority']
