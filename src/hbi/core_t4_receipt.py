"""PIT-003A: bounded, original-byte T-4 source receipts; never model/bet authority.

The receipt proves what the collector actually fetched, not source publication.
Independent certification is a separate, fail-closed evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .core_pit_roster_verification import attest_t4_receipt, parse_rikstoto_roster, parse_time
from .core_shadow_pilot import plan_t4_source_receipts
from .providers.rikstoto import FetchResult, RikstotoClient

SCHEMA = "PIT_T4_SOURCE_RECEIPT_V1"
MAX_WAIT_SECONDS = 360
TARGET_BEFORE_T4_SECONDS = 60


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_once(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    if digest(path.read_bytes()) != digest(raw):
        raise OSError("ORIGINAL_RAW_READBACK_HASH_MISMATCH")
    return digest(raw)


def _received(fetch: FetchResult, now: datetime, t4: datetime) -> list[str]:
    problems = []
    completed = fetch.response_completed_at
    if not fetch.success or fetch.status_code != 200:
        problems.append("HTTP_SOURCE_UNAVAILABLE")
    if (not isinstance(getattr(fetch, "raw_body", None), bytes)
            or fetch.response_body_sha256 != digest(fetch.raw_body)):
        problems.append("RAW_BODY_HASH_MISMATCH_OR_MISSING")
    if completed is None or completed.utcoffset() is None:
        problems.append("SOURCE_OBSERVATION_CLOCK_MISSING")
    elif completed > now:
        problems.append("OBSERVATION_AFTER_COLLECTOR_RECEIPT")
    if now >= t4 or (completed is not None and completed >= t4):
        problems.append("RESPONSE_AFTER_T4")
    return problems


def _scratch_set(payload: Any, race_number: int) -> set[str] | None:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None
    mapping = payload.get("result")
    if not isinstance(mapping, dict):
        return None
    rows = mapping.get(str(race_number))
    if not isinstance(rows, list) or not all(type(v) is int and v > 0 for v in rows):
        return None
    if len(rows) != len(set(rows)):
        return None
    return {str(value) for value in rows}


def _schedule_start(payload: Any, race_id: str) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    try:
        races = RikstotoClient().discover_races(
            FetchResult("calendar", payload, True, 200, 0.0)
        )
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    found = [race.start_time for race in races if race.race_id == race_id]
    return found[0].astimezone(UTC) if len(found) == 1 else None


def capture_one(
    target: dict[str, Any], *, client: RikstotoClient, out: Path,
    clock: Callable[[], datetime], sleeper: Callable[[float], None],
    max_wait_seconds: float = MAX_WAIT_SECONDS,
) -> dict[str, Any]:
    """Capture three existing official GETs, strictly before conservative T-4.

    A late invocation writes only a BLOCKED receipt and makes ZERO provider GETs.
    Raw bodies remain immutable and outside the mutable CORE-003 SQLite state.
    """
    race_id = str(target["race_id"])
    t4 = parse_time(target["effective_t4_utc"])
    start = parse_time(target["canonical_start_utc"])
    if t4 is None or start is None:
        raise ValueError("INVALID_RECEIPT_TARGET_CLOCK")
    now = clock().astimezone(UTC)
    item: dict[str, Any] = {
        "schema": SCHEMA, "race_id": race_id,
        "raceday_key": target["raceday_key"], "race_number": target["race_number"],
        "canonical_start_utc": start.isoformat(), "t_minus_4_utc": t4.isoformat(),
        "earliest_source_start_utc": target.get("earliest_source_start_utc"),
        "attempt_started_at_utc": now.isoformat(), "source_published_at_utc": None,
        "sources": {}, "runners": [], "blockers": [], "pit_status": "PIT_NOT_CERTIFIED",
        "bet_authority": False, "research_only": True,
    }
    blockers: set[str] = set()
    delay = (t4 - timedelta(seconds=TARGET_BEFORE_T4_SECONDS) - now).total_seconds()
    if now >= t4:
        blockers.add("MISSED_T4")
    elif delay > max_wait_seconds:
        blockers.add("T4_NOT_YET_IN_CAPTURE_WINDOW")
    else:
        if delay > 0:
            sleeper(delay)
        if clock().astimezone(UTC) >= t4:
            blockers.add("MISSED_T4")
    if blockers:
        item["blockers"] = sorted(blockers)
        item["status"] = "PENDING" if "T4_NOT_YET_IN_CAPTURE_WINDOW" in blockers else "BLOCKED"
        item["receipt_written_at_utc"] = clock().astimezone(UTC).isoformat()
        return item

    # Bound every call by the clock. Failed/partial calls NEVER create a pass.
    for role in ("racedays", "starts", "scratched"):
        if clock().astimezone(UTC) >= t4:
            blockers.add("MISSED_T4")
            break
        request_at = clock().astimezone(UTC)
        try:
            if role == "racedays":
                fetch = client.racedays(retain_raw_body=True)
            elif role == "starts":
                fetch = client.starts(str(target["raceday_key"]), retain_raw_body=True)
            else:
                fetch = client.scratched(str(target["raceday_key"]), retain_raw_body=True)
        except (OSError, ValueError, TypeError, TimeoutError) as exc:
            blockers.add("SOURCE_FETCH_EXCEPTION_" + type(exc).__name__.upper())
            break
        received = clock().astimezone(UTC)
        blockers.update(_received(fetch, received, t4))
        receipt = {
            "source_uri": fetch.url,
            "request_started_at_utc": request_at.isoformat(),
            "source_observed_at_utc": (
                fetch.response_completed_at.isoformat()
                if fetch.response_completed_at is not None else None
            ),
            "collector_received_at_utc": received.isoformat(),
            "source_published_at_utc": None,
            "http_date": fetch.http_date, "etag": fetch.http_etag,
            "last_modified": fetch.http_last_modified, "http_status": fetch.status_code,
            "raw_sha256": fetch.response_body_sha256, "raw_path": None,
        }
        if isinstance(getattr(fetch, "raw_body", None), bytes):
            fname = role + ".raw.json"
            try:
                receipt["raw_sha256"] = write_once(out / fname, fetch.raw_body)
                receipt["raw_path"] = fname
            except (OSError, FileExistsError):
                blockers.add("ORIGINAL_RAW_ARCHIVE_WRITE_FAILED")
        item["sources"][role] = receipt
        if role == "starts":
            roster, error = parse_rikstoto_roster(
                json.dumps(fetch.payload) if isinstance(fetch.payload, dict) else None,
                int(target["race_number"]), str(target["raceday_key"])
            )
            if error:
                blockers.add(error)
            else:
                item["runners"] = [
                    {"start_number": int(k), "horse_name": v["name"],
                     "registration_number": v["reg"], "scratched": v["scratched"]}
                    for k, v in sorted(roster["all"].items(), key=lambda kv: int(kv[0]))
                ]
        if role == "scratched":
            flags = _scratch_set(fetch.payload, int(target["race_number"]))
            if flags is None:
                blockers.add("UNVERIFIED_SCRATCH_SOURCE")
            elif {str(r["start_number"]) for r in item["runners"] if r["scratched"]} != flags:
                blockers.add("SCRATCH_REVISION_CONFLICT")
        if role == "racedays":
            official = _schedule_start(fetch.payload, race_id)
            if official is None:
                blockers.add("INDEPENDENT_START_CLOCK_MISSING")
            elif official != start or official < t4 + timedelta(minutes=4):
                blockers.add("START_CLOCK_CONFLICT")
            else:
                item["source_start_utc"] = official.isoformat()
        if received >= t4:
            blockers.add("RESPONSE_AFTER_T4")
            break
    if set(item["sources"]) != {"racedays", "starts", "scratched"}:
        blockers.add("INCOMPLETE_T4_SOURCE_SET")
    registrations = [r["registration_number"] for r in item["runners"]]
    if not registrations or any(
        not isinstance(reg, str) or not reg.strip()
        or reg.upper().startswith(("TMP", "TEMP", "UNKNOWN"))
        for reg in registrations
    ) or len(registrations) != len(set(registrations)):
        blockers.add("STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED")
    if item["sources"] and not blockers:
        item["status"] = "SOURCE_OBSERVED_BEFORE_T4"
    else:
        item["status"] = "BLOCKED"
    # Even valid receipts cannot prove publication or independent PIT on their own.
    blockers.add("SOURCE_PUBLICATION_UNATTESTED")
    blockers.add("COLLECTOR_ARCHIVE_NOT_CORROBORATED")
    item["blockers"] = sorted(blockers)
    item["receipt_written_at_utc"] = clock().astimezone(UTC).isoformat()
    return item


def run_source_capture(
    db: Path, out: Path, *, client: RikstotoClient | None = None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
    max_wait_seconds: float = MAX_WAIT_SECONDS,
) -> dict[str, Any]:
    clock = clock or (lambda: datetime.now(UTC))
    sleeper = sleeper or time.sleep
    out.mkdir(parents=True, exist_ok=False)
    uri = "file:" + str(db.resolve()) + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        plan = plan_t4_source_receipts(connection, now=clock(), max_races=2)
    finally:
        connection.close()
    provider = client or RikstotoClient()
    records = []
    for index, target in enumerate(plan["eligible"], 1):
        folder = out / f"race-{index:03d}"
        folder.mkdir(exist_ok=False)
        receipt = capture_one(
            target, client=provider, out=folder, clock=clock,
            sleeper=sleeper, max_wait_seconds=max_wait_seconds,
        )
        receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
        write_once(folder / "receipt.json", receipt_bytes)
        records.append({
            "race_id": receipt["race_id"], "status": receipt["status"],
            "blockers": receipt["blockers"],
            "receipt_path": str(folder.relative_to(out) / "receipt.json"),
            "receipt_sha256": digest(receipt_bytes),
        })
    index = {
        "schema": "PIT_T4_CAPTURE_INDEX_V1", "authority": "SOURCE_RESEARCH_ONLY_NO_BET",
        "created_at_utc": clock().astimezone(UTC).isoformat(),
        "plan": plan, "records": records, "bet_authority": False,
    }
    write_once(out / "index.json", (json.dumps(index, indent=2, sort_keys=True) + "\n").encode())
    return index


def run_attestation(receipts: Path, model_reports: Path, out: Path) -> dict[str, Any]:
    """Link frozen model hashes without modifying any previously frozen model."""
    out.mkdir(parents=True, exist_ok=False)
    index = json.loads((receipts / "index.json").read_text())
    models = {}
    if model_reports.is_dir():
        for report_path in model_reports.glob("race-*/shadow.json"):
            raw = report_path.read_bytes()
            value = json.loads(raw)
            race_id = value.get("race", {}).get("race_id")
            if race_id in models:
                models[race_id] = (None, None)
            else:
                models[race_id] = (value, raw)
    results = []
    for row in index["records"]:
        receipt_path = receipts / row["receipt_path"]
        original = receipt_path.read_bytes()
        if digest(original) != row["receipt_sha256"]:
            raise ValueError("RECEIPT_INDEX_HASH_MISMATCH")
        receipt = json.loads(original)
        model, raw = models.get(receipt["race_id"], (None, None))
        result = attest_t4_receipt(
            receipt, receipt_dir=receipt_path.parent,
            model_report=model, model_raw=raw, collector_archive=None,
            provenance_mode="LIVE",
        )
        results.append(result)
    output = {
        "schema": "PIT_T4_ATTESTATION_INDEX_V1", "results": results,
        "pit_certified_count": sum(x["pit_status"] == "INDEPENDENT_PIT_CERTIFIED" for x in results),
        "bet_authority": False,
    }
    write_once(out / "index.json", (json.dumps(output, indent=2, sort_keys=True) + "\n").encode())
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--db", type=Path, required=True)
    capture.add_argument("--out", type=Path, required=True)
    attest = sub.add_parser("attest")
    attest.add_argument("--receipts", type=Path, required=True)
    attest.add_argument("--model-reports", type=Path, required=True)
    attest.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = (
        run_source_capture(args.db, args.out)
        if args.action == "capture" else
        run_attestation(args.receipts, args.model_reports, args.out)
    )
    print(json.dumps({
        "schema": result["schema"], "bet_authority": False,
        "captures": len(result.get("records", [])),
        "certified": result.get("pit_certified_count", 0),
    }))


if __name__ == "__main__":
    main()
