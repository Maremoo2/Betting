"""RELEASE-003 fault injection. Synthetic software tests, never live-day evidence."""
import hashlib
import json
from pathlib import Path

import pytest
from test_prewatch_day import inputs

import hbi.collector_handoff as importer
import hbi.prewatch_shadow_handoff as shadow


def test_adapter_failure_has_no_successful_publication_and_releases_lock(tmp_path, monkeypatch):
    kwargs = inputs(tmp_path)
    source_sha = hashlib.sha256(kwargs['db'].read_bytes()).hexdigest()

    def broken(*args, **kwargs):
        raise ValueError('INJECTED_SHADOW_ADAPTER_FAILURE')

    monkeypatch.setattr(shadow, 'build_handoff', broken)
    with pytest.raises(ValueError, match='SHADOW_ADAPTER_FAILURE'):
        shadow.run_day(**kwargs)
    assert not (kwargs['out'] / 'prewatch-day.json').exists()
    assert not (kwargs['out'] / '.writer.lock').exists()
    assert hashlib.sha256(kwargs['db'].read_bytes()).hexdigest() == source_sha


@pytest.mark.parametrize('kind', ['write', 'readback'])
def test_log_failure_never_succeeds_or_repairs_conflicting_bytes(tmp_path, monkeypatch, kind):
    kwargs = inputs(tmp_path)
    original = importer.append_shadow_events

    def broken(path, events):
        if kind == 'write':
            raise OSError('INJECTED_LOG_WRITE_FAILURE')
        path.write_bytes(b'INJECTED_BAD_READBACK\n')
        return []

    monkeypatch.setattr(importer, 'append_shadow_events', broken)
    with pytest.raises(OSError, match='LOG_WRITE_FAILURE|LOG_READBACK_FAILURE'):
        shadow.run_day(**kwargs)
    assert not (kwargs['out'] / '.writer.lock').exists()
    monkeypatch.setattr(importer, 'append_shadow_events', original)
    if kind == 'write':
        report = shadow.run_day(**kwargs)
        assert report['counts']['terminal'] == 2
    else:
        frozen = (kwargs['out'] / 'prewatch-events.jsonl').read_bytes()
        with pytest.raises(ValueError, match='EVENT_LOG_CONFLICT'):
            shadow.run_day(**kwargs)
        assert (kwargs['out'] / 'prewatch-events.jsonl').read_bytes() == frozen


def test_missing_and_corrupt_provenance_is_visible_for_every_race(tmp_path):
    kwargs = inputs(tmp_path)
    kwargs['provenance'].write_text('not valid JSON')
    result = shadow.run_day(**kwargs)
    assert result['counts']['terminal'] == result['counts']['discovered'] == 2
    assert all('COLLECTOR_AUTHENTICATED_ARCHIVE_UNAVAILABLE' in r['blockers']
               for r in result['races'])
    assert all(r['runtime_gate']['engine_status'] == 'NOT_RUN' for r in result['races'])
    assert json.loads((kwargs['out'] / 'prewatch-day.json').read_bytes()) == result


def test_changed_source_snapshot_cannot_reuse_a_bound_working_copy(tmp_path):
    kwargs = inputs(tmp_path)
    shadow.run_day(**kwargs)
    frozen = (kwargs['out'] / 'prewatch-day.json').read_bytes()
    # Synthetic mutation, not editing any real source or production database.
    kwargs['db'].write_bytes(kwargs['db'].read_bytes() + b'different snapshot')
    with pytest.raises(ValueError, match='SOURCE_DATABASE_CONFLICT'):
        shadow.run_day(**kwargs)
    assert (kwargs['out'] / 'prewatch-day.json').read_bytes() == frozen


def test_isolated_acceptance_cannot_activate_on_main_or_share_its_writer_group():
    workflow = (Path(__file__).parents[1] / '.github/workflows/core-003-shadow-pilot.yml').read_text()
    assert "github.ref == 'refs/heads/main' && 'core003-isolated-source-pilot'" in workflow
    assert "format('core003-acceptance-{0}', github.run_id)" in workflow
    step = workflow.split('      - name: Branch-only isolated source to Pre-Watch acceptance')[1]
    assert "github.ref != 'refs/heads/main'" in step.split('shell:')[0]
    assert "github.event_name == 'workflow_dispatch'" in step.split('shell:')[0]
    assert 'inputs.shadow_acceptance && inputs.execute' in step.split('shell:')[0]
    assert 'Path(os.environ["RUNNER_TEMP"]) / "v3313-isolated-acceptance"' in step
    assert 'MANUAL_DISPATCH_PARTIAL_NOT_SCHEDULED_FULL_DAY' in step
    outcomes = workflow.split('  outcome-research:')[1]
    assert "github.ref == 'refs/heads/main' && 'core003-isolated-outcome-research'" in outcomes
    assert "format('core003-acceptance-outcomes-{0}', github.run_id)" in outcomes
    assert "&& !(github.event_name == 'workflow_dispatch' && github.ref != 'refs/heads/main' && inputs.shadow_acceptance)" in outcomes
