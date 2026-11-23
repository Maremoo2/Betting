"""Genuine late originals and TEST_ONLY integration clocks; never live admission."""
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from test_model_admission_evidence import NOW, SOURCE
from test_model_admission_evidence import cohort as cohort_fixture

from hbi import admission_originals, cloud_run003_model
from hbi.atg_admission_source import verify_history_original
from hbi.history_availability import load_new
from hbi.providers.atg import AtgClient
from hbi.shadow import ShadowPolicy

cohort = cohort_fixture


def test_genuine_retrospective_game_originals_still_reject_late_clocks():
    count = 0
    for uri, (ref, raw) in load_new(Path(__file__).parents[1] / 'tests/fixtures').items():
        prefix = AtgClient.GAME_API + '/vinnare_'
        if not uri.startswith(prefix):
            continue
        game = json.loads(raw)
        start = AtgClient._parse_time(game['races'][0]['startTime'])
        cutoff = start - timedelta(minutes=ShadowPolicy().target_minutes_to_start)
        with pytest.raises(ValueError, match='ATG_HISTORY_NOT_BEFORE_CUTOFF'):
            verify_history_original(raw, uri=uri, sha256=ref['sha256'],
                                    completed_at=datetime.fromisoformat(ref['observed_at']),
                                    cutoff=cutoff, provider_race_id=uri.removeprefix(prefix))
        count += 1
    assert count == 32


@pytest.mark.parametrize('delta', [0, 0.5])
def test_source_at_now_before_t4_is_valid_but_future_information_is_not(cohort, monkeypatch, delta):
    store, proofs, scratch = cohort
    stamp = NOW + timedelta(seconds=delta)
    updated = tuple(replace(p, observed_at=stamp, history_completed_at=stamp) for p in proofs)
    pins = admission_originals._REVIEWED_RECEIPTS | {
        (role, uri, digest, stamp) for p in updated for role, uri, digest in (
            ('REGISTRY_BINDING', p.original_uri, p.original_sha256),
            ('ATG_HISTORY', p.history_original_uri, p.history_original_sha256))}
    monkeypatch.setattr(admission_originals, '_REVIEWED_RECEIPTS', pins)
    if delta:
        monkeypatch.setattr(cloud_run003_model, 'run_and_persist_fundamental',
                            lambda *a, **k: pytest.fail('future source invoked model'))
    report = cloud_run003_model.assess_and_run(
        store, SOURCE, now=NOW, identity_evidence=updated, scratch_evidence=(scratch,))
    assert report['p_win_computed'] == (0 if delta else 1)
    if delta:
        assert store.fetch_table('predictions') == []
