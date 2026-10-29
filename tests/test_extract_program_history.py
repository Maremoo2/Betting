"""Research-only regression tests; no official race results assumed for fake rows."""
from datetime import date

import fitz
import pytest

from hbi.extract_program_history import (
    DATE_TOKEN,
    PILOT_FIELDS,
    audit_exit_code,
    extract,
    infer_dates_backward,
)


def test_cross_year_not_backdated_from_current_year():
    rows = infer_dates_backward(
        ['25/11-01/3', '28/11-03/3', '17/12-01/4', '27/01-03/3', '01/10-07/8'],
        date(2026, 11, 1),
    )
    assert [x['year_inferred_iso'] for x in rows] == [
        '2025-11-25', '2025-11-28', '2025-12-17', '2026-01-27', '2026-10-01'
    ]
    assert all(x['year_inferred_not_attested'] for x in rows)


def test_numeric_and_monte_form_codes_accepted():
    for v in ['15/09-01/10m', '04/09-08/2', '13/10-01/4']:
        assert DATE_TOKEN.fullmatch(v)


def test_impossible_day_month_fails():
    with pytest.raises(ValueError):
        infer_dates_backward(['31/02-01/4'], date(2026, 11, 1))


def test_future_calendar_year_not_accepted():
    rows = infer_dates_backward(['18/12-01/4'], date(2026, 11, 1))
    assert rows[0]['year_inferred_iso'] == '2025-12-18'


class DummyPage:
    def __init__(self, n=5):
        self.rect = fitz.Rect(0, 0, 595, 842)
        self.n = n

    def search_for(self, name):
        return [fitz.Rect(70.866, 107.45, 160.3, 118)] if name == 'FAKE HORSE' else []

    def get_text(self, kind):
        assert kind == 'words'
        out = []
        for i in range(self.n):
            y = 117.2 + i * 7.4
            for x, val in [
                (231.2, 'A. Driver'), (292.0, 'B'),
                (315.2, f'{10 + i:02d}/10-01/{i+1}'),
                (355.8, '2140'), (377.3, str(i)), (384.7, '31,0'),
                (418.2, '16'), (437.6, '99'),
            ]:
                out.append((x, y, x + len(val) * 3, y + 7, val, 0, 0, 0))
        return out


def test_five_rows_are_joined_by_actual_vertical_coordinate():
    rows = extract(DummyPage(), ['FAKE HORSE'], 'RIKSTOTO:FAKE_NR_2026-11-01:2', date(2026, 11, 1), 'a' * 64)
    assert len(rows) == 5
    assert rows[0]['date_program_code'] == '10/10-01/1'
    assert rows[-1]['program_odds_column_raw'] == '99'
    assert rows[2]['finish_raw'] == '2'
    assert all(not r['historic_result_independently_verified'] for r in rows)


def test_missing_fifth_form_row_rejected():
    with pytest.raises(ValueError, match='REQUIRE_FIVE_VISIBLE_FORM_ROWS'):
        extract(DummyPage(n=4), ['FAKE HORSE'], 'RIKSTOTO:FAKE_NR_2026-11-01:2', date(2026, 11, 1), 'a' * 64)


def test_runner_not_found_rejected():
    with pytest.raises(ValueError, match='NAME_ANCHOR_AMBIGUOUS'):
        extract(DummyPage(), ['NOT ON PAGE'], 'RIKSTOTO:FAKE_NR_2026-11-01:2', date(2026, 11, 1), 'a' * 64)


def test_program_names_keep_unicode_identity_anchors():
    assert 'SOLØR HANNA' in PILOT_FIELDS['momarken_20261101'][2]
    assert 'SØYSET NORAH' in PILOT_FIELDS['bjerke_20261031'][2]


def test_empty_or_partial_audit_must_fail_ci():
    assert audit_exit_code({'all_source_pdf_rows_found': False, 'row_count': 0, 'horses_with_five_rows': 0, 'issues': ['ENCODING']}) == 1
    assert audit_exit_code({'all_source_pdf_rows_found': True, 'row_count': 60, 'horses_with_five_rows': 12, 'issues': []}) == 1
    assert audit_exit_code({'all_source_pdf_rows_found': True, 'row_count': 120, 'horses_with_five_rows': 24, 'issues': []}) == 0
