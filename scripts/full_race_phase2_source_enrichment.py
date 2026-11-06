"""Phase 2: original-backed per-runner history context; NEVER re-estimate Champion.

Only uses already archived ATG/Rikstoto *pre-race* source bytes and the original
Full Race Intelligence shadow report. Missing individual past starts, historic
opponents, finish times, disqualifications and race shapes remain MISSING.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "FULL_RACE_INTELLIGENCE_PHASE2_SOURCE_V1"
TRACKS = ("FARJESTAD_V64", "BERGSAKER_V85", "KLOSTERSKOGEN_V75")
ATG_BASE = "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_"
MISSING = "MISSING"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clock(text: Any) -> datetime:
    if not isinstance(text, str):
        raise TypeError("REQUIRED_ORIGINAL_UTC_MISSING")
    d = datetime.fromisoformat(text)
    if d.utcoffset() is None:
        raise ValueError("REQUIRED_ORIGINAL_UTC_NAIVE")
    return d.astimezone(UTC)


def _source_bytes(root: Path, subdir: str, digest: str) -> bytes:
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("ORIGINAL_SOURCE_SHA_REQUIRED")
    name = digest + ".json"
    candidate = root / subdir / name
    if candidate.is_symlink():
        raise ValueError("ORIGINAL_SYMLINK_REJECTED")
    raw = candidate.read_bytes()
    if _sha(raw) != digest:
        raise ValueError("ORIGINAL_SOURCE_SHA_MISMATCH")
    return raw


def _receipt_map(folder: Path, atg: dict) -> dict[str, tuple[dict, dict]]:
    indexed: dict[str, tuple[dict, dict]] = {}
    for receipt in atg["original_atg_receipts"]:
        url = receipt.get("url")
        digest = receipt.get("response_sha256")
        if (not isinstance(url, str)
                or not url.startswith(ATG_BASE)
                or receipt.get("http_status") != 200
                or receipt.get("success") is not True
                or receipt.get("raw_original_path") != str(digest) + ".json"):
            continue  # calendar originals are separately attested by source probe
        raw = _source_bytes(folder, "atg-originals", digest)
        payload = json.loads(raw)
        now = _clock(receipt["response_completed_utc"])
        older = indexed.get(url)
        if older is None or now < _clock(older[1]["response_completed_utc"]):
            indexed[url] = (payload, receipt)
        elif older[0] != payload:
            raise ValueError("SAME_URL_ORIGINAL_CONFLICT")
    return indexed


def _person(data: Any) -> dict:
    if not isinstance(data, dict):
        return {"id":None,"name":MISSING}
    first = data.get("firstName") or ""
    last = data.get("lastName") or ""
    return {
        "id":data.get("id") if type(data.get("id")) is int else None,
        "name":" ".join(x for x in (first,last) if x).strip() or
               data.get("name") or MISSING,
    }


def _number(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _historical(entrant: dict, receipt: dict, observed: datetime) -> dict:
    horse = entrant.get("horse")
    if not isinstance(horse, dict):
        raise TypeError("ATG_ENTRY_HORSE_RECORD_REQUIRED")
    stats = horse.get("statistics") or {}
    life = stats.get("life") or {}
    years = stats.get("years") or {}
    if not isinstance(life, dict) or not isinstance(years, dict):
        raise TypeError("ATG_HORSE_STATISTICS_SCHEMA_UNVERIFIED")
    recent = stats.get("lastFiveStarts") or {}
    annual = {}
    for year in ("2025","2026"):
        values = years.get(year)
        if not isinstance(values, dict):
            annual[year] = MISSING
            continue
        placements = values.get("placement") or {}
        annual[year] = {
            "starts":_number(values.get("starts")),
            "wins":_number(placements.get("1")),
            "seconds":_number(placements.get("2")),
            "thirds":_number(placements.get("3")),
            "earnings_raw_ore_or_provider_units":values.get("earnings"),
            "not_individual_race_results":True,
        }
    return {
        "atg_horse_id":horse.get("id") if type(horse.get("id")) is int else None,
        "atg_source_observed_utc":observed.isoformat(),
        "atg_original_sha256":receipt["response_sha256"],
        "life_starts":_number(life.get("starts")),
        "life_wins":_number((life.get("placement") or {}).get("1")),
        "life_seconds":_number((life.get("placement") or {}).get("2")),
        "life_thirds":_number((life.get("placement") or {}).get("3")),
        "life_earnings_provider_raw":life.get("earnings"),
        "current_pre_race_money_provider_raw":horse.get("money"),
        "start_points_at_source":life.get("startPoints"),
        "calendar_years":annual,
        "best_historical_records_not_recent_results":life.get("records") or MISSING,
        "recent_5_aggregate_average_odds_raw":(
            recent.get("averageOdds") if isinstance(recent,dict)
            else None
        ),
        "last_5_individual_results":MISSING,
        "last_10_individual_results":MISSING,
        "last_5_10_history_gap_reason":"ATG_GAME_HAS_AGGREGATE_STATS_NOT_PAST_RACE_ROWS",
        "last_start_date":MISSING,
        "days_since_last_start":MISSING,
        "recent_finishing_times":MISSING,
        "recent_kilometre_times":MISSING,
        "recent_margins":MISSING,
        "recent_gallops_and_disqualifications":MISSING,
        "previous_opponents_and_head_to_head":MISSING,
        "prior_opponent_strength_at_historic_race":MISSING,
        "class_adjusted_performance":MISSING,
        "verified_pace_and_sections":MISSING,
        "horse_age_at_source":horse.get("age"),
        "current_driver":_person(entrant.get("driver")),
        "current_trainer":_person(horse.get("trainer")),
        "driver_change_from_previous_start":MISSING,
        "trainer_change_from_previous_start":MISSING,
        "post_position_from_atg":entrant.get("postPosition"),
        "declared_distance_m":entrant.get("distance"),
        "shoe_change_reported":horse.get("shoes"),
        "sulky_change_reported":horse.get("sulky"),
        "source_status":"ATG_PRE_RACE_AGGREGATE_AND_DECLARATION_ONLY",
    }


def build(originals: Path, full_race: Path) -> dict:
    raw_report = (originals / "original-capture" /
                  "weekend-race-intelligence.json").read_bytes()
    raw_atg = (originals / "atg-original-readiness" /
               "atg-readiness.json").read_bytes()
    source, atg = json.loads(raw_report), json.loads(raw_atg)
    full = json.loads(full_race.read_bytes())
    if (source.get("schema") != "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
            or atg.get("schema") != "WEEKEND_ATG_AUTHENTIC_SOURCE_DIAGNOSTIC_V1"
            or full.get("schema") != "FULL_RACE_INTELLIGENCE_ORIGINALS_V1"
            or full.get("source_capture_sha256") != _sha(raw_report)
            or any(x.get("bet_authority") is not False for x in
                   (source,atg,full))):
        raise ValueError("PHASE2_SOURCE_REPORT_JOIN_UNTRUSTED")
    receipts = _receipt_map(originals/"atg-original-readiness",atg)
    prior_races = {q["physical_race_id"]:q
                   for g in full["rounds"] for q in g["races"]}
    games = []
    for game in source["weekend_rounds"]:
        if game["name"] not in TRACKS:
            continue
        if game["name"] not in atg["rounds"]:
            raise ValueError("ATG_TARGET_NOT_IN_ORIGINAL_PROBE")
        if atg["rounds"][game["name"]].get("status") == "HISTORICAL_SKIP_NO_NEW_MODEL":
            games.append({
                "name":game["name"],"legs":[],"active":0,
                "current_aggregate_history_verified":0,
                "source_status":"HISTORICAL_DO_NOT_REPROCESS",
                "source_blocker":"SOME_PHYSICAL_RACES_ALREADY_STARTED",
            })
            continue
        probe = {q["physical_race_id"]:q for q in atg["rounds"][game["name"]]["legs"]}
        leg_reports=[]
        for leg in game["legs"]:
            rid = leg["physical_race_id"]
            previous = prior_races.get(rid)
            if not previous or "runners" not in previous:
                raise ValueError("PHASE1_RACE_MISSING")
            p = probe.get(rid)
            if p is None:
                raise ValueError("ORIGINAL_ATG_RACE_IDENTITY_MISSING")
            original = receipts.get(ATG_BASE+str(p.get("atg_race_id")))
            start = _clock(leg["race_start_utc"])
            details: dict[int,dict] = {}
            race_metadata = {}
            source_status = "ATG_RACE_ORIGINAL_NOT_AVAILABLE"
            if original:
                payload, receipt = original
                rows = payload.get("races")
                if not isinstance(rows,list) or len(rows) != 1:
                    raise ValueError("ATG_RACE_ORIGINAL_NOT_UNIQUE")
                race = rows[0]
                if (race.get("id") != p["atg_race_id"]
                        or race.get("number") != leg["race_no"]):
                    raise ValueError("ATG_RACE_NUMBER_IDENTITY_CONFLICT")
                observed = _clock(receipt["response_completed_utc"])
                if observed >= start or race.get("status") not in ("upcoming","bettable"):
                    source_status = "AFTER_START_OR_NOT_PRESTART_NO_HISTORY_PROMOTION"
                else:
                    entrants = race.get("starts")
                    if not isinstance(entrants,list):
                        raise ValueError("ATG_RACE_STARTS_NOT_LIST")
                    for entrant in entrants:
                        n = entrant.get("number")
                        if type(n) is not int or n in details:
                            raise ValueError("ATG_DUPLICATE_START_NUMBER")
                        details[n] = entrant
                    race_metadata = {
                        "race_name":race.get("name"),
                        "race_terms":race.get("terms"),
                        "race_prize":race.get("prize"),
                        "race_distance_m":race.get("distance"),
                        "start_method":race.get("startMethod"),
                        "track_condition":(race.get("track") or {}).get("condition"),
                        "source_original_sha256":receipt["response_sha256"],
                        "observed_at_utc":observed.isoformat(),
                    }
                    source_status = "PRESTART_ATG_ORIGINAL_SHA_VERIFIED"
            output=[]
            canonical_by = {r["selection_id"]:r for r in previous["runners"]}
            history_count=0
            for row in leg["runners"]:
                no = row["number"]
                old = canonical_by.get(str(no))
                if old is None or old["horse_name"] != row["name"]:
                    raise ValueError("RIKSTOTO_AND_PHASE1_CANONICAL_FIELD_CONFLICT")
                ent = details.get(no)
                matched = bool(
                    row["active"] and ent
                    and isinstance(ent.get("horse"),dict)
                    and ent["horse"].get("name") == row["name"]
                    and type(ent["horse"].get("id")) is int
                )
                if matched:
                    evidence=_historical(ent,receipt,observed)
                    research_p = old["p_win"]
                    if (research_p is not None and
                            (evidence["life_starts"] !=
                             old["historical_factors"]["lifetime_starts"]
                             or evidence["life_wins"] !=
                             old["historical_factors"]["lifetime_wins"])):
                        raise ValueError("HISTORIC_LIFETIME_STATS_VS_FROZEN_CHAMPION_CONFLICT")
                    history_count+=1
                else:
                    evidence={
                        "source_status":"NOT_PIT_IDENTITY_MATCHED" if ent else
                                        "MISSING_IN_ATG_ORIGINAL",
                        "last_5_individual_results":MISSING,
                        "last_10_individual_results":MISSING,
                        "prior_opponent_strength_at_historic_race":MISSING,
                        "previous_opponents_and_head_to_head":MISSING,
                    }
                output.append({
                    "number":no,"name":row["name"],
                    "active":row["active"],
                    "horse_registration":row["horse_registration"],
                    "identity_cross_provider_attested":False,
                    "exact_atg_name_number_join":matched,
                    "original_champion_p_win_unchanged":old["p_win"],
                    "original_research_fair_odds":old["fair_odds"],
                    "research_ev_from_original_win_quote_only":(
                        old["research_ev_roi_arithmetic"]
                        if previous["win_full_field_verified"] else None
                    ),
                    "unqualified_raw_odds_for_context":old["win_odds_raw"],
                    "collective_share_not_model_probability":old[
                        "collective_share_not_p_win"],
                    "prestart_aggregate_history":evidence,
                    "decision":"NOT_EXECUTABLE" if row["active"] else "NOT_APPLICABLE",
                })
            # A snapshot-of-opponents aggregate is NOT a measure of historic
            # opponents actually faced by this horse in earlier races.
            entrants=[x["prestart_aggregate_history"] for x in output
                      if x["active"] and x["exact_atg_name_number_join"]]
            rates=[x["life_wins"]/x["life_starts"] for x in entrants
                   if isinstance(x.get("life_starts"),int)
                   and isinstance(x.get("life_wins"),int)
                   and x["life_starts"]>0]
            leg_reports.append({
                "leg":leg["leg"],"physical_race_id":rid,
                "source_start_utc":leg["race_start_utc"],
                "source_admission":source_status,
                "race_metadata":race_metadata,
                "active_runners":leg["active_runners"],
                "exact_current_name_number_stat_sources":history_count,
                "pit_certified":False,
                "prior_opponent_strength_at_prior_dates":MISSING,
                "current_field_lifetime_win_rate_median_NOT_class_adjusted":(
                    sorted(rates)[len(rates)//2] if rates else None),
                "full_win_verified":previous["win_full_field_verified"],
                "full_fundamental_model_unchanged":previous["full_field_model_valid"],
                "research_best_win":previous["best_single_win_research_only"],
                "research_best_dutch":previous["best_dutch_research_only"],
                "hardgate_blockers":previous["hardgate_blockers"],
                "runners":output,
            })
        games.append({
            "name":game["name"],"legs":leg_reports,
            "active":sum(x["active_runners"] for x in leg_reports),
            "current_aggregate_history_verified":sum(
                x["exact_current_name_number_stat_sources"] for x in leg_reports),
        })
    return {
        "schema":SCHEMA,"source_capture_sha256":_sha(raw_report),
        "atg_readiness_sha256":_sha(raw_atg),
        "full_race_source_sha256":_sha(full_race.read_bytes()),
        "analysis_generated_utc":datetime.now(UTC).isoformat(),
        "bet_authority":False,"model_unchanged":True,"pit_hardgates_unchanged":True,
        "v85_system_ev":"NOT_ESTABLISHED",
        "available_history_basis":"ATG_PRE_RACE_LIFETIME_AND_YEAR_AGGREGATES",
        "individual_last_5_10_source_contract":"NOT_AVAILABLE_IN_ATG_RACE_SNAPSHOT",
        "prior_opponents_and_h2h":"NOT_ESTABLISHED",
        "games":games,
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-root",required=True,type=Path)
    p.add_argument("--full-race",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    result=build(args.original_root,args.full_race)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(
        result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "legs":sum(len(g["legs"]) for g in result["games"]),
        "active":sum(g["active"] for g in result["games"]),
        "current_aggregate_history_verified":sum(
            g["current_aggregate_history_verified"] for g in result["games"]),
        "individual_last_5_10_complete":0,
        "bet_authority":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
