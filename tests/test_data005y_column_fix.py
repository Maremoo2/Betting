"""DATA-005Y: source-backed research PDF column alignment; never model admission.

Synthetic rows test rejection behavior. Authentic DNT PDFs are supplied only through
HBI_DNT_PROBE_DIR and are never committed to this repository.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from datetime import date
from pathlib import Path

import fitz
import pytest

from hbi.extract_program_history import (
    PILOT_FIELDS,
    audit_exit_code,
    extract,
    verify_and_export_probe,
)


class ControlledPage:
    rect = fitz.Rect(0, 0, 595, 842)

    def __init__(self, *, rows=5, duplicate_pr=False, omit_odds=False, broken_order=False):
        self.rows = rows
        self.duplicate_pr = duplicate_pr
        self.omit_odds = omit_odds
        self.broken_order = broken_order

    def search_for(self, name):
        return [fitz.Rect(70.866, 107.45, 160.3, 118)] if name == 'FAKE HORSE' else []

    def get_text(self, mode):
        assert mode == 'words'
        words = []
        for index in range(self.rows):
            y = 117.2 + index * 7.4
            # Deliberately start the long prize and odds tokens left of the old
            # fixed column limits. PDF x1, not x0, is the correct column cue.
            cols = [
                (231.2, 260.1, 'A. Driver'),
                (292.0, 298.0, 'B'),
                (315.2, 340.1, f'{10 + index:02d}/10-01/{index+1}'),
                (355.8, 373.9, '2140'),
                (377.3, 380.4, str(index)),
                (385.0, 406.0, '31,0'),
                (411.0, 425.0, '175'),
            ]
            if not self.omit_odds:
                cols.append((430.0, 444.0, '1072'))
            if self.duplicate_pr:
                cols.append((416.0, 428.0, '99'))
            if self.broken_order:
                cols[-1] = (430.0, 430.9, '1072')
            words.extend((x0, y, x1, y+5, value, 0, 0, 0) for x0,x1,value in cols)
        return words


def _test_extract(page):
    return extract(page, ['FAKE HORSE'], 'RIKSTOTO:FAKE_NR_2026-11-01:2', date(2026, 11, 1), 'a' * 64)


def test_long_pr_and_odds_are_assigned_by_glyph_right_edge():
    records = _test_extract(ControlledPage())
    assert len(records) == 5
    assert [(r['km_time_raw'], r['program_pr_column_raw'], r['program_odds_column_raw'])
            for r in records] == [('31,0', '175', '1072')] * 5
    assert all(r['exact_horse_identity_attested'] is False for r in records)
    assert all(r['historic_result_independently_verified'] is False for r in records)
    assert all(r['history_candidate_not_model_eligible'] is True for r in records)
    assert all(r['year_inferred_not_attested'] is True for r in records)


def test_missing_odds_is_a_structural_error_not_silent_partial_export():
    with pytest.raises(ValueError, match='HISTORY_COLUMN_MISALIGNMENT'):
        _test_extract(ControlledPage(omit_odds=True))


def test_split_pr_with_two_source_tokens_fails_closed():
    with pytest.raises(ValueError, match='HISTORY_COLUMN_MISALIGNMENT'):
        _test_extract(ControlledPage(duplicate_pr=True))


def test_low_confidence_spanning_glyph_does_not_change_source_column():
    with pytest.raises(ValueError, match='HISTORY_COLUMN_MISALIGNMENT'):
        _test_extract(ControlledPage(broken_order=True))


def test_missing_fifth_form_row_fails_closed():
    with pytest.raises(ValueError, match='REQUIRE_FIVE_VISIBLE_FORM_ROWS'):
        _test_extract(ControlledPage(rows=4))


@pytest.fixture
def authentic_source_root(tmp_path):
    given = os.environ.get('HBI_DNT_PROBE_DIR')
    if not given:
        pytest.skip('Real DNT archive not provided via HBI_DNT_PROBE_DIR; no fake real-source PASS')
    source = Path(given)
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'raw').mkdir()
    shutil.copy2(source / 'manifest.json', root / 'manifest.json')
    for item in json.loads((source / 'manifest.json').read_text(encoding='utf-8'))['records']:
        src = source / item['evidence_path']
        if item['status'] == 200 and src.is_file():
            dst = root / item['evidence_path']
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return root


def test_full_original_pdf_bundle_replays_120_rows_and_only_eight_field_changes(authentic_source_root):
    root = authentic_source_root
    raw = Path(os.environ['HBI_DNT_PROBE_DIR']) / 'candidate_form_rows.csv'
    assert raw.is_file(), 'Explicitly supply original candidate file, not a new export'
    with raw.open(encoding='utf-8-sig', newline='') as f:
        before = list(csv.DictReader(f))
    report = verify_and_export_probe(root)
    assert audit_exit_code(report) == 0, report
    assert report['model_eligible'] is False and report['bet_authorized'] is False
    assert report['source_publication_time_attested'] is False
    assert report['independent_individual_ueln_verified'] == 0
    assert report['row_count'] == 120 and report['horses_with_five_rows'] == 24
    with (root / 'candidate_form_rows.csv').open(encoding='utf-8-sig', newline='') as f:
        after = list(csv.DictReader(f))
    assert len(after) == len(before) == 120
    keys = ['race_id','horse_name','form_row_order_oldest_to_newest','date_program_code']
    assert [[v[k] for k in keys] for v in after] == [[v[k] for k in keys] for v in before]
    differences = [
        (i, field, old[field], new[field])
        for i, (old, new) in enumerate(zip(before, after))
        for field in old
        if old[field] != new[field]
    ]
    assert len(differences) == 8, differences
    assert {before[i]['horse_name'] for i,_,_,_ in differences} == {
        'ROS LYNET', 'HVALSTAD IL', 'BJØRLIMINDI (S)', 'MYR TØTTA'
    }
    expected = {
        ('ROS LYNET', '15/05-05/11'): ('', '16', '1072'),
        ('HVALSTAD IL', '26/09-05/3'): ('26,4', '175', None),
        ('BJØRLIMINDI (S)', '04/07-05/12'): ('25,2a', '100', None),
        ('MYR TØTTA', '26/09-09/12'): ('32,2', '100', None),
    }
    for row in after:
        k = (row['horse_name'], row['date_program_code'])
        if k not in expected:
            continue
        km, pr, odds = expected[k]
        if km:
            assert row['km_time_raw'] == km
        assert row['program_pr_column_raw'] == pr
        if odds:
            assert row['program_odds_column_raw'] == odds
        assert row['history_candidate_not_model_eligible'] == 'True'
    assert not any(' ' in row['program_pr_column_raw'] for row in after)
    assert not any(not row['program_odds_column_raw'] for row in after)
    assert all(row['year_inferred_not_attested'] == 'True' for row in after)
    assert all(row['historic_result_independently_verified'] == 'False' for row in after)
    for _, _, names in PILOT_FIELDS.values():
        assert len(names) == 12
    input_bundle = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for item in input_bundle['records']:
        body = (root / item['evidence_path']).read_bytes()
        assert hashlib.sha256(body).hexdigest() == item['sha256']


def test_corrupt_original_pdf_hash_cannot_pass(authentic_source_root):
    root = authentic_source_root
    file = root / 'raw' / 'bjerke_20261031_program_0.body'
    file.write_bytes(file.read_bytes() + b'CORRUPTED_SYNTHETIC')
    report = verify_and_export_probe(root)
    assert audit_exit_code(report) == 1
    assert report['all_source_pdf_rows_found'] is False
    assert any('RAW_PDF_SHA256_MISMATCH' in x for x in report['issues'])
