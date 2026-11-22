"""Accelerated clock contracts only; never counted as observed live-day evidence."""
import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'acceptance_clock', Path(__file__).parents[1] / 'scripts/release003_clock.py'
)
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)
PIN = 'a' * 40
INVENTORY = [{'start_utc': '2026-11-22T11:20:00+00:00'},
             {'start_utc': '2026-11-22T21:25:00+00:00'}]


def plan():
    return clock.make_plan('2026-11-22T10:00:00Z', '2026-11-22T22:30:00Z', PIN, INVENTORY)


def test_whole_programme_window_and_nonoverlapping_phases():
    p = plan()
    assert len(p['ticks']) == 150
    groups = []
    for phase in range(3):
        low = clock.stamp(p['start']) + timedelta(seconds=phase * clock.PHASE_SECONDS)
        high = low + timedelta(seconds=clock.PHASE_SECONDS)
        groups.append([t for t in p['ticks'] if low <= clock.stamp(t) < high])
    assert [t for g in groups for t in g] == p['ticks']


@pytest.mark.parametrize('start,end', [
    ('2026-11-22T11:17:00Z', '2026-11-22T22:30:00Z'),
    ('2026-11-22T10:00:00Z', '2026-11-22T21:30:00Z'),
    ('2025-11-22T10:00:00Z', '2025-11-22T22:30:00Z'),
    ('2026-11-22T10:00:00', '2026-11-22T22:30:00Z'),
])
def test_incomplete_late_or_naive_plan_rejected(start, end):
    with pytest.raises(ValueError):
        clock.make_plan(start, end, PIN, INVENTORY)


class Time:
    def __init__(self, value):
        self.now = value

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


def test_real_dispatch_protocol_with_fake_clock_and_no_duplicate_posts(tmp_path):
    p = plan()
    p['ticks'] = p['ticks'][:2]
    time = Time(clock.stamp(p['start']))
    posted = []

    def api(path, method='GET', payload=None):
        if '/branches/' in path:
            return {'commit': {'sha': PIN}}
        if method == 'POST':
            posted.append(payload['inputs']['acceptance_tick_utc'])
            return None
        return {'workflow_runs': [{'id': i + 1, 'display_title': 'V3313 tick ' + value,
                                  'head_sha': PIN, 'created_at': value}
                                 for i, value in enumerate(posted)]}

    rows = clock.run_phase(p, 0, tmp_path / 'first', request=api, clock=time, sleep=time.sleep)
    assert len(posted) == 2 and [r['workflow_run_id'] for r in rows] == [1, 2]
    time.now = clock.stamp(p['start'])
    clock.run_phase(p, 0, tmp_path / 'retry', request=api, clock=time, sleep=time.sleep)
    assert len(posted) == 2


def test_late_ticks_are_not_backfilled(tmp_path):
    p = plan()
    p['ticks'] = p['ticks'][:1]
    time = Time(clock.stamp(p['start']) + timedelta(minutes=3))
    rows = clock.run_phase(p, 0, tmp_path, request=lambda *a: pytest.fail('late source access'),
                           clock=time, sleep=time.sleep)
    assert rows[0]['status'] == 'MISSED_CONTROLLER_SLOT_NOT_BACKFILLED'


def test_moved_head_stops_before_provider_probe_dispatch(tmp_path):
    p = plan()
    time = Time(clock.stamp(p['start']))
    rows = clock.run_phase(p, 0, tmp_path, request=lambda *a: {'commit': {'sha': 'b' * 40}},
                           clock=time, sleep=time.sleep)
    assert len(rows) == 1 and rows[0]['status'] == 'DISPATCH_BLOCKED'
    assert rows[0]['reason'] == 'ACCEPTANCE_HEAD_MOVED_STOP_DISPATCH'


def test_clock_jobs_are_opt_in_branch_only_and_standard_linux():
    workflow = (Path(__file__).parents[1] / '.github/workflows/core-003-shadow-pilot.yml').read_text()
    assert "if: ${{ !inputs.acceptance_schedule }}" in workflow
    assert workflow.count('  acceptance-clock-') == 3
    for number in range(3):
        job = workflow.split(f'  acceptance-clock-{number}:', 1)[1]
        job = job.split('\n  acceptance-clock-', 1)[0]
        assert "github.ref != 'refs/heads/main' && inputs.acceptance_schedule" in job
        assert 'runs-on: ubuntu-latest' in job
        assert 'actions: write' in job
        assert 'timeout-minutes: 350' in job
    guard = workflow.split('Enforce branch acceptance SHA before source access', 1)[1]
    assert guard.index('FROZEN_ACCEPTANCE_HEAD_CHANGED_NO_SOURCE_ACCESS') < guard.index('Execute research source capture')
