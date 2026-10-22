"""Offline import of existing crawler caches; labels never become PRE features."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from rikstoto_crawler.transport import HOST, digest

from .date_overview import timestamp, write
from .historical_truth import verify_field
from .provider_capability import name_key


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def archive_sources(spec, base):
    path = base / spec["path"]
    raw = path.read_bytes()
    if sha(raw) != spec["sha256"]:
        raise ValueError("BACKFILL_ARCHIVE_SHA256_MISMATCH")
    if spec["format"] == "M4_TRUTH_REGRESSION_ONLY":
        data = json.loads(raw)
        if data["schema"] != "RIKSTOTO_HISTORICAL_TRUTH_V1":
            raise ValueError("UNSUPPORTED_M4_SCHEMA")
        return [(s, {"archive_sha256": sha(raw), "source_index": i})
                for i, s in enumerate(data["sources"])]
    if spec["format"] != "CRAWLER_NATIVE_ZIP":
        raise ValueError("UNSUPPORTED_BACKFILL_FORMAT")
    result = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or any(
            PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names
        ):
            raise ValueError("UNSAFE_BACKFILL_ZIP")
        if sum(i.file_size for i in archive.infolist()) > 2_000_000_000:
            raise ValueError("BACKFILL_ZIP_TOO_LARGE")
        freezes, posts = {}, {}
        for name in sorted(names):
            parts = PurePosixPath(name).parts
            if not name.endswith(".json"):
                continue
            if not {"raw-markets", "raw-results", "inventory", "market-days", "result-days"}.intersection(parts):
                continue
            body = archive.read(name)
            doc = json.loads(body)
            if "market-days" in parts:
                if doc.get("stage") != "MARKET_ONLY" or digest(doc["races"]) != doc["sha256"]:
                    raise ValueError("BACKFILL_PRE_FREEZE_MISMATCH")
                freezes[PurePosixPath(name).name] = doc["sha256"]
            elif "result-days" in parts:
                posts[PurePosixPath(name).name] = doc
            elif "path" in doc and "body" in doc:
                result.append((doc, {"archive_sha256": sha(raw), "member": name, "member_sha256": sha(body)}))
        for day, post in posts.items():
            if post.get("stage") != "RESULTS" or post["pre_sha256"] != freezes.get(day):
                raise ValueError("BACKFILL_POST_PRE_BINDING_MISMATCH")
    if not result:
        raise ValueError("NATIVE_ARCHIVE_RAW_ENVELOPES_MISSING; WEEKLY_MARKET_ONLY_IS_INSUFFICIENT")
    return result


def load_sources(manifest, base):
    versions = defaultdict(dict)
    for spec in manifest["archives"]:
        for source, ref in archive_sources(spec, base):
            path = source["path"]
            # Market cache fields are never candidates for fundamental inputs.
            if not (re.fullmatch(r"/racedays/dates/\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}", path)
                    or re.fullmatch(r"/results/racedays/(\d{4}-\d{2}-\d{2})/\1/list", path)
                    or re.fullmatch(r"/racedays/[A-Z0-9]+_NR_\d{4}-\d{2}-\d{2}/starts", path)
                    or re.fullmatch(r"/results/raceDays/[A-Z0-9]+_NR_\d{4}-\d{2}-\d{2}/\d+/completeresults", path)):
                continue
            if source["url"] != HOST + "/api" + path or source["body_sha256"] != digest(source["body"]):
                raise ValueError("BACKFILL_SOURCE_INTEGRITY_FAILURE")
            timestamp(source["fetched_at"])
            if source["body"].get("success") is not True:
                raise ValueError("BACKFILL_UNSUCCESSFUL_SOURCE")
            variant = versions[path].setdefault(source["body_sha256"], {"source": source, "refs": []})
            if timestamp(source["fetched_at"]) < timestamp(variant["source"]["fetched_at"]):
                variant["source"] = source
            variant["refs"].append({**ref, "url": source["url"], "body_sha256": source["body_sha256"],
                                    "fetched_at": source["fetched_at"], "published_at": None})
    return versions


def meeting_rows(path, source):
    value = source["body"]["result"]
    if path.startswith("/racedays/dates/"):
        first, last = path.split("/")[-2:]
        for m in value:
            key = m["raceDayKey"]
            if not first <= key[-10:] <= last:
                raise ValueError("CENSUS_DATE_OUTSIDE_ARCHIVE_MONTH")
            yield key, m
    elif path.endswith("/list"):
        day = path.split("/")[-2]
        for group in value:
            if group["date"][:10] != day:
                raise ValueError("INVENTORY_DAY_MISMATCH")
            for m in group["raceDays"]:
                if m.get("isMultiTrack") is not True:
                    if m["raceDay"][-10:] != day:
                        raise ValueError("INVENTORY_MEETING_DATE_MISMATCH")
                    yield m["raceDay"], m


def feature(value, source, cutoff):
    observed = source["fetched_at"] if source else None
    proven = value is not None and observed and cutoff and timestamp(observed) < timestamp(cutoff)
    return {"value": value, "status": "PIT_VERIFIED" if proven else "UNRESOLVED",
            "source_observed_at": observed, "published_at": None,
            "source_url": source["url"] if source else None,
            "source_body_sha256": source["body_sha256"] if source else None,
            "availability_basis": "DIRECT_OBSERVATION_UPPER_BOUND" if proven else "NO_PRE_RACE_AVAILABILITY_PROOF"}


def make_record(key, meta, meeting, sources, conflicts):
    number = meta["raceNumber"]
    day = key[-10:]
    date.fromisoformat(day)
    if not re.fullmatch(r"[A-Z0-9]+_NR_\d{4}-\d{2}-\d{2}", key) or type(number) is not int or number <= 0:
        raise ValueError("INVALID_HISTORICAL_RACE_IDENTITY")
    start_path = f"/racedays/{key}/starts"
    result_path = f"/results/raceDays/{key}/{number}/completeresults"
    roster_source = sources.get(start_path)
    result_source = sources.get(result_path)
    rows = roster_source["source"]["body"]["result"].get(str(number), []) if roster_source else []
    result = result_source["source"]["body"]["result"] if result_source else {}
    reasons = []
    if start_path in conflicts or result_path in conflicts:
        reasons.append("CONFLICTING_AUTHORITATIVE_SOURCE_VERSIONS")
    valid, error = verify_field(rows, key, number, result)
    if meeting.get("isMultiTrack") is True:
        valid, error = False, "COMPOSITE_MEETING_NOT_INDEPENDENT"
    elif not rows:
        valid, error = False, "MISSING_HISTORICAL_ROSTER"
    elif any(not name_key(r.get("horseName")) for r in rows):
        valid, error = False, "HISTORICAL_ROSTER_IDENTITY_NAME_MISSING"
    if error:
        reasons.append(error)
    cutoff = None
    try:
        parsed = datetime.fromisoformat(meta["startTime"])
        if parsed.date().isoformat() != day:
            raise ValueError("HISTORICAL_EVENT_CLOCK_UNKNOWN_OR_MIGRATED")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Europe/Oslo"))
        cutoff = parsed.isoformat()
    except (KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc))
    identity_conflict = any(token in str(error) for token in ("IDENTITY", "DUPLICATE"))
    if identity_conflict:
        reasons.append("RESULT_OR_ROSTER_IDENTITY_CONFLICT")
    result_time = result.get("startTime")
    if result_time and not result_time.startswith("0001-") and result_time[:10] != day:
        reasons.append("RESULT_EVENT_DATE_CONFLICT")
    labels_ok = valid and not error and not any("CONFLICT" in r for r in reasons)
    # A retrospectively retrieved label is allowed: no fetched-before-event test here.
    labels = []
    if labels_ok:
        active_numbers = {r["startNumber"] for r in rows if r["isScratched"] is False}
        for r in result["results"]:
            if r["startNumber"] not in active_numbers:
                reasons.append("SCRATCHED_RESULT_ROW_EXCLUDED:" + str(r["startNumber"]))
                continue
            labels.append({"selection_id": str(r["startNumber"]), "registration": r["horseRegistrationNumber"],
                           "placing": r["place"] if type(r["place"]) is int and r["place"] > 0 else None,
                           "place_raw": r["place"], "km_time_raw": r.get("kmTime"), "distance_m_raw": r.get("distance"),
                           "gallop": None, "disqualified": None, "did_not_finish": None,
                           "semantics": "NUMERIC_PLACING" if type(r["place"]) is int and r["place"] > 0 else "UNRESOLVED_CODE",
                           "published_at": None, "fetched_at": result_source["source"]["fetched_at"],
                           "role": "RETROSPECTIVE_LABEL_ONLY", "json_pointer": f"/result/results/{result['results'].index(r)}"})
    roster = [{"selection_id": str(r["startNumber"]), "name": r["horseName"],
               "registration_observed": r.get("horseRegistrationNumber"),
               "identity_status": "IDENTITY_VERIFIED" if valid and not any("CONFLICT" in r for r in reasons) else "UNRESOLVED",
               "scratched": r.get("isScratched"), "features": {
                   "driver": feature(r.get("driverName"), roster_source["source"], cutoff),
                   "extra_distance_m": feature(r.get("extraDistance"), roster_source["source"], cutoff)}} for r in rows]
    refs = [ref for p in (start_path, result_path) for ref in sources.get(p, {}).get("refs", [])]
    return {"race_id": f"RIKSTOTO:{key}:{number}", "raceday_key": key, "date": day, "month": day[:7],
            "race_number": number, "track": meeting.get("raceDayName") or meeting.get("trackCode"),
            "country": meeting.get("countryIsoCode"), "discipline": {"T": "trot", "G": "gallop"}.get(meeting.get("sportType")),
            "event_time": cutoff, "event_time_basis": "PROVIDER_OSLO_CONTRACT_IF_NAIVE",
            "status": "CONFLICT" if any("CONFLICT" in r for r in reasons) else "RESULT_VERIFIED" if labels_ok else "UNRESOLVED",
            "full_field_identity_verified": valid and not any("CONFLICT" in r for r in reasons),
            "authoritative_result_verified": labels_ok, "roster": roster, "labels": labels,
            "source_refs": refs, "reasons": reasons + ["FUNDAMENTAL_FEATURE_CONTRACT_NOT_CONFIGURED"],
            "model_eligible": False, "research_only": True, "imported": False}


def quarantine(row, reason):
    row.update(status="CONFLICT", full_field_identity_verified=False,
               authoritative_result_verified=False, model_eligible=False, labels=[])
    row["reasons"].append(reason)
    for h in row["roster"]:
        h["identity_status"] = "UNRESOLVED"
        for f in h["features"].values():
            f["status"] = "UNRESOLVED"


def market_scope(meeting):
    if meeting.get("countryIsoCode") not in {"NO", "SE"}:
        return False, "OUTSIDE_ACTIVE_COUNTRIES_OR_COUNTRY_UNKNOWN"
    if meeting.get("sportType") != "T":
        return False, "OUTSIDE_TROT_OR_DISCIPLINE_UNKNOWN"
    return True, None


def run_batch(manifest_path, output):
    from .cli import _store, cmd_import_races

    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_bytes())
    if manifest["schema"] != "HBI_BACKFILL_INPUT_V1":
        raise ValueError("UNSUPPORTED_BATCH_MANIFEST")
    versions = load_sources(manifest, manifest_path.parent)
    conflicts = {p for p, variants in versions.items() if len(variants) > 1}
    sources = {p: next(iter(v.values())) for p, v in versions.items() if len(v) == 1}
    records = {}
    excluded_markets = {}
    inventory_items = list(sources.items()) + [(p, v) for p in sorted(conflicts)
        if p.startswith("/racedays/dates/") or p.endswith("/list") for v in versions[p].values()]
    for path, item in sorted(inventory_items, key=lambda pair: pair[0]):
        if not (path.startswith("/racedays/dates/") or path.endswith("/list")):
            continue
        for key, meeting in meeting_rows(path, item["source"]):
            allowed, reason = market_scope(meeting)
            if not allowed:
                exclusion = {"meeting_id": key, "country": meeting.get("countryIsoCode"),
                    "sport_type": meeting.get("sportType"), "reason": reason,
                    "inventory_races": len(meeting.get("races", [])),
                    "roster_source_present": f"/racedays/{key}/starts" in versions,
                    "source_refs": item["refs"]}
                excluded_markets[digest({k: v for k, v in exclusion.items() if k != "source_refs"})] = exclusion
                continue
            for meta in meeting.get("races", []):
                # Inventory-only entries are not imported as collected start fields.
                if f"/racedays/{key}/starts" not in versions:
                    continue
                record = make_record(key, meta, meeting, sources, conflicts)
                record["source_refs"].extend(item["refs"])
                if path in conflicts:
                    quarantine(record, "CONFLICTING_INVENTORY_SOURCE_VERSIONS")
                rid = record["race_id"]
                if rid in records and digest({k: v for k, v in records[rid].items() if k != "source_refs"}) != digest({k: v for k, v in record.items() if k != "source_refs"}):
                    quarantine(records[rid], "CONFLICTING_INVENTORY_RACE_METADATA")
                    records[rid]["source_refs"].extend(record["source_refs"])
                elif rid not in records:
                    records[rid] = record
                else:
                    records[rid]["source_refs"].extend(record["source_refs"])
    rows = sorted(records.values(), key=lambda r: r["race_id"])
    identity_names = defaultdict(set)
    for row in rows:
        for h in row["roster"]:
            registration = h["registration_observed"]
            if registration and not str(registration).upper().startswith("TMP"):
                identity_names[registration].add(name_key(h["name"]))
    identity_conflicts = {key for key, names in identity_names.items() if len(names) > 1}
    for row in rows:
        if any(h["registration_observed"] in identity_conflicts for h in row["roster"]):
            quarantine(row, "CROSS_ARCHIVE_HORSE_IDENTITY_NAME_CONFLICT")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cards = []
    for row in rows:
        missing = [k for k in ("event_time", "track", "country", "discipline") if not row[k]]
        row["reasons"].extend("CANONICAL_IMPORT_MISSING:" + k for k in missing)
        if not row["full_field_identity_verified"]:
            row["reasons"].append("CANONICAL_IMPORT_IDENTITY_NOT_VERIFIED")
        if row["full_field_identity_verified"] and all(row[k] for k in ("event_time", "track", "country", "discipline")):
            row["imported"] = True
            cards.append({"race": {"race_id": row["race_id"], "race_date": row["date"], "country": row["country"],
                "track": row["track"], "race_no": row["race_number"], "start_time_utc": timestamp(row["event_time"]).isoformat(),
                "discipline": row["discipline"], "created_at_utc": min((ref["fetched_at"] for ref in row["source_refs"]), key=timestamp)},
                "runners": [{"race_id": row["race_id"], "selection_id": h["selection_id"], "horse_name": h["name"],
                             "scratched": int(h["scratched"])} for h in row["roster"]]})
    write(output / "canonical-races.json", {"races": cards})
    with (output / "import.log").open("x") as log, redirect_stdout(log):
        cmd_import_races(argparse.Namespace(db=str(output / "research.sqlite"), schema=None, file=output / "canonical-races.json"))
    store = _store(str(output / "research.sqlite"))
    for row in rows:
        if row["imported"]:
            store.insert_provider_payload(
                payload_id=digest({"manifest": sha(manifest_path.read_bytes()), "race": row["race_id"]}),
                provider="RIKSTOTO", category="HISTORICAL_RESEARCH_DATASET",
                provider_raceday_key=row["raceday_key"], race_number=row["race_number"],
                observed_at=max(timestamp(ref["fetched_at"]) for ref in row["source_refs"]),
                source_uri=row["source_refs"][0]["url"], payload=row,
            )
    from .model_dataset import candidate

    for row in rows:
        row["model_candidate"] = candidate(row)
    with (output / "dataset.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    per_month = {}
    for month in sorted({r["month"] for r in rows}):
        selected = [r for r in rows if r["month"] == month]
        per_month[month] = {"races": len(selected), "runners": sum(len(r["roster"]) for r in selected),
            "identity_verified_runners": sum(h["identity_status"] == "IDENTITY_VERIFIED" for r in selected for h in r["roster"]),
            "full_field_identity_verified_races": sum(r["full_field_identity_verified"] for r in selected),
            "imported_races": sum(r["imported"] for r in selected),
            "result_verified_races": sum(r["authoritative_result_verified"] for r in selected),
            "result_label_rows": sum(len(r["labels"]) for r in selected),
            "numeric_placing_labels": sum(l["placing"] is not None for r in selected for l in r["labels"]),
            "excluded_scratched_label_rows": sum(reason.startswith("SCRATCHED_RESULT_ROW_EXCLUDED:") for r in selected for reason in r["reasons"]),
            "feature_pit_verified_runners": sum(all(f["status"] == "PIT_VERIFIED" for f in h["features"].values())
                for r in selected for h in r["roster"]), "model_eligible": 0}
    by_country = {}
    for country in ("NO", "SE"):
        selected = [r for r in rows if r["country"] == country]
        by_country[country] = {"races": len(selected),
            "runners": sum(len(r["roster"]) for r in selected),
            "verified_result_races": sum(r["authoritative_result_verified"] for r in selected),
            "active_raw_labels": sum(len(r["labels"]) for r in selected),
            "feature_pit_verified_runners": sum(all(f["status"] == "PIT_VERIFIED" for f in h["features"].values())
                for r in selected for h in r["roster"]), "model_eligible": 0}
    code = {p.name: sha(p.read_bytes()) for p in (Path(__file__), Path(__file__).with_name("historical_truth.py"),
        Path(__file__).with_name("model_dataset.py"),
        Path(__file__).parents[1] / "rikstoto_crawler/archive.py",
        Path(__file__).parents[1] / "rikstoto_crawler/transport.py")}
    report = {"schema": "HBI_RESEARCH_DATASET_V1", "dataset_id": digest({"manifest": manifest, "code": code}),
        "input_manifest_sha256": sha(manifest_path.read_bytes()), "code_sha256": code, "sources": manifest["archives"],
        "cohort": manifest["cohort"], "per_month": per_month,
        "active_product_scope": {"countries": ["NO", "SE"], "discipline": "trot"},
        "by_country": by_country, "excluded_inventory_meetings": list(excluded_markets.values()), "races": len(rows),
        "imported_races": store.count("races"), "imported_runners": store.count("runners"),
        "provenance_payloads": store.count("provider_payloads"),
        "status_counts": dict(Counter(r["status"] for r in rows)), "conflicting_source_paths": sorted(conflicts),
        "conflicting_sources": {p: list(versions[p].values()) for p in sorted(conflicts)},
        "dataset_sha256": sha((output / "dataset.jsonl").read_bytes()), "model_eligible": 0,
        "collection_completeness": "UNKNOWN; SELECTED_INPUTS_ONLY",
        "terminal_status": "M5_PARTIAL" if rows else "M5_BLOCKED",
        "limitations": [("NO_INDEPENDENTLY_AVAILABLE_2015_ONWARD_MONTHLY_BACKFILL_DEMONSTRATED"
                         if manifest["cohort"] == "M4_REGRESSION_ONLY" or not rows
                         else "SELECTED_ARCHIVES_NOT_A_COLLECTION_COMPLETENESS_CERTIFICATE"),
                        "LABEL_FETCH_TIME_IS_NOT_A_PRE_RACE_FEATURE_AVAILABILITY_CERTIFICATE",
                        "FUNDAMENTAL_FEATURE_CONTRACT_NOT_CONFIGURED"]}
    write(output / "model-readiness.json", report)
    return report


def cli(args):
    try:
        report = run_batch(args.manifest, args.output)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"allowed": False, "error": str(exc)}))
        raise SystemExit(2) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["terminal_status"] == "M5_BLOCKED":
        raise SystemExit(2)
