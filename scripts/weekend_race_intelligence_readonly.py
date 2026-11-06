"""P0 weekend race intelligence: *existing* Rikstoto reader and market verifier.

One independent read-only source snapshot. Does NOT alter the frozen Champion,
V3.3.12, CORE-003, thresholds, HBI state, tickets or betting authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from hbi.providers.rikstoto import RikstotoClient
from rikstoto_crawler.capture import assess, field_market
from rikstoto_crawler.extract import keyed

SCHEMA = "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
TARGETS = (
    ("ROMME_V65", "2026-11-06", ("romme",), "V65", 6),
    ("BERGSAKER_V85", "2026-11-07", ("bergsaker",), "V85", 8),
    ("KLOSTERSKOGEN_V75", "2026-11-07", ("klosterskogen",), "V75", 7),
    ("HARSTAD_SECONDARY", "2026-11-07", ("harstad",), None, None),
)


def _norm(value: object) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(value).lower())
        if not unicodedata.combining(c)
    )


def _date(meeting: dict) -> str | None:
    key = str(meeting.get("raceDayKey") or meeting.get("raceDay") or "")
    match = re.search(r"_NR_(\d{4}-\d{2}-\d{2})$", key)
    return match.group(1) if match else None


def _meetings(response: object) -> list[dict]:
    if not isinstance(response, dict) or not isinstance(response.get("result"), list):
        return []
    items = []
    for row in response["result"]:
        if not isinstance(row, dict):
            continue
        if row.get("raceDayKey") or row.get("raceDay"):
            items.append(row)
        for day in row.get("raceDays") or []:
            if isinstance(day, dict):
                items.append(day)
    return items


def _targets(groups: list[dict]) -> dict[str, list[dict]]:
    matches = {name: [] for name, *_ in TARGETS}
    unique = set()
    for item in groups:
        key = str(item.get("raceDayKey") or item.get("raceDay") or "")
        if not key or key in unique:
            continue
        unique.add(key)
        raw_name = str(item.get("raceDayName") or item.get("trackName") or "")
        # X1 is a synthetic cross-track pool wrapper: its races are NOT
        # physical Bergsaker/Klosterskogen race IDs.
        if "/" in raw_name or str(item.get("trackCode") or "").startswith("X"):
            continue
        label = _norm(raw_name + " " + str(item.get("trackCode") or ""))
        date = _date(item)
        for name, target_date, identifiers, _, _ in TARGETS:
            if date == target_date and any(x in label for x in identifiers):
                matches[name].append(item)
    return matches


def _pool_legs(meeting: dict, product: str | None) -> tuple[list[dict], list[str]]:
    """Only map first-party same-physical-raceday pool metadata, never inferred odds."""
    if product is None:
        return [], []
    pools = [p for p in meeting.get("pools") or []
             if isinstance(p, dict) and str(p.get("product")) == product]
    if not pools:
        return [], ["PRODUCT_NOT_FOUND_IN_ORIGINAL_MEETING"]
    if len(pools) != 1:
        return [], ["AMBIGUOUS_MULTIPLE_PRODUCT_POOLS"]
    pool = pools[0]
    if pool.get("isMultiTrack") is True or pool.get("isSecondary") is True:
        return [], ["MULTITRACK_OR_SECONDARY_REQUIRES_CROSS_RACEDAY_SOURCE"]
    number_list = pool.get("raceNumbers")
    numbers = []
    if not isinstance(number_list, list):
        return [], ["SOURCE_POOL_HAS_NO_ORDERED_RACE_NUMBERS"]
    for n in number_list:
        try:
            value = int(n)
        except (ValueError, TypeError):
            return [], ["INVALID_POOL_RACE_NUMBER"]
        if value < 1 or value in numbers:
            return [], ["DUPLICATE_OR_INVALID_POOL_RACE_NUMBER"]
        numbers.append(value)
    known = {int(r["raceNumber"]) for r in meeting.get("races") or []
             if isinstance(r, dict) and r.get("raceNumber") is not None}
    if not numbers or not set(numbers) <= known:
        return [], ["POOL_RACES_NOT_SUBSET_OF_PHYSICAL_MEETING"]
    key = str(meeting.get("raceDayKey") or meeting.get("raceDay"))
    return [
        {"leg": leg, "race_no": number,
         "physical_race_id": f"RIKSTOTO:{key}:{number}",
         "pool_key": pool.get("poolKey"),
         "source_mapping": "SAME_RACEDAY_ORDERED_PROVIDER_POOL"}
        for leg, number in enumerate(numbers, 1)
    ], []


def _capture(client: RikstotoClient, path: str, originals: Path) -> tuple[object, dict]:
    result = client._fetch(path, retain_raw_body=True)
    receipt = {
        "url": result.url, "http_status": result.status_code,
        "request_path": path,
        "response_completed_utc": (
            result.response_completed_at.isoformat() if result.response_completed_at else None
        ),
        "response_sha256": result.response_body_sha256,
        "http_date": result.http_date,
        "http_last_modified": result.http_last_modified,
        "http_etag": result.http_etag,
        "success": result.success, "error": result.error,
    }
    raw = getattr(result, "raw_body", b"")
    if result.success and raw:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != result.response_body_sha256:
            raise ValueError("RAW_PROVIDER_RESPONSE_SHA_MISMATCH")
        location = "originals/" + actual + ".json"
        destination = originals / (actual + ".json")
        if destination.exists() and destination.read_bytes() != raw:
            raise ValueError("ORIGINAL_SHA_COLLISION")
        if not destination.exists():
            with destination.open("xb") as stream:
                stream.write(raw)
        receipt["original_relative_path"] = location
        receipt["original_bytes"] = len(raw)
    return result.payload if result.success else None, receipt


def _scratched(payload: object, race_no: int) -> set[int] | None:
    """Do not translate an unknown provider scratch schema into 'no scratches'."""
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        return None
    contents = payload["result"]
    sub = contents.get(str(race_no), [])
    if not isinstance(sub, list):
        return None
    selected = set()
    for row in sub:
        if isinstance(row, dict) and row.get("startNumber") is not None:
            selected.add(int(row["startNumber"]))
        elif isinstance(row, int):
            selected.add(row)
        else:
            return None
    return selected


def _roster(starts: object, race_no: int) -> tuple[list[dict], list[str]]:
    if not isinstance(starts, dict) or not isinstance(starts.get("result"), dict):
        return [], ["STARTS_SOURCE_NOT_AVAILABLE"]
    rows = starts["result"].get(str(race_no))
    if not isinstance(rows, list) or not rows:
        return [], ["PHYSICAL_RACE_STARTS_NOT_FOUND"]
    try:
        seen = set()
        registrations = set()
        output = []
        for item in rows:
            n = int(item["startNumber"])
            registration = str(item["horseRegistrationNumber"])
            if (
                n < 1 or n in seen or not registration
                or type(item.get("isScratched")) is not bool
                or not str(item.get("horseName") or "").strip()
            ):
                raise ValueError("INVALID_OR_DUPLICATE_RUNNER_IDENTITY")
            if registration in registrations:
                raise ValueError("DUPLICATE_HORSE_REGISTRATION")
            seen.add(n)
            registrations.add(registration)
            output.append({
                "number": n, "name": item["horseName"],
                "horse_registration": registration,
                "identity_status": (
                    "BLOCKED_TMP_NOT_AUTHORITY" if registration.startswith("TMP-")
                    else "PROVIDER_REGISTRATION_ONLY_NOT_CROSS_VERIFIED"
                ),
                "scratched_in_starts": item["isScratched"],
                "active": not item["isScratched"],
                "p_win": None, "fair_odds": None, "frozen_min_odds": None,
                "model_ev": None, "decision": (
                    "PASS" if not item["isScratched"] else "NOT_APPLICABLE"
                ),
                "decision_reason": (
                    "NO_PIT_VERIFIED_INDEPENDENT_FUNDAMENTAL"
                    if not item["isScratched"] else "SCRATCHED"
                ),
                "win_odds": None, "win_odds_observed_utc": None,
                "raw_win_odds_unqualified": None, "collective_share": None,
            })
        return sorted(output, key=lambda r: r["number"]), []
    except (TypeError, ValueError, KeyError):
        return [], ["INVALID_OR_DUPLICATE_RUNNER_IDENTITY"]


def _assess_win(win_payload: object, roster: list[dict]) -> str:
    if not roster or not isinstance(win_payload, dict):
        return "NOT_VERIFIED"
    raw = win_payload.get("result")
    if not isinstance(raw, list):
        return "NOT_VERIFIED"
    try:
        raw_index = keyed(raw)
        # A partial pre-race pool can carry isolated prices, which are only
        # descriptive until exact full-field market completeness is verified.
        for r in roster:
            snapshot = raw_index.get(str(r["number"]))
            if snapshot and type(snapshot.get("odds")) in (int, float):
                odds = float(snapshot["odds"])
                if odds > 1:
                    r["raw_win_odds_unqualified"] = odds
        market = field_market(
            raw,
            {str(r["number"]): r for r in roster},
            {str(r["number"]) for r in roster if r["active"]},
            ["odds"],
        )
        if market["status"] != "COMPLETE":
            return market["status"] + ":" + str(market.get("reason"))
        for r in roster:
            if r["active"]:
                source = raw_index[str(r["number"])]
                r["win_odds"] = market["values"][str(r["number"])][0]
                r["win_odds_observed_utc"] = source.get("lastUpdated")
        return "COMPLETE_RESEARCH_PRICE_NOT_EXECUTABILITY_CERTIFIED"
    except (ValueError, KeyError, TypeError):
        return "INVALID_OR_INCOMPLETE"


def _original_report(*, client: RikstotoClient, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    originals = output / "originals"
    originals.mkdir()
    as_of = datetime.now(UTC).isoformat()
    receipts = []
    discovery, source = _capture(client, "/racedays/", originals)
    receipts.append(source)
    groups = _meetings(discovery)
    # Official historical discovery endpoint is an optional fallback; it does
    # not prove race-specific WIN or even current runner status.
    if not all(_targets(groups).get(k) for k in ("BERGSAKER_V85", "KLOSTERSKOGEN_V75")):
        extra, rec = _capture(
            client, "/results/racedays/2026-11-06/2026-11-07/list", originals
        )
        receipts.append(rec)
        groups.extend(_meetings(extra))
    matches = _targets(groups)
    # Preserve original cross-track pool metadata without treating X1
    # pseudo-races as additional physical track races.
    composite_meetings = [{
        "key": str(g.get("raceDayKey") or g.get("raceDay")),
        "name": g.get("raceDayName"),
        "products": [p.get("product") for p in g.get("pools", [])
                     if isinstance(p, dict)],
        "physical_race_id_authority": False,
        "reason": "MULTITRACK_POOL_SYNTHETIC_RACEDAY_NOT_PHYSICAL_TRACK",
    } for g in groups if isinstance(g, dict)
       and "/" in str(g.get("raceDayName") or "")]
    rounds = []
    for target_name, target_day, _, product, expected_legs in TARGETS:
        candidates = matches[target_name]
        game = {
            "name": target_name, "race_date": target_day,
            "product": product, "expected_legs": expected_legs,
            "meetings_found": len(candidates), "source_raceday_keys": [],
            "legs": [], "race_catalog": [],
            "legs_verified": 0, "active_runners": None,
            "fundamental_complete_fields": 0,
            "win_complete_fields": 0, "collective_complete_fields": 0,
            "pit_eligible_fields": 0,
            "bet_count": 0, "watch_count": 0, "pass_count": None,
            "total_runners_observed": None,
            "system_ev": "NOT_ESTABLISHED", "jackpot": None,
            "turnover": None, "turnover_status": "NOT_VERIFIED",
            "blockers": [], "bet_authority": False,
        }
        if not candidates:
            game["blockers"].append("MEETING_NOT_FOUND_IN_PROVIDER_RACEDAY_DISCOVERY")
        for meeting in candidates:
            key = str(meeting.get("raceDayKey") or meeting.get("raceDay"))
            if not re.fullmatch(r"[A-Za-z0-9]+_NR_20\d{2}-\d{2}-\d{2}", key):
                game["blockers"].append("PHYSICAL_RACEDAY_KEY_NOT_VERIFIED")
                continue
            game["source_raceday_keys"].append(key)
            game["race_catalog"].extend({
                "race_no": int(r["raceNumber"]),
                "physical_race_id": f"RIKSTOTO:{key}:{int(r['raceNumber'])}",
                "race_start_source": r.get("startTime"),
                "distance_m": r.get("distance"),
                "start_method": r.get("startMethod"),
            } for r in meeting.get("races") or []
            if isinstance(r, dict) and r.get("raceNumber") is not None)
            mapping, problems = _pool_legs(meeting, product)
            game["blockers"].extend(problems)
            if product is None:
                # Secondary Harstad: physical races without a claimed V-game.
                mapping = [{"leg": None, "race_no": r["race_no"],
                            "physical_race_id": r["physical_race_id"],
                            "pool_key": None, "source_mapping": "SECONDARY_RACE_CATALOG"}
                           for r in game["race_catalog"]
                           if r["physical_race_id"].startswith(f"RIKSTOTO:{key}:")]
            if not mapping:
                continue
            # Reuse the verified V3 research parser for percentage shares.
            # A collective percentage is NOT a WIN model probability.
            pool_meta = next((p for p in meeting.get("pools") or []
                              if isinstance(p, dict) and p.get("product") == product), None)
            distribution = None
            if pool_meta is not None and product in {"V65", "V75", "V85"}:
                anchor = pool_meta.get("raceNumber")
                if type(anchor) is int and anchor > 0:
                    distribution, pool_receipt = _capture(
                        client,
                        f"/game/{key}/betdistribution/investment/{product}?raceNumber={anchor}",
                        originals,
                    )
                    receipts.append(pool_receipt)
                else:
                    game["blockers"].append("POOL_ANCHOR_RACE_NUMBER_UNVERIFIED")
            # Turnover/jackpot remain market *context*, never EV evidence.
            context, context_receipt = _capture(
                client, f"/results/raceDays/{key}/totalInvestment", originals
            )
            receipts.append(context_receipt)
            game["turnover_status"] = (
                "RAW_PROVIDER_CONTEXT_SAVED_NOT_INTERPRETED"
                if context is not None else "NOT_VERIFIED"
            )
            # Join the official investment line using the *exact* product,
            # poolKey, raceday and raceNumber. The numeric unit is NOT certified:
            # never present provider integer amounts as NOK/SEK or as jackpot.
            if isinstance(context, dict) and isinstance(context.get("result"), list) and pool_meta:
                matching = [x for x in context["result"] if isinstance(x, dict)
                            and x.get("raceDay") == key
                            and x.get("poolKey") == pool_meta.get("poolKey")
                            and x.get("product") == product
                            and x.get("raceNumber") == pool_meta.get("raceNumber")]
                if len(matching) == 1:
                    entry = matching[0]
                    if (type(entry.get("totalInvestment")) is int
                            and entry["totalInvestment"] >= 0):
                        game["turnover"] = {
                            "provider_raw_total_investment": entry["totalInvestment"],
                            "raw_number_of_systems": entry.get("numberOfSystems"),
                            "raw_max_pay_value_not_jackpot": entry.get("maxPayValue"),
                            "unit": "UNVERIFIED_PROVIDER_RAW_UNIT",
                            "exact_pool_key": pool_meta.get("poolKey"),
                            "source_sha256": context_receipt["response_sha256"],
                            "source_observed_utc": context_receipt["response_completed_utc"],
                        }
                        game["turnover_status"] = "EXACT_POOL_SOURCE_RAW_UNIT_UNVERIFIED"
                    if type(entry.get("jackpot")) in (int, float):
                        game["jackpot"] = {
                            "provider_raw": entry["jackpot"],
                            "unit": "UNVERIFIED_PROVIDER_RAW_UNIT",
                        }
            starts, starts_receipt = _capture(client, f"/racedays/{key}/starts", originals)
            scratched, scratch_receipt = _capture(
                client, f"/racedays/{key}/scratched", originals
            )
            receipts.extend([starts_receipt, scratch_receipt])
            for leg in mapping:
                no = leg["race_no"]
                field, issues = _roster(starts, no)
                if any(r.get("identity_status") == "BLOCKED_TMP_NOT_AUTHORITY"
                       for r in field):
                    issues.append("TMP_IDENTITIES_NOT_AUTHORITATIVE_FOR_MODEL")
                scratch_numbers = _scratched(scratched, no)
                if scratch_numbers is None:
                    issues.append("SCRATCHED_ENDPOINT_UNVERIFIED")
                elif field and {r["number"] for r in field if r["scratched_in_starts"]} != scratch_numbers:
                    issues.append("SCRATCHED_STARTS_SOURCE_CONFLICT")
                win, win_receipt = _capture(
                    client, f"/game/{key}/betdistribution/winodds/{no}", originals
                )
                receipts.append(win_receipt)
                win_status = _assess_win(win, field)
                collective_status = "NO_VALIDATED_POOL_DISTRIBUTION"
                if field and pool_meta is not None and isinstance(distribution, dict):
                    try:
                        raw_starts = starts["result"][str(no)]
                        parsed = assess(
                            key, no, raw_starts, win.get("result") or []
                            if isinstance(win, dict) else [], [], [(pool_meta, distribution.get("result") or [])],
                        )
                        choices = parsed["collective"]
                        if len(choices) == 1 and choices[0]["status"] == "COMPLETE":
                            shares = choices[0]["pCOL"]
                            for runner in field:
                                if runner["active"]:
                                    runner["collective_share"] = shares[str(runner["number"])]
                            collective_status = "COMPLETE_PUBLIC_POOL_SHARE_NOT_PWIN"
                        elif choices:
                            collective_status = choices[0]["status"] + ":" + str(
                                choices[0].get("reason") or ""
                            )
                    except (KeyError, ValueError, TypeError):
                        collective_status = "INVALID_POOL_SOURCE_OR_CROSS_FIELD"
                if collective_status != "COMPLETE_PUBLIC_POOL_SHARE_NOT_PWIN":
                    issues.append("COLLECTIVE_DISTRIBUTION_NOT_VERIFIED")
                if not win_status.startswith("COMPLETE"):
                    issues.append("WIN_ORIGINAL_INCOMPLETE_OR_UNAVAILABLE")
                source_race = next(
                    (r for r in game["race_catalog"] if r["physical_race_id"] == leg["physical_race_id"]),
                    {},
                )
                start_raw = source_race.get("race_start_source")
                start_utc = None
                if isinstance(start_raw, str):
                    try:
                        start_utc = client.parse_timestamp(start_raw).isoformat()
                    except (ValueError, TypeError):
                        issues.append("START_TIME_INVALID")
                if start_utc is None:
                    issues.append("START_TIME_NOT_SOURCE_VERIFIED")
                if not field:
                    issues.append("FULL_FIELD_NOT_VERIFIED")
                issues.extend([
                    "INDEPENDENT_HISTORY_AND_IDENTITY_NOT_PIT_CERTIFIED",
                    "NO_FROZEN_FUNDAMENTAL_PROBABILITIES",
                    "NO_REPLAYED_T4_SOURCE_RECEIPTS",
                ])
                game["legs"].append({
                    **leg, "race_start_utc": start_utc,
                    "total_runners": len(field) if field else None,
                    "active_runners": sum(r["active"] for r in field) if field else None,
                    "scratched_runners": sum(not r["active"] for r in field) if field else None,
                    "runners": field, "win_status": win_status,
                    "collective_status": collective_status,
                    "scratch_status": "VERIFIED" if scratch_numbers is not None
                                      and "SCRATCHED_STARTS_SOURCE_CONFLICT" not in issues
                                      else "NOT_VERIFIED",
                    "fundamental_eligible": False, "pit_certified": False,
                    "blockers": sorted(set(issues)),
                })
        if product and expected_legs is not None and len(game["legs"]) != expected_legs:
            game["blockers"].append("LEG_COUNT_NOT_VERIFIED_AGAINST_ORIGINAL_POOL")
        game["legs"].sort(key=lambda r: (r["leg"] is None, r["leg"] or 999, r["physical_race_id"]))
        game["legs_verified"] = sum(
            leg["source_mapping"] == "SAME_RACEDAY_ORDERED_PROVIDER_POOL"
            for leg in game["legs"]
        )
        known = [r for x in game["legs"] for r in x["runners"]]
        if game["legs"] and all(x["active_runners"] is not None for x in game["legs"]):
            game["active_runners"] = sum(x["active_runners"] for x in game["legs"])
            game["total_runners_observed"] = len(known)
            game["pass_count"] = sum(r["decision"] == "PASS" for r in known)
            game["win_complete_fields"] = sum(x["win_status"].startswith("COMPLETE")
                                              for x in game["legs"])
            game["collective_complete_fields"] = sum(
                x["collective_status"] == "COMPLETE_PUBLIC_POOL_SHARE_NOT_PWIN"
                for x in game["legs"]
            )
        game["blockers"] = sorted(set(game["blockers"]))
        rounds.append(game)
    report = {
        "schema": SCHEMA, "source_as_of_utc": as_of,
        "source_observation_completed_utc": datetime.now(UTC).isoformat(),
        "authority": "RESEARCH_ONLY_NO_BET", "bet_authority": False,
        "frozen_model_changed": False,
        "new_model_invocations": 0, "model_predictions_made": 0,
        "weekend_rounds": rounds, "original_receipts": receipts,
        "composite_pool_wrappers_not_physical_races": composite_meetings,
        "original_sha256": {r["request_path"]: r["response_sha256"] for r in receipts},
        "v85_v75_v65_system_ev": "NOT_ESTABLISHED",
        "interpretation": (
            "No synthetic p(win), executable historical prices or inferred cross-track game legs. "
            "Public pool percentages never substitute for winner probability. "
            "Blocked runners PASS; a scheduled watcher is NOT T-4 certification."
        ),
    }
    with (output / "weekend-race-intelligence.json").open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = _original_report(client=RikstotoClient(timeout=10), output=args.output)
    print(json.dumps({
        "schema": report["schema"], "source_as_of_utc": report["source_as_of_utc"],
        "rounds": [{
            "name": r["name"], "meetings": r["meetings_found"], "legs": r["legs_verified"],
            "active": r["active_runners"], "wins": r["win_complete_fields"],
            "blockers": r["blockers"],
        } for r in report["weekend_rounds"]]
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
