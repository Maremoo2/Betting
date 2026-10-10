import copy
import json
from pathlib import Path

import pytest

from hbi.research_lab import audit_race, digest, evaluate, register


def fixture():
    race = {'race_id': 'test', 'start_at': '2018-01-02T12:00:00Z',
            'active_runner_ids': ['a', 'b'], 'winner_id': 'a', 'result_complete': True,
            'identity_verified': True, 'country': 'NO',
            'market_snapshot_type': 'PRE_RACE_VERIFIED',
            'market_available_at': '2018-01-02T11:59:00Z', 'runners': []}
    for name, p in [('a', .6), ('b', .4)]:
        race['runners'].append({'runner_id': name, 'identity_verified': True,
                                'model_probability': p, 'market_probability': .5,
                                'prediction_at': '2018-01-02T11:59:00Z',
                                'features': {'past_starts': {'value': 3,
                                             'source_sha256': 'fixture',
                                             'event_at': '2017-12-01T12:00:00Z',
                                             'available_at': '2017-12-01T13:00:00Z'}}})
    plan = {'experiment_id': 'smoke', 'hypothesis_id': 'HYP-002', 'git_commit': 'fixture',
            'features': ['past_starts'], 'model': 'synthetic', 'hyperparameters': {},
            'dataset_sha256': digest([race]), 'primary_metrics': ['log_loss', 'brier'],
            'exclusions': ['non-PIT', 'dead heat'], 'slices': ['country'],
            'train_period': ['2015-01-01T00:00:00Z', '2017-12-31T23:59:59Z'],
            'test_period': ['2018-01-01T00:00:00Z', '2018-12-31T23:59:59Z'],
            'data_cutoff': '2018-12-31T23:59:59Z', 'test_role': 'development'}
    return race, plan


def test_registration_and_evaluation(tmp_path):
    race, plan = fixture()
    registry = json.loads(Path('research/registry.json').read_text())
    registration = register(plan, registry, tmp_path / 'registration.json')
    result = evaluate(registration, [race], tmp_path / 'result.json')
    assert result['model']['brier'] == pytest.approx(.32)
    assert result['paired_log_loss_difference'] < 0
    assert result['economic_result'].startswith('NOT_ESTABLISHED')
    with pytest.raises(FileExistsError):
        register(plan, registry, tmp_path / 'registration.json')
    with pytest.raises(ValueError, match='checksum'):
        evaluate(registration, [], tmp_path / 'other.json')


@pytest.mark.parametrize('failure', ['future_feature', 'late_available', 'missing_runner',
                                   'identity', 'terminal_market', 'late_prediction',
                                   'normalization', 'dead_heat'])
def test_fail_closed(failure):
    race, plan = fixture()
    if failure == 'future_feature':
        race['runners'][0]['features']['past_starts']['event_at'] = race['start_at']
    elif failure == 'late_available':
        race['runners'][0]['features']['past_starts']['available_at'] = race['start_at']
    elif failure == 'missing_runner':
        race['runners'].pop()
    elif failure == 'identity':
        race['runners'][0]['identity_verified'] = False
    elif failure == 'terminal_market':
        race['market_snapshot_type'] = 'HISTORICAL_TERMINAL'
    elif failure == 'late_prediction':
        race['runners'][0]['prediction_at'] = race['start_at']
    elif failure == 'normalization':
        race['runners'][0]['model_probability'] = .9
    else:
        race['dead_heat'] = True
    with pytest.raises(ValueError):
        audit_race(race, plan)


def test_lockbox_and_overlap_blocked(tmp_path):
    _, plan = fixture()
    registry = json.loads(Path('research/registry.json').read_text())
    locked = copy.deepcopy(plan)
    locked['test_role'] = 'historical_lockbox_candidate'
    with pytest.raises(ValueError, match='Lockbox'):
        register(locked, registry, tmp_path / 'locked.json')
    plan['train_period'][1] = plan['test_period'][0]
    with pytest.raises(ValueError, match='Overlapping'):
        register(plan, registry, tmp_path / 'overlap.json')
