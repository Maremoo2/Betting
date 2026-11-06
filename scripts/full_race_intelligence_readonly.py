"""Original-backed full-race intelligence: all physical races; NO BET.

Accepts immutable captured Rikstoto bytes and optionally the already computed
market-free Champion research bundle. Never invokes or modifies the model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from hbi.full_race_intelligence import analyze_race

CAPTURE_SCHEMA = "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
RESEARCH_SCHEMA = "WEEKEND_AUTHENTIC_CHAMPION_V1_1_RESEARCH_V1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _receipt(folder: Path, source: dict, path: str) -> dict:
    items = [r for r in source["original_receipts"] if r["request_path"] == path]
    if len(items) != 1:
        raise ValueError("ORIGINAL_RECEIPT_MISSING_OR_DUPLICATE")
    r = items[0]
    digest = r.get("response_sha256")
    if (r.get("http_status") != 200 or r.get("success") is not True
            or not isinstance(digest, str) or len(digest) != 64
            or r.get("original_relative_path") != "originals/" + digest + ".json"):
        raise ValueError("ORIGINAL_RECEIPT_INVALID")
    original = folder / "originals" / (digest + ".json")
    if original.is_symlink() or _sha(original.read_bytes()) != digest:
        raise ValueError("ORIGINAL_BYTES_SHA_MISMATCH")
    timestamp = datetime.fromisoformat(r["response_completed_utc"])
    if timestamp.utcoffset() is None:
        raise ValueError("ORIGINAL_UTC_NOT_AWARE")
    return r


def _models(raw: bytes | None, source_sha: str) -> dict:
    if raw is None:
        return {}
    content = json.loads(raw)
    if (content.get("schema") != RESEARCH_SCHEMA
            or content.get("bet_authority") is not False
            or content.get("original_report_sha256") != source_sha
            or content.get("actual_model_version") != "FUNDAMENTAL_CHAMPION_V1_1"):
        raise ValueError("FROZEN_RESEARCH_SOURCE_NOT_ATTESTED")
    return {
        leg["physical_race_id"]: leg
        for group in content["rounds"].values()
        for leg in group["legs"]
    }


def build(folder: Path, research_file: Path | None, cutoff: str) -> dict:
    raw = (folder / "weekend-race-intelligence.json").read_bytes()
    source = json.loads(raw)
    if (source.get("schema") != CAPTURE_SCHEMA
            or source.get("bet_authority") is not False
            or source.get("new_model_invocations") != 0):
        raise ValueError("PROVIDER_REPORT_SOURCE_INVALID")
    model_raw = research_file.read_bytes() if research_file else None
    models = _models(model_raw, _sha(raw))
    rounds = []
    for game in source["weekend_rounds"]:
        races = []
        for leg in game["legs"]:
            physical = leg["physical_race_id"]
            key, number = physical.removeprefix("RIKSTOTO:").rsplit(":", 1)
            if int(number) != leg["race_no"]:
                raise ValueError("PHYSICAL_SOURCE_RACE_NUMBER_MISMATCH")
            start_r = _receipt(folder, source, "/racedays/" + key + "/starts")
            scratch_r = _receipt(folder, source, "/racedays/" + key + "/scratched")
            win_r = _receipt(folder, source, (
                "/game/" + key + "/betdistribution/winodds/" + number
            ))
            model = models.get(physical)
            by_no = {}
            if model:
                if (len(model["runners"]) != len(leg["runners"])
                        or model["active_runners"] != leg["active_runners"]
                        or model["source_sha256"]["rikstoto_starts"]
                        != start_r["response_sha256"]):
                    raise ValueError("MODEL_ORIGINAL_CANONICAL_ROSTER_CONFLICT")
                by_no = {r["number"]:r for r in model["runners"]}
                if set(by_no) != {r["number"] for r in leg["runners"]}:
                    raise ValueError("MODEL_ORIGINAL_SELECTION_SET_CONFLICT")
            data = []
            for horse in leg["runners"]:
                linked = by_no.get(horse["number"])
                if linked and (
                    linked["name"] != horse["name"]
                    or linked["rikstoto_registration"] != horse["horse_registration"]
                    or linked["scratched"] == horse["active"]
                ):
                    raise ValueError("MODEL_ORIGINAL_HORSE_NAME_SCRATCH_CONFLICT")
                data.append({
                    "selection_id":str(horse["number"]),
                    "horse_name":horse["name"],
                    "scratched":not horse["active"],
                    "rikstoto_registration":horse["horse_registration"],
                    "atg_horse_id":linked.get("atg_horse_id_matched") if linked else None,
                    "identity_attested":False,
                    "history_source_sha256":(
                        linked.get("history_original_sha256") if linked else None
                    ),
                    "lifetime_starts":linked.get("history_starts") if linked else None,
                    "lifetime_wins":linked.get("history_wins") if linked else None,
                    "p_win_frozen":(
                        linked["p_win_research"] if linked and
                        linked.get("model_status") == "ASSESSED" else None
                    ),
                    "win_odds_raw":horse.get("win_odds") or horse.get("raw_win_odds_unqualified"),
                    "win_price_source_sha256":win_r["response_sha256"],
                    "win_observed_at_utc":win_r["response_completed_utc"],
                    "win_provider_updated_raw":None,
                    "collective_share":horse.get("collective_share"),
                    "minimum_frozen_bet_odds":horse.get("frozen_min_odds"),
                    "data_quality":linked.get("data_quality") if linked else "MISSING_HISTORY",
                    "blockers":list(linked.get("blockers") or []) if linked
                                else ["NO_FROZEN_FUNDAMENTAL_FULL_FIELD"],
                })
            if not leg.get("race_start_utc"):
                races.append({
                    "physical_race_id":physical, "status":"START_NOT_SOURCE_VERIFIED",
                    "runner_count":len(data), "bet_authority":False,
                })
                continue
            analysis = analyze_race({
                "physical_race_id":physical,
                "round_name":game["name"], "leg":leg.get("leg"),
                "start_utc":leg["race_start_utc"], "runners":data,
                "pit_certified":False,
                "full_field_win_verified":leg["win_status"].startswith(
                    "COMPLETE_RESEARCH_PRICE"
                ),
                "model_version":model.get("model_version") if model else None,
                "model_run_id":model.get("actual_model_run_id") if model else None,
                "source_model_sha256":_sha(model_raw) if model_raw else None,
                "source_original_sha256":{
                    "starts":start_r["response_sha256"],
                    "scratches":scratch_r["response_sha256"],
                    "win":win_r["response_sha256"],
                },
            }, decision_time_utc=cutoff)
            analysis["market_source_status"] = leg["win_status"]
            analysis["collective_source_status"] = leg["collective_status"]
            analysis["scratched_count"] = leg["scratched_runners"]
            races.append(analysis)
        rounds.append({
            "name":game["name"],"product":game["product"],
            "race_date":game["race_date"],"races":races,
            "count":len(races),
            "active":sum(x.get("active_count",0) for x in races),
            "blockers":game["blockers"],
        })
    return {
        "schema":"FULL_RACE_INTELLIGENCE_ORIGINALS_V1",
        "source_capture_sha256":_sha(raw),
        "source_capture_asof_utc":source["source_as_of_utc"],
        "model_bundle_sha256":_sha(model_raw) if model_raw else None,
        "analysis_cutoff_utc":cutoff,
        "bet_authority":False,
        "frozen_model_unchanged":True,
        "pit_hardgates_unchanged":True,
        "v85_system_ev":"NOT_ESTABLISHED",
        "rounds":rounds,
    }


def markdown(report: dict) -> str:
    lines = ["# Full Race Intelligence: original-only shadow research",
             "",
             "Capture UTC: " + report["source_capture_asof_utc"],
             "Analysis UTC: " + report["analysis_cutoff_utc"],
             "Source SHA256: " + report["source_capture_sha256"],
             "Champion source SHA256: " + str(report["model_bundle_sha256"]),
             "",
             "**NO BET**. Simulated stakes in dutching are arithmetic, not wagering recommendations.",
             ""]
    for game in report["rounds"]:
        lines += ["## " + game["name"], "", "Physical races: "
                  + str(game["count"]) + " | Active: " + str(game["active"]), ""]
        for race in game["races"]:
            lines += ["### " + race["physical_race_id"], ""]
            if "runners" not in race:
                lines += ["SOURCE START BLOCKED", ""]
                continue
            lines += [
                "Start: " + race["start_utc"] + " | Full model: "
                + str(race["full_field_model_valid"]) + " | Full WIN: "
                + str(race["win_full_field_verified"]) + " | Quotes: "
                + str(race["win_quote_count"]) + "/" + str(race["active_count"]),
                "Status: NOT_EXECUTABLE; " + ", ".join(race["hardgate_blockers"]),
                "",
                "| # | Hest | Research p(win) | Fair odds | WIN quote | Arithmetic EV | V-share |",
                "|---:|---|---:|---:|---:|---:|---:|",
            ]
            fmt = lambda v, scale=1: (
                format(v*scale,".2f") if isinstance(v,(int,float)) else "MISSING"
            )
            for h in race["runners"]:
                if h["scratched"]:
                    continue
                lines.append(
                    "| " + h["selection_id"] + " | " + str(h["horse_name"]) + " | "
                    + fmt(h["p_win"],100) + "% | " + fmt(h["fair_odds"]) + " | "
                    + fmt(h["win_odds_raw"]) + " | "
                    + fmt(h["research_ev_roi_arithmetic"],100) + "% | "
                    + fmt(h["collective_share_not_p_win"],100) + "% |"
                )
            lines += ["", "Win favourite: " + str(race["win_favourite"]),
                      "Provisional quoted leader: " + str(race["win_quoted_leader_provisional"]),
                      "Separate collective favourite: " + str(race["collective_favourite_separate"]),
                      "Overpricing proven: NO", ""]
            for d in race["dutching_scenarios"]:
                if d["status"] == "ARITHMETIC_RESEARCH_ONLY":
                    lines += [d["name"] + " simulated ROI "
                              + fmt(d["ev_roi_hypothetical"],100) + "%; "
                              + "full outcomes in JSON; NOT_EXECUTABLE."]
                else:
                    lines += [d["name"] + " " + d["reason"]]
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-capture",type=Path,required=True)
    p.add_argument("--frozen-research",type=Path)
    p.add_argument("--output-json",type=Path,required=True)
    p.add_argument("--output-md",type=Path,required=True)
    a = p.parse_args()
    report = build(a.original_capture,a.frozen_research,datetime.now(UTC).isoformat())
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(
        json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
        encoding="utf-8",
    )
    a.output_md.write_text(markdown(report),encoding="utf-8")
    print(json.dumps({
        "physical_races":sum(g["count"] for g in report["rounds"]),
        "active_runners":sum(g["active"] for g in report["rounds"]),
        "model_full_field_races":sum(
            r.get("full_field_model_valid",False) for g in report["rounds"] for r in g["races"]),
        "full_win_races":sum(
            r.get("win_full_field_verified",False) for g in report["rounds"] for r in g["races"]),
        "bet_authority":False,
    },sort_keys=True))


if __name__ == "__main__":
    main()
