"""MERGE-RECOVERY-001: WIN times never precede response completion (offline)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hbi.provider_capability import resolve_field
from hbi.providers.rikstoto import FetchResult, RikstotoClient
from hbi.rikstoto_collector import RikstotoCollector


class Journal:
    def __init__(self):
        self.market_rows = []
        self.win_rows = []
        self.audit_rows = []

    def record_provider_fetch(self, **kwargs):
        self.audit_rows.append(kwargs)

    def insert_provider_market_snapshot(self, **kwargs):
        self.market_rows.append(kwargs)
        return True

    def insert_market_snapshot(self, snapshot, **kwargs):
        self.win_rows.append(snapshot)
        return True


RACE = "RIKSTOTO:S2_NR_2026-11-12:1"
START = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
DONE = START + timedelta(seconds=3)


def fetched(completed=DONE):
    return FetchResult(
        url="https://www.rikstoto.no/api/racedays/S2_NR_2026-11-12/V/1",
        payload={"result": [{"startNumber": 1, "odds": 3.5, "updatedAt": START.isoformat()}]},
        success=True, status_code=200, latency_ms=3000,
        response_completed_at=completed, response_body_sha256="a" * 64,
    )


def test_win_uses_completed_http_response_in_both_sqlite_tables():
    store = Journal()
    collector = RikstotoCollector(store, client=RikstotoClient(), clock=lambda: DONE)
    collector._store_fetch_rows(
        race_id=RACE, product="V", fetch=fetched(), observed_at=START
    )
    assert len(store.market_rows) == len(store.win_rows) == 1
    assert store.market_rows[0]["observed_at"] == DONE
    assert store.win_rows[0].captured_at == DONE
    assert store.audit_rows[0]["fetched_at"] == DONE
    assert store.market_rows[0]["provider_updated_at"] != DONE  # not receipt clock


def test_missing_completion_is_stamped_conservatively_at_processing():
    processed = DONE + timedelta(seconds=4)
    store = Journal()
    collector = RikstotoCollector(store, client=RikstotoClient(), clock=lambda: processed)
    collector._store_fetch_rows(
        race_id=RACE, product="V", fetch=fetched(completed=None),
        observed_at=START,
    )
    assert store.market_rows[0]["observed_at"] == processed
    assert store.win_rows[0].captured_at == processed


def test_completion_earlier_than_callers_clock_does_not_backdate():
    store = Journal()
    collector = RikstotoCollector(store, client=RikstotoClient(), clock=lambda: DONE)
    later = DONE + timedelta(seconds=2)
    collector._store_fetch_rows(
        race_id=RACE, product="V", fetch=fetched(), observed_at=later
    )
    assert store.market_rows[0]["observed_at"] == later


def test_naive_response_completion_fails_closed():
    store = Journal()
    collector = RikstotoCollector(store, client=RikstotoClient())
    with pytest.raises(ValueError, match="WIN_RESPONSE_COMPLETION_CLOCK_NAIVE"):
        collector._store_fetch_rows(
            race_id=RACE, product="V",
            fetch=fetched(datetime(2026, 11, 12, 15, 0)), observed_at=START
        )
    assert not store.market_rows and not store.win_rows


def test_atg_wrong_physical_race_id_is_rejected():
    """The existing full-field gate binds ATG payload.id to the calendar race ref."""
    now = START
    expected = START + timedelta(minutes=35)
    canonical = [
        {"startNumber": 1, "horseName": "Authentic Name",
         "raceNumber": 1, "isScratched": False},
        {"startNumber": 2, "horseName": "Second Horse",
         "raceNumber": 1, "isScratched": False},
    ]
    payload = {
        "id": "WRONG_RACE_ID", "sport": "trot", "status": "upcoming",
        "startTime": expected.isoformat(),
        "track": {"countryCode": "SE"},
        "starts": [
            {"number": 1, "horse": {"id": "ATG-ONE", "name": "Authentic Name"}},
            {"number": 2, "horse": {"id": "ATG-TWO", "name": "Second Horse"}},
        ],
    }
    _, evidence = resolve_field(
        starts=canonical, scratches=set(), scratch_ok=True,
        payload=payload, country="SE", discipline="trot",
        race_number=1, expected_start=expected, observed_at=now,
        provider_race_id="EXPECTED_RACE_ID", source_uri="https://www.atg.se/",
    )
    assert "PROVIDER_RACE_IDENTITY_OR_TIME" in evidence["reasons"]
    assert evidence["passed"] is False
