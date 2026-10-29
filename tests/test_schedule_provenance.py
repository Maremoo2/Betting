"""Research-only QA of additive schedule provenance. All races are synthetic."""
from __future__ import annotations
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hbi.schedule_provenance import (
    append_observation, aware_utc, make_event, schedule_research_status,
)

PKG=Path(__file__).resolve().parents[1]
URL="https://www.rikstoto.no/api/racedays/"
RACE="RIKSTOTO:TEST_NR_2026-11-01:1"
OBS=datetime(2026,11,1,9,tzinfo=UTC)
START=datetime(2026,11,1,11,tzinfo=UTC)
SHA=hashlib.sha256(b'{"test_only":true}').hexdigest()
MIGRATION=PKG/"db/migrations/0008_schedule_provenance_research.sql"


def ev(**kw):
    data=dict(race_id=RACE,source_uri=URL,observed_at=OBS,source_schedule_raw="2026-11-01T12:00:00+01:00",normalized_start=START)
    data.update(kw)
    return make_event(**data)


@pytest.fixture
def db(tmp_path):
    path=tmp_path/"test.sqlite"
    with sqlite3.connect(path) as c:
        c.executescript(MIGRATION.read_text())
    return path


def sql(db):
    return sqlite3.connect(db,timeout=10)


def test_migration_creates_append_only_table(db):
    with sql(db) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='race_schedule_observations'").fetchone()


def test_migration_idempotent(db):
    with sql(db) as c:
        c.executescript(MIGRATION.read_text())


def test_research_state_without_rows(db):
    with sql(db) as c:
        assert schedule_research_status(c,RACE)["status"]=="NO_SCHEDULE_EVIDENCE"


def test_parsed_event_never_promoted(db):
    event=ev()
    assert event.source_grade=="PARSED_ONLY"
    assert event.source_time_basis=="CALLER_SUPPLIED_UNVERIFIED"
    with sql(db) as c:
        assert append_observation(c,event)
        row=c.execute("SELECT research_only,pit_verified,model_eligible,bet_authorized,source_body_sha256 FROM race_schedule_observations").fetchone()
        assert row==(1,0,0,0,None)
        assert schedule_research_status(c,RACE)["status"]=="UNVERIFIED_OBSERVATION_CLOCK"


def test_exact_hash_is_hash_only_not_raw_source(db):
    event=ev(raw_body_sha256=SHA, completion_verified=True, http_etag='"version1"')
    assert event.source_grade=="HASH_ONLY_NO_RAW_BYTES"
    with sql(db) as c:
        assert append_observation(c,event)
        assert schedule_research_status(c,RACE)["status"]=="HASH_ONLY_SOURCE_REPLAY_NOT_PROVEN"
        row=c.execute("SELECT source_body_sha256,http_etag,model_eligible FROM race_schedule_observations").fetchone()
        assert row==(SHA,'"version1"',0)


def test_idempotent_duplicate(db):
    with sql(db) as c:
        assert append_observation(c,ev())
        assert not append_observation(c,ev())
        assert c.execute("SELECT count(*) FROM race_schedule_observations").fetchone()[0]==1


def test_each_fresh_observation_has_distinct_id(db):
    with sql(db) as c:
        assert append_observation(c,ev())
        assert append_observation(c,ev(observed_at=OBS+timedelta(seconds=1)))
        assert schedule_research_status(c,RACE)["versions"]==2


def test_changed_schedule_keeps_both_versions(db):
    with sql(db) as c:
        assert append_observation(c,ev())
        assert append_observation(c,ev(source_schedule_raw="2026-11-01T12:14:00+01:00",normalized_start=START+timedelta(minutes=14),observed_at=OBS+timedelta(minutes=1)))
        assert schedule_research_status(c,RACE)["status"]=="CLOCK_VERSION_CONFLICT_REVIEW"


@pytest.mark.parametrize("q",[
    "UPDATE race_schedule_observations SET normalized_start_utc='2099-01-01'",
    "DELETE FROM race_schedule_observations",
    "UPDATE race_schedule_observations SET research_only=0",
    "UPDATE race_schedule_observations SET model_eligible=1",
    "UPDATE race_schedule_observations SET bet_authorized=1",
])
def test_immutability(db,q):
    with sql(db) as c:
        append_observation(c,ev())
    with pytest.raises(sqlite3.IntegrityError):
        with sql(db) as c:
            c.execute(q)


