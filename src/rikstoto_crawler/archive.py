"""Resumable historic census, daily market freezes and separate verified outcomes."""
from __future__ import annotations

import calendar
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from pre_winner.config_v1 import CONFIG, CONFIG_HASH
from pre_winner.signals import classify

from .capture import ALIASES, assess
from .extract import PRODUCTS, keyed, utc
from .job import horse_name
from .transport import ArchiveClient, digest, write_json

COLLECTIVE_PRODUCTS = PRODUCTS | {"V76"}


def months(first, last):
    start, end = date.fromisoformat(first + "-01"), date.fromisoformat(last + "-01")
    if start > end or end >= datetime.now(UTC).date().replace(day=1):
        raise ValueError("Use a finished, chronological historical month range")
    current = start
    while current <= end:
        yield current.strftime("%Y-%m")
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)


def timing_quality(day, start, win, pool):
    """Shared migration timestamps must never look like a contemporaneous race."""
    try:
        if not start or start.startswith("0001-"):
            raise ValueError("START_TIME_MISSING_OR_SENTINEL")
        if utc(start).astimezone(ZoneInfo("Europe/Oslo")).date().isoformat() != day:
            raise ValueError("START_DATE_MISMATCH")
        values = [w["lastUpdated"] for w in win] + [pool["provider_updated_at"]]
        if any(utc(v).astimezone(ZoneInfo("Europe/Oslo")).date().isoformat() != day
               for v in values):
            raise ValueError("UPDATE_ON_UNRELATED_DAY")
        return pool.get("timing_class", "UNKNOWN")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return "UNKNOWN:" + str(exc)


def verify_outcome(roster, active, result):
    if not isinstance(result, dict) or result.get("isComplete") is not True:
        raise ValueError("RESULT_NOT_COMPLETE")
    indexed, field = keyed(result["results"]), keyed(roster)
    if not set(active) <= indexed.keys() or indexed.keys() - field.keys():
        raise ValueError("RESULT_FIELD_MISMATCH")
    for n in active:
        if (indexed[n].get("horseRegistrationNumber") != field[n]["horseRegistrationNumber"]
                or horse_name(indexed[n].get("horseName", "")) != horse_name(field[n]["horseName"])):
            raise ValueError("RESULT_IDENTITY_MISMATCH")
    winners = [n for n in active if indexed[n].get("place") == 1]
    if not winners:
        raise ValueError("NO_VERIFIED_WINNER")
    return {"winners": winners, "dead_heat": len(winners) != 1}


def locked_json(path, value):
    path = Path(path)
    if path.exists():
        if digest(json.loads(path.read_text(encoding="utf-8"))) != digest(value):
            raise ValueError("Immutable archive changed")
    else:
        write_json(path, value)


def census(root, first, last, client):
    root = Path(root)
    inventory = []
    for month in reversed(list(months(first, last))):
        end = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
        path = f"/racedays/dates/{month}-01/{month}-{end:02d}"
        record = client.get(path)
        meetings = record["body"]["result"]
        if not isinstance(meetings, list):
            raise TypeError("Unsupported historical discovery schema")
        locked_json(root / "inventory" / (month + ".json"), record)
        inventory.append({"month": month, "meetings": len(meetings),
                          "races": sum(len(m.get("races", [])) for m in meetings),
                          "products": dict(Counter(p["product"] for m in meetings for p in m.get("pools", []))),
                          "status": "DISCOVERED" if meetings else "EMPTY_DISCOVERY_NOT_PROOF_OF_NO_RACING"})
        write_json(root / "census.json", inventory)
    return inventory


