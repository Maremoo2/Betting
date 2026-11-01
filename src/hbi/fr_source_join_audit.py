"""P0 FR original-source calendar identity diagnostic, NO model/BET authority.

One public GET to Rikstoto race calendar and at most 7 official ATG day
calendars. Strict matching of country, trot, track, race number, UTC time,
upcoming status and uniqueness. Do NOT resolve horse IDs by dates alone.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .providers.atg import AtgClient, AtgFetchResult
from .providers.rikstoto import RikstotoClient, RikstotoRace

PARIS = ZoneInfo("Europe/Paris")


def _name(name: str) -> str:
    normalized = AtgClient._normalize_name(name)
    return {"parisvincennes": "vincennes"}.get(normalized, normalized)


def _parsed_payload_hash(value: object) -> str | None:
    """Only hash the parsed representation, NEVER claim provider raw body SHA."""
    try:
        return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return None


def classify_original_fr_race(
    race: RikstotoRace, response: AtgFetchResult,
) -> dict[str, Any]:
    """Fail-closed source-level match, never a field or horse-history join."""
    ref = {
        "rikstoto_race_id": race.race_id,
        "rikstoto_track": race.raceday_name,
        "rikstoto_race_number": race.race_number,
        "rikstoto_start_time_utc": (
            race.start_time.astimezone(UTC).isoformat()
            if race.start_time.utcoffset() is not None else None
        ),
        "atg_source_url": response.url,
        "atg_http_status": response.status_code,
        "atg_parsed_payload_sha256_not_raw_http": (
            _parsed_payload_hash(response.payload) if response.success else None
        ),
        "exact_source_race_identity_verified": False,
        "full_field_history_verified": False,
        "pit_source_published_before_event_verified": False,
        "bet_authority": False,
    }
    if race.country_code != "FR" or race.sport_type not in {"trot", "Trot"}:
        return {**ref, "reason": "NOT_CANONICAL_FRENCH_TROT"}
    if race.start_time.utcoffset() is None or type(race.race_number) is not int:
        return {**ref, "reason": "INVALID_CANONICAL_RACE_IDENTITY"}
    if not response.success or response.status_code != 200:
        return {**ref, "reason": "ATG_CALENDAR_FETCH_FAILED"}
    if not isinstance(response.payload, dict) or not isinstance(
        response.payload.get("tracks"), list
    ):
        return {**ref, "reason": "ATG_CALENDAR_SCHEMA_INVALID"}
    tracks = [
        t for t in response.payload["tracks"]
        if isinstance(t, dict) and t.get("countryCode") == "FR"
        and t.get("sport") == "trot"
        and isinstance(t.get("name"), str)
    ]
    same_track = [t for t in tracks if _name(t["name"]) == _name(race.raceday_name)]
    ref["fr_atg_trot_venues_observed"] = sorted({t["name"] for t in tracks})
    if not same_track:
        return {**ref, "reason": "NO_IDENTICAL_FR_HIPPODROME_IN_ATG"}
    if any(not isinstance(t.get("races"), list) for t in same_track):
        return {**ref, "reason": "ATG_MEETING_RACE_LIST_INVALID"}
    same_number = [
        r for t in same_track for r in t["races"]
        if isinstance(r, dict) and type(r.get("number")) is int
        and r["number"] == race.race_number
    ]
    if not same_number:
        return {**ref, "reason": "NO_IDENTICAL_RACE_NUMBER_AT_SAME_TRACK"}
    exact = [
        r for r in same_number
        if r.get("status") == "upcoming"
        and isinstance(r.get("id"), str) and bool(r["id"])
        and (time := AtgClient._parse_time(r.get("startTime"))) is not None
        and abs((time - race.start_time).total_seconds()) <= 300
    ]
    if len(exact) != 1:
        return {
            **ref, "reason": ("AMBIGUOUS_SAME_TRACK_RACE_TIME"
                               if len(exact) > 1 else
                               "RACE_START_OR_UPCOMING_STATUS_MISMATCH"),
            "possible_same_number_count": len(same_number),
            "exact_candidate_count": len(exact),
        }
    return {
        **ref, "reason": "EXACT_PROVIDER_CALENDAR_IDENTITY_ONLY",
        "exact_source_race_identity_verified": True,
        "atg_race_id": exact[0]["id"],
        "atg_source_start_utc": (
            AtgClient._parse_time(exact[0]["startTime"]).isoformat()
        ),
        "possible_same_number_count": len(same_number),
        "exact_candidate_count": 1,
    }


def run_source_overlap_audit(
    *, rikstoto: RikstotoClient | None = None,
    atg: AtgClient | None = None,
    now: datetime | None = None,
    horizon_days: int = 7,
) -> dict[str, Any]:
    clock = now or datetime.now(UTC)
    if clock.utcoffset() is None or type(horizon_days) is not int or not 1 <= horizon_days <= 7:
        raise ValueError("Timezone-aware current time and 1..7 day horizon required")
    rik = rikstoto or RikstotoClient()
    atg_client = atg or AtgClient()
    original = rik.racedays()
    report: dict[str, Any] = {
        "schema": "FR_INDEPENDENT_EXACT_SOURCE_JOIN_DIAGNOSTIC_V1",
        "captured_at_utc": clock.astimezone(UTC).isoformat(),
        "rikstoto_source_url": original.url,
        "rikstoto_http_status": original.status_code,
        "rikstoto_raw_response_sha256": original.response_body_sha256,
        "rikstoto_source_success": (
            original.success and original.status_code == 200
            and isinstance(original.payload, dict)
            and isinstance(original.payload.get("result"), list)
        ),
        "source_snapshot_first_published_at_verified": False,
        "live_full_field_fr_pass": False,
        "full_field_history_join_performed": False,
        "market_data_used_as_horse_features": False,
        "pit_certified": False,
        "frozen_strategy_modified": False,
        "bet_authority": False,
        "races": [],
    }
    if not report["rikstoto_source_success"]:
        report["status"] = "RIKSTOTO_ORIGINAL_CALENDAR_NOT_VERIFIED"
        return report
    future_cutoff = clock + timedelta(days=horizon_days)
    races = [
        r for r in rik.discover_races(original)
        if r.country_code == "FR"
        and r.sport_type.lower() == "trot"
        and r.progress_status == "Future"
        and clock < r.start_time <= future_cutoff
    ]
    races.sort(key=lambda r: (r.start_time, r.race_id))
    if len(races) > 100:
        report["status"] = "SOURCE_RACE_DENOMINATOR_UNBOUNDED"
        return report
    calendar_dates = sorted({
        r.start_time.astimezone(PARIS).date() for r in races
    })
    if len(calendar_dates) > 7:
        report["status"] = "SOURCE_DAY_DENOMINATOR_UNBOUNDED"
        return report
    calendars: dict[str, AtgFetchResult] = {}
    for day in calendar_dates:
        calendars[day.isoformat()] = atg_client.calendar_day(day)
    report["atg_calendar_dates_queried"] = list(calendars)
    report["atg_calendar_source_success_count"] = sum(
        c.success and c.status_code == 200
        and isinstance(c.payload, dict) and isinstance(c.payload.get("tracks"), list)
        for c in calendars.values()
    )
    for race in races:
        day = race.start_time.astimezone(PARIS).date().isoformat()
        report["races"].append(classify_original_fr_race(race, calendars[day]))
    report["rikstoto_fr_races_in_window"] = len(races)
    report["exact_calendar_identity_matches"] = sum(
        row["exact_source_race_identity_verified"] for row in report["races"]
    )
    report["reasons"] = dict(sorted(Counter(
        row["reason"] for row in report["races"]
    ).items()))
    if not races:
        report["status"] = "NO_CANONICAL_FR_FUTURE_RACES_IN_SOURCE_WINDOW"
    elif report["atg_calendar_source_success_count"] != len(calendars):
        report["status"] = "INCOMPLETE_ATG_ORIGINAL_CALENDAR_SOURCE"
    elif not report["exact_calendar_identity_matches"]:
        report["status"] = "NO_IDENTICAL_FR_RACES_ACROSS_OFFICIAL_SOURCES"
    else:
        report["status"] = "FR_CALENDAR_MATCH_FOUND_FULL_FIELD_STILL_UNVERIFIED"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon-days", type=int, default=7)
    args = parser.parse_args()
    payload = run_source_overlap_audit(horizon_days=args.horizon_days)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({
        k: v for k, v in payload.items() if k != "races"
    }, ensure_ascii=False, indent=2))
    if not payload["rikstoto_source_success"]:
        raise SystemExit(2)
    if payload.get("atg_calendar_source_success_count") != len(
        payload.get("atg_calendar_dates_queried", [])
    ):
        raise SystemExit(2)
    # Successful source DIAGNOSIS is NOT a successful full-field capability;
    # existing HBI Provider Live Smoke remains the only live full-field gate.


if __name__ == "__main__":
    main()
