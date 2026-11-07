"""Source-original historical race evidence and point-in-time admission.

Never treat the date of a past race as proof that its full result was available
at a later prediction cutoff. Dynamic ATG horse.statistics in a historical
result response are NOT the horse's pre-historic-race strength.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

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
    if (not isinstance(source_uri,str)
            or not source_uri.endswith("/vinnare_" + claimed_atg_race_id)):
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
    if observed > cutoff or (published is not None and published > cutoff):
        evidence["status"]="NOT_AVAILABLE_AT_PIT"
        return evidence
    payload = json.loads(raw_original)
    races = payload.get("races") if isinstance(payload,dict) else None
    if (not isinstance(races,list) or len(races)!=1
            or races[0].get("id")!=claimed_atg_race_id):
        raise ValueError("HISTORIC_ATG_RACE_NOT_UNIQUE")
    race=races[0]
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
    if not isinstance(result,dict):
        evidence["status"]="PARTIAL"
        evidence["reason"]="INDIVIDUAL_RESULT_NOT_IN_SOURCE"
        return evidence
    contenders=[]
    for other in starts:
        if not isinstance(other,dict) or not isinstance(other.get("horse"),dict):
            continue
        id_value=other["horse"].get("id")
        contenders.append({
            "horse_id":id_value if type(id_value) is int and id_value>0 else None,
            "name_at_original":other["horse"].get("name"),
            "number":other.get("number"),
            "result_raw":other.get("result"),
            "status":"VERIFIED_RESULT_ROW" if isinstance(other.get("result"),dict)
                     else "PARTIAL",
        })
    if len(contenders)!=len(starts):
        evidence["status"]="PARTIAL"
        evidence["reason"]="PREVIOUS_FIELD_HAS_MISSING_HORSE_IDENTITIES"
    else:
        evidence["status"]="VERIFIED"
    track=race.get("track") or {}
    evidence["fields"]={
        "race_date":race.get("date",MISSING),
        "track":track.get("name",MISSING),
        "distance_m":race.get("distance",MISSING),
        "start_method":race.get("startMethod",MISSING),
        "post_position":row.get("postPosition",MISSING),
        "placing":result.get("place",MISSING),
        "finish_time":result.get("time",MISSING),
        "kilometre_time":result.get("kilometreTime",MISSING),
        "margin":result.get("margin",MISSING),
        "prize_earned":result.get("prize",MISSING),
        "race_class":race.get("terms",MISSING),
        "race_prize":race.get("prize",MISSING),
        "gallop":result.get("gallop",MISSING),
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
                and _instant(item["source_observed_at_utc"])<=cutoff):
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
