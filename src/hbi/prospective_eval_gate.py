"""Fail-closed, research-only prospective paired evaluation admission gate.

Not a model trainer, not a performance claim, not a Champion/Bet promotion gate.
All timestamps, source publication and code/feature lineage must be independently
recorded before a race; outcome is admitted only after the race start.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta


def utc_time(value):
    try:
        dt=datetime.fromisoformat(str(value))
    except (ValueError,TypeError):return None
    return dt if dt.utcoffset() is not None else None


def distribution(value):
    if not isinstance(value,dict) or len(value)<2:return False
    # JSON strings and booleans are not numeric probability evidence.
    if any(type(v) not in (int, float) for v in value.values()):return False
    if any(not isinstance(k,str) or not k.strip() for k in value):return False
    try:
        vals=[float(v) for v in value.values()]
    except (TypeError,ValueError,OverflowError):return False
    return (all(math.isfinite(v) and 0<v<1 for v in vals)
            and math.isclose(sum(vals),1,rel_tol=0,abs_tol=1e-9))


def validate_one(record):
    errors=[]
    keys=['race_id','race_start_utc','preregistered_at_utc','frozen_at_utc',
          'feature_max_asof_utc','market_snapshot_at_utc','outcome_observed_at_utc',
          'model_version','champion_version','market_model_version',
          'candidate_probabilities','champion_probabilities','market_probabilities',
          'winner_selection_id','roster_pit_certified','source_publication_attested',
          'start_clock_history_attested','market_free_feature_lineage_attested']
    for k in keys:
        if k not in record:errors.append('MISSING_'+k.upper())
    if errors:return {'race_id':record.get('race_id'),'status':'BLOCKED','reasons':errors}
    times={k:utc_time(record.get(k)) for k in (
        'race_start_utc','preregistered_at_utc','frozen_at_utc',
        'feature_max_asof_utc','market_snapshot_at_utc','outcome_observed_at_utc')}
    if any(v is None for v in times.values()): errors.append('MISSING_OR_NAIVE_TIME')
    else:
        start=times['race_start_utc'];prereg=times['preregistered_at_utc'];frozen=times['frozen_at_utc']
        if not prereg<=frozen<=start-timedelta(minutes=4):errors.append('PREREG_FREEZE_OR_T4_ORDER')
        if times['feature_max_asof_utc']>frozen:errors.append('FEATURE_FUTURE_LEAKAGE')
        if times['market_snapshot_at_utc']>frozen:errors.append('MARKET_FUTURE_LEAKAGE')
        if times['outcome_observed_at_utc']<start:errors.append('OUTCOME_RECORDED_BEFORE_START')
    for k in ('roster_pit_certified','source_publication_attested',
              'start_clock_history_attested','market_free_feature_lineage_attested'):
        if record[k] is not True:errors.append('UNATTESTED_'+k.upper())
    for k in ('model_version','champion_version','market_model_version'):
        if not isinstance(record[k],str) or not record[k].strip():errors.append('INVALID_MODEL_VERSION')
    arrays=('candidate_probabilities','champion_probabilities','market_probabilities')
    if not all(distribution(record[k]) for k in arrays):errors.append('INVALID_DISTRIBUTION')
    elif not (set(record[arrays[0]])==set(record[arrays[1]])==set(record[arrays[2]])):
        errors.append('NONPAIRED_SELECTION_SETS')
    if all(distribution(record[k]) for k in arrays) and str(record['winner_selection_id']) not in record[arrays[0]]:
        errors.append('WINNER_OUTSIDE_FROZEN_FIELD')
    return {'race_id':record['race_id'],'status':'EVALUABLE_RESEARCH_ONLY' if not errors else 'BLOCKED',
            'reasons':sorted(set(errors)),'betting_authority':False,'promotion_authority':False}


def validate_cohort(records, *, experiment_id, frozen_protocol_hash):
    if not isinstance(records,list):raise TypeError('Expected list of frozen rows')
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError('Nonempty experiment ID required')
    if not isinstance(frozen_protocol_hash, str) or re.fullmatch(r'[a-fA-F0-9]{64}', frozen_protocol_hash) is None:
        raise ValueError('Real SHA-256-encoded protocol reference required')
    if not records:
        return {'schema': 'PROSPECTIVE_PAIRED_EVALUATION_GATE_V1',
                'experiment_id': experiment_id, 'protocol_sha256': frozen_protocol_hash,
                'status': 'NO_EVIDENCE', 'count': 0, 'admitted': 0, 'blocked': 0,
                'model_promotion_authority': False, 'betting_authority': False,
                'cases': []}
    if any(not isinstance(x, dict) for x in records):
        raise ValueError('All race records must be mappings')
    results=[validate_one(x) for x in records]
    ids=[r.get('race_id') for r in results]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate physical race IDs; must resolve before pairing')
    fingerprint=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schema':'PROSPECTIVE_PAIRED_EVALUATION_GATE_V1','experiment_id':experiment_id,
            'status': 'UNATTESTED_CLAIMS_ONLY',
            'protocol_sha256':frozen_protocol_hash,'frozen_rows_sha256':fingerprint,
            'count':len(results),'admitted':sum(r['status']=='EVALUABLE_RESEARCH_ONLY' for r in results),
            'blocked':sum(r['status']=='BLOCKED' for r in results),
            'model_promotion_authority':False,'betting_authority':False,
            'cases':results}
