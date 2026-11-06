"""Bounded one-time official ATG *historic race* results for Karat River.

The ten race dates/track/number are discovery hints, NOT original evidence.
Only original ATG race bytes with horse id 767446 and published race result
can establish a result. Fetched after Färjestad start: RETROSPECTIVE ONLY.
Never read a historical race's dynamic horse.statistics as point-in-time truth.
No betting, modelling, threshold changes, or scheduled jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from hbi.providers.atg import AtgClient
from scripts.weekend_atg_readiness_readonly import _get_original

SCHEMA="KARAT_RIVER_HISTORICAL_ATG_RESULTS_RESEARCH_ONLY_V1"
HORSE_ID=767446
MAX_REQUESTS=20
TARGET_RACE_START="2026-11-06T18:30:00+00:00"
# Third-party discovery hints only; never accepted without ATG original match.
CANDIDATES=(
    ("2026-06-06","Mantorp",8),
    ("2026-05-13","Axevalla",5),
    ("2026-04-25","Finland",11),
    ("2026-04-11","Jägersro",8),
    ("2026-03-28","Solvalla",11),
    ("2026-03-07","Halmstad",7),
    ("2026-02-14","Åby",7),
    ("2026-01-31","Färjestad",6),
    ("2025-12-26","Solvalla",5),
    ("2025-12-06","Åby",6),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first_party_result(payload: dict, rid: str) -> dict:
    races=payload.get("races") if isinstance(payload,dict) else None
    if not isinstance(races,list) or len(races)!=1 or races[0].get("id")!=rid:
        raise ValueError("HISTORICAL_ATG_PHYSICAL_RACE_CONFLICT")
    race=races[0]
    if race.get("status")!="results":
        raise ValueError("HISTORICAL_RESULT_NOT_FINAL")
    starts=race.get("starts")
    if not isinstance(starts,list) or not starts:
        raise ValueError("HISTORICAL_STARTS_MISSING")
    matches=[row for row in starts if isinstance(row,dict) and
             isinstance(row.get("horse"),dict) and
             row["horse"].get("id")==HORSE_ID and
             row["horse"].get("name")=="Karat River"]
    if len(matches)!=1:
        raise ValueError("KARAT_HORSE_ID_NOT_UNIQUELY_VERIFIED")
    entry=matches[0]
    # Actual result is a separate sibling of HORSE; the horse.statistics
    # blob is dynamic and must never be reused for prior-date strength.
    outcome=entry.get("result")
    if not isinstance(outcome,dict):
        raise ValueError("HISTORIC_KARAT_RESULT_MISSING")
    opponents=[]
    for row in starts:
        if not isinstance(row,dict):
            continue
        horse=row.get("horse")
        if not isinstance(horse,dict):
            continue
        opponents.append({
            "number":row.get("number"),"horse_id":horse.get("id"),
            "horse_name":horse.get("name"),
            "historical_pre_race_money_raw_unverified_unit":horse.get("money"),
            "historic_result":row.get("result"),
            "do_not_use_current_horse_statistics_as_pit":True,
        })
    return {
        "race_id":rid,"race_name":race.get("name"),"race_date":race.get("date"),
        "track":(race.get("track") or {}).get("name"),
        "start_method":race.get("startMethod"),
        "distance_m":race.get("distance"),"terms":race.get("terms"),
        "prize":race.get("prize"),"start_number":entry.get("number"),
        "post_position":entry.get("postPosition"),
        "driver":entry.get("driver"),
        "result":outcome,
        "opponents_in_same_historic_race":opponents,
        "opponent_actual_previous_strength":None,
        "opponent_strength_blocker":"NO_PIT_PAST_RESULTS_FOR_ALL_OPPONENTS",
    }


def capture(output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=False)
    originals=output/"originals"
    originals.mkdir()
    receipts=[]
    items=[]
    request_count=0
    for date,track_name,number in CANDIDATES:
        if date >= TARGET_RACE_START[:10]:
            raise ValueError("HISTORICAL_RESULT_EVENT_NOT_PRE_RACE")
        hint={"date":date,"track_hint":track_name,"race_hint":number,
              "hint_is_original_source":False}
        calendar_url=(AtgClient.CALENDAR_API+"/calendar/day/"
                      +date+"?headToHeadEnabled=true")
        cal, receipt=_get_original(calendar_url,originals)
        request_count+=1
        receipts.append(receipt)
        entry={**hint,"status":"CALENDAR_NOT_ATTESTED",
               "atg_race_id":None,"original_race_sha256":None,
               "verified_atg_historic_result":None}
        if not cal.success or not isinstance(cal.payload,dict):
            entry["reason"]="ATG_HISTORIC_CALENDAR_HTTP_OR_SCHEMA"
            items.append(entry)
            continue
        tracks=[
            t for t in cal.payload.get("tracks",[])
            if isinstance(t,dict)
            and str(t.get("name") or "").casefold()==track_name.casefold()
        ]
        if len(tracks)!=1:
            entry.update(status="TRACK_NOT_UNIQUE_IN_ATG_CALENDAR")
            items.append(entry)
            continue
        calendar_races=[
            r for r in tracks[0].get("races",[])
            if isinstance(r,dict) and r.get("number")==number
        ]
        if len(calendar_races)!=1:
            entry.update(status="RACE_NOT_UNIQUE_IN_ATG_CALENDAR")
            items.append(entry)
            continue
        atg_id=calendar_races[0].get("id")
        if (not isinstance(atg_id,str)
                or not atg_id.startswith(date+"_")
                or atg_id.rsplit("_",1)[-1]!=str(number)):
            raise ValueError("ATG_CALENDAR_RACE_ID_INVALID")
        url=AtgClient.GAME_API+"/vinnare_"+atg_id
        result,result_receipt=_get_original(url,originals)
        request_count+=1
        receipts.append(result_receipt)
        entry["atg_race_id"]=atg_id
        if result.success and isinstance(result.payload,dict):
            try:
                extracted=_first_party_result(result.payload,atg_id)
            except (ValueError,TypeError,KeyError) as exc:
                entry.update(status="HISTORIC_RESULT_SOURCE_REJECTED",reason=str(exc))
            else:
                entry.update(
                    status="HISTORIC_EVENT_RESULT_VERIFIED_RESEARCH_ONLY",
                    original_race_sha256=result_receipt["response_sha256"],
                    verified_atg_historic_result=extracted,
                )
        else:
            entry.update(status="RESULT_HTTP_OR_PAYLOAD_UNAVAILABLE")
        items.append(entry)
        if result_receipt.get("http_status") in (403,429):
            break  # source quota backpressure; never bypass
        time.sleep(0.15)
    if request_count>MAX_REQUESTS:
        raise ValueError("OFFICIAL_HISTORIC_REQUEST_BUDGET_EXCEEDED")
    return {
        "schema":SCHEMA,"bet_authority":False,
        "original_source_capture_after_current_farsjestad_start":True,
        "prospective_farsjestad_signal":False,
        "do_not_reuse_current_horse_statistics_as_historical_pit":True,
        "historical_hints_only":list(CANDIDATES),
        "capture_complete_utc":datetime.now(UTC).isoformat(),
        "request_count":request_count,
        "verified_result_count":sum(
            r["status"]=="HISTORIC_EVENT_RESULT_VERIFIED_RESEARCH_ONLY"
            for r in items
        ),
        "items":items,"original_atg_receipts":receipts,
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    out=capture(a.output)
    (a.output/"index.json").write_text(
        json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "verified_results":out["verified_result_count"],
        "requests":out["request_count"],
        "statuses":[(x["date"],x["status"]) for x in out["items"]],
        "bet_authority":False,
    },ensure_ascii=False))


if __name__=="__main__":
    main()
