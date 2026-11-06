"""Immutable-original, market-free Champion V1.1 weekend research replay.

Runs the existing unchanged estimator ONLY on exact full fields admitted by the
existing FULL_FIELD_ONLY_V1 resolver. This is NOT the production database/PIT
cohort, not an executable frozen forecast, and never grants BET authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hbi.fundamental import MarketFreeFundamentalChampionV1
from hbi.provider_capability import resolve_field
from hbi.providers.atg import AtgClient, AtgFetchResult

SCHEMA = "WEEKEND_AUTHENTIC_CHAMPION_V1_1_RESEARCH_V1"
TRACKS = {
    "BERGSAKER_V85": ("Bergsåker", "SE"),
    "KLOSTERSKOGEN_V75": ("Klosterskogen", "NO"),
}


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("ORIGINAL_SOURCE_UTC_MISSING")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("ORIGINAL_SOURCE_UTC_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("ORIGINAL_SOURCE_UTC_NOT_AWARE")
    return parsed.astimezone(UTC)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _verified_bytes(folder: Path, expected: str, name: str) -> bytes:
    if (not isinstance(expected, str) or len(expected) != 64
            or any(ch not in "0123456789abcdef" for ch in expected)):
        raise ValueError("ORIGINAL_SHA_INVALID")
    path = folder / name
    if path.is_symlink() or path.name != name:
        raise ValueError("ORIGINAL_PATH_INVALID")
    body = path.read_bytes()
    if _sha(body) != expected:
        raise ValueError("ORIGINAL_SHA_MISMATCH")
    return body


def _rikstoto(source: dict, folder: Path, request_path: str, completed: datetime) -> tuple[dict, dict]:
    choices = [r for r in source["original_receipts"] if r["request_path"] == request_path]
    if len(choices) != 1:
        raise ValueError("RIKSTOTO_ORIGINAL_MISSING_OR_DUPLICATED")
    receipt = choices[0]
    if receipt.get("http_status") != 200 or receipt.get("success") is not True:
        raise ValueError("RIKSTOTO_ORIGINAL_HTTP_NOT_SUCCESS")
    digest = receipt["response_sha256"]
    if receipt.get("original_relative_path") != f"originals/{digest}.json":
        raise ValueError("RIKSTOTO_ORIGINAL_PATH_MISMATCH")
    stamp = _time(receipt["response_completed_utc"])
    if stamp > completed:
        raise ValueError("RIKSTOTO_SOURCE_AFTER_CAPTURE")
    raw = _verified_bytes(folder / "originals", digest, digest + ".json")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise TypeError("RIKSTOTO_ORIGINAL_NOT_OBJECT")
    return result, receipt


def _atg_receipts(source: dict, folder: Path, completed: datetime) -> dict:
    indexed = {}
    for receipt in source["original_atg_receipts"]:
        url = receipt["url"]
        if (not isinstance(url, str) or
                not (url.startswith(AtgClient.GAME_API + "/vinnare_")
                     or url.startswith(AtgClient.CALENDAR_API + "/calendar/day/2026-11-07?"))):
            raise ValueError("UNAPPROVED_ATG_ORIGINAL_URL")
        stamp = _time(receipt["response_completed_utc"])
        if stamp > completed:
            raise ValueError("ATG_RECEIPT_AFTER_CAPTURE")
        if receipt.get("http_status") != 200 or receipt.get("success") is not True:
            raise ValueError("ATG_ORIGINAL_HTTP_NOT_SUCCESS")
        digest = receipt["response_sha256"]
        if receipt.get("raw_original_path") != digest + ".json":
            raise ValueError("ATG_ORIGINAL_PATH_MISMATCH")
        raw = _verified_bytes(folder / "atg-originals", digest, digest + ".json")
        payload = json.loads(raw)
        if url in indexed and indexed[url][0] != payload:
            raise ValueError("DUPLICATED_ATG_SOURCE_CONFLICT")
        indexed[url] = (payload, receipt)
    if not indexed:
        raise ValueError("ATG_ORIGINALS_MISSING")
    return indexed


def _canonical(starts: list, original_scratches: list, leg: dict) -> tuple[list, set[int]]:
    if not isinstance(starts, list) or not isinstance(original_scratches, list):
        raise TypeError("ORIGINAL_STARTS_OR_SCRATCHES_INVALID")
    by_no = {}
    for item in starts:
        if (not isinstance(item, dict) or type(item.get("startNumber")) is not int
                or item["startNumber"] < 1 or item["startNumber"] in by_no
                or type(item.get("isScratched")) is not bool
                or not item.get("horseRegistrationNumber")
                or not item.get("horseName")
                or item.get("raceKey") != leg["physical_race_id"].split("RIKSTOTO:")[1].replace(":", "#")
                or item.get("raceNumber") != leg["race_no"]):
            raise ValueError("CANONICAL_ORIGINAL_ROSTER_DEFECT")
        by_no[item["startNumber"]] = item
    scratched = set()
    for value in original_scratches:
        n = value.get("startNumber") if isinstance(value, dict) else value
        if type(n) is not int or n not in by_no or n in scratched:
            raise ValueError("ORIGINAL_SCRATCH_INVALID")
        scratched.add(n)
    if scratched != {n for n, row in by_no.items() if row["isScratched"]}:
        raise ValueError("ORIGINAL_SCRATCH_CONFLICT")
    if len({r["horseRegistrationNumber"] for r in starts}) != len(starts):
        raise ValueError("DUPLICATE_RIKSTOTO_REGISTRATION")
    as_reported = {r["number"]: r for r in leg["runners"]}
    if (set(as_reported) != set(by_no)
            or any(as_reported[n]["name"] != row["horseName"]
                   or as_reported[n]["horse_registration"] != row["horseRegistrationNumber"]
                   or as_reported[n]["active"] is row["isScratched"]
                   for n, row in by_no.items())):
        raise ValueError("REPORTED_ROSTER_NOT_ORIGINAL")
    active = [row for row in starts if not row["isScratched"]]
    if len(active) != leg["active_runners"] or len(active) < 2:
        raise ValueError("ACTIVE_FULL_FIELD_CONFLICT")
    return active, scratched


def audit(original_capture: Path, atg_folder: Path) -> dict:
    original_capture, atg_folder = Path(original_capture), Path(atg_folder)
    original_raw = (original_capture / "weekend-race-intelligence.json").read_bytes()
    atg_raw = (atg_folder / "atg-readiness.json").read_bytes()
    source, atg = json.loads(original_raw), json.loads(atg_raw)
    if (source.get("schema") != "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
            or source.get("bet_authority") is not False
            or source.get("new_model_invocations") != 0
            or atg.get("schema") != "WEEKEND_ATG_AUTHENTIC_SOURCE_DIAGNOSTIC_V1"
            or atg.get("bet_authority") is not False
            or atg.get("model_invocations") != 0
            or atg.get("pit_certified") is not False):
        raise ValueError("UNQUALIFIED_ORIGINAL_REPORT")
    completed = _time(atg["completed_utc"])
    if completed < _time(source["source_as_of_utc"]):
        raise ValueError("ORIGINALS_OBSERVATION_REVERSED")
    originals = _atg_receipts(atg, atg_folder, completed)
    calendar_key = (AtgClient.CALENDAR_API
                    + "/calendar/day/2026-11-07?headToHeadEnabled=true")
    if calendar_key not in originals:
        raise ValueError("APPROVED_ATG_CALENDAR_MISSING")
    cal_payload, cal_receipt = originals[calendar_key]
    calendar = AtgFetchResult(
        url=calendar_key, payload=cal_payload, success=True,
        status_code=200, latency_ms=0,
    )
    model = MarketFreeFundamentalChampionV1()
    rounds, research_assessed = {}, 0
    for game in source["weekend_rounds"]:
        name = game["name"]
        if name not in TRACKS:
            continue
        if not game.get("source_raceday_keys") or len(game["source_raceday_keys"]) != 1:
            raise ValueError("SOURCE_RACEDAY_KEY_NOT_UNIQUE")
        track, country = TRACKS[name]
        key = game["source_raceday_keys"][0]
        starts_data, starts_receipt = _rikstoto(
            source, original_capture, f"/racedays/{key}/starts", completed,
        )
        scratches_data, scratches_receipt = _rikstoto(
            source, original_capture, f"/racedays/{key}/scratched", completed,
        )
        starts = starts_data.get("result")
        scratch = scratches_data.get("result")
        if not isinstance(starts, dict) or not isinstance(scratch, dict):
            raise TypeError("ORIGINAL_CANONICAL_RACEDAY_INVALID")
        lookup = {leg["leg"]: leg for leg in atg["rounds"][name]["legs"]}
        report_legs = []
        for leg in game["legs"]:
            race_no = leg["race_no"]
            rid = f"RIKSTOTO:{key}:{race_no}"
            if rid != leg["physical_race_id"]:
                raise ValueError("PHYSICAL_RACE_JOIN_CONFLICT")
            active, scratches = _canonical(
                starts.get(str(race_no)), scratch.get(str(race_no), []), leg,
            )
            start = _time(leg["race_start_utc"])
            if completed >= start:
                raise ValueError("ATG_RESEARCH_SOURCE_NOT_PRE_RACE")
            probe = lookup.get(leg["leg"])
            if probe is None or probe["physical_race_id"] != rid:
                raise ValueError("ATG_REPORT_LEG_JOIN_CONFLICT")
            resolved = AtgClient().resolve_race(
                calendar, track_name=track, race_number=race_no,
                expected_start=start, country=country, discipline="trot",
            )
            if resolved is None or resolved.race_id != probe["atg_race_id"]:
                raise ValueError("ATG_PHYSICAL_RACE_ID_UNVERIFIED")
            url = AtgClient.GAME_API + "/vinnare_" + resolved.race_id
            if url not in originals:
                raise ValueError("ATG_RACE_ORIGINAL_NOT_FOUND")
            body, game_receipt = originals[url]
            races = body.get("races") if isinstance(body, dict) else None
            if not isinstance(races, list) or len(races) != 1:
                raise ValueError("ATG_ORIGINAL_RACE_NOT_UNIQUE")
            observed = _time(game_receipt["response_completed_utc"])
            if not _time(cal_receipt["response_completed_utc"]) <= observed <= completed:
                raise ValueError("ATG_SOURCE_CLOCK_CONFLICT")
            matched, evidence = resolve_field(
                starts=starts[str(race_no)], scratches=scratches, scratch_ok=True,
                payload=races[0], country=country, discipline="trot",
                race_number=race_no, expected_start=start, observed_at=observed,
                provider_race_id=resolved.race_id, source_uri=url, probe=False,
            )
            if (len(matched) != probe["atg_full_field_match_count"]
                    or bool(matched) != (probe["source_contract_status"] ==
                                         "ATG_FULL_FIELD_HISTORY_CONTRACT")):
                raise ValueError("ATG_SOURCE_REPLAY_CONFLICT")
            source_rows = {q["number"]: q for q in races[0]["starts"]
                           if isinstance(q, dict) and type(q.get("number")) is int}
            report_runners = {q["number"]: q for q in leg["runners"]}
            result_runners = []
            for s in starts[str(race_no)]:
                n = s["startNumber"]
                data = source_rows.get(n, {})
                horse = data.get("horse") if isinstance(data.get("horse"), dict) else {}
                matched_row = next((v for v in evidence["runners"]
                                    if v["selection_id"] == str(n)), {})
                valid = (str(n) in matched and not s["isScratched"])
                stats = horse.get("statistics") if isinstance(horse.get("statistics"), dict) else {}
                life = stats.get("life") if isinstance(stats.get("life"), dict) else {}
                wins = life.get("placement", {}).get("1") if isinstance(life.get("placement"), dict) else None
                result_runners.append({
                    "number": n, "name": s["horseName"],
                    "rikstoto_registration": s["horseRegistrationNumber"],
                    "atg_horse_id_unjoined": horse.get("id"),
                    "atg_horse_id_matched": horse.get("id") if valid else None,
                    "scratched": s["isScratched"],
                    "name_number_join": bool(valid),
                    "independent_registration_attested": False,
                    "history_starts": life.get("starts") if valid else None,
                    "history_wins": wins if valid else None,
                    "history_original_sha256": game_receipt["response_sha256"] if valid else None,
                    "history_observed_at_utc": observed.isoformat() if valid else None,
                    "provider_match_reason": matched_row.get("reason"),
                    "data_quality": ("QUALIFIED_RESEARCH_SOURCE" if valid and len(matched) == len(active)
                                     else "BLOCKED"),
                    "model_status": "NOT_ASSESSED",
                    "p_win_research": None, "fair_odds_research": None,
                    "win_odds": report_runners[n].get("win_odds"),
                    "win_status": leg["win_status"],
                    "decision": "NOT_APPLICABLE" if s["isScratched"] else "NOT_EXECUTABLE",
                    "blockers": ([] if s["isScratched"] else
                        ["PRODUCTION_PIT_NOT_CERTIFIED", "FULL_FIELD_WIN_NOT_VERIFIED",
                         "INDEPENDENT_REGISTRATION_NOT_ATTESTED"]),
                })
            probabilities = {}
            run_id = None
            if len(matched) == len(active) and evidence["passed"] is True:
                rows = []
                for selection, item in sorted(matched.items(), key=lambda pair: int(pair[0])):
                    horse = item["horse"]
                    life = horse["statistics"]["life"]
                    rows.append({
                        "selection_id": selection, "scratched": False,
                        "history_total_starts": life["starts"],
                        "history_total_wins": life["placement"]["1"],
                        "feature_as_of_utc": observed.isoformat(),
                        "data_quality": "FULL_FIELD_HISTORY_ATG",
                    })
                result = model.estimate(race_id=rid, rows=rows, created_at=completed)
                if (not result.shadow_eligible or result.status != "OK"
                        or result.known_history_runners != len(active)
                        or len(result.probabilities) != len(active)
                        or abs(sum(result.probabilities.values()) - 1.0) > 1e-10):
                    raise ValueError("CHAMPION_RESEARCH_FULL_FIELD_MODEL_REJECTED")
                probabilities, run_id = result.probabilities, result.run_id
                research_assessed += len(active)
                for row in result_runners:
                    if row["scratched"]:
                        continue
                    p = probabilities[str(row["number"])]
                    row.update(model_status="ASSESSED", p_win_research=p,
                               fair_odds_research=1.0 / p)
            else:
                for row in result_runners:
                    if not row["scratched"]:
                        row["blockers"].append(
                            row["provider_match_reason"] or "FULL_FIELD_ONLY_COHORT_INCOMPLETE"
                        )
                        row["blockers"].append("RESEARCH_MODEL_FULL_FIELD_NOT_ADMITTED")
            report_legs.append({
                "leg": leg["leg"], "physical_race_id": rid,
                "atg_race_id": resolved.race_id,
                "start_at_utc": start.isoformat(),
                "t4_at_utc": (start - timedelta(minutes=4)).isoformat(),
                "active_runners": len(active),
                "atg_valid_history": sum(r["name_number_join"] for r in result_runners),
                "independent_registrations_attested": 0,
                "full_field_fundamental_research_ready": bool(probabilities),
                "model_assessed_runners": len(probabilities),
                "actual_model_run_id": run_id,
                "model_version": model.VERSION,
                "model_calibration": model.CALIBRATION_VERSION,
                "model_probability_sum": sum(probabilities.values()) if probabilities else None,
                "provider_contract_errors": evidence["reasons"],
                "win_full_field_verified": False,
                "pit_certified": False, "bet_signals": 0,
                "readiness_blockers": (["PRODUCTION_PIT_NOT_CERTIFIED",
                                        "INDEPENDENT_REGISTRATION_NOT_ATTESTED",
                                        "FULL_FIELD_WIN_NOT_VERIFIED"]
                                       if probabilities else
                                       ["FULL_FIELD_ONLY_COHORT_INCOMPLETE"] + evidence["reasons"]),
                "source_sha256": {
                    "rikstoto_starts": starts_receipt["response_sha256"],
                    "rikstoto_scratches": scratches_receipt["response_sha256"],
                    "atg_calendar": cal_receipt["response_sha256"],
                    "atg_game": game_receipt["response_sha256"],
                }, "runners": result_runners,
            })
        rounds[name] = {"legs": report_legs}
    return {
        "schema": SCHEMA, "research_only": True, "bet_authority": False,
        "actual_model_version": model.VERSION,
        "market_free_model_executed": True,
        "model_assessed_runners": research_assessed,
        "pit_certified": False, "actual_t4_certified_count": 0, "bet_signals": 0,
        "v85_system_ev": "NOT_ESTABLISHED",
        "original_report_sha256": _sha(original_raw),
        "atg_report_sha256": _sha(atg_raw),
        "source_observation_utc": completed.isoformat(),
        "decision_layer": "NOT_EXECUTABLE_ONLY",
        "limitations": [
            "Actual unchanged Champion V1.1 estimate on original ATG lifetime wins/starts.",
            "Research-only point-in-time source observed before race; not approved T-4 forecast.",
            "No SQLite production full_field_gate, independent registration or betting admission.",
            "No market odds, public V percentages or later race results entered model.",
            "Unmatched fields are blocked without country-suffix aliases.",
        ],
        "rounds": rounds,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-capture", type=Path, required=True)
    p.add_argument("--atg-readiness", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = audit(args.original_capture, args.atg_readiness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        fh.write("\n")
    print(json.dumps({
        "model_assessed_runners": report["model_assessed_runners"],
        "by_round": {k: [(r["leg"], r["model_assessed_runners"])
                        for r in v["legs"]] for k, v in report["rounds"].items()},
        "bet_authority": False, "pit_certified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
