"""TEST_ONLY receipts probe the validator, never attest a real source or field."""
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from hbi import admission_originals
from hbi.shadow import ShadowPolicy

START = datetime(2026, 11, 22, 12, tzinfo=UTC)
CUTOFF = START - timedelta(minutes=ShadowPolicy().target_minutes_to_start)
RAW = b'{"test_only":true}'
URI = 'https://registry.test.invalid/TEST_ONLY'
SHA = hashlib.sha256(RAW).hexdigest()


@pytest.mark.parametrize(('delta', 'accepted'), [(-1, True), (0, True), (1, False)])
def test_reviewed_original_obeys_inclusive_information_time(monkeypatch, delta, accepted):
    observed = CUTOFF + timedelta(seconds=delta)
    monkeypatch.setattr(admission_originals, '_REVIEWED_RECEIPTS',
                        frozenset({('REGISTRY_BINDING', URI, SHA, observed)}))
    result = admission_originals.verified_original(
        'REGISTRY_BINDING', URI, SHA, observed, RAW, CUTOFF)
    assert (result is not None) == accepted


@pytest.mark.parametrize('cutoff', [None, 'not-a-clock', CUTOFF.replace(tzinfo=None)])
def test_invalid_cutoff_cannot_raise_or_qualify(monkeypatch, cutoff):
    observed = CUTOFF - timedelta(seconds=1)
    monkeypatch.setattr(admission_originals, '_REVIEWED_RECEIPTS',
                        frozenset({('REGISTRY_BINDING', URI, SHA, observed)}))
    assert admission_originals.verified_original(
        'REGISTRY_BINDING', URI, SHA, observed, RAW, cutoff) is None


@pytest.mark.parametrize('changed', ['hash', 'uri', 'unreviewed', 'naive-observed'])
def test_early_timestamp_never_substitutes_for_original_authority(monkeypatch, changed):
    observed = CUTOFF - timedelta(seconds=1)
    monkeypatch.setattr(admission_originals, '_REVIEWED_RECEIPTS',
                        frozenset({('REGISTRY_BINDING', URI, SHA, observed)}))
    uri, sha, stamp = URI, SHA, observed
    if changed == 'hash':
        sha = '0' * 64
    elif changed == 'uri':
        uri += '/fabricated'
    elif changed == 'unreviewed':
        monkeypatch.setattr(admission_originals, '_REVIEWED_RECEIPTS', frozenset())
    else:
        stamp = observed.replace(tzinfo=None)
    assert admission_originals.verified_original(
        'REGISTRY_BINDING', uri, sha, stamp, RAW, CUTOFF) is None
