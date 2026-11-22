"""TEST_ONLY structural cases; authentic archive replay is reported separately."""
import hashlib
import json

import pytest
from test_mvp023a_historical_coverage import fixture, put_json

from hbi.mvp023a_historical_coverage import build_coverage, digest


def test_unbound_cache_is_never_read_or_counted_as_original(tmp_path):
    fixture(tmp_path, market=False)
    path = '/racedays/BJ_NR_2020-01-04/starts'
    cache = tmp_path / 'raw-markets' / (hashlib.sha256(path.encode()).hexdigest() + '.json')
    put_json(cache, {'test_only_corrupt_unbound_cache': True})
    row = build_coverage(tmp_path)['by_race'][0]
    assert row['categories']['DISCOVERED_METADATA_ONLY']
    assert not row['categories']['SOURCE_ARCHIVED']
    assert not row['categories']['PIT_MODEL_ELIGIBLE']
    assert row['source_receipt_sha256'] == {}


def test_source_metadata_strata_are_preserved_without_feature_approval(tmp_path):
    fixture(tmp_path, market=False)
    file = tmp_path / 'inventory/2020-01.json'
    doc = json.loads(file.read_bytes())
    meeting = doc['body']['result'][0]
    meeting['sportType'] = 'T'
    meeting['races'][0].update(startMethod='Auto', distance=2140, raceType='TEST_ONLY')
    doc['body_sha256'] = digest(doc['body'])
    put_json(file, doc)
    report = build_coverage(tmp_path)
    row = report['by_race'][0]
    assert row['metadata_dimensions']['sport_type'] == 'T'
    assert row['metadata_dimensions']['start_method'] == 'Auto'
    assert row['metadata_source_sha256'] == doc['body_sha256']
    assert row['metadata_source_uri'] == doc['url']
    assert row['metadata_dimensions_role'] == 'SOURCE_METADATA_NOT_MODEL_FEATURES'
    assert report['by_sport_type']['T']['physical_races'] == 1
    assert report['by_start_method']['Auto']['physical_races'] == 1
    assert report['by_distance']['2140']['physical_races'] == 1
    assert report['by_runner_count']['UNKNOWN']['physical_races'] == 1
    assert report['intended_scope_counts']['NO_SE_TROT_METADATA_REFERENCES'] == 1
    assert not row['categories']['HISTORY_FEATURES_VERIFIED']
    assert not row['categories']['PIT_MODEL_ELIGIBLE']


def test_missing_sport_and_unverified_country_are_not_guessed(tmp_path):
    fixture(tmp_path, market=False)
    report = build_coverage(tmp_path)
    assert report['by_sport_type']['UNKNOWN']['physical_races'] == 1
    assert report['intended_scope_counts']['NO_SE_TROT_METADATA_REFERENCES'] == 0
    for key in ('by_distance', 'by_runner_count', 'by_race_type'):
        assert report[key]['UNKNOWN']['physical_races'] == 1


def test_bound_original_integrity_failure_still_blocks(tmp_path):
    case = fixture(tmp_path)
    path = case['row']['sources'][0]['path']
    cache = tmp_path / 'raw-markets' / (hashlib.sha256(path.encode()).hexdigest() + '.json')
    body = json.loads(cache.read_bytes())
    body['body_sha256'] = '0' * 64
    put_json(cache, body)
    with pytest.raises(ValueError, match='ORIGINAL_SOURCE_SHA_OR_ORIGIN_CONFLICT'):
        build_coverage(tmp_path)
