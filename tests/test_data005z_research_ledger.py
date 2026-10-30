"""Research-only DATA-005Z gate. Never imports this ledger into an HBI runtime/model."""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'research' / 'data005z-pilot-history-evidence-v1.json'
SHA = re.compile(r'^[0-9a-f]{64}$')
EXPECTED_TIERS = {
    'DNT_RESULT_LINK_REVIEWED_BY_SAME_AGENT_NOT_DOUBLE_READ': 104,
    'TRIAL_DNT_SOURCE_CORROBORATED_NOT_RACE_START': 2,
    'SECONDARY_RESULT_FIELD_MATCH': 12,
    'SECONDARY_PARTIAL_RESULT': 1,
    'STARTLIST_ONLY_NO_RESULT': 1,
}
REVIEW_STATUSES = set(EXPECTED_TIERS)


def validate(data: dict) -> None:
    def require(cond: bool, message: str) -> None:
        if not cond:
            raise ValueError(message)

    require(data.get('schema') == 'DATA005Z_RESEARCH_REVIEW_LEDGER_V1', 'UNKNOWN_SCHEMA')
    flags = data['permissions']
    for flag in ('research_only', 'no_runtime_reader', 'not_an_intelligence_bridge_event',
                 'no_model_promotion'):
        require(flags.get(flag) is True, 'UNSAFE_PERMISSION:' + flag)
    for flag in ('model_eligible', 'bet_authorized'):
        require(flags.get(flag) is False, 'UNSAFE_PERMISSION:' + flag)
    source = data['source_artifact']
    require(SHA.fullmatch(source['archive_sha256']) is not None, 'BAD_ARCHIVE_SHA')
    require(source['capture_sha256_verified'] is True, 'SOURCE_HASH_NOT_VERIFIED')
    require(source['capture_record_count'] == 5, 'SOURCE_RESPONSE_COUNT')
    versions = source['source_program_versions']
    require({v['label'] for v in versions} == {
        'bjerke_20261031_program_0', 'momarken_20261101_program_0'
    } and len(versions) == 2, 'BAD_PROGRAM_SET')
    program_sha = set()
    for v in versions:
        require(SHA.fullmatch(v['pdf_sha256']) is not None, 'BAD_PROGRAM_SHA')
        observed = datetime.fromisoformat(v['capture_utc'])
        require(observed.tzinfo is not None and observed.utcoffset() is not None,
                'UNZONED_CAPTURE')
        program_sha.add(v['pdf_sha256'])
    require(len(program_sha) == 2, 'SAME_PROGRAM_SHA')
    require(all(SHA.fullmatch(x) is not None for x in data['input_file_digests'].values()),
            'BAD_INPUT_SHA')
    require(set(data['input_file_digests']) == {
        'history_120', 'swedish_14', 'identity_24', 'initial_23_review'
    }, 'UNEXPECTED_INPUTS')
    history = data['historical_rows']
    identities = data['identity_candidates']
    require(len(history) == 120, 'HISTORY_COUNT')
    require(len(identities) == 24, 'IDENTITY_COUNT')
    require(len({i['candidate_only_fingerprint_sha256'] for i in identities}) == 24,
            'DUPLICATE_CANDIDATE_FINGERPRINT')
    names = set()
    start_numbers = set()
    for i in identities:
        key = (i['target_race_id'], i['horse_name_from_program'])
        require(key not in names, 'DUPLICATE_CANDIDATE_NAME')
        names.add(key)
        slot = (i['target_race_id'], i['current_start_number'])
        require(slot not in start_numbers, 'DUPLICATE_START_NUMBER')
        start_numbers.add(slot)
        require(i['source_pdf_sha256'] in program_sha, 'IDENTITY_SOURCE_MISMATCH')
        require(SHA.fullmatch(i['candidate_only_fingerprint_sha256']) is not None,
                'INVALID_CANDIDATE_FINGERPRINT')
        require(i['official_registration_namespace'] is None
                and i['official_registration_id'] is None, 'FALSE_PERMANENT_ID')
        for flag in ('ueln_attested', 'individual_identity_verified',
                     'history_model_eligible', 'bet_authorized'):
            require(i[flag] is False, 'UNSAFE_IDENTITY_FLAG:' + flag)
    require(Counter(i['target_race_id'] for i in identities) == {
        'RIKSTOTO:BJ_NR_2026-10-31:2': 12,
        'RIKSTOTO:MO_NR_2026-11-01:2': 12,
    }, 'IDENTITY_FIELD_COUNT')

    history_keys = set()
    row_keys = set()
    foreign_ids = set()
    for r in history:
        key = (r['target_race_id'], r['horse_name_from_program'],
               r['program_history_code_raw'])
        require(key not in history_keys, 'DUPLICATE_HISTORY_ROW')
        history_keys.add(key)
        require((r['target_race_id'], r['horse_name_from_program']) in names,
                'ORPHAN_HISTORY_HORSE')
        require(r['source_pdf_sha256'] in program_sha, 'HISTORY_SOURCE_MISMATCH')
        require(SHA.fullmatch(r['row_key_sha256']) is not None, 'BAD_ROW_KEY')
        require(r['row_key_sha256'] not in row_keys, 'DUPLICATE_ROW_KEY')
        row_keys.add(r['row_key_sha256'])
        require(r['source_review_tier'] in REVIEW_STATUSES, 'UNRECOGNIZED_REVIEW_TIER')
        for flag in ('source_result_response_hash_attested',
                     'independent_human_double_read', 'history_model_eligible',
                     'bet_authorized'):
            require(r[flag] is False, 'UNSAFE_HISTORY_FLAG:' + flag)
        if r['source_review_tier'] == 'DNT_RESULT_LINK_REVIEWED_BY_SAME_AGENT_NOT_DOUBLE_READ':
            require((r['source_review_url'] or '').startswith('https://old.travsport.no/'),
                    'MISSING_OR_WRONG_DNT_RESULT_URL')
            require(r['swedish_review_id'] is None, 'DNT_SV_LINK_CONFLICT')
        elif r['source_review_tier'].startswith('SECONDARY_') or r['source_review_tier'] == 'STARTLIST_ONLY_NO_RESULT':
            require(r['swedish_review_id'] is not None, 'MISSING_SWEDISH_LINK')
            require((r['source_review_url'] or '').startswith('https://'),
                    'MISSING_SWEDISH_SUPPORT_URL')
            require(r['swedish_review_id'] not in foreign_ids, 'DUPLICATE_SWEDISH_REVIEW')
            foreign_ids.add(r['swedish_review_id'])
        else:
            require(r['swedish_review_id'] is None, 'TRIAL_SV_LINK_CONFLICT')
    require(foreign_ids == {f'SV-{i:02d}' for i in range(1, 15)},
            'INCOMPLETE_SWEDISH_REVIEW_SET')
    require(Counter(r['source_review_tier'] for r in history) == EXPECTED_TIERS,
            'SOURCE_REVIEW_COUNT_CONFLICT')
    require(Counter(r['target_race_id'] for r in history) == {
        'RIKSTOTO:BJ_NR_2026-10-31:2': 60,
        'RIKSTOTO:MO_NR_2026-11-01:2': 60,
    }, 'HISTORICAL_FIELD_COUNT')
    summary = data['summary']
    require(summary['history_rows'] == 120 and summary['identity_candidates'] == 24
            and summary['swedish_history_rows'] == 14, 'INCORRECT_SUMMARY')
    require(summary['source_review_tiers'] == EXPECTED_TIERS, 'SUMMARY_REVIEW_MISMATCH')
    require(summary['norwegian_missing_result_urls_reconciled_from_earlier_journal'] == 23
            and summary['norwegian_result_url_coverage'] == 104,
            'RECONCILIATION_NOT_DOCUMENTED')
    for field in ('first_party_swedish_result_bytes_verified',
                  'official_permanent_ids_attested', 'human_independent_reviews',
                  'model_eligible_rows', 'bet_authorized_rows'):
        require(summary[field] == 0, 'PREMATURE_PROMOTION:' + field)