def collect_day(root, day, meetings, client):
    root = Path(root)
    pre_path = root / "market-days" / (day + ".json")
    post_path = root / "result-days" / (day + ".json")
    if post_path.exists():
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        post = json.loads(post_path.read_text(encoding="utf-8"))
        if pre["sha256"] != digest(pre["races"]) or post["pre_sha256"] != pre["sha256"]:
            raise ValueError("Daily market/result freeze checksum mismatch")
        return post["summary"]
    if pre_path.exists():
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        if pre["sha256"] != digest(pre["races"]):
            raise ValueError("Daily market freeze checksum mismatch")
        rows = pre["races"]
    else:
        rows = []
        for meeting in meetings:
            key = meeting["raceDayKey"]
            country = meeting.get("countryIsoCode") or ("NO" if meeting.get("isDomestic") is True else "UNKNOWN")
            sources, pools, coverage = [], [], []

            def get(path):
                record = client.get(path)
                sources.append({k: record[k] for k in ("path", "url", "body_sha256", "fetched_at")})  # noqa: B023
                return record["body"]["result"]

            try:
                starts = get(f"/racedays/{key}/starts")
            except (OSError, ValueError, TypeError) as exc:
                rows.append({"race_id": key, "country": country, "category": "RAW_OR_REJECTED", "reason": str(exc)})
                continue
            for meta in meeting.get("pools", []):
                item = {"pool_id": meta["poolKey"], "product": meta["product"], "status": "UNSUPPORTED"}
                if ALIASES.get(meta["product"], meta["product"]) in COLLECTIVE_PRODUCTS:
                    if meta.get("isMultiTrack") or meta.get("isSecondary"):
                        item["status"] = "MULTITRACK_OR_SECONDARY_UNSUPPORTED"
                    else:
                        try:
                            distribution = get(f"/game/{key}/betdistribution/investment/{meta['product']}"
                                               f"?raceNumber={meta['raceNumber']}")
                            pools.append((meta, distribution))
                            item["status"] = "FETCHED"
                        except (OSError, ValueError, TypeError) as exc:
                            item.update(status="FETCH_ERROR", reason=str(exc))
                coverage.append(item)
            shared_sources = list(sources)
            for race in meeting.get("races", []):
                sources = list(shared_sources)
                number = race["raceNumber"]
                row = {"race_id": f"RIKSTOTO:{key}:{number}", "raceday_key": key, "race_number": number,
                       "day": day, "country": country, "country_from_domestic_flag": not bool(meeting.get("countryIsoCode")),
                       "metadata": race, "pool_coverage": coverage, "category": "RAW_OR_REJECTED",
                       "roster": starts.get(str(number), []), "historical_terminal_archive": True,
                       "prospective": False, "executable": False}
                try:
                    win = get(f"/game/{key}/betdistribution/winodds/{number}")
                    try:
                        place = get(f"/game/{key}/betdistribution/placeodds/{number}")
                    except (OSError, ValueError, TypeError) as exc:
                        place = []
                        row["place_fetch_error"] = str(exc)
                    row.update(assess(key, number, row["roster"], win, place,
                                      [(m, r) for m, r in pools if number in m["raceNumbers"]]))
                    for pool in row["collective"]:
                        if pool["status"] == "COMPLETE":
                            active_win = [w for w in win if str(w["startNumber"]) in row["active_field"]]
                            pool["timing_class"] = timing_quality(day, race.get("startTime"), active_win, pool)
                            if row["pWIN"]:
                                pool["signals"] = {n: classify(pool["pCOL"][n], row["pWIN"][n])["signal"]
                                                   for n in row["active_field"]}
                    if row["pWIN"]:
                        row["category"] = "FULL_WIN_AND_COLLECTIVE" if any(
                            p["status"] == "COMPLETE" for p in row["collective"]) else "WIN_ONLY"
                except (OSError, KeyError, ValueError, TypeError, OverflowError) as exc:
                    row["reason"] = str(exc)
                row["sources"] = list(sources)
                rows.append(row)
        unique = {}
        for row in rows:
            rid = row["race_id"]
            if rid not in unique:
                unique[rid] = row
            elif digest(unique[rid]) != digest(row):
                unique[rid] = {"race_id": rid, "category": "RAW_OR_REJECTED",
                               "reason": "CONFLICTING_RACE_RECORDS", "conflicting_hashes": [digest(unique[rid]), digest(row)]}
        rows = list(unique.values())
        locked_json(pre_path, {"stage": "MARKET_ONLY", "config_hash": CONFIG_HASH,
                               "races": rows, "sha256": digest(rows)})
    outcomes, stats, pool_stats, timing_stats = [], Counter(), Counter(), Counter()
    for row in rows:
        stats[row["category"]] += 1
        for pool in row.get("collective", []):
            pool_stats[pool["provider_product"] + ":" + pool["status"]] += 1
            if pool["status"] == "COMPLETE":
                timing_stats[pool.get("timing_class", "UNKNOWN")] += 1
        if not row.get("pWIN") or row.get("metadata", {}).get("progressStatus") != "Finished":
            continue
        outcome = {"race_id": row["race_id"], "status": "RESULT_UNVERIFIED"}
        try:
            record = client.get(f"/results/raceDays/{row['raceday_key']}/{row['race_number']}/completeresults", result=True)
            outcome.update(verify_outcome(row["roster"], row["active_field"], record["body"]["result"]))
            outcome.update(status="VERIFIED_FULL_FIELD", source_sha256=record["body_sha256"])
            stats["verified_results"] += 1
            if row["category"] == "FULL_WIN_AND_COLLECTIVE":
                stats["full_markets_and_verified_results"] += 1
            if not outcome["dead_heat"]:
                winner = outcome["winners"][0]
                outcome["win_log_loss"] = -math.log(row["pWIN"][winner])
                outcome["win_brier"] = sum((p - (n == winner)) ** 2 for n, p in row["pWIN"].items())
        except (OSError, KeyError, ValueError, TypeError) as exc:
            outcome["reason"] = str(exc)
            stats["unverified_results"] += 1
        outcomes.append(outcome)
    summary = {"day": day, "discovered_meetings": len(meetings), "counts": dict(stats),
               "roi": "NOT_ESTABLISHED", "prospective": False,
               "pool_counts": dict(pool_stats), "timing_counts": dict(timing_stats)}
    locked_json(post_path, {"stage": "RESULTS", "pre_sha256": digest(rows), "outcomes": outcomes, "summary": summary})
    return summary


