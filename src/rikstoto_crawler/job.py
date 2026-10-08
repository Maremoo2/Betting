"""Resumable market crawl, immutable PRE freeze, then an explicit POST stage."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .extract import PRODUCTS, extract_race, keyed
from .transport import ArchiveClient, digest, write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def horse_name(value):
    """Presentation suffixes only, alongside mandatory identical provider horse ID."""
    value = unicodedata.normalize("NFKC", value).replace("*", "").strip()
    value = re.sub(r"\s*\((?:S|SE|NO|DK|FR|FI|DE|IT|NL|US|GB|IE|BE|CA|AU|NZ)\)\s*$", "", value)
    return " ".join(value.casefold().split())


def freeze(root, rows):
    pre = root / "pre.jsonl"
    body = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
                   for r in sorted(rows, key=lambda r: r["race_id"]))
    if pre.exists():
        if pre.read_text(encoding="utf-8") != body:
            raise ValueError("immutable PRE freeze already exists with different content")
        if (root / "freeze.json").exists():
            return read(root / "freeze.json")
    else:
        with pre.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(body)
    manifest = {"frozen_at": datetime.now(UTC).isoformat(), "races": len(rows),
                "pre_sha256": digest(rows), "file_sha256": file_hash(pre),
                "prospective": False, "outcomes_in_pre": False}
    write_json(root / "freeze.json", manifest)
    return manifest


def file_hash(path):
    from hashlib import sha256

    return sha256(Path(path).read_bytes()).hexdigest()


def _rows(envelope):
    value = envelope["body"]["result"]
    if not isinstance(value, list):
        raise TypeError("expected list provider schema")
    return value


def market_stability_digest(record):
    """Only identity-keyed market lists are unordered; retain every field/value."""
    from copy import deepcopy

    body = deepcopy(record["body"])
    result = body["result"]
    if not isinstance(result, list):
        raise TypeError("unsupported stability market schema")
    if result and all("startNumber" in r for r in result):
        by_number = keyed(result)
        body["result"] = [by_number[n] for n in sorted(by_number, key=int)]
    elif result:
        identities = [(r["raceKey"], r["raceNumber"]) for r in result]
        if len(set(identities)) != len(identities):
            raise ValueError("ambiguous stability race identity")
        for race in result:
            by_number = keyed(race["investmentDistribution"])
            race["investmentDistribution"] = [by_number[n] for n in sorted(by_number, key=int)]
        body["result"] = sorted(result, key=lambda r: (r["raceKey"], r["raceNumber"]))
    return digest(body)


def crawl(root, days, *, countries=("NO", "SE", "FR"), max_races_per_meeting=0,
          client=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    config = {"days": sorted(set(days)), "countries": sorted(set(countries)),
              "max_races_per_meeting": max_races_per_meeting}
    config_path = root / "config.json"
    if config_path.exists() and read(config_path) != config:
        raise ValueError("resume configuration changed; use a new output directory")
    if (root / "quality.json").exists() and (root / "freeze.json").exists():
        frozen = read(root / "freeze.json")
        if file_hash(root / "pre.jsonl") != frozen["file_sha256"]:
            raise ValueError("PRE freeze integrity mismatch")
        return read(root / "quality.json")
    write_json(config_path, config)
    client = client or ArchiveClient(root)
    checkpoint_path = root / "checkpoint.json"
    checkpoint = read(checkpoint_path) if checkpoint_path.exists() else {
        "done": [], "rejected": {}, "fetch_errors": {}, "unsupported_pools": {},
        "stability": {}, "observed_days": []}
    done = set(checkpoint["done"])
    def checkpoint_now():
        checkpoint["done"] = sorted(done)
        write_json(checkpoint_path, checkpoint)
    for day in config["days"]:
        if date.fromisoformat(day) >= datetime.now(UTC).date():
            raise ValueError("historical dates only")
        try:
            discovery = client.get(f"/results/racedays/{day}/{day}/list")
        except (OSError, ValueError, TypeError) as exc:
            checkpoint["fetch_errors"][day] = str(exc)
            checkpoint_now()
            continue
        checkpoint["fetch_errors"].pop(day, None)
        meetings = [meeting for group in _rows(discovery) for meeting in group["raceDays"]
                    if meeting["countryIsoCode"] in config["countries"]]
        checkpoint["observed_days"] = sorted(set(checkpoint["observed_days"]) | {day})
        for meeting in meetings:
            key = meeting["raceDay"]
            candidate_races = [r for r in meeting["races"] if any(
                p["product"] in PRODUCTS and r["raceNumber"] in p["raceNumbers"]
                for p in meeting["pools"])]
            if max_races_per_meeting:
                candidate_races = candidate_races[:max_races_per_meeting]
            if not candidate_races:
                continue
            try:
                starts = client.get(f"/racedays/{key}/starts")
                info = client.get(f"/racedays/{key}/raceInfo")
                scratches = client.get(f"/results/raceDays/{key}/scratchedStarts")
                totals = client.get(f"/results/raceDays/{key}/totalInvestment")
            except (OSError, ValueError, TypeError) as exc:
                checkpoint["fetch_errors"][key] = str(exc)
                checkpoint_now()
                continue
            checkpoint["fetch_errors"].pop(key, None)
            pool_data, pool_sources = {}, {}
            for pool in meeting["pools"]:
                if pool["product"] not in PRODUCTS:
                    continue
                if pool.get("isMultiTrack") or pool.get("isSecondary"):
                    checkpoint["unsupported_pools"][pool["poolKey"]] = "MULTITRACK_OR_SECONDARY"
                    continue
                try:
                    path = (f"/game/{key}/betdistribution/investment/{pool['product']}"
                            f"?raceNumber={pool['raceNumber']}")
                    record = client.get(path)
                    pool_data[pool["poolKey"]] = record
                    pool_sources[pool["poolKey"]] = pool
                    checkpoint["fetch_errors"].pop(pool["poolKey"], None)
                except (OSError, ValueError, TypeError) as exc:
                    checkpoint["fetch_errors"][pool["poolKey"]] = str(exc)
            for race in candidate_races:
                n = race["raceNumber"]
                race_id = f"RIKSTOTO:{key}:{n}"
                if race_id in done:
                    continue
                try:
                    win = client.get(f"/game/{key}/betdistribution/winodds/{n}")
                    place = client.get(f"/game/{key}/betdistribution/placeodds/{n}")
                    per_race = {}
                    used_sources = []
                    for pk, record in pool_data.items():
                        matches = [r for r in _rows(record) if r["raceNumber"] == n]
                        if len(matches) == 1 and n in pool_sources[pk]["raceNumbers"]:
                            meta = pool_sources[pk]
                            per_race[pk] = {**matches[0], "product": meta["product"],
                                            "leg": meta["raceNumbers"].index(n) + 1,
                                            "pool_start_race": meta["raceNumber"],
                                            "pool_race_numbers": meta["raceNumbers"],
                                            "source": {k: record[k] for k in
                                                       ("url", "path", "fetched_at", "body_sha256")}}
                            used_sources.append(record)
                    matching_info = [r for r in _rows(info) if r["raceNumber"] == n]
                    if len(matching_info) != 1:
                        raise ValueError("missing/ambiguous race info")
                    row = extract_race(meeting, race, starts["body"]["result"][str(n)],
                                       matching_info[0], scratches["body"]["result"],
                                       _rows(win), _rows(place), per_race, _rows(totals))
                    # A second retrieval of the first accepted race in each meeting
                    # establishes archive stability, not real-time availability.
                    if key not in checkpoint["stability"]:
                        stability_sources = [win, place, *used_sources]
                        repeated = [client.get(s["path"], refresh=True) for s in stability_sources]
                        stable = all(market_stability_digest(a) == market_stability_digest(b)
                                     for a, b in zip(stability_sources, repeated, strict=True))
                        checkpoint["stability"][key] = {
                            "stable": stable, "country": meeting["countryIsoCode"],
                            "comparison": "ALL_VALUES_WITH_IDENTITY_KEYED_LIST_ORDER_NORMALIZED",
                            "race_id": race_id, "paths": [s["path"] for s in stability_sources],
                            "checked_at": datetime.now(UTC).isoformat()}
                    if not checkpoint["stability"][key]["stable"]:
                        raise ValueError("historical terminal archive changed during verification")
                    row["sources"] = [{k: s[k] for k in ("url", "path", "fetched_at", "body_sha256")}
                                      for s in [discovery, starts, info, scratches, totals,
                                                win, place, *used_sources]]
                    row["archive_stability_verified"] = True
                    filename = digest(race_id) + ".json"
                    write_json(root / "pre-rows" / filename, row)
                    done.add(race_id)
                    checkpoint["rejected"].pop(race_id, None)
                except (KeyError, TypeError, ValueError, OSError) as exc:
                    checkpoint["rejected"][race_id] = str(exc)
                checkpoint_now()
                print(f"PRE {day} accepted={len(done)} rejected={len(checkpoint['rejected'])}",
                      flush=True)
        checkpoint_now()
    rows = [read(p) for p in sorted((root / "pre-rows").glob("*.json"))]
    manifest = freeze(root, rows)
    per_country = Counter(r["country"] for r in rows)
    report = {"schema_version": "RIKSTOTO_CRAWLER_QUALITY_V1", "config": config,
              "freeze": manifest, "accepted": len(rows), "by_country": dict(per_country),
              "rejected": checkpoint["rejected"], "fetch_errors": checkpoint["fetch_errors"],
              "unsupported_pools": checkpoint["unsupported_pools"],
              "stability": checkpoint["stability"],
              "observed_days": checkpoint["observed_days"],
              "contemporaneous_races": sum(any(p["contemporaneous"] for p in r["collective"].values())
                                            for r in rows),
              "requests_this_invocation": client.requests, "prospective": False,
              "protocol_m0_m6": "UNAVAILABLE", "production_database_written": False}
    write_json(root / "quality.json", report)
    return report


def validate_sample(report):
    """Frozen pre-outcome expansion gate. Never learn thresholds from winners."""
    attempted = report["accepted"] + len(report["rejected"])
    reasons = []
    if len(report["config"]["days"]) < 5:
        reasons.append("FIVE_HISTORICAL_DAYS_REQUIRED")
    if report["accepted"] < 10:
        reasons.append("TEN_COMPLETE_RACES_REQUIRED")
    if not attempted or report["accepted"] / attempted < .8:
        reasons.append("COMPLETE_FIELD_RATE_BELOW_80_PERCENT")
    if report["fetch_errors"]:
        reasons.append("UNRESOLVED_FETCH_ERRORS")
    for country in ("NO", "SE"):
        if report["by_country"].get(country, 0) < 2:
            reasons.append(f"TWO_COMPLETE_{country}_RACES_REQUIRED")
    if not report["stability"] or any(not s["stable"] for s in report["stability"].values()):
        reasons.append("TERMINAL_ARCHIVE_STABILITY_NOT_VERIFIED")
    if len(report.get("observed_days", report["config"]["days"])) < 5:
        reasons.append("FIVE_OBSERVED_DAYS_REQUIRED")
    return {"allowed": not reasons, "reasons": reasons,
            "purpose": "HISTORICAL_ARCHIVE_EXPANSION_ONLY", "prospective": False}


def january(root, sample_root, *, client=None):
    sample_root = Path(sample_root)
    quality = read(sample_root / "quality.json")
    manifest = read(sample_root / "freeze.json")
    if file_hash(sample_root / "pre.jsonl") != manifest["file_sha256"]:
        raise ValueError("sample PRE integrity mismatch")
    rows = [json.loads(line) for line in (sample_root / "pre.jsonl").read_text(
        encoding="utf-8").splitlines()]
    if quality["accepted"] != len(rows) or quality["by_country"] != dict(
        Counter(row["country"] for row in rows)
    ):
        raise ValueError("sample quality counts do not match frozen PRE")
    gate = validate_sample(quality)
    if not gate["allowed"]:
        raise ValueError("JANUARY_BLOCKED:" + "|".join(gate["reasons"]))
    days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(31)]
    return crawl(root, days, countries=quality["config"]["countries"], client=client)


def post(root, *, client=None):
    root = Path(root)
    manifest = read(root / "freeze.json")
    if file_hash(root / "pre.jsonl") != manifest["file_sha256"]:
        raise ValueError("PRE freeze integrity mismatch")
    rows = [json.loads(line) for line in (root / "pre.jsonl").read_text(encoding="utf-8").splitlines()]
    client = client or ArchiveClient(root)
    joined, rejected = [], {}
    for row in rows:
        try:
            record = client.get(f"/results/raceDays/{row['raceday_key']}/{row['race_number']}"
                                "/completeresults", result=True)
            result = record["body"]["result"]
            if result.get("isComplete") is not True:
                raise ValueError("OFFICIAL_RESULT_INCOMPLETE")
            results = keyed(result["results"])
            if not set(row["active_field"]) <= set(results):
                raise ValueError("OFFICIAL_RESULT_FIELD_INCOMPLETE")
            outcomes = {}
            pre_names = Counter(horse_name(row["runners"][n]["horse_name"])
                                for n in row["active_field"])
            result_names = Counter(horse_name(results[n].get("horseName", ""))
                                   for n in row["active_field"])
            for n in row["active_field"]:
                actual = results[n]
                expected = row["runners"][n]
                name = horse_name(expected["horse_name"])
                same_id = actual.get("horseRegistrationNumber") == expected["horse_id"]
                race_local = (not expected["horse_id_stable"]
                              and not actual.get("horseRegistrationNumber")
                              and pre_names[name] == result_names[name] == 1)
                if (not (same_id or race_local)
                        or horse_name(actual.get("horseName", "")) != name):
                    raise ValueError("RESULT_IDENTITY_MISMATCH")
                outcomes[n] = {"place": actual["place"], "km_time": actual.get("kmTime"),
                               "identity_method": "EXACT_PROVIDER_ID_AND_NAME" if same_id
                               else "RACE_START_NUMBER_UNIQUE_NAME",
                               "stable_identity_verified": same_id and expected["horse_id_stable"]}
            if not any(v["place"] == 1 for v in outcomes.values()):
                raise ValueError("NO_OFFICIAL_WINNER")
            joined.append({"race_id": row["race_id"], "pre_file_sha256": manifest["file_sha256"],
                           "outcomes": outcomes, "source_url": record["url"],
                           "fetched_at": record["fetched_at"], "retrospective": True})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            rejected[row["race_id"]] = str(exc)
    if file_hash(root / "pre.jsonl") != manifest["file_sha256"]:
        raise ValueError("PRE changed during POST")
    write_json(root / "post-results.json", {"rows": joined, "rejected": rejected,
                                           "pre_freeze": manifest, "retrospective": True})
    return {"joined": len(joined), "rejected": len(rejected), "pre_unchanged": True}
