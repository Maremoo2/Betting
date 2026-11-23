"""Synthetic profile contracts; public real originals are evaluated separately."""
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from hbi.history_source_verification import inspect_dnt_profile_history

REG = "578001020225281"
URI = "https://www.travsport.no/sportsbasen/sportssok/horse/" + REG
CUTOFF = datetime(2026, 11, 23, 18, 11, tzinfo=UTC)
HEADERS = ["Kusknavn", "Banenavn", "Dato", "Løp", "Dist.", "Spor", "Prog.nr.",
           "T", "Tid", "Plas.", "R", "G", "Odds"]


def source(*, identifier=REG, reference=True, display_day="20.11.2026", extra=""):
    def row(day, display):
        link = f'<a href="/travbaner/test/results/{day}#race-2">02</a>' if reference else '02'
        cells = ["DRIVER", "TRACK", display, link, "1/2140", "1", "1", "", "15,2a",
                 "1", "", "", "25"]
        return '<tr>' + ''.join('<td>' + c + '</td>' for c in cells) + '</tr>'
    raw = ('UELN: ' + identifier + '<table><thead><tr>'
           + ''.join('<th>' + h + '</th>' for h in HEADERS)
           + '</tr></thead>' + row('2026-11-23', '23.11.2026')
           + row('2026-11-20', display_day) + extra + '</table>').encode()
    return {'status': 200, 'url': URI, 'final_url': URI, 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'observed_at': (CUTOFF-timedelta(seconds=1)).isoformat()}, raw


def inspect(pair):
    return inspect_dnt_profile_history(pair, registration=REG, target_date='2026-11-23',
                                       cutoff=CUTOFF)


def test_original_identity_and_individual_race_excerpts_never_grant_admission():
    d = inspect(source())
    assert len(d['prior_race_excerpts']) == len(d['current_or_future_excluded']) == 1
    assert d['prior_race_excerpts'][0]['date'] == '2026-11-20'
    assert not d['pit_certified'] and not d['model_eligible']
    assert not d['independent_identity_attested']
    assert d['excerpt_not_certified_last_five_actual_starts']


@pytest.mark.parametrize('attack', ['hash', 'source', 'ueln', 'equal', 'late', 'naive', 'date'])
def test_wrong_source_identity_hash_or_late_original_is_rejected(attack):
    meta, raw = source(identifier='578001020225280' if attack == 'ueln' else REG,
                       display_day='19.11.2026' if attack == 'date' else '20.11.2026')
    if attack == 'hash': meta['sha256'] = '0'*64
    if attack == 'source': meta['url'] = 'https://example.com/unrelated'
    if attack == 'equal': meta['observed_at'] = CUTOFF.isoformat()
    if attack == 'late': meta['observed_at'] = (CUTOFF+timedelta(seconds=1)).isoformat()
    if attack == 'naive': meta['observed_at'] = '2026-11-23T10:00:00'
    with pytest.raises(ValueError): inspect((meta, raw))


def test_missing_race_reference_is_reported_without_constructing_an_id():
    d = inspect(source(reference=False))
    assert not d['prior_race_excerpts']
    assert len(d['unbound_rows']) == 2
    assert all(r['reason'] == 'DNT_PROFILE_HISTORY_ROW_UNBOUND' for r in d['unbound_rows'])
    assert not d['model_eligible']
