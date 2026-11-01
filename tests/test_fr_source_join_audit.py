"""FR source join negatives: track, race no, UTC start, status, duplicate identity."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from hbi.fr_source_join_audit import classify_original_fr_race, run_source_overlap_audit
from hbi.providers.atg import AtgFetchResult
from hbi.providers.rikstoto import FetchResult, RikstotoRace

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
PARIS = ZoneInfo("Europe/Paris")
START = datetime(2026, 11, 1, 14, 15, tzinfo=UTC)
RACEDAY = "F1_NR_2026-11-01"


def race(**change):
    kwargs = {
        "raceday_key": RACEDAY, "raceday_name": "Laval", "track_code": "5305",
        "country_code": "FR", "sport_type": "trot", "race_number": 4, "start_time": START,
        "start_time_raw": "2026-11-01T15:15:00+01:00", "start_method": "auto",
        "progress_status": "Future", "pools": (), "single_leg_products": ("V",),
    }
    return RikstotoRace(**{**kwargs, **change})


def calendar(*, track="Laval", number=4, start=START,
             status="upcoming", country="FR", discipline="trot"):
    return AtgFetchResult(
        "https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/2026-11-01",
        {"tracks": [{
            "name": track, "countryCode": country, "sport": discipline,
            "races": [{
                "number": number, "id": "2026-11-01_53_4",
                "status": status, "startTime": start.isoformat(),
            }],
        }]},
        True, 200, 1.0,
    )


def test_identical_fr_course_is_only_calendar_match_never_history_or_bet():
    item = classify_original_fr_race(race(), calendar())
    assert item["reason"] == "EXACT_PROVIDER_CALENDAR_IDENTITY_ONLY"
    assert item["exact_source_race_identity_verified"] is True
    assert item["full_field_history_verified"] is False
    assert item["pit_source_published_before_event_verified"] is False
    assert item["bet_authority"] is False
    assert len(item["atg_parsed_payload_sha256_not_raw_http"]) == 64


@pytest.mark.parametrize(("variation", "expected"), [
    ({"track": "Vincennes"}, "NO_IDENTICAL_FR_HIPPODROME_IN_ATG"),
    ({"track": "Laval", "number": 3}, "NO_IDENTICAL_RACE_NUMBER_AT_SAME_TRACK"),
    ({"track": "Laval", "start": START + timedelta(minutes=6)},
     "RACE_START_OR_UPCOMING_STATUS_MISMATCH"),
    ({"track": "Laval", "status": "results"},
     "RACE_START_OR_UPCOMING_STATUS_MISMATCH"),
    ({"track": "Laval", "country": "SE"}, "NO_IDENTICAL_FR_HIPPODROME_IN_ATG"),
    ({"track": "Laval", "discipline": "gallop"},
     "NO_IDENTICAL_FR_HIPPODROME_IN_ATG"),
])
def test_no_cross_race_join_on_same_country_or_number_alone(variation, expected):
    detail = classify_original_fr_race(race(), calendar(**variation))
    assert detail["reason"] == expected
    assert not detail["exact_source_race_identity_verified"]
    assert not detail["full_field_history_verified"]


def test_duplicated_same_provider_race_is_ambiguity_not_success():
    feed = calendar()
    feed.payload["tracks"].append(deepcopy(feed.payload["tracks"][0]))
    result = classify_original_fr_race(race(), feed)
    assert result["reason"] == "AMBIGUOUS_SAME_TRACK_RACE_TIME"
    assert result["exact_candidate_count"] == 2
    assert not result["exact_source_race_identity_verified"]


def test_malformed_calendar_and_unavailable_original_fail_closed():
    c = calendar()
    c.payload["tracks"] = "not-a-list"
    assert classify_original_fr_race(race(), c)["reason"] == "ATG_CALENDAR_SCHEMA_INVALID"
    c = AtgFetchResult(calendar().url, None, False, 403, 1.0, "Forbidden")
    assert classify_original_fr_race(race(), c)["reason"] == "ATG_CALENDAR_FETCH_FAILED"


def test_strict_existing_verified_paris_vincennes_alias():
    target = race(raceday_name="Paris-Vincennes")
    other = calendar(track="Vincennes")
    assert classify_original_fr_race(target, other)["exact_source_race_identity_verified"]
    not_aliased = race(raceday_name="Paris-Laval")
    assert not classify_original_fr_race(not_aliased, calendar())[
        "exact_source_race_identity_verified"
    ]


class FakeRikstoto:
    def __init__(self, races=None, success=True):
        self.races = races if races is not None else [race()]
        self.success = success
        self.calls = 0

    def racedays(self):
        self.calls += 1
        return FetchResult(
            "https://www.rikstoto.no/api/racedays/",
            {"result": []} if self.success else None,
            self.success, 200 if self.success else 503, 1.0,
            response_body_sha256="a" * 64 if self.success else None,
        )

    def discover_races(self, original):
        assert original.success
        return self.races


class FakeAtg:
    def __init__(self, response=None):
        self.response = response if response is not None else calendar()
        self.dates = []

    def calendar_day(self, day):
        self.dates.append(day.isoformat())
        return self.response


def test_source_audit_realistic_laval_vs_vincennes_cannot_become_live_fr_pass():
    rik, atg = FakeRikstoto(), FakeAtg(calendar(track="Vincennes"))
    report = run_source_overlap_audit(rikstoto=rik, atg=atg, now=NOW)
    assert rik.calls == 1
    assert atg.dates == ["2026-11-01"]
    assert report["status"] == "NO_IDENTICAL_FR_RACES_ACROSS_OFFICIAL_SOURCES"
    assert report["rikstoto_fr_races_in_window"] == 1
    assert report["exact_calendar_identity_matches"] == 0
    assert report["reasons"] == {"NO_IDENTICAL_FR_HIPPODROME_IN_ATG": 1}
    assert report["rikstoto_raw_response_sha256"] == "a" * 64
    assert report["source_snapshot_first_published_at_verified"] is False
    assert report["live_full_field_fr_pass"] is False
    assert report["pit_certified"] is False
    assert report["bet_authority"] is False


def test_source_audit_calendar_match_is_still_not_full_field():
    report = run_source_overlap_audit(
        rikstoto=FakeRikstoto(), atg=FakeAtg(), now=NOW,
    )
    assert report["status"] == "FR_CALENDAR_MATCH_FOUND_FULL_FIELD_STILL_UNVERIFIED"
    assert report["exact_calendar_identity_matches"] == 1
    assert report["live_full_field_fr_pass"] is False
    assert report["full_field_history_join_performed"] is False


def test_broken_rikstoto_source_does_not_contact_atg():
    atg = FakeAtg()
    report = run_source_overlap_audit(
        rikstoto=FakeRikstoto(success=False), atg=atg, now=NOW,
    )
    assert report["status"] == "RIKSTOTO_ORIGINAL_CALENDAR_NOT_VERIFIED"
    assert not atg.dates
    assert report["bet_authority"] is False


def test_empty_fr_program_is_coverage_unknown_not_green():
    atg = FakeAtg()
    report = run_source_overlap_audit(
        rikstoto=FakeRikstoto(races=[]), atg=atg, now=NOW,
    )
    assert report["status"] == "NO_CANONICAL_FR_FUTURE_RACES_IN_SOURCE_WINDOW"
    assert report["exact_calendar_identity_matches"] == 0
    assert report["live_full_field_fr_pass"] is False
    assert atg.dates == []


def test_missing_atg_public_calendar_does_not_change_fr_registry():
    forbidden = AtgFetchResult(calendar().url, None, False, 500, 1.0)
    result = run_source_overlap_audit(
        rikstoto=FakeRikstoto(), atg=FakeAtg(forbidden), now=NOW,
    )
    assert result["status"] == "INCOMPLETE_ATG_ORIGINAL_CALENDAR_SOURCE"
    assert result["reasons"] == {"ATG_CALENDAR_FETCH_FAILED": 1}
    assert result["bet_authority"] is False


@pytest.mark.parametrize("bad", [0, 8, -1, 3.5, True])
def test_out_of_bounds_calendar_horizon_rejected(bad):
    with pytest.raises(ValueError, match="1..7"):
        run_source_overlap_audit(
            rikstoto=FakeRikstoto(), atg=FakeAtg(), now=NOW,
            horizon_days=bad,
        )


def test_malformed_canonical_time_rejected_without_live_promotion():
    unusual = race(start_time=datetime(2026, 11, 1, 14, 15))
    result = classify_original_fr_race(unusual, calendar())
    assert result["reason"] == "INVALID_CANONICAL_RACE_IDENTITY"
    assert not result["exact_source_race_identity_verified"]
