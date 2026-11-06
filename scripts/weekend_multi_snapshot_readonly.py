"""Read-only, SHA-verified comparison of genuine weekend source observations.

This is a research diagnostic, not a model invocation, PIT certification, BET
decision, scheduling mechanism, or reconstruction of missing observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "WEEKEND_MULTISNAPSHOT_SOURCE_AUDIT_V1"
INPUT_SCHEMA = "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("SOURCE_TIME_UNVERIFIED")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("SOURCE_TIME_UNVERIFIED") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("SOURCE_TIME_UNVERIFIED")
    return parsed.astimezone(UTC)


def _read_snapshot(folder: Path) -> dict:
    """Require original bytes, actual response-completion UTC and matching SHA."""
    report = json.loads((folder / "weekend-race-intelligence.json").read_bytes())
    if (report.get("schema") != INPUT_SCHEMA or report.get("bet_authority") is not False
            or report.get("new_model_invocations") != 0
            or report.get("model_predictions_made") != 0):
        raise ValueError("UNQUALIFIED_OR_MODELLED_SOURCE_REPORT")
    started = _utc(report.get("source_as_of_utc"))
    finished = _utc(report.get("source_observation_completed_utc"))
    if finished < started:
        raise ValueError("SOURCE_CLOCK_ORDER_CONFLICT")
    verified = {}
    receipt_ids = set()
    for receipt in report.get("original_receipts", []):
        path = receipt.get("request_path")
        sha = receipt.get("response_sha256")
        stamp = _utc(receipt.get("response_completed_utc"))
        if stamp < started or stamp > finished:
            raise ValueError("RECEIPT_OUTSIDE_OBSERVATION_WINDOW")
        if not isinstance(path, str) or not isinstance(sha, str) or len(sha) != 64:
            raise ValueError("ORIGINAL_RECEIPT_INVALID")
        if path in receipt_ids:
            raise ValueError("DUPLICATE_REQUEST_PATH_IN_OBSERVATION")
        receipt_ids.add(path)
        raw_path = receipt.get("original_relative_path")
        body = None
        if raw_path:
            if raw_path != f"originals/{sha}.json":
                raise ValueError("ORIGINAL_PATH_SHA_CONFLICT")
            body = (folder / raw_path).read_bytes()
            if hashlib.sha256(body).hexdigest() != sha:
                raise ValueError("ORIGINAL_SHA_MISMATCH")
        elif receipt.get("success") is True:
            raise ValueError("SUCCESSFUL_SOURCE_WITHOUT_ORIGINAL")
        verified[path] = (receipt, json.loads(body) if body is not None else None)
    if not verified:
        raise ValueError("NO_ORIGINAL_RECEIPTS")
    fingerprint = hashlib.sha256(json.dumps(
        sorted((p, r[0]["response_sha256"]) for p, r in verified.items()),
        separators=(",", ":"),
    ).encode()).hexdigest()
    return {"report": report, "receipts": verified, "started": started,
            "finished": finished, "payload_fingerprint": fingerprint}


def _market(snapshot: dict, race_key: str, number: int, runners: list[dict]) -> dict:
    path = f"/game/{race_key}/betdistribution/winodds/{number}"
    entry = snapshot["receipts"].get(path)
    if not entry or entry[0].get("http_status") != 200 or entry[1] is None:
        return {"status": "SOURCE_UNAVAILABLE", "reason": "NO_SUCCESSFUL_WIN_ORIGINAL",
                "by_number": {}, "observed_utc": None, "valid": 0}
    receipt, source = entry
    if not isinstance(source, dict):
        return {"status": "SOURCE_UNAVAILABLE", "reason": "WIN_RESPONSE_NOT_OBJECT",
                "by_number": {}, "observed_utc": receipt["response_completed_utc"], "valid": 0}
    if str(source.get("errorCode") or "").upper() == "MARKET_NOT_OPEN":
        return {"status": "MARKET_NOT_OPEN", "reason": "EXPLICIT_PROVIDER_MARKET_NOT_OPEN",
                "by_number": {}, "observed_utc": receipt["response_completed_utc"], "valid": 0}
    raw = source.get("result")
    if not isinstance(raw, list):
        return {"status": "SOURCE_UNAVAILABLE", "reason": "WIN_RESULT_LIST_UNAVAILABLE",
                "by_number": {}, "observed_utc": receipt["response_completed_utc"], "valid": 0}
    indexed = {}
    for row in raw:
        if (not isinstance(row, dict) or type(row.get("startNumber")) is not int
                or row["startNumber"] < 1 or row["startNumber"] in indexed):
            return {"status": "JOIN_DEFECT", "reason": "DUPLICATE_OR_INVALID_SOURCE_START_NUMBER",
                    "by_number": {}, "observed_utc": receipt["response_completed_utc"], "valid": 0}
        indexed[row["startNumber"]] = row
    roster_ids = {r["number"] for r in runners}
    if set(indexed) - roster_ids:
        return {"status": "JOIN_DEFECT", "reason": "MARKET_HAS_RUNNERS_OUTSIDE_PHYSICAL_ROSTER",
                "by_number": {}, "observed_utc": receipt["response_completed_utc"], "valid": 0}
    output = {}
    valid = 0
    all_aware = True
    for runner in runners:
        n = runner["number"]
        item = indexed.get(n)
        odds = item.get("odds") if item else None
        if (type(odds) in (int, float) and math.isfinite(odds) and odds > 1
                and runner["active"]):
            price = float(odds)
            valid += 1
        else:
            price = None
        stamp = item.get("lastUpdated") if item else None
        try:
            _utc(stamp)
        except ValueError:
            if runner["active"]:
                all_aware = False
        output[n] = {
            "raw_odds": odds, "qualified_price": price,
            "provider_timestamp_uninterpreted": stamp,
            "source_time_status": "PROVIDER_UTC_VERIFIED" if stamp is not None
            and isinstance(stamp, str) and _aware(stamp) else "SOURCE_TIME_UNVERIFIED",
        }
    active = sum(r["active"] for r in runners)
    if valid == active and all_aware:
        status, reason = "COMPLETE_WIN_VERIFIED", None
    elif valid == active:
        status, reason = "SOURCE_TIME_UNVERIFIED", "PROVIDER_ODDS_TIME_HAS_NO_OFFSET"
    else:
        status, reason = "MARKET_PARTIAL", "ACTIVE_RUNNERS_WITHOUT_VALID_WIN_PRICE"
    return {"status": status, "reason": reason, "by_number": output,
            "observed_utc": receipt["response_completed_utc"], "source_sha256":
            receipt["response_sha256"], "valid": valid}


def _aware(stamp: str) -> bool:
    try:
        _utc(stamp)
        return True
    except ValueError:
        return False


def _validate_roster(snapshot: dict, race_key: str, race_no: int, runners: list[dict]) -> None:
    item = snapshot["receipts"].get(f"/racedays/{race_key}/starts")
    if not item or not isinstance(item[1], dict):
        raise ValueError("ORIGINAL_STARTS_UNAVAILABLE")
    original = item[1].get("result", {}).get(str(race_no))
    if not isinstance(original, list):
        raise ValueError("ORIGINAL_PHYSICAL_ROSTER_UNAVAILABLE")
    index = {r["startNumber"]: r for r in original}
    if len(index) != len(original) or set(index) != {r["number"] for r in runners}:
        raise ValueError("ORIGINAL_ROSTER_MISMATCH")
    for r in runners:
        source = index[r["number"]]
        if (source.get("horseName") != r["name"]
                or str(source.get("horseRegistrationNumber")) != r["horse_registration"]
                or source.get("isScratched") is not (not r["active"])):
            raise ValueError("ORIGINAL_RUNNER_IDENTITY_OR_SCRATCH_MISMATCH")


def _rounds(snapshot: dict) -> dict:
    result = {}
    for game in snapshot["report"]["weekend_rounds"]:
        name = game["name"]
        if name in result:
            raise ValueError("DUPLICATE_GAME")
        seen = set()
        legs = {}
        for leg in game["legs"]:
            leg_no = leg["leg"] if leg["leg"] is not None else leg["race_no"]
            race_id = leg["physical_race_id"]
            if leg_no in seen or not race_id.startswith("RIKSTOTO:"):
                raise ValueError("DUPLICATE_OR_INVALID_PHYSICAL_RACE")
            seen.add(leg_no)
            race_key, race_no = race_id[len("RIKSTOTO:"):].rsplit(":", 1)
            if int(race_no) != leg["race_no"]:
                raise ValueError("PHYSICAL_RACE_NUMBER_CONFLICT")
            _validate_roster(snapshot, race_key, leg["race_no"], leg["runners"])
            market = _market(snapshot, race_key, leg["race_no"], leg["runners"])
            active = [r for r in leg["runners"] if r["active"]]
            runners = []
            for runner in leg["runners"]:
                n = runner["number"]
                price = market["by_number"].get(n, {})
                runners.append({
                    "number": n, "name": runner["name"], "active": runner["active"],
                    "scratched": not runner["active"],
                    "provider_registration": runner["horse_registration"],
                    "independent_identity_status": "NOT_ATTESTED",
                    "fundamental_history_status": "NOT_PROBED",
                    "data_quality": "BLOCKED",
                    "model_status": "NOT_ASSESSED",
                    "p_win": None, "fair_odds": None,
                    "model_market_deviation": None, "frozen_min_odds": None,
                    "win_odds": price.get("qualified_price"),
                    "win_odds_raw": price.get("raw_odds"),
                    "win_source_utc": market["observed_utc"],
                    "win_provider_timestamp_uninterpreted":
                        price.get("provider_timestamp_uninterpreted"),
                    "win_source_time_status": price.get("source_time_status", "SOURCE_TIME_UNVERIFIED"),
                    "collective_share": runner.get("collective_share"),
                    "decision": "NOT_EXECUTABLE" if runner["active"] else "NOT_APPLICABLE",
                    "blockers": (["NO_INDEPENDENT_IDENTITY_ATTESTATION",
                                  "FUNDAMENTAL_HISTORY_NOT_PROBED",
                                  "NO_QUALIFIED_MODEL_RUN",
                                  "PIT_NOT_CERTIFIED"]
                                 if runner["active"] else ["SCRATCHED"]),
                })
            legs[leg_no] = {
                "leg": leg["leg"], "physical_race_id": race_id,
                "pool_key": leg["pool_key"], "start_utc": leg["race_start_utc"],
                "active_runners": len(active), "scratched_runners": len(runners) - len(active),
                "win_status": market["status"], "win_reason": market["reason"],
                "valid_win_prices": market["valid"], "win_original_sha256": market.get("source_sha256"),
                "win_observed_utc": market["observed_utc"],
                "fundamental_history_count": None,
                "independent_identity_attested_count": 0,
                "fundamental_full_field_ready": False,
                "win_full_field_ready": market["status"] == "COMPLETE_WIN_VERIFIED",
                "pit_certified": False, "model_invocations": 0,
                "blockers": [
                    "INDEPENDENT_IDENTITIES_NOT_ATTESTED",
                    "AUTHENTIC_ATG_HISTORY_NOT_PROBED_IN_THIS_PILOT",
                    "NO_FROZEN_FUNDAMENTAL_RUN",
                    "NO_PROSPECTIVE_T4_CERTIFICATION",
                ], "runners": runners,
            }
        result[name] = legs
    return result


def compare(baseline: Path, latest: Path) -> dict:
    first = _read_snapshot(Path(baseline))
    second = _read_snapshot(Path(latest))
    if second["finished"] <= first["finished"]:
        raise ValueError("OBSERVATION_CLOCK_NOT_ADVANCING_OR_DUPLICATE")
    a, b = _rounds(first), _rounds(second)
    rounds = {}
    for name in sorted(set(a) | set(b)):
        old_legs, new_legs = a.get(name, {}), b.get(name, {})
        legs = []
        for leg_no in sorted(set(old_legs) | set(new_legs)):
            old, new = old_legs.get(leg_no), new_legs.get(leg_no)
            if not old or not new:
                legs.append({"leg": leg_no, "status": "MISSING_PHYSICAL_LEG_NOT_RECONSTRUCTED"})
                continue
            if old["physical_race_id"] != new["physical_race_id"]:
                legs.append({"leg": leg_no, "status": "PHYSICAL_RACE_ID_CHANGED",
                             "before": old["physical_race_id"], "after": new["physical_race_id"]})
                continue
            if old["pool_key"] != new["pool_key"]:
                legs.append({"leg": leg_no, "status": "POOL_KEY_CHANGED",
                             "physical_race_id": old["physical_race_id"],
                             "before_pool_key": old["pool_key"], "after_pool_key": new["pool_key"]})
                continue
            before = {r["number"]: r for r in old["runners"]}
            after = {r["number"]: r for r in new["runners"]}
            if (set(before) != set(after)
                    or any(before[n]["name"] != after[n]["name"] or
                           before[n]["provider_registration"] != after[n]["provider_registration"]
                           for n in before)):
                legs.append({"leg": leg_no, "status": "RUNNER_IDENTITY_CHANGED",
                             "physical_race_id": old["physical_race_id"]})
                continue
            scratches = [{"number": n, "name": after[n]["name"],
                          "before": before[n]["scratched"], "after": after[n]["scratched"]}
                         for n in sorted(before)
                         if before[n]["scratched"] != after[n]["scratched"]]
            odds = [{"number": n, "name": after[n]["name"],
                     "before": before[n]["win_odds"], "after": after[n]["win_odds"]}
                    for n in sorted(before) if before[n]["win_odds"] != after[n]["win_odds"]]
            shares = [{"number": n, "name": after[n]["name"],
                       "before": before[n]["collective_share"],
                       "after": after[n]["collective_share"]}
                      for n in sorted(before)
                      if before[n]["collective_share"] != after[n]["collective_share"]]
            legs.append({
                "leg": leg_no, "status": "COMPARABLE",
                "physical_race_id": old["physical_race_id"],
                "pool_key": old["pool_key"],
                "before": {"active": old["active_runners"], "valid_win": old["valid_win_prices"],
                           "win_status": old["win_status"]},
                "after": {"active": new["active_runners"], "valid_win": new["valid_win_prices"],
                          "win_status": new["win_status"]},
                "new_scratches": scratches, "price_changes": odds,
                "collective_share_changes": shares,
                "runners": new["runners"], "latest_leg_readiness": {
                    k: new[k] for k in ("fundamental_history_count",
                                      "independent_identity_attested_count",
                                      "fundamental_full_field_ready",
                                      "win_full_field_ready", "pit_certified",
                                      "model_invocations", "blockers")},
            })
        rounds[name] = {"legs": legs, "active_runners_latest": sum(
            r["active_runners"] for r in new_legs.values()),
            "win_complete_latest": sum(r["win_full_field_ready"] for r in new_legs.values())}
    return {
        "schema": SCHEMA, "research_only": True, "bet_authority": False,
        "baseline_completed_utc": first["finished"].isoformat(),
        "latest_completed_utc": second["finished"].isoformat(),
        "baseline_payload_fingerprint_sha256": first["payload_fingerprint"],
        "latest_payload_fingerprint_sha256": second["payload_fingerprint"],
        "market_payloads_unchanged": first["payload_fingerprint"] == second["payload_fingerprint"],
        "actual_t4_captures": 0, "t4_certified": False,
        "model_assessed_runners": 0, "bet_signals": 0,
        "v85_system_ev": "NOT_ESTABLISHED", "rounds": rounds,
        "limitations": [
            "WIN prices and public percentages are observation-only, not probabilities.",
            "No original ATG history or independent horse identity in this pilot.",
            "Only genuinely observed response completion times, never scheduled runs.",
            "No prospective T-4 certification or model invocation in these sources.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--latest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    result = compare(args.baseline, args.latest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({
        "schema": result["schema"], "baseline_completed_utc":
            result["baseline_completed_utc"], "latest_completed_utc":
            result["latest_completed_utc"], "rounds": {
                name: {"legs": len(item["legs"]), "win_complete": item["win_complete_latest"]}
                for name, item in result["rounds"].items()
            }, "bet_authority": False,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
