import os
import sqlite3
from pathlib import Path

import pytest

from hbi.core_gap_audit import _source_observation, audit_day_sources


def test_observation_none():
    assert _source_observation([], '2026-10-28T10:00:00+00:00')['status']=='NO_ARCHIVED_PAYLOAD'


def test_observation_late():
    a=_source_observation(['2026-10-28T10:01:00+00:00'], '2026-10-28T10:00:00+00:00')
    assert a['status']=='ONLY_AFTER_CUTOFF' and a['events_pre_cutoff']==0


def test_observation_exact_cutoff():
    a=_source_observation(['2026-10-28T10:00:00+00:00'], '2026-10-28T10:00:00+00:00')
    assert a['status']=='BEFORE_CUTOFF' and a['events_pre_cutoff']==1


def test_observation_non_lexicographic_offsets():
    a=_source_observation(['2026-10-28T12:00:00+02:00'], '2026-10-28T10:01:00+00:00')
    assert a['status']=='BEFORE_CUTOFF'


def test_observation_before_after():
    a=_source_observation(['2026-10-28T10:00:00+00:00','2026-10-28T10:03:00+00:00'],
                          '2026-10-28T10:02:00+00:00')
    assert a['latest_pre_cutoff_utc'].endswith('10:00:00+00:00')
    assert a['first_after_cutoff_utc'].endswith('10:03:00+00:00')


def test_archive_replay(tmp_path):
    path=Path(os.environ.get('HBI_CORE_003_ARCHIVE',
        str(Path(__file__).resolve().parents[1]/'reports/core_003_day_fixture.sqlite')))
    if not path.is_file():
        pytest.skip('CORE-003 historical SQLite fixture not provided; set HBI_CORE_003_ARCHIVE')
    conn=sqlite3.connect(f'file:{path.as_posix()}?mode=ro&immutable=1',uri=True)
    conn.row_factory=sqlite3.Row
    try:report=audit_day_sources(conn,race_date='2026-10-28')
    finally:conn.close()
    assert report['baseline_summary']['blocked_races']==22
    assert len(report['race_sources'])==31
    assert report['blocker_diagnoses']['HISTORY_CAPTURED_TOO_LATE']>=1
    assert all(r['stage']!='SKIPPED_DISCIPLINE' for r in report['race_sources'])
    assert report['authority']=='ARCHIVAL_RESEARCH_ONLY'