@pytest.mark.parametrize("changes,error",[
    ({"race_id":"not-a-race"},"INVALID_RACE_ID"),
    ({"race_id":"RIKSTOTO:TEST_2026:0"},"INVALID_RACE_ID"),
    ({"source_uri":"http://www.rikstoto.no/api/racedays/"},"INVALID_DISCOVERY_SOURCE_URI"),
    ({"source_uri":"https://example.com/api/racedays/"},"INVALID_DISCOVERY_SOURCE_URI"),
    ({"source_uri":URL+"?q=1"},"INVALID_DISCOVERY_SOURCE_URI"),
    ({"source_schedule_raw":""},"MISSING_RAW_SCHEDULE_TIME"),
    ({"source_schedule_raw":"x"*101},"MISSING_RAW_SCHEDULE_TIME"),
    ({"observed_at":datetime(2026,11,1,9)},"NAIVE_OR_INVALID_TIME"),
    ({"normalized_start":datetime(2026,11,1,11)},"NAIVE_OR_INVALID_TIME"),
    ({"raw_body_sha256":"abc"},"INVALID_RAW_BODY_SHA256"),
    ({"raw_body_sha256":SHA},"UNVERIFIED_HASH_CANNOT_CLAIM_RAW_HTTP"),
    ({"completion_verified":True},"COMPLETION_WITHOUT_BODY_HASH"),
    ({"http_date":"foo\rbar"},"INVALID_HTTP_HEADER"),
    ({"http_etag":"foo\nbar"},"INVALID_HTTP_HEADER"),
    ({"http_last_modified":"x"*513},"INVALID_HTTP_HEADER"),
])
def test_invalid_input_fails_closed(changes,error):
    with pytest.raises(ValueError,match=error):
        ev(**changes)


def test_utc_conversion():
    assert aware_utc(datetime.fromisoformat("2026-11-01T12:00:00+01:00"))==START


def test_at_or_after_start_stored_not_admitted(db):
    event=ev(observed_at=START)
    assert event.before_declared_start==0
    with sql(db) as c:
        append_observation(c,event)
        assert c.execute("SELECT model_eligible FROM race_schedule_observations").fetchone()[0]==0


def test_hash_change_never_collapses_to_old_event(db):
    with sql(db) as c:
        a=ev(raw_body_sha256=SHA,completion_verified=True)
        b=ev(raw_body_sha256="b"*64,completion_verified=True)
        append_observation(c,a)
        append_observation(c,b)
        assert a.event_id != b.event_id
        assert c.execute("SELECT count(*) FROM race_schedule_observations").fetchone()[0]==2


def test_tampered_sql_promotion_is_rejected(db):
    with sql(db) as c:
        append_observation(c,ev())
    with pytest.raises(sqlite3.IntegrityError):
        with sql(db) as c:
            c.execute("INSERT INTO race_schedule_observations (event_id,race_id,source_uri,observed_at_utc,source_schedule_raw,normalized_start_utc,source_grade,source_time_basis,before_declared_start,model_eligible) VALUES ('x','r','u','t','s','t','PARSED_ONLY','CALLER_SUPPLIED_UNVERIFIED',1,1)")


def test_rollback_atomic_with_mock_race_table(db):
    with sql(db) as c:
        c.execute("CREATE TABLE races (race_id TEXT PRIMARY KEY, start_time_utc TEXT NOT NULL)")
        c.execute("CREATE TRIGGER fail_all BEFORE INSERT ON races BEGIN SELECT RAISE(ABORT,'SIMULATED_UPSERT_FAILURE'); END")
    with pytest.raises(sqlite3.IntegrityError):
        with sql(db) as c:
            append_observation(c,ev())
            c.execute("INSERT INTO races VALUES (?,?)",(RACE,START.isoformat()))
    with sql(db) as c:
        assert c.execute("SELECT count(*) FROM race_schedule_observations").fetchone()[0]==0


def test_replay_retains_multiple_versions(db):
    with sql(db) as c:
        for idx in range(5):
            append_observation(c,ev(observed_at=OBS+timedelta(seconds=idx)))
    with sql(db) as c:
        assert schedule_research_status(c,RACE)["versions"]==5


def test_concurrent_distinct_writers(db):
    def do(i):
        with sql(db) as c:
            c.execute("BEGIN IMMEDIATE")
            return append_observation(c,ev(observed_at=OBS+timedelta(seconds=i)))
    with ThreadPoolExecutor(max_workers=8) as exe:
        assert all(exe.map(do,range(20)))
    with sql(db) as c:
        assert c.execute("SELECT count(*) FROM race_schedule_observations").fetchone()[0]==20


def test_concurrent_identical_writers_idempotent(db):
    def do(_):
        with sql(db) as c:
            c.execute("BEGIN IMMEDIATE")
            return append_observation(c,ev())
    with ThreadPoolExecutor(max_workers=8) as exe:
        result=list(exe.map(do,range(20)))
    assert sum(result)==1


def test_failed_insert_does_not_leak_raw_payload(db):
    with sql(db) as c:
        append_observation(c,ev())
    with sql(db) as c:
        schema=c.execute("SELECT sql FROM sqlite_master WHERE name='race_schedule_observations'").fetchone()[0]
    assert "raw_body_bytes" not in schema
    assert "source_body_sha256" in schema


def test_historical_retro_capture_cannot_be_called_verified(db):
    e=ev(observed_at=OBS+timedelta(hours=5))
    assert e.before_declared_start==0
    assert e.source_grade=="PARSED_ONLY"
