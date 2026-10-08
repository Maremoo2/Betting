"""Pure historical extraction. No outcome inspection and no p(win) estimates."""
from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from zoneinfo import ZoneInfo

from betting.v33 import POLICY_HASH, divergence, normalize

PRODUCTS = {"V4", "V5", "V64", "V65", "V75", "V85", "V86"}
OSLO = ZoneInfo("Europe/Oslo")


def utc(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=OSLO).astimezone(UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def numeric(value, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("nonfinite/non-numeric market field")
    if value < minimum:
        raise ValueError("market field below minimum")
    return value


def keyed(rows):
    result = {}
    for row in rows:
        key = str(row["startNumber"])
        if key in result or not key.isdigit() or int(key) <= 0:
            raise ValueError("ambiguous runner number")
        result[key] = row
    return result


def extract_race(meeting, race, starts, info, scratches, win, place, pools, investments):
    """Strict full-field extraction; terminal archive is NOT executable pre-race PIT."""
    key, number = meeting["raceDay"], race["raceNumber"]
    if race.get("isAbandoned") or race.get("progressStatus") != "Finished":
        raise ValueError("race not normally finished")
    start = utc(race["startTime"])
    all_runners = keyed(starts)
    if not all_runners or any(type(r.get("isScratched")) is not bool for r in starts):
        raise ValueError("unknown active/scratch status")
    scratched = {k for k, row in all_runners.items() if row["isScratched"]}
    # The historical endpoint commonly supplies a per-race list of start numbers.
    extra = scratches.get(str(number), [])
    if not isinstance(extra, list):
        raise TypeError("unsupported scratch schema")
    for value in extra:
        n = str(value["startNumber"] if isinstance(value, dict) else value)
        if n not in all_runners:
            raise ValueError("scratch outside roster")
        scratched.add(n)
    active = set(all_runners) - scratched
    if len(active) < 2:
        raise ValueError("insufficient active field")
    runners = {}
    for n, row in all_runners.items():
        if row.get("raceNumber") != number or row.get("raceKey") != f"{key}#{number}":
            raise ValueError("runner race identity mismatch")
        if not row.get("horseName") or not row.get("horseRegistrationNumber"):
            raise ValueError("runner identity absent")
        runners[n] = {"start_number": n, "horse_name": row["horseName"],
                      "horse_id": row["horseRegistrationNumber"],
                      "horse_id_stable": not row["horseRegistrationNumber"].startswith("TMP-"),
                      "driver_name": row.get("driverName"), "scratched": n in scratched,
                      "identity_match": "EXACT_RACE_START_NUMBER", "match_confidence": 1}
    if len({r["horse_id"] for r in runners.values()}) != len(runners):
        raise ValueError("duplicate horse identity")
    wins, places = keyed(win), keyed(place)
    if not active <= set(wins) or not active <= set(places):
        raise ValueError("incomplete WIN/PLACE field")
    if (set(wins) | set(places)) - set(all_runners):
        raise ValueError("odds outside roster")
    odds, win_times = {}, []
    for n in active:
        w, p = wins[n], places[n]
        odds[n] = numeric(w["odds"], minimum=1.000001)
        lo, hi = numeric(p["minOdds"], minimum=1), numeric(p["maxOdds"], minimum=1)
        if hi < lo:
            raise ValueError("inverted PLACE range")
        wt, pt = utc(w["lastUpdated"]), utc(p["lastUpdated"])
        if wt.date() != start.date() or pt.date() != start.date():
            raise ValueError("market update on unrelated day")
        win_times.append(wt)
        runners[n].update(win_odds=odds[n], place_min=lo, place_max=hi,
                          win_updated_at=wt.isoformat(), place_updated_at=pt.isoformat())
    pwin = normalize(odds, active, odds=True)
    collective, rejected_pools = {}, {}
    for pool_key, pool in pools.items():
        try:
            if pool["raceKey"] != f"{key}#{number}" or pool["raceNumber"] != number:
                raise ValueError("collective race identity mismatch")
            dist = keyed(pool["investmentDistribution"])
            if not active <= set(dist) or set(dist) - set(all_runners):
                raise ValueError("incomplete collective field")
            updated = utc(pool["updatedTime"])
            if updated.date() > start.date():
                raise ValueError("collective update after race day")
            shares = {n: numeric(dist[n]["percentage"]) for n in active}
            if any(v > 100 for v in shares.values()):
                raise ValueError("invalid collective percentage")
            pcol = normalize(shares, active)
            product = pool["product"]
            leg = pool["leg"]
            if (product not in PRODUCTS or type(leg) is not int or leg < 1
                    or pool["pool_race_numbers"][leg - 1] != number
                    or pool["pool_start_race"] != pool["pool_race_numbers"][0]
                    or pool_key != f"{key}#{product}#{pool['pool_start_race']}"):
                raise ValueError("collective product/leg identity mismatch")
            skew = max(abs((t - updated).total_seconds()) for t in win_times)
            # Preserve archive shares even for later legs; do not pretend contemporaneous data.
            collective[pool_key] = {"product": product, "leg": leg,
                                    "pool_start_race": pool["pool_start_race"],
                                    "pool_race_numbers": pool["pool_race_numbers"],
                                    "source": pool.get("source"),
                                    "updated_at": updated.isoformat(), "win_skew_seconds": skew,
                                    "contemporaneous": skew <= 60, "raw_shares": shares,
                                    "pCOL": pcol, "signals": {
                                        n: divergence(pcol[n], pwin[n]) for n in active}}
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            rejected_pools[pool_key] = str(exc)
    if not collective:
        raise ValueError("NO_COMPLETE_COLLECTIVE_POOL")
    turnover = {}
    for product in ("V", "P"):
        matching = [r for r in investments if r.get("raceDay") == key
                    and r.get("product") == product and r.get("raceNumber") == number]
        if len(matching) != 1:
            raise ValueError("missing/ambiguous V/P turnover")
        raw = numeric(matching[0]["totalInvestment"], minimum=1)
        turnover[product] = {"raw_minor_units": raw, "nok": raw / 100,
                             "scale": 100, "pool_key": matching[0]["poolKey"]}
    pool_totals = {}
    for pool_key in collective:
        matches = [r for r in investments if r.get("poolKey") == pool_key]
        if len(matches) != 1:
            raise ValueError("missing/ambiguous collective pool turnover")
        raw = numeric(matches[0]["totalInvestment"], minimum=1)
        pool_totals[pool_key] = {"raw_minor_units": raw, "nok": raw / 100}
    flags = []
    if turnover["V"]["raw_minor_units"] == turnover["P"]["raw_minor_units"]:
        flags.append("VP_TURNOVER_IDENTICAL")
    if all(runners[n]["place_min"] == runners[n]["place_max"] for n in active):
        flags.append("PLACE_RANGE_COLLAPSED_ALL_ACTIVE")
    if meeting["countryIsoCode"] == "SE" and flags:
        flags.append("SE_PLACE_SEMANTICS_UNVERIFIED")
    return {"schema_version": "RIKSTOTO_PRE_WINNER_ARCHIVE_V2",
            "data_quality_flags": flags, "place_semantics_verified": False,
            "race_id": f"RIKSTOTO:{key}:{number}", "raceday_key": key,
            "race_number": number, "date": key[-10:], "track": meeting["raceDayName"],
            "country": meeting["countryIsoCode"], "sport": meeting["sportType"],
            "provider_is_merged": race.get("isMerged"),
            "race_start": start.isoformat(), "distance": info.get("distance"),
            "race_name": info.get("raceName"), "runners": runners,
            "active_field": sorted(active, key=int), "pWIN": pwin,
            "collective": collective, "rejected_pools": rejected_pools,
            "turnover": turnover, "collective_turnover": pool_totals,
            "policy_hash": POLICY_HASH, "snapshot_kind": "HISTORICAL_TERMINAL_ARCHIVE",
            "prospective": False, "executable": False,
            "signal_protocol": "V3.3_RESEARCH_EVIDENCE_ONLY",
            "m0_m6_status": "NOT_CONFIGURED_PROTOCOL_NOT_RETRIEVED"}
