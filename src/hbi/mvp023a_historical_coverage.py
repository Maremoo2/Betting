"""MVP-023A: offline, source-bound historical race coverage (NO BET).

Scans existing Rikstoto historic inventory, frozen market/result days and original
raw caches; it does not fetch, fit, settle, promote or access a lockbox result
outside the explicitly supplied root. Coverage is always relative to that root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from rikstoto_crawler.archive import verify_outcome
from rikstoto_crawler.transport import HOST, digest

SCHEMA = "MVP023A_HISTORICAL_COVERAGE_V1"
ID_RE = re.compile(r"^RIKSTOTO:([A-Z0-9]+_NR_(\d{4}-\d{2}-\d{2})):(\d+)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CATEGORIES = (
    "DISCOVERED_METADATA_ONLY", "SOURCE_ARCHIVED", "FULL_FIELD_VERIFIED",
    "IDENTITY_VERIFIED", "HISTORY_FEATURES_VERIFIED", "RESULT_VERIFIED",
    "MARKET_COMPLETE", "MARKET_PRE_RACE_VERIFIED", "PIT_MODEL_ELIGIBLE",
    "RETROSPECTIVE_DIAGNOSTIC_ONLY", "BLOCKED_SOURCE", "BLOCKED_IDENTITY",
    "BLOCKED_TIME", "BLOCKED_CONTRACT",
)


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("SYMLINKED_SOURCE_REJECTED")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("INVALID_ARCHIVE_DOCUMENT")
    return doc


def _time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value or value.startswith("0001-"):
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return None
        return instant.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _physical_id(race_id: object) -> tuple[str, str, int] | None:
    match = ID_RE.fullmatch(str(race_id))
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def _original(root: Path, path: str, *, result: bool = False) -> dict | None:
    """Authenticate actual stored provider envelope; missing cache means UNKNOWN."""
    if not isinstance(path, str) or not path.startswith("/") or ".." in path:
        raise ValueError("UNTRUSTED_SOURCE_PATH")
    parent = "raw-results" if result else "raw-markets"
    target = root / parent / (hashlib.sha256(path.encode()).hexdigest() + ".json")
    if not target.exists():
        return None
    record = _read(target)
    if (
        record.get("path") != path
        or record.get("url") != HOST + "/api" + path
        or not isinstance(record.get("body"), dict)
        or record.get("body_sha256") != digest(record["body"])
        or _time(record.get("fetched_at")) is None
    ):
        raise ValueError("ORIGINAL_SOURCE_SHA_OR_ORIGIN_CONFLICT:" + path)
    return record


def _inventory(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for file in sorted((root / "inventory").glob("*.json")):
        doc = _read(file)
        if (
            doc.get("path") != "/racedays/dates/" + file.stem + "-01/"
            + file.stem + "-" + str(_month_last_day(file.stem)).zfill(2)
            or doc.get("url") != HOST + "/api" + doc.get("path", "")
            or not isinstance(doc.get("body"), dict)
            or doc.get("body_sha256") != digest(doc["body"])
            or _time(doc.get("fetched_at")) is None
        ):
            raise ValueError("HISTORICAL_INVENTORY_ORIGIN_OR_SHA_INVALID:" + file.name)
        meetings = doc["body"].get("result")
        if not isinstance(meetings, list):
            raise ValueError("INVALID_INVENTORY_MEETINGS")
        for meeting in meetings:
            key = meeting.get("raceDayKey") if isinstance(meeting, dict) else None
            if not isinstance(key, str) or re.fullmatch(r"[A-Z0-9]+_NR_\d{4}-\d{2}-\d{2}", key) is None:
                raise ValueError("INVALID_INVENTORY_RACEDAY")
            if key[-10:-3] != file.stem:
                raise ValueError("INVENTORY_MONTH_RACE_MISMATCH")
            country = meeting.get("countryIsoCode") or (
                "NO" if meeting.get("isDomestic") is True else "UNKNOWN"
            )
            for race in meeting.get("races", []):
                number = race.get("raceNumber") if isinstance(race, dict) else None
                if type(number) is not int or number < 1:
                    raise ValueError("INVALID_INVENTORY_RACE_NUMBER")
                rid = f"RIKSTOTO:{key}:{number}"
                value = {
                    "race_id": rid, "day": key[-10:], "month": key[-10:-3],
                    "year": int(key[-10:-6]), "country": country,
                    "track": meeting.get("raceDayName") or meeting.get("trackCode") or "UNKNOWN",
                    "start_time_original": race.get("startTime"),
                    "metadata_observed_at_utc": doc["fetched_at"],
                    "metadata_source_sha256": doc["body_sha256"],
                }
                if rid in out and out[rid] != value:
                    # Two different versions must not win on iteration order.
                    out[rid]["metadata_conflict"] = True
                else:
                    out.setdefault(rid, value)
    return out


def _month_last_day(month: str) -> int:
    import calendar

    year, number = month.split("-")
    return calendar.monthrange(int(year), int(number))[1]


def _verified_roster(row: dict, source: dict | None, race_no: int) -> tuple[set[str], bool, bool]:
    """Return exact active numbers, checked field, and stable *provider* ID set."""
    if source is None:
        return set(), False, False
    body = source.get("body", {}).get("result")
    if not isinstance(body, dict):
        return set(), False, False
    original = body.get(str(race_no))
    if not isinstance(original, list) or not original:
        return set(), False, False
    original_numbers: set[str] = set()
    active: set[str] = set()
    registrations: list[str] = []
    for h in original:
        if (
            not isinstance(h, dict)
            or type(h.get("startNumber")) is not int or h["startNumber"] <= 0
            or h.get("raceNumber") != race_no
            or h.get("raceKey") != row.get("raceday_key", "") + "#" + str(race_no)
            or h.get("isScratched") not in (True, False)
            or type(h.get("isScratched")) is not bool
            or not isinstance(h.get("horseName"), str) or not h["horseName"].strip()
        ):
            return set(), False, False
        number = str(h["startNumber"])
        if number in original_numbers:
            return set(), False, False
        original_numbers.add(number)
        if not h["isScratched"]:
            active.add(number)
            registrations.append(str(h.get("horseRegistrationNumber") or ""))
    declared = row.get("active_field")
    if not isinstance(declared, list) or len(declared) != len(active) or set(map(str, declared)) != active:
        return active, False, False
    if not isinstance(row.get("roster"), list) or digest(row["roster"]) != digest(original):
        return active, False, False
    stable = bool(registrations) and len(registrations) == len(set(registrations)) and all(
        registration and not registration.upper().startswith(("TMP", "TEMP", "UNKNOWN"))
        for registration in registrations
    )
    return active, len(active) >= 2, stable


def _normalized_complete(values: object, active: set[str]) -> bool:
    if not isinstance(values, dict) or set(values) != active or not active:
        return False
    return all(
        type(v) in (int, float) and math.isfinite(v) and 0 < v <= 1
        for v in values.values()
    ) and abs(sum(values.values()) - 1) < 1e-6


def _assess(
    root: Path, item: dict, market_row: dict | None, outcome: dict | None,
    *, freeze_verified: bool, result_binding_verified: bool,
) -> dict:
    rid = item["race_id"]
    key, _, number = _physical_id(rid)
    row = market_row or {}
    reasons: list[str] = []
    start = _time(item.get("start_time_original"))
    if start is None or start.astimezone(ZoneInfo("Europe/Oslo")).date().isoformat() != item["day"]:
        reasons.append("SOURCE_START_CLOCK_MISSING_SENTINEL_OR_UNVERIFIED")
        start = None
    if item.get("metadata_conflict") or (row and row.get("race_id") != rid):
        reasons.append("SOURCE_RACE_METADATA_CONFLICT")
    refs = row.get("sources")
    receipts = {}
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
                reasons.append("SOURCE_RECEIPT_MALFORMED")
                continue
            original = _original(root, ref["path"])
            if original is None:
                reasons.append("SOURCE_RAW_ORIGINAL_MISSING")
                continue
            if any(original.get(k) != ref.get(k) for k in ("path", "url", "body_sha256", "fetched_at")):
                raise ValueError("FROZEN_SOURCE_RECEIPT_CONFLICT:" + rid)
            if ref["path"] in receipts and receipts[ref["path"]] != original["body_sha256"]:
                raise ValueError("CONFLICTING_ORIGINAL_SOURCE_RECEIPTS:" + rid)
            receipts[ref["path"]] = original["body_sha256"]
    starts = _original(root, f"/racedays/{key}/starts")
    if starts is not None and f"/racedays/{key}/starts" not in receipts:
        starts = None  # An unbound cache is not an authenticated archived freeze input.
    active, field, provider_ids_stable = _verified_roster(row, starts, number)
    win_path = f"/game/{key}/betdistribution/winodds/{number}"
    win = _original(root, win_path) if win_path in receipts else None
    win_rows = win.get("body", {}).get("result") if win else None
    win_ids = {str(h["startNumber"]) for h in win_rows if isinstance(h, dict)
               and type(h.get("startNumber")) is int} if isinstance(win_rows, list) else set()
    win_odds_valid = bool(
        isinstance(win_rows, list) and len(win_rows) == len(active)
        and all(
            isinstance(h, dict) and type(h.get("odds")) in (int, float)
            and math.isfinite(h["odds"]) and h["odds"] > 1
            for h in win_rows
        )
    )
    implied = (
        {str(h["startNumber"]): 1 / h["odds"] for h in win_rows}
        if win_odds_valid else {}
    )
    implied_total = sum(implied.values())
    repriced = (
        bool(implied and implied_total > 0 and isinstance(row.get("pWIN"), dict))
        and all(
            type(row["pWIN"].get(n)) in (int, float)
            and math.isfinite(row["pWIN"][n])
            and abs(row["pWIN"][n] - v / implied_total) < 1e-6
            for n, v in implied.items()
        )
    )
    market_complete = bool(
        field and win is not None and win_odds_valid
        and win_ids == active and _normalized_complete(row.get("pWIN"), active)
        and repriced
    )
    collective_complete = any(
        p.get("status") == "COMPLETE" and _normalized_complete(p.get("pCOL"), active)
        for p in (row.get("collective") or []) if isinstance(p, dict)
    )
    cutoff = start - timedelta(minutes=4) if start else None
    win_observed = _time(win.get("fetched_at")) if win else None
    starts_observed = _time(starts.get("fetched_at")) if starts else None
    win_updates = [_time(h.get("lastUpdated")) for h in win_rows] if isinstance(win_rows, list) else []
    market_pre_race = bool(
        market_complete and cutoff and win_observed and starts_observed
        and win_observed < cutoff and starts_observed < cutoff
        and win_updates and all(t is not None and t <= win_observed and t < cutoff for t in win_updates)
    )
    verified_result = False
    if outcome and result_binding_verified and outcome.get("status") == "VERIFIED_FULL_FIELD" and field:
        result_path = f"/results/raceDays/{key}/{number}/completeresults"
        original = _original(root, result_path, result=True)
        if original and original["body_sha256"] == outcome.get("source_sha256"):
            try:
                verified = verify_outcome(
                    row["roster"], sorted(active), original["body"]["result"],
                )
            except (KeyError, TypeError, ValueError):
                pass
            else:
                verified_result = verified["winners"] == outcome.get("winners") and (
                    verified["dead_heat"] == outcome.get("dead_heat")
                )
    # An ID inside one provider's original is NOT independent cross-provider verification.
    identity_verified = False
    history_verified = False  # Archive contains no accredited PIT feature source/clock contract.
    pit_eligible = False  # No qualifying pre-decision independent fundamentals/identity.
    source_archived = bool(freeze_verified and starts and refs and len(receipts) == len(refs))
    blocked_source = not source_archived or not freeze_verified
    blocked_identity = not identity_verified
    blocked_time = not market_pre_race or start is None
    blocked_contract = bool(item.get("metadata_conflict") or "SOURCE_RACE_METADATA_CONFLICT" in reasons)
    if not provider_ids_stable and field:
        reasons.append("TMP_OR_UNSTABLE_PROVIDER_REGISTRATION")
    if not identity_verified:
        reasons.append("INDEPENDENT_HORSE_IDENTITY_NOT_ATTESTED")
    if not history_verified:
        reasons.append("HISTORICAL_PIT_FEATURE_SOURCES_UNVERIFIED")
    if not source_archived:
        reasons.append("RAW_ORIGINAL_CHAIN_INCOMPLETE")
    if not field:
        reasons.append("ACTIVE_FIELD_OR_SCRATCH_MISMATCH")
    if not market_complete:
        reasons.append("COMPLETE_ORIGINAL_WIN_MARKET_MISSING")
    if not market_pre_race:
        reasons.append("PRE_T4_MARKET_OR_PUBLICATION_UNVERIFIED")
    if not verified_result:
        reasons.append("OFFICIAL_COMPLETE_RESULT_NOT_VERIFIED")
    if not result_binding_verified and outcome:
        reasons.append("RESULT_DAY_PRE_FREEZE_BINDING_INVALID")
    if not outcome:
        reasons.append("NO_ARCHIVED_RESULT")
    flags = {
        "DISCOVERED_METADATA_ONLY": not bool(market_row),
        "SOURCE_ARCHIVED": source_archived,
        "FULL_FIELD_VERIFIED": field,
        "IDENTITY_VERIFIED": identity_verified,
        "HISTORY_FEATURES_VERIFIED": history_verified,
        "RESULT_VERIFIED": verified_result,
        "MARKET_COMPLETE": market_complete,
        "MARKET_PRE_RACE_VERIFIED": market_pre_race,
        "PIT_MODEL_ELIGIBLE": pit_eligible,
        "RETROSPECTIVE_DIAGNOSTIC_ONLY": bool(market_row and not pit_eligible),
        "BLOCKED_SOURCE": blocked_source,
        "BLOCKED_IDENTITY": blocked_identity,
        "BLOCKED_TIME": blocked_time,
        "BLOCKED_CONTRACT": blocked_contract,
    }
    priority = (
        "SOURCE_RACE_METADATA_CONFLICT", "RAW_ORIGINAL_CHAIN_INCOMPLETE",
        "ACTIVE_FIELD_OR_SCRATCH_MISMATCH", "INDEPENDENT_HORSE_IDENTITY_NOT_ATTESTED",
        "HISTORICAL_PIT_FEATURE_SOURCES_UNVERIFIED", "PRE_T4_MARKET_OR_PUBLICATION_UNVERIFIED",
        "OFFICIAL_COMPLETE_RESULT_NOT_VERIFIED",
    )
    reason = next((r for r in priority if r in reasons), reasons[0] if reasons else None)
    return {
        **{k: item[k] for k in ("race_id", "day", "month", "year", "country", "track")},
        "start_time_original": item.get("start_time_original"),
        "start_time_verified_utc": start.isoformat() if start else None,
        "cutoff_t4_utc": cutoff.isoformat() if cutoff else None,
        "active_runners": len(active) if field else None,
        "provider_registrations_stable": provider_ids_stable,
        "collective_complete_retrospective": collective_complete,
        "categories": flags, "primary_blocker": reason,
        "blockers": sorted(set(reasons)),
        "source_receipt_sha256": dict(sorted(receipts.items())),
        "market_original_sha256": win["body_sha256"] if win else None,
        "official_result_sha256": outcome.get("source_sha256") if verified_result else None,
        "result_role": "RETROSPECTIVE_LABEL_ONLY" if verified_result else "UNVERIFIED",
        "historical_feature_status": "MISSING",
        "bet_authority": False,
    }



def _weekly_market_days(root: Path) -> tuple[dict[str, dict], int]:
    """Verify existing MARKET_ONLY weekly ZIP manifests without extracting files."""
    days: dict[str, dict] = {}
    count = 0
    for zip_path in sorted((root / "weekly").glob("*-MARKET.zip")):
        if zip_path.is_symlink():
            raise ValueError("SYMLINKED_WEEKLY_ARCHIVE_REJECTED")
        with ZipFile(zip_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "MANIFEST.json" not in names:
                raise ValueError("WEEKLY_ARCHIVE_MEMBERS_INVALID")
            if any(name.startswith("/") or "/" in name or "\\" in name or ".." in name for name in names):
                raise ValueError("WEEKLY_ARCHIVE_MEMBER_PATH_INVALID")
            if sum(item.file_size for item in archive.infolist()) > 500_000_000:
                raise ValueError("WEEKLY_ARCHIVE_TOO_LARGE")
            manifest = json.loads(archive.read("MANIFEST.json"))
            checks = manifest.get("files_sha256")
            expected = {day + ".json" for day in manifest.get("days", [])}
            if (
                manifest.get("stage") != "MARKET_ONLY"
                or manifest.get("retrospective") is not True
                or not isinstance(checks, dict) or set(checks) != expected
                or set(names) != expected | {"MANIFEST.json"}
                or not isinstance(manifest.get("week"), str)
                or not zip_path.stem.startswith(manifest["week"] + "-")
            ):
                raise ValueError("WEEKLY_ARCHIVE_MANIFEST_INVALID")
            for name in sorted(expected):
                raw = archive.read(name)
                if hashlib.sha256(raw).hexdigest() != checks[name]:
                    raise ValueError("WEEKLY_MARKET_MEMBER_SHA_MISMATCH:" + name)
                doc = json.loads(raw)
                if (
                    doc.get("stage") != "MARKET_ONLY"
                    or not isinstance(doc.get("races"), list)
                    or doc.get("sha256") != digest(doc["races"])
                ):
                    raise ValueError("WEEKLY_MARKET_DAY_FREEZE_INVALID:" + name)
                day = name.removesuffix(".json")
                if day in days and digest(days[day]) != digest(doc):
                    raise ValueError("CONFLICTING_WEEKLY_MARKET_DAY:" + day)
                days[day] = doc
        count += 1
    return days, count


def build_coverage(root: Path) -> dict:
    """Build from a supplied UNPACKED native archive root; never touch network."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError("HISTORICAL_ARCHIVE_ROOT_NOT_FOUND")
    metadata = _inventory(root)
    market_days, weekly_count = _weekly_market_days(root)
    for path in sorted((root / "market-days").glob("*.json")):
        doc = _read(path)
        if doc.get("stage") != "MARKET_ONLY" or not isinstance(doc.get("races"), list) or doc.get("sha256") != digest(doc["races"]):
            raise ValueError("MARKET_DAY_FREEZE_SHA_INVALID:" + path.name)
        if path.stem in market_days and digest(market_days[path.stem]) != digest(doc):
            raise ValueError("WEEKLY_DAILY_FREEZE_CONFLICT:" + path.stem)
        market_days[path.stem] = doc
        for row in doc["races"]:
            rid = row.get("race_id") if isinstance(row, dict) else None
            parsed = _physical_id(rid)
            if parsed is None:
                raise ValueError("UNVERIFIED_PHYSICAL_RACE_ID")
            key, day, number = parsed
            if day != path.stem:
                raise ValueError("MARKET_DAY_RACE_DATE_CONFLICT")
            metadata.setdefault(rid, {
                "race_id": rid, "day": day, "month": day[:7],
                "year": int(day[:4]), "country": row.get("country") or "UNKNOWN",
                "track": "UNKNOWN", "start_time_original": (row.get("metadata") or {}).get("startTime"),
            })
    # Weekly-only input is a valid derived freeze, but without original raw
    # envelopes it remains source-blocked. Do not make weekly rows invisible.
    for day, document in sorted(market_days.items()):
        for row in document["races"]:
            parsed = _physical_id(row.get("race_id") if isinstance(row, dict) else None)
            if parsed is None or parsed[1] != day:
                raise ValueError("WEEKLY_PHYSICAL_RACE_ID_INVALID")
            rid = row["race_id"]
            metadata.setdefault(rid, {
                "race_id": rid, "day": day, "month": day[:7],
                "year": int(day[:4]), "country": row.get("country") or "UNKNOWN",
                "track": "UNKNOWN", "start_time_original": (row.get("metadata") or {}).get("startTime"),
            })
    results = {}
    for path in sorted((root / "result-days").glob("*.json")):
        doc = _read(path)
        pre = market_days.get(path.stem)
        if doc.get("stage") != "RESULTS" or not isinstance(doc.get("outcomes"), list):
            raise ValueError("RESULT_DAY_SCHEMA_INVALID:" + path.name)
        bound = bool(pre and doc.get("pre_sha256") == pre.get("sha256"))
        if pre and not bound:
            raise ValueError("RESULT_DAY_FROZEN_MARKET_SHA_MISMATCH:" + path.name)
        outcomes = {}
        for outcome in doc["outcomes"]:
            rid = outcome.get("race_id") if isinstance(outcome, dict) else None
            if rid in outcomes:
                raise ValueError("DUPLICATE_OFFICIAL_RESULT:" + str(rid))
            outcomes[rid] = outcome
        results[path.stem] = (outcomes, bound)
    rows = []
    for rid in sorted(metadata):
        item = metadata[rid]
        day = item["day"]
        document = market_days.get(day)
        matches = [r for r in document["races"] if r.get("race_id") == rid] if document else []
        if len(matches) > 1:
            raise ValueError("DUPLICATE_PHYSICAL_RACE_FREEZE:" + rid)
        outcome, bound = results.get(day, ({}, False))
        rows.append(_assess(
            root, item, matches[0] if matches else None, outcome.get(rid),
            freeze_verified=bool(document), result_binding_verified=bound,
        ))
    counters: dict[str, dict[str, Counter]] = {
        dimension: defaultdict(Counter)
        for dimension in ("by_year", "by_month", "by_country", "by_track")
    }
    totals = Counter()
    blockers = Counter()
    for row in rows:
        for label, key in (("by_year", str(row["year"])), ("by_month", row["month"]),
                           ("by_country", row["country"]), ("by_track", row["track"])):
            counters[label][key]["physical_races"] += 1
            for category, enabled in row["categories"].items():
                counters[label][key][category] += int(enabled)
        totals["physical_races"] += 1
        for category, enabled in row["categories"].items():
            totals[category] += int(enabled)
        if row["primary_blocker"]:
            blockers[row["primary_blocker"]] += 1
    return {
        "schema": SCHEMA, "research_only": True, "bet_authority": False,
        "historical_not_prospective": True, "production_betting_ready": False,
        "training_performed": False, "fitting_authorized": False,
        "year_scope": "2015-2026; only supplied source files inspected",
        "source_root": str(root),
        "source_file_count": {
            "inventories": len(list((root / "inventory").glob("*.json"))),
            "market_days": len(market_days), "result_days": len(results),
            "weekly_market_archives": weekly_count,
        },
        "counts": dict(totals), "primary_blockers": dict(sorted(blockers.items())),
        **{label: {
            key: {**dict(count), "coverage_denominator": count["physical_races"]}
            for key, count in sorted(group.items())
        } for label, group in counters.items()},
        "by_race": rows,
        "data_sha256": digest(rows),
        "readiness": {
            "fundamental_training": "BLOCKED_SOURCE",
            "benter_combination_fit": "BLOCKED_SOURCE",
            "economic_ev": "BLOCKED_TIME",
            "pit_model_eligible": 0,
            "eligible_race_count_verified": totals["PIT_MODEL_ELIGIBLE"],
            "lockbox_2025_accessed_for_tuning": False,
        },
        "limits": [
            "Count applies only to source files under supplied root, not all 202946 discovery entries.",
            "A historic fetch date is not a past publication timestamp.",
            "Stable provider IDs do not attest independent cross-provider horse identity.",
            "No past-start PIT feature contract exists in old market-day archive.",
            "No historic terminal price is asserted executable or pre-race.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_coverage(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: no silent replacement of prior research output.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
