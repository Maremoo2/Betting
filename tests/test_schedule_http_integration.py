"""Synthetic HTTP -> Rikstoto discovery -> SQLite schedule provenance integration tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from hbi.providers.rikstoto import FetchResult, RikstotoClient
from hbi.rikstoto_collector import RikstotoCollector
from hbi.schedule_clock_gate import assess
from hbi.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.rikstoto.no/api/racedays/"
RACE = "RIKSTOTO:BJ_NR_2026-11-01:1"
OBS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)


class Response:
    status = 200
    headers = {
        "Date": "Sat, 31 Oct 2026 10:00:03 GMT",
        "ETag": '"v1"',
        "Last-Modified": "Sat, 31 Oct 2026 09:59:00 GMT",
    }

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


def test_http_hash_is_of_original_bytes_not_reserialized_json():
    raw = b' { "result": [] }\n'
    with patch("hbi.providers.rikstoto.urllib.request.urlopen", return_value=Response(raw)):
        result = RikstotoClient().racedays()
    assert result.success
    assert result.payload == {"result": []}
    assert result.response_body_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.response_completed_at.tzinfo is not None
    assert result.http_date == Response.headers["Date"]
    assert result.http_etag == Response.headers["ETag"]
    assert not hasattr(result, "body")
    assert not hasattr(result, "raw_body")


class SyntheticRacedays:
    def __init__(self, start="2026-11-01T13:00:00+01:00", *, complete=True):
        self.start = start
        self.complete = complete
        self.requests = 0

    def racedays(self):
        self.requests += 1
        payload = {
            "result": [{
                "raceDayName": "Bjerke",
                "raceDayKey": "BJ_NR_2026-11-01",
                "trackCode": "BJ",
                "sportType": "T",
                "countryIsoCode": "NO",
                "pools": [],
                "singleLegProducts": [],
                "races": [{
                    "raceNumber": 1,
                    "startTime": self.start,
                    "startMethod": "Auto",
                    "progressStatus": "Future",
                }],
            }]
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return FetchResult(
            url=SOURCE,
            payload=payload,
            success=True,
            status_code=200,
            latency_ms=2.0,
            response_body_sha256=digest if self.complete else None,
            response_completed_at=(
                OBS + timedelta(minutes=(self.requests - 1) * 5, seconds=self.requests)
                if self.complete else None
            ),
            http_date=Response.headers["Date"] if self.complete else None,
        )

    @staticmethod
    def discover_races(fetch):
        return RikstotoClient().discover_races(fetch)


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "hbi.sqlite")
    s.initialize(ROOT / "db" / "schema.sql")
    s.apply_migrations(ROOT / "db" / "migrations")
    return s


def journal(store):
    with store.connect() as conn:
        return conn.execute(
            "SELECT source_grade,source_time_basis,source_body_sha256,"
            "normalized_start_utc,observed_at_utc FROM race_schedule_observations "
            "WHERE race_id=? ORDER BY observed_at_utc", (RACE,)
        ).fetchall()


def test_collector_persists_hashed_source_and_current_race(store):
    collector = RikstotoCollector(store, client=SyntheticRacedays())
    assert len(collector.discover(OBS)) == 1
    observations = journal(store)
    assert len(observations) == 1
    assert observations[0][0] == "HASH_ONLY_NO_RAW_BYTES"
    assert observations[0][1] == "HTTP_RESPONSE_COMPLETED"
    assert len(observations[0][2]) == 64
    assert observations[0][3] == "2026-11-01T12:00:00+00:00"
    assert datetime.fromisoformat(observations[0][4]) > OBS
    assert store.get_race(RACE)["start_time_utc"] == observations[0][3]
    with store.connect() as conn:
        review = assess(conn, race_id=RACE, decision_time=OBS + timedelta(minutes=2))
    assert review.status == "CLOCK_CONSISTENT_RESEARCH_ONLY"
    assert not review.model_eligible and not review.bet_authorized


def test_second_discovery_preserves_first_version_and_flags_conflict(store):
    feed = SyntheticRacedays()
    collector = RikstotoCollector(store, client=feed)
    collector.discover(OBS)
    feed.start = "2026-11-01T12:45:00+01:00"
    collector.discover(OBS + timedelta(minutes=5))
    assert len(journal(store)) == 2
    assert store.get_race(RACE)["start_time_utc"] == "2026-11-01T11:45:00+00:00"
    with store.connect() as conn:
        review = assess(conn, race_id=RACE, decision_time=OBS + timedelta(minutes=6))
    assert review.status == "CLOCK_CONFLICT_QUARANTINE"
    assert review.precutoff_distinct_clocks == 2


def test_fake_payload_without_http_completion_stays_unverified(store):
    collector = RikstotoCollector(store, client=SyntheticRacedays(complete=False))
    collector.discover(OBS)
    observations = journal(store)
    assert len(observations) == 1
    assert observations[0][0] == "PARSED_ONLY"
    assert observations[0][1] == "CALLER_SUPPLIED_UNVERIFIED"
    assert observations[0][2] is None
    with store.connect() as conn:
        review = assess(conn, race_id=RACE, decision_time=OBS + timedelta(minutes=2))
    assert "SOURCE_RESPONSE_COMPLETION_UNVERIFIED" in review.blockers
    assert not review.bet_authorized


def test_failed_race_upsert_rolls_back_schedule_observation(store):
    with store.connect() as conn:
        conn.execute(
            "CREATE TRIGGER fail_race BEFORE INSERT ON races BEGIN "
            "SELECT RAISE(ABORT,'SYNTHETIC_RACE_FAILURE'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        RikstotoCollector(store, client=SyntheticRacedays()).discover(OBS)
    assert journal(store) == []
    assert store.get_race(RACE) is None


def test_failed_provider_fetch_creates_no_schedule_observation(store):
    class FailedDiscovery(SyntheticRacedays):
        def racedays(self):
            return FetchResult(
                url=SOURCE,
                payload=None,
                success=False,
                status_code=503,
                latency_ms=1.0,
                error="SYNTHETIC_503",
            )

    assert RikstotoCollector(store, client=FailedDiscovery()).discover(OBS) == []
    assert journal(store) == []