def load() -> dict:
    return json.loads(LEDGER.read_text(encoding='utf-8'))


def test_source_linkage_research_only_gate():
    validate(load())


@pytest.mark.parametrize('mutation,expected', [
    (lambda d: d['historical_rows'].append(copy.deepcopy(d['historical_rows'][0])),
     'HISTORY_COUNT'),
    (lambda d: d['historical_rows'][0].update(history_model_eligible=True),
     'UNSAFE_HISTORY_FLAG'),
    (lambda d: d['identity_candidates'][0].update(official_registration_id='57800000'),
     'FALSE_PERMANENT_ID'),
    (lambda d: d['source_artifact'].update(capture_sha256_verified=False),
     'SOURCE_HASH_NOT_VERIFIED'),
    (lambda d: d['historical_rows'][0].update(source_pdf_sha256='x' * 64),
     'HISTORY_SOURCE_MISMATCH'),
    (lambda d: d['permissions'].update(model_eligible=True),
     'UNSAFE_PERMISSION'),
    (lambda d: d['summary'].update(official_permanent_ids_attested=1),
     'PREMATURE_PROMOTION'),
    (lambda d: d['source_artifact']['source_program_versions'][0].update(
        capture_utc='2026-10-30T09:59:32'), 'UNZONED_CAPTURE'),
])
def test_fail_closed_on_invalid_evidence(mutation, expected):
    evidence = load()
    mutation(evidence)
    with pytest.raises(ValueError, match=expected):
        validate(evidence)


def test_provenance_urls_restored_without_source_promotion():
    evidence = load()
    records = [r for r in evidence['historical_rows'] if r['source_review_tier'].startswith('DNT_')]
    assert len(records) == 104
    assert all(r['source_review_url'] and not r['source_result_response_hash_attested'] for r in records)
    assert evidence['summary']['norwegian_missing_result_urls_reconciled_from_earlier_journal'] == 23


def test_no_pipeline_or_model_imports_in_tested_review_ledger():
    evidence = load()
    assert evidence['permissions']['no_runtime_reader'] is True
    assert evidence['summary']['model_eligible_rows'] == 0
    assert evidence['summary']['bet_authorized_rows'] == 0
