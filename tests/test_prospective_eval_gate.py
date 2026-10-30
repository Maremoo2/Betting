import json
from pathlib import Path
import pytest
from hbi.prospective_eval_gate import validate_cohort,validate_one

def row():
    p={'1':0.6,'2':0.4};q={'1':0.7,'2':0.3}
    return {'race_id':'T:1','race_start_utc':'2026-10-31T15:00:00+00:00',
            'preregistered_at_utc':'2026-10-29T12:00:00+00:00',
            'frozen_at_utc':'2026-10-31T14:54:00+00:00',
            'feature_max_asof_utc':'2026-10-31T14:49:00+00:00',
            'market_snapshot_at_utc':'2026-10-31T14:53:00+00:00',
            'outcome_observed_at_utc':'2026-10-31T18:00:00+00:00',
            'model_version':'RESEARCH_CANDIDATE_V1','champion_version':'SHADOW_CHAMPION_V1.1',
            'market_model_version':'MARKET_V1','candidate_probabilities':p,
            'champion_probabilities':q,'market_probabilities':p,
            'winner_selection_id':'1','roster_pit_certified':True,
            'source_publication_attested':True,'start_clock_history_attested':True,
            'market_free_feature_lineage_attested':True}

def test_synthetic_eligible_not_promoted():
    r=validate_one(row());assert r['status']=='EVALUABLE_RESEARCH_ONLY'
    assert not r['betting_authority'] and not r['promotion_authority']

@pytest.mark.parametrize('field',[ 'roster_pit_certified','source_publication_attested',
    'start_clock_history_attested','market_free_feature_lineage_attested'])
def test_attestation_guards(field):
    r=row();r[field]=False
    assert validate_one(r)['status']=='BLOCKED'

@pytest.mark.parametrize('field,time',[
    ('feature_max_asof_utc','2026-10-31T14:58:00+00:00'),
    ('market_snapshot_at_utc','2026-10-31T14:58:00+00:00'),
    ('frozen_at_utc','2026-10-31T14:59:00+00:00'),
    ('preregistered_at_utc','2026-11-01T15:00:00+00:00'),
    ('outcome_observed_at_utc','2026-10-31T14:00:00+00:00'),
])
def test_time_and_future_guards(field,time):
    r=row();r[field]=time
    assert validate_one(r)['status']=='BLOCKED'


def test_missing_offset_invalid():
    r=row();r['frozen_at_utc']='2026-10-31T14:54:00'
    assert 'MISSING_OR_NAIVE_TIME' in validate_one(r)['reasons']


def test_outcome_outside_field_blocks():
    r=row();r['winner_selection_id']='3'
    assert 'WINNER_OUTSIDE_FROZEN_FIELD' in validate_one(r)['reasons']


def test_market_and_challenger_keys_must_match():
    r=row();r['market_probabilities']={'1':0.6,'3':0.4}
    assert 'NONPAIRED_SELECTION_SETS' in validate_one(r)['reasons']


def test_invalid_probability_sum_or_zeros_block():
    r=row();r['candidate_probabilities']={'1':0.99,'2':0.0}
    assert 'INVALID_DISTRIBUTION' in validate_one(r)['reasons']


def test_cohort_hash_determinism_and_duplicate_rejection():
    r=row();p='a'*64
    a=validate_cohort([r],experiment_id='research-1',frozen_protocol_hash=p)
    b=validate_cohort([r],experiment_id='research-1',frozen_protocol_hash=p)
    assert a['frozen_rows_sha256']==b['frozen_rows_sha256']
    assert a['admitted']==1 and a['model_promotion_authority'] is False
    with pytest.raises(ValueError,match='Duplicate'):
        validate_cohort([r,r],experiment_id='research-1',frozen_protocol_hash=p)


def test_existing_archived_records_cannot_pass_without_pit():
    r=row();r['roster_pit_certified']=False;r['source_publication_attested']=False
    assert validate_one(r)['status']=='BLOCKED'