def package_weeks(root):
    root = Path(root)
    weeks = defaultdict(list)
    for path in sorted((root / "market-days").glob("*.json")):
        iso = date.fromisoformat(path.stem).isocalendar()
        weeks[f"{iso.year}-W{iso.week:02d}"].append(path)
    for week, paths in weeks.items():
        target = root / "weekly" / (week + "-MARKET.zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest = {"stage": "MARKET_ONLY", "retrospective": True, "config_hash": CONFIG_HASH,
                    "week": week, "days": [p.stem for p in paths],
                    "files_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in paths}}
        with ZipFile(target, "w", ZIP_DEFLATED) as archive:
            archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
            for path in paths:
                archive.write(path, path.name)
    return len(weeks)


def run(root, first="2015-01", last="2025-12", *, mode="full", client=None):
    root = Path(root)
    if mode not in {"census", "pilot", "full"}:
        raise ValueError("Unknown archive mode")
    root.mkdir(parents=True, exist_ok=True)
    locked_json(root / "config.json", {"first": first, "last": last, "frozen_rules": CONFIG,
                                       "config_hash": CONFIG_HASH, "prospective": False, "pilot_subset": mode == "pilot"})
    client = client or ArchiveClient(root)
    inventory = census(root, first, last, client)
    if mode == "census":
        return {"months": len(inventory), "races": sum(r["races"] for r in inventory)}
    selected, seen_years = [], set()
    for month in inventory:
        record = json.loads((root / "inventory" / (month["month"] + ".json")).read_text(encoding="utf-8"))
        days = defaultdict(list)
        for meeting in record["body"]["result"]:
            day = meeting["raceDayKey"][-10:]
            date.fromisoformat(day)
            days[day].append(meeting)
        for day, meetings in sorted(days.items(), reverse=True):
            if mode == "pilot":
                if day[:4] in seen_years:
                    continue
                seen_years.add(day[:4])
                meetings = sorted(meetings, key=lambda m: m.get("isDomestic") is not True)[:1]
                meetings = [{**m, "races": m["races"][:5]} for m in meetings]
            selected.append((day, meetings))
    reports = []
    for day, meetings in selected:
        reports.append(collect_day(root, day, meetings, client))
        write_json(root / "progress.json", {"status": "RUNNING", "mode": mode, "days_completed": len(reports),
                                             "days_total": len(selected), "last": reports[-1]})
    counts, year_counts, pool_counts, timing_counts = Counter(), defaultdict(Counter), Counter(), Counter()
    for report in reports:
        counts.update(report["counts"])
        year_counts[report["day"][:4]].update(report["counts"])
        pool_counts.update(report.get("pool_counts", {}))
        timing_counts.update(report.get("timing_counts", {}))
    result = {"status": "COLLECTION_COMPLETE", "mode": mode, "days": len(reports), "counts": dict(counts),
              "weekly_archives": package_weeks(root), "historical_not_prospective": True,
              "roi": "NOT_ESTABLISHED", "by_year": {y: dict(c) for y, c in year_counts.items()},
              "pool_counts": dict(pool_counts), "timing_counts": dict(timing_counts), "empty_months": [m["month"] for m in inventory if not m["meetings"]]}
    write_json(root / "FINAL.json", result)
    return result
