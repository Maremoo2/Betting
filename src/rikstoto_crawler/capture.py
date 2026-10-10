"""Versioned research capture; independent availability, never a betting decision."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .extract import PRODUCTS, keyed, numeric, utc
from .transport import ArchiveClient, digest, write_json

ALIASES = {"V5A": "V5"}


def field_market(rows, roster, active, fields):
    """Preserve raw values; derive only from an exact complete active field."""
    try:
        indexed = keyed(rows)
        if not active <= indexed.keys() or indexed.keys() - roster.keys():
            raise ValueError("INCOMPLETE_FIELD")
        values = {}
        for n in active:
            values[n] = [numeric(indexed[n][f], minimum=1) for f in fields]
            if len(fields) == 2 and values[n][1] < values[n][0]:
                raise ValueError("INVERTED_PLACE_RANGE")
            utc(indexed[n]["lastUpdated"])
        return {"status": "COMPLETE", "values": values}
    except (KeyError, ValueError, TypeError) as exc:
        return {"status": "INVALID_OR_INCOMPLETE", "reason": str(exc)}


def assess(key, number, starts, win, place, distributions):
    roster = keyed(starts)
    if not roster or any(type(r.get("isScratched")) is not bool for r in starts):
        raise ValueError("UNKNOWN_FIELD")
    if any(r.get("raceKey") != f"{key}#{number}" or r.get("raceNumber") != number or not r.get("horseRegistrationNumber")
           or not r.get("horseName") for r in starts):
        raise ValueError("IDENTITY_MISMATCH")
    if len({r["horseRegistrationNumber"] for r in starts}) != len(starts):
        raise ValueError("DUPLICATE_IDENTITY")
    active = {n for n, r in roster.items() if not r["isScratched"]}
    if len(active) < 2:
        raise ValueError("INSUFFICIENT_FIELD")
    markets = {"WIN": field_market(win, roster, active, ["odds"]),
               "PLACE": field_market(place, roster, active, ["minOdds", "maxOdds"])}
    pwin = None
    if markets["WIN"]["status"] == "COMPLETE":
        inverse = {n: 1 / v[0] for n, v in markets["WIN"]["values"].items()}
        pwin = {n: v / sum(inverse.values()) for n, v in inverse.items()}
    collective = []
    for meta, rows in distributions:
        item = {"pool_id": meta["poolKey"], "provider_product": meta["product"],
                "product": ALIASES.get(meta["product"], meta["product"]),
                "leg": meta["raceNumbers"].index(number) + 1, "status": "INVALID_OR_INCOMPLETE"}
        try:
            matches = [r for r in rows if r.get("raceNumber") == number]
            if len(matches) != 1 or matches[0].get("raceKey") != f"{key}#{number}":
                raise ValueError("POOL_RACE_MISMATCH")
            row = matches[0]
            indexed = keyed(row["investmentDistribution"])
            if not active <= indexed.keys() or indexed.keys() - roster.keys():
                raise ValueError("INCOMPLETE_COLLECTIVE_FIELD")
            shares = {n: numeric(indexed[n]["percentage"]) for n in active}
            total = sum(shares.values())
            if total <= 0:
                raise ValueError("EMPTY_COLLECTIVE")
            item.update(status="COMPLETE", pCOL={n: v / total for n, v in shares.items()},
                        provider_updated_at=utc(row["updatedTime"]).isoformat())
            if pwin is not None:
                times = [utc(r["lastUpdated"]) for r in win if str(r["startNumber"]) in active]
                skew = max(abs((utc(row["updatedTime"]) - t).total_seconds()) for t in times)
                item.update(skew_seconds=skew, timing_class="PRIMARY" if skew <= 60 else
                            "SECONDARY" if skew <= 300 else "EXCLUDE_DIAGNOSTIC",
                            delta={n: item["pCOL"][n] - pwin[n] for n in active},
                            ratio={n: item["pCOL"][n] / pwin[n] for n in active})
        except (KeyError, ValueError, TypeError) as exc:
            item["reason"] = str(exc)
        collective.append(item)
    return {"active_field": sorted(active, key=int), "markets": markets,
            "pWIN": pwin, "collective": collective}


def collect(root, days, *, countries=("NO", "SE", "DK", "FR"), client=None, refresh=False, meeting_key=None, race_numbers=None, include_combinations=True):
    root = Path(root)
    if (root / "freeze.json").exists() or (root / "pre.jsonl").exists():
        raise ValueError("Use a new V3 output directory; frozen PRE is read-only")
    root.mkdir(parents=True, exist_ok=True)
    client = client or ArchiveClient(root)
    records, failures = [], {}
    for day in sorted(set(days)):
        def fetch(path):
            envelope = client.get(path, refresh=refresh)
            sources.append({k: envelope[k] for k in ("path", "url", "fetched_at", "body_sha256")})  # noqa: B023
            return envelope["body"]["result"]
        sources = []
        try:
            groups = fetch(f"/results/racedays/{day}/{day}/list")
        except (OSError, ValueError, TypeError) as exc:
            failures[day] = str(exc)
            continue
        discovery_sources = list(sources)
        for meeting in [m for g in groups for m in g["raceDays"]
                        if m["countryIsoCode"] in countries
                        and (meeting_key is None or m["raceDay"] == meeting_key)]:
            selected = [r for r in meeting["races"]
                        if race_numbers is None or r["raceNumber"] in race_numbers]
            if not selected:
                continue
            selected_numbers = {r["raceNumber"] for r in selected}
            key = meeting["raceDay"]
            sources = list(discovery_sources)
            try:
                starts = fetch(f"/racedays/{key}/starts")
                totals = fetch(f"/results/raceDays/{key}/totalInvestment")
            except (OSError, ValueError, TypeError) as exc:
                failures[key] = str(exc)
                continue
            meeting_sources = list(sources)
            pools, coverage, combinations = [], [], []
            for meta in meeting["pools"]:
                if not selected_numbers.intersection(meta["raceNumbers"]):
                    continue
                product = ALIASES.get(meta["product"], meta["product"])
                status = {"pool_id": meta["poolKey"], "provider_product": meta["product"],
                          "product": product, "status": "UNSUPPORTED_ENDPOINT"}
                if product in PRODUCTS and not (meta.get("isMultiTrack") or meta.get("isSecondary")):
                    try:
                        rows = fetch(f"/game/{key}/betdistribution/investment/{meta['product']}"
                                     f"?raceNumber={meta['raceNumber']}")
                        if not isinstance(rows, list):
                            raise TypeError("UNSUPPORTED_SCHEMA")
                        pools.append((meta, rows))
                        status["status"] = "FETCHED"
                    except (OSError, ValueError, TypeError) as exc:
                        status.update(status="FETCH_ERROR", reason=str(exc))
                        failures[meta["poolKey"]] = str(exc)
                routes = {"TV": "tv", "DUO": "duo", "T": "t", "DD": "dd"}
                if meta["product"] in routes and include_combinations:
                    for race_no in ([meta["raceNumber"]] if meta["product"] == "DD" else meta["raceNumbers"]):
                        if meta["product"] != "DD" and race_no not in selected_numbers:
                            continue
                        combo = {"pool_id": meta["poolKey"], "product": meta["product"],
                                 "race_number": race_no, "status": "FETCH_ERROR"}
                        try:
                            combo["raw_rows"] = fetch(f"/game/{key}/odds/{routes[meta['product']]}/{race_no}")
                            combo["status"] = "RAW_SCHEMA_UNVERIFIED" if combo["raw_rows"] else "EMPTY"
                            status["status"] = "RAW_FETCHED"
                        except (OSError, ValueError, TypeError) as exc:
                            combo["reason"] = str(exc)
                            failures[f"{meta['poolKey']}:{race_no}"] = str(exc)
                        combinations.append(combo)
                elif meta["product"] in routes:
                    status["status"] = "NOT_REQUESTED"
                elif meta["product"] in {"V", "P", "VP"}:
                    status["status"] = "RUNNER_ENDPOINT"
                if status["status"] == "UNSUPPORTED_ENDPOINT" and (meta.get("isMultiTrack") or meta.get("isSecondary")):
                    status["reason"] = "MULTITRACK_OR_SECONDARY"
                coverage.append(status)
            pool_sources = sources[len(meeting_sources):]
            for race in selected:
                number = race["raceNumber"]
                sources = meeting_sources + pool_sources
                record = {"schema_version": "RIKSTOTO_RESEARCH_CAPTURE_V3", "day": day,
                          "country": meeting["countryIsoCode"], "raceday_key": key,
                          "race_number": number, "race_id": f"RIKSTOTO:{key}:{number}",
                          "observed_race_metadata": race, "product_coverage": coverage,
                          "turnover_raw": totals, "executable": False,
                          "combination_markets": [c for c in combinations if c["race_number"] == number]}
                record["raw_roster"] = starts.get(str(number), [])
                try:
                    win = fetch(f"/game/{key}/betdistribution/winodds/{number}")
                    try:
                        place = fetch(f"/game/{key}/betdistribution/placeodds/{number}")
                    except (OSError, ValueError, TypeError) as exc:
                        place = []
                        record["place_fetch_error"] = str(exc)
                        failures[record["race_id"] + ":PLACE"] = str(exc)
                    record.update(raw_roster=starts.get(str(number), []), raw_win=win, raw_place=place)
                    record.update(assess(key, number, record["raw_roster"], win, place,
                                         [(m, r) for m, r in pools if number in m["raceNumbers"]]))
                except (OSError, KeyError, ValueError, TypeError) as exc:
                    record["assessment_error"] = str(exc)
                    failures[record["race_id"]] = str(exc)
                record["sources"] = list(sources)
                record["captured_at"] = max(s["fetched_at"] for s in sources)
                record["observation_completed_at"] = datetime.now(UTC).isoformat()
                record["snapshot_kind"] = "OBSERVED_MARKET_CAPTURE" if refresh else "HISTORICAL_ARCHIVE"
                record["snapshot_id"] = digest({k: v for k, v in record.items()
                                                if k != "observation_completed_at"})
                destination = root / "captures" / day / (record["snapshot_id"] + ".json")
                if not destination.exists():
                    write_json(destination, record)
                records.append(record)
    report = {"schema_version": "RIKSTOTO_CAPTURE_COVERAGE_V3", "captures": len(records),
              "failures": failures, "by_country": dict(Counter(r["country"] for r in records)),
              "win_complete": sum(r.get("markets", {}).get("WIN", {}).get("status") == "COMPLETE" for r in records),
              "place_complete": sum(r.get("markets", {}).get("PLACE", {}).get("status") == "COMPLETE" for r in records),
              "unsupported_products": sorted({p["provider_product"] for r in records
                                               for p in r["product_coverage"] if p["status"] == "UNSUPPORTED_ENDPOINT"})}
    by_day_country_product = Counter()
    for row in records:
        for pool in row["product_coverage"]:
            # Count each discovered pool once per invocation, not once per race.
            by_day_country_product[(row["day"], row["country"], pool["provider_product"],
                                    pool["status"], pool["pool_id"])] = 1
    grouped = Counter()
    for day, country, product, status, _ in by_day_country_product:
        grouped[(day, country, product, status)] += 1
    report["pool_coverage"] = [{"day": day, "country": country, "provider_product": product,
                                "status": status, "pools": count}
                               for (day, country, product, status), count in sorted(grouped.items())]
    write_json(root / "coverage.json", report)
    return report
