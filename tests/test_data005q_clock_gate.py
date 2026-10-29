import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hbi.schedule_clock_gate import assess, parse_utc
from hbi.schedule_provenance import append_observation, make_event

ROOT = Path(__file__).resolve().parents[1]
DDL = ROOT / 'db' / 'migrations' / '0008_schedule_provenance_research.sql'
if not DDL.is_file():  # Standalone DATA-005Q package uses the DATA-005P baseline.
    DDL = ROOT / 'baseline_p' / 'db' / 'migrations' / '0008_schedule_provenance_research.sql'
RACE = 'RIKSTOTO:MO_NR_2026-10-17:8'
START = datetime(2026, 10, 17, 18, 48, tzinfo=UTC)
CUTOFF = datetime(2026, 10, 17, 18, 41, tzinfo=UTC)
SOURCE = 'https://www.rikstoto.no/api/racedays/'

@pytest.fixture
def db():
    c=sqlite3.connect(':memory:')
    c.executescript(DDL.read_text(encoding='utf-8'))
    yield c
    c.close()

def event(c, start=START, observed=None, verified=True):
    obs=observed or (CUTOFF - timedelta(minutes=1))
    e=make_event(race_id=RACE,source_uri=SOURCE,observed_at=obs,
        source_schedule_raw=start.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Oslo')).replace(tzinfo=None).isoformat(),
        normalized_start=start,raw_body_sha256='a'*64 if verified else None,
        completion_verified=verified)
    append_observation(c,e)
    return e

def test_no_schema_fails_closed():
    c=sqlite3.connect(':memory:')
    r=assess(c,race_id=RACE,decision_time=CUTOFF)
    assert r.status=='MISSING_CLOCK_PROVENANCE' and 'JOURNAL_NOT_INSTALLED' in r.blockers
    assert r.model_eligible is False and r.bet_authorized is False
    c.close()

def test_no_observation_fails_closed(db):
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert 'NO_OBSERVATION_BY_CUTOFF' in r.blockers

def test_one_hashed_schedule_is_not_a_raw_archive(db):
    event(db)
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert r.status=='CLOCK_CONSISTENT_RESEARCH_ONLY'
    assert r.asof_clock_consistent and not r.model_eligible and not r.bet_authorized
    assert 'RAW_RESPONSE_NOT_REPLAYABLE' in r.blockers

def test_parsed_source_is_not_http_verified(db):
    event(db,verified=False)
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert 'SOURCE_RESPONSE_COMPLETION_UNVERIFIED' in r.blockers

def test_conflicting_times_before_decision_quarantine(db):
    event(db)
    event(db,start=START-timedelta(minutes=15), observed=CUTOFF-timedelta(minutes=2))
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert r.status=='CLOCK_CONFLICT_QUARANTINE' and r.precutoff_distinct_clocks==2

def test_after_published_start_is_quarantined(db):
    event(db,start=CUTOFF-timedelta(minutes=1), observed=CUTOFF-timedelta(minutes=2))
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert 'DECISION_AT_OR_AFTER_PUBLISHED_START' in r.blockers

def test_late_observation_does_not_retroactively_pass(db):
    event(db,observed=CUTOFF+timedelta(minutes=2))
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert r.status=='MISSING_CLOCK_PROVENANCE' and r.precutoff_observations==0

def test_later_change_flagged_without_rewriting_asof(db):
    event(db)
    event(db,start=START-timedelta(minutes=15),observed=CUTOFF+timedelta(minutes=3))
    r=assess(db,race_id=RACE,decision_time=CUTOFF,retrospective_through=CUTOFF+timedelta(minutes=5))
    assert r.status=='CLOCK_CONFLICT_QUARANTINE'
    assert r.precutoff_distinct_clocks==1 and r.retrospective_clock_changed

def test_later_same_clock_does_not_create_version_conflict(db):
    event(db)
    event(db,observed=CUTOFF+timedelta(minutes=1))
    r=assess(db,race_id=RACE,decision_time=CUTOFF,retrospective_through=CUTOFF+timedelta(minutes=5))
    assert r.status=='CLOCK_CONSISTENT_RESEARCH_ONLY'
    assert r.retrospective_new_observations==1

def test_external_official_clock_mismatch_not_physical_start(db):
    event(db)
    r=assess(db,race_id=RACE,decision_time=CUTOFF,external_published_start=START-timedelta(minutes=15))
    assert r.retrospective_published_clock_conflict
    assert not r.physical_off_time_attested
    assert 'FROZEN_AFTER_EXTERNAL_PUBLISHED_START_REVIEW' in r.blockers

def test_external_clock_equal_no_conflict(db):
    event(db)
    r=assess(db,race_id=RACE,decision_time=CUTOFF,external_published_start=START)
    assert not r.retrospective_published_clock_conflict

@pytest.mark.parametrize('x',["2026-10-17T18:41:00", "bad", "", None])
def test_bad_timestamp(x):
    with pytest.raises(ValueError):
        parse_utc(x)

def test_naive_decision_fails(db):
    with pytest.raises(ValueError):
        assess(db,race_id=RACE,decision_time=datetime(2026,10,17,18,41))

def test_retrospective_before_cutoff_invalid(db):
    with pytest.raises(ValueError):
        assess(db,race_id=RACE,decision_time=CUTOFF,retrospective_through=CUTOFF-timedelta(seconds=1))

def test_invalid_race_id_rejected(db):
    with pytest.raises(ValueError):
        assess(db,race_id='MO:8',decision_time=CUTOFF)

def test_additive_journal_immutable(db):
    e=event(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('DELETE FROM race_schedule_observations')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE race_schedule_observations SET source_grade='PARSED_ONLY'")
    assert e.event_id

def test_hash_only_never_approves_anything(db):
    event(db)
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert not r.original_http_bytes_replayable and not r.source_publication_attested
    assert not r.full_field_verified and not r.model_eligible and not r.bet_authorized

@pytest.mark.parametrize('minutes',[0,1,5,15,60])
def test_early_clock_cuts_off_correctly(db, minutes):
    event(db,start=START-timedelta(minutes=minutes))
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert r.asof_clock_consistent is (minutes < 7)

@pytest.mark.parametrize('offset',[0,2,30])
def test_future_observation_cannot_upgrade_old_decision(db,offset):
    event(db,observed=CUTOFF+timedelta(seconds=1+offset))
    r=assess(db,race_id=RACE,decision_time=CUTOFF)
    assert r.precutoff_observations==0 and not r.model_eligible
