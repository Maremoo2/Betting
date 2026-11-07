"""P0 Saturday original-only Challenger V2 SHADOW alongside unchanged Champion.

No provider calls. Original Saturday capture (Rikstoto) is checked against a
PREEXISTING archived source/Champion/ATG bundle. Never re-runs Champion,
changes frozen p(win), backfills results, certifies PIT or creates a BET.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from hbi.challenger_v2_shadow import estimate_shadow

SCHEMA = "P0_CHALLENGER_V2_SATURDAY_PRESTART_SHADOW_V1"
ATG_GAME = "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_"
TRACKS = ("BERGSAKER_V85", "KLOSTERSKOGEN_V75")


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _clock(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError("RESEARCH_SOURCE_TIME_NOT_AWARE")
    return dt.astimezone(UTC)


def _verified_archive(root: Path, sub: str, receipt: dict) -> dict:
    digest = receipt.get("response_sha256")
    if (receipt.get("http_status") != 200 or receipt.get("success") is not True
            or not isinstance(digest, str) or len(digest) != 64):
        raise ValueError("ORIGINAL_SOURCE_NOT_ATTESTED")
    path = root / sub / (digest + ".json")
    if path.is_symlink():
        raise ValueError("ORIGINAL_SOURCE_SYMLINK")
    body = path.read_bytes()
    if _sha(body) != digest:
        raise ValueError("ORIGINAL_SOURCE_HASH_MISMATCH")
    return json.loads(body)


def _price_source(current: dict, rid: str) -> dict:
    key, n = rid.removeprefix("RIKSTOTO:").rsplit(":", 1)
    path = f"/game/{key}/betdistribution/winodds/{n}"
    items = [r for r in current["original_receipts"]
             if r.get("request_path") == path]
    if len(items) != 1:
        raise ValueError("LIVE_WIN_ORIGINAL_RECEIPT_NOT_UNIQUE")
    return items[0]


def audit(
    *, baseline_root: Path, latest_root: Path, as_of_utc: str,
) -> dict:
    now = _clock(as_of_utc)
    old_bytes = (baseline_root / "original-capture"
                 / "weekend-race-intelligence.json").read_bytes()
    old = json.loads(old_bytes)
    new_bytes = (latest_root / "weekend-race-intelligence.json").read_bytes()
    new = json.loads(new_bytes)
    model_bytes = (baseline_root / "champion-research-v1_1.json").read_bytes()
    model = json.loads(model_bytes)
    atg_bytes = (baseline_root / "atg-original-readiness"
                 / "atg-readiness.json").read_bytes()
    atg = json.loads(atg_bytes)
    if (old.get("schema") != "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
            or new.get("schema") != old["schema"]
            or model.get("schema") != "WEEKEND_AUTHENTIC_CHAMPION_V1_1_RESEARCH_V1"
            or model.get("original_report_sha256") != _sha(old_bytes)
            or model.get("atg_report_sha256") != _sha(atg_bytes)
            or atg.get("schema") != "WEEKEND_ATG_AUTHENTIC_SOURCE_DIAGNOSTIC_V1"
            or any(x.get("bet_authority") is not False for x in (old,new,model,atg))):
        raise ValueError("SOURCE_FROZEN_CHAMPION_ORIGINAL_LINK_DEFECT")
    if (_clock(model["source_observation_utc"]) > now
            or _clock(new["source_observation_completed_utc"]) > now):
        raise ValueError("SOURCE_REPORT_FROM_FUTURE")
    atg_receipts = {}
    for item in atg["original_atg_receipts"]:
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(ATG_GAME):
            continue
        if url not in atg_receipts or _clock(item["response_completed_utc"]) < _clock(
            atg_receipts[url]["response_completed_utc"]
        ):
            atg_receipts[url] = item
    old_rounds = {x["name"]:x for x in old["weekend_rounds"]}
    new_rounds = {x["name"]:x for x in new["weekend_rounds"]}
    reports = []
    total_modelled = 0
    for name in TRACKS:
        group, before = new_rounds[name], old_rounds[name]
        models = {leg["physical_race_id"]:leg for leg in model["rounds"][name]["legs"]}
        old_fields = {leg["physical_race_id"]:leg for leg in before["legs"]}
        round_rows = []
        for leg in group["legs"]:
            rid = leg["physical_race_id"]
            prior = old_fields.get(rid)
            original_model = models.get(rid)
            if prior is None or original_model is None:
                raise ValueError("ORIGINAL_CHAMPION_LEG_NOT_UNIQUE")
            roster = [(r["number"],r["name"],r["active"],r["horse_registration"])
                      for r in leg["runners"]]
            old_roster = [(r["number"],r["name"],r["active"],r["horse_registration"])
                          for r in prior["runners"]]
            if roster != old_roster:
                round_rows.append({
                    "race_id":rid,"leg":leg["leg"],
                    "status":"BLOCKED_FIELD_CHANGED_NO_REUSE_OF_OLD_P",
                    "p_win":None,"bet_authority":False,
                })
                continue
            start = _clock(leg["race_start_utc"])
            if now >= start:
                round_rows.append({
                    "race_id":rid,"leg":leg["leg"],
                    "status":"ALREADY_STARTED_NO_NEW_MODEL_RESEARCH",
                    "p_win":None,"bet_authority":False,
                })
                continue
            if not original_model["full_field_fundamental_research_ready"]:
                round_rows.append({
                    "race_id":rid,"leg":leg["leg"],
                    "status":"BLOCKED_ORIGINAL_CHAMPION_FULL_FIELD_HISTORY_IDENTITY",
                    "modelled":0,"active_runners":leg["active_runners"],
                    "blockers":original_model.get("readiness_blockers"),
                    "bet_authority":False,
                })
                continue
            atg_rid = original_model["atg_race_id"]
            url = ATG_GAME + atg_rid
            receipt = atg_receipts.get(url)
            if receipt is None:
                raise ValueError("BASELINE_ATG_ORIGINAL_MISSING")
            if _clock(receipt["response_completed_utc"]) >= start:
                raise ValueError("HISTORIC_FUNDAMENTAL_OBSERVED_AFTER_RACE")
            payload = _verified_archive(
                baseline_root,
                "atg-original-readiness/atg-originals",receipt,
            )
            races = payload.get("races")
            if (not isinstance(races,list) or len(races) != 1
                    or races[0].get("id") != atg_rid
                    or races[0].get("number") != leg["race_no"]):
                raise ValueError("ATG_RACE_ORIGINAL_NOT_IDENTICAL")
            index = {s["number"]:s for s in races[0]["starts"]
                     if isinstance(s,dict) and type(s.get("number")) is int}
            if len(index) != len(races[0]["starts"]):
                raise ValueError("ATG_RACE_RUNNER_NUMBER_COLLISION")
            old_model = {r["number"]:r for r in original_model["runners"]}
            rows = []
            for r in leg["runners"]:
                mm = old_model.get(r["number"])
                if (mm is None or mm["name"] != r["name"]
                        or mm["scratched"] == r["active"]):
                    raise ValueError("FROZEN_CHAMPION_AND_CANONICAL_RUNNER_CONFLICT")
                rec = index.get(r["number"])
                horse = rec.get("horse") if isinstance(rec,dict) else None
                stats = horse.get("statistics") if isinstance(horse,dict) else {}
                career = stats.get("life") if isinstance(stats,dict) else {}
                annual = (stats.get("years") or {}).get("2026") if isinstance(stats,dict) else {}
                placement = career.get("placement",{}) if isinstance(career,dict) else {}
                annual_p = annual.get("placement",{}) if isinstance(annual,dict) else {}
                if r["active"] and (
                    not isinstance(horse,dict)
                    or horse.get("name") != r["name"]
                    or career.get("starts") != mm.get("history_starts")
                    or placement.get("1") != mm.get("history_wins")
                ):
                    raise ValueError("ATG_ORIGINAL_LIFETIME_AND_CHAMPION_INPUT_CONFLICT")
                rows.append({
                    "selection_id":str(r["number"]),
                    "scratched":not r["active"],
                    "horse_name":r["name"],
                    "atg_horse_id":horse.get("id") if isinstance(horse,dict) else None,
                    "historical_source_sha256":receipt["response_sha256"],
                    "historical_observed_at_utc":receipt["response_completed_utc"],
                    "career_starts":career.get("starts") if isinstance(career,dict) else None,
                    "career_wins":placement.get("1"),
                    "season_starts":annual.get("starts") if isinstance(annual,dict) else None,
                    "season_wins":annual_p.get("1"),
                    "independent_registration_attested":False,
                })
            challenger = estimate_shadow(
                race_id=rid,start_at_utc=leg["race_start_utc"],
                as_of_utc=now.isoformat(),runners=rows,
            )
            total_modelled += sum(
                x.get("p_win_challenger") is not None
                for x in challenger["runners"]
            )
            selected = {x["selection_id"]:x for x in challenger["runners"]}
            prices = _price_source(new,rid)
            baseline_horses = []
            for r in leg["runners"]:
                initial = old_model[r["number"]]
                result = selected[str(r["number"])]
                p1 = initial.get("p_win_research")
                p2 = result.get("p_win_challenger")
                quote = r.get("raw_win_odds_unqualified")
                if quote is not None and quote <= 1:
                    quote = None
                baseline_horses.append({
                    "number":r["number"],"name":r["name"],"active":r["active"],
                    "champion_p_win_immutable":p1,"challenger_p_win_shadow":p2,
                    "challenger_minus_champion":p2-p1 if p1 and p2 else None,
                    "career_starts":rows[r["number"]-1].get("career_starts")
                       if r["number"]-1 < len(rows) else None,
                    "season_starts":next(
                        (z["season_starts"] for z in rows
                         if z["selection_id"] == str(r["number"])),None),
                    "season_wins":next(
                        (z["season_wins"] for z in rows
                         if z["selection_id"] == str(r["number"])),None),
                    "raw_win_quote_unqualified":quote,
                    "raw_win_quote_source_sha256":prices.get("response_sha256"),
                    "champion_arithmetic_ev_unqualified":p1*quote-1 if p1 and quote else None,
                    "challenger_arithmetic_ev_unqualified":p2*quote-1 if p2 and quote else None,
                    "collective_share_separate_not_p_win":r.get("collective_share"),
                    "decision":"NOT_EXECUTABLE" if r["active"] else "NOT_APPLICABLE",
                })
            round_rows.append({
                "race_id":rid,"leg":leg["leg"],
                "start_utc":leg["race_start_utc"],
                "source_model_run_sha256":original_model["actual_model_run_id"],
                "champion_original_report_sha256":_sha(model_bytes),
                "source_atg_receipt_sha256":receipt["response_sha256"],
                "champion_frozen_p_win_sum":original_model["model_probability_sum"],
                "challenger":challenger,
                "win_full_field":leg["win_status"].startswith("COMPLETE"),
                "collective_share_full":leg["collective_status"].startswith("COMPLETE"),
                "raw_quote_count":sum(x["raw_win_quote_unqualified"] is not None
                                      and x["active"] for x in baseline_horses),
                "active_runners":leg["active_runners"],
                "runners":baseline_horses,
                "pit_certified":False,
                "bet_authority":False,
                "decision":"NOT_EXECUTABLE",
            })
        reports.append({
            "round":name,"legs":round_rows,
            "challenger_full_fields":sum(x.get("challenger",{}).get("p_win_sum") is not None
                                         for x in round_rows),
        })
    return {
        "schema":SCHEMA,"cutoff_utc":now.isoformat(),
        "new_source_asof_utc":new["source_as_of_utc"],
        "baseline_source_sha256":_sha(old_bytes),
        "live_source_sha256":_sha(new_bytes),
        "frozen_champion_report_sha256":_sha(model_bytes),
        "atg_original_receipts_sha_verified":len(atg_receipts),
        "champion_unchanged":True,"challenger_role":"SHADOW_ONLY",
        "challenger_assessed_horses":total_modelled,
        "calibration_status":"NOT_VALIDATED",
        "bet_authority":False,"v85_system_ev":"NOT_ESTABLISHED",
        "pit_hardgates_unchanged":True,
        "outcome_data_used":False,"market_in_fundamental_model":False,
        "rounds":reports,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-root",type=Path,required=True)
    p.add_argument("--latest-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args = p.parse_args()
    result = audit(
        baseline_root=args.baseline_root,latest_root=args.latest_root,
        as_of_utc=datetime.now(UTC).isoformat(),
    )
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(
        json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "challenger_assessed":result["challenger_assessed_horses"],
        "rounds":[(x["round"],x["challenger_full_fields"]) for x in result["rounds"]],
        "bet_authority":False,
    }))


if __name__=="__main__":
    main()
