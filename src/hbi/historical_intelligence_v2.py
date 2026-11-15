"""Source-original historical race evidence and point-in-time admission.

Never treat the date of a past race as proof that its full result was available
at a later prediction cutoff. Dynamic ATG horse.statistics in a historical
result response are NOT the horse's pre-historic-race strength.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .providers.atg import AtgClient

SCHEMA = "HISTORICAL_INTELLIGENCE_V2_ORIGINAL_PIT_V1"
MISSING = "MISSING"
FIELDS = (
    "race_date", "track", "distance_m", "start_method", "post_position",
    "placing", "finish_time", "kilometre_time", "margin", "prize_earned",
    "race_class", "race_prize", "gallop", "disqualified", "not_finished",
    "driver", "trainer", "track_condition", "race_comment",
)


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("HISTORIC_SOURCE_UTC_REQUIRED")
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError("HISTORIC_SOURCE_TIME_NOT_AWARE")
    return dt.astimezone(UTC)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verified_past_race(
    raw_original: bytes, *,
    claimed_sha256: str,
    claimed_atg_race_id: str,
    source_uri: str,
    observed_at_utc: str,
    source_published_at_utc: str | None,
    model_cutoff_utc: str,
    current_race_start_utc: str,
    horse_id: int,
) -> dict[str, Any]:
    """First-party exact ID result; only witnessed-before-cutoff may be used.

    Source publication time is often unavailable. A stored original actually
    observed before the cutoff can still support a research feature, but is
    never promoted to provider-publication/PIT certification.
    """
    if _sha(raw_original) != claimed_sha256:
        raise ValueError("HISTORIC_RAW_SHA_MISMATCH")
    race_key = (re.fullmatch(r"(\d{4}-\d{2}-\d{2})_([1-9]\d*)_([1-9]\d*)", claimed_atg_race_id)
                if isinstance(claimed_atg_race_id, str) else None)
    if not race_key or source_uri != f"{AtgClient.GAME_API}/vinnare_{claimed_atg_race_id}":
        raise ValueError("HISTORIC_SOURCE_URI_RACE_ID_CONFLICT")
    if type(horse_id) is not int or horse_id <= 0:
        return {
            "schema":SCHEMA,"status":"IDENTITY_UNRESOLVED",
            "horse_id":None,"original_sha256":claimed_sha256,
        }
    cutoff, start, observed = (
        _instant(model_cutoff_utc),_instant(current_race_start_utc),
        _instant(observed_at_utc)
    )
    published = (_instant(source_published_at_utc)
                 if source_published_at_utc is not None else None)
    if not cutoff < start:
        raise ValueError("MODEL_CUTOFF_NOT_BEFORE_CURRENT_RACE")
    evidence = {
        "schema":SCHEMA, "horse_id":horse_id,
        "source_uri":source_uri,
        "original_sha256":claimed_sha256,
        "source_observed_at_utc":observed.isoformat(),
        "source_published_at_utc":published.isoformat() if published else None,
        "model_cutoff_utc":cutoff.isoformat(),
        "provider_publication_attested":published is not None,
        "pit_certified":False,"bet_authority":False,
        "fields":{k:MISSING for k in FIELDS},
        "opponents":[],"opponent_prior_strength_at_that_race":MISSING,
        "complete_prior_horse_history_index_attested":False,
    }
    if observed >= cutoff or (published is not None and published >= cutoff):
        evidence["status"]="NOT_AVAILABLE_AT_PIT"
        return evidence
    payload = json.loads(raw_original)
    races = payload.get("races") if isinstance(payload,dict) else None
    if (not isinstance(races, list) or len(races) != 1
            or not isinstance(races[0], dict) or races[0].get("id") != claimed_atg_race_id):
        raise ValueError("HISTORIC_ATG_RACE_NOT_UNIQUE")
    race=races[0]
    day, track_id, race_number = race_key.groups()
    track = race.get("track")
    if (race.get("date") != day or type(race.get("number")) is not int
            or race["number"] != int(race_number) or not isinstance(track, dict)
            or type(track.get("id")) is not int or track["id"] != int(track_id)
            or track.get("countryCode") not in {"NO", "SE"} or race.get("sport") != "trot"):
        raise ValueError("HISTORIC_ATG_RACE_METADATA_CONFLICT")
    if published is not None and published > observed:
        raise ValueError("HISTORIC_PUBLICATION_AFTER_OBSERVATION")
    available = published if published is not None else observed
    stockholm = ZoneInfo("Europe/Stockholm")
    event_clock = race.get("startTime")
    if event_clock is None:
        precedes_source = date.fromisoformat(day) < available.astimezone(stockholm).date()
    else:
        from .history_feasibility import local_instant

        event = datetime.fromisoformat(event_clock)
        if event.utcoffset() is None:
            event = _instant(local_instant(event_clock, stockholm.key))
        if event.astimezone(stockholm).date().isoformat() != day:
            raise ValueError("HISTORIC_EVENT_CLOCK_DATE_CONFLICT")
        precedes_source = event < available
    if not precedes_source:
        evidence.update(status="NOT_AVAILABLE_AT_PIT", reason="HISTORIC_EVENT_NOT_BEFORE_SOURCE")
        return evidence
    if race.get("status")!="results":
        evidence["status"]="PARTIAL"
        evidence["reason"]="OFFICIAL_PAST_RESULT_NOT_FINAL"
        return evidence
    starts=race.get("starts")
    if not isinstance(starts,list) or len(starts)<2:
        raise ValueError("HISTORIC_RACE_STARTERS_INVALID")
    matches=[r for r in starts if isinstance(r,dict)
             and isinstance(r.get("horse"),dict)
             and r["horse"].get("id")==horse_id]
    if len(matches)!=1:
        evidence["status"]="IDENTITY_UNRESOLVED"
        evidence["reason"]="HORSE_PERMANENT_ID_NOT_UNIQUE_IN_PAST_RACE"
        return evidence
    row=matches[0]
    result=row.get("result")
    if row.get("scratched") is True or not isinstance(result, dict) or not result:
        evidence.update(status="PARTIAL", reason="INDIVIDUAL_RESULT_NOT_IN_SOURCE")
        return evidence
    if "startNumber" in result and (
        type(result["startNumber"]) is not int or type(row.get("number")) is not int
        or result["startNumber"] != row["number"]
    ):
        raise ValueError("HISTORIC_RESULT_START_NUMBER_CONFLICT")
    contenders = []
    field_ids, field_numbers = set(), set()
    for other in starts:
        if not isinstance(other, dict) or not isinstance(other.get("horse"), dict):
            continue
        other_id = other["horse"].get("id")
        number = other.get("number")
        if type(other_id) is not int or other_id <= 0 or type(number) is not int or number <= 0:
            continue
        if other_id in field_ids or number in field_numbers:
            raise ValueError("HISTORIC_ATG_FIELD_IDENTITY_CONFLICT")
        field_ids.add(other_id)
        field_numbers.add(number)
        contenders.append({
            "horse_id": other_id,
            "name_at_original": other["horse"].get("name"),
            "number": number,
            "result_raw": other.get("result"),
            "status": "VERIFIED_RESULT_ROW" if isinstance(other.get("result"), dict) else "PARTIAL",
        })
    if len(contenders) != len(starts):
        evidence.update(status="PARTIAL", reason="PREVIOUS_FIELD_HAS_MISSING_HORSE_IDENTITIES")
    else:
        evidence["status"] = "VERIFIED"
    evidence["fields"]={
        "race_date":race.get("date",MISSING),
        "track":track.get("name",MISSING),
        "distance_m":row.get("distance", race.get("distance", MISSING)),
        "start_method":race.get("startMethod",MISSING),
        "post_position":row.get("postPosition",MISSING),
        "placing":result.get("place",MISSING),
        "finish_time":result.get("time",MISSING),
        "kilometre_time":result.get("kmTime", result.get("kilometreTime", MISSING)),
        "margin":result.get("margin",MISSING),
        "prize_earned":result.get("prizeMoney", result.get("prize", MISSING)),
        "race_class":race.get("terms",MISSING),
        "race_prize":race.get("prize",MISSING),
        "gallop":result.get("galloped", result.get("gallop", MISSING)),
        "disqualified":result.get("disqualified",MISSING),
        "not_finished":result.get("notFinished",MISSING),
        "driver":row.get("driver",MISSING),
        "trainer":MISSING,
        "track_condition":track.get("condition",MISSING),
        "race_comment":result.get("comment",MISSING),
    }
    evidence["opponents"]=contenders
    # Deliberately reject "horse.statistics" from the historical response:
    # when downloaded later, that blob can already include future races.
    evidence["dynamic_horse_statistics_ignored"]=True
    return evidence


def history_coverage(
    original_results: list[dict[str,Any]], *,
    current_horse_id: int | None,
    current_model_cutoff_utc: str,
    original_history_index_complete: bool=False,
) -> dict[str,Any]:
    """Partial retrieval never proves complete last-5, last-10 or last-20."""
    if type(current_horse_id) is not int or current_horse_id<=0:
        return {
            "status":"IDENTITY_UNRESOLVED","last_5":"MISSING",
            "last_10":"MISSING","last_20":"MISSING",
            "verified_historical_results":0,"usable_as_pit":0,
        }
    cutoff=_instant(current_model_cutoff_utc)
    useful=[]
    seen=set()
    for item in original_results:
        if item.get("horse_id")!=current_horse_id:
            continue
        key=item.get("source_uri")
        if key in seen:
            raise ValueError("HISTORICAL_ORIGINAL_DUPLICATE_RACE")
        seen.add(key)
        if (item.get("status")=="VERIFIED"
                and _instant(item["source_observed_at_utc"]) < cutoff):
            useful.append(item)
    # The complete history index needs separate independent attestation
    # (a collection of cherry-picked races cannot be called 'last 10').
    state="VERIFIED" if original_history_index_complete and len(useful)>=20 else (
        "PARTIAL" if useful else "MISSING"
    )
    return {
        "status":state,
        "verified_historical_results":len(useful),
        "usable_as_pit":len(useful),
        "last_5":"VERIFIED" if original_history_index_complete and len(useful)>=5 else "MISSING",
        "last_10":"VERIFIED" if original_history_index_complete and len(useful)>=10 else "MISSING",
        "last_20":"VERIFIED" if original_history_index_complete and len(useful)>=20 else "MISSING",
        "opponent_strength_historic":"MISSING_NO_PRIOR_AT_THAT_RACE_OPPONENT_PROVENANCE",
        "source_published_at_attested":all(
            x.get("source_published_at_utc") is not None for x in useful
        ) if useful else False,
        "outcome_trained_or_updated":False,
    }
