"""CLOUD-RUN-002: ingest verified Collector NO/SE program snapshots into existing HBI.

Research-only. Reuses Collector's already parsed structured_program and the original
starts/PDF receipt verifier in collector_handoff. No live odds, model or bet promotion.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .cloud_run001_archive import audit_release
from .collector_handoff import OriginalArchive, name_key
from .ingestion import RaceCard
from .storage import SQLiteStore

SCHEMA = "CLOUD_RUN002_COLLECTOR_SOURCE_V1"
CATEGORY = "COLLECTOR_ARCHIVED_PROGRAM_V1"
COUNTRIES = {"NO", "SE"}
HHMM = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")
OSLO = ZoneInfo("Europe/Oslo")


@dataclass(frozen=True)
class SourceRace:
    card: RaceCard
    meeting_id: str
    race_no: int
    received_at: datetime
    source_uri: str
    payload: dict[str, object]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _when(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise TypeError("COLLECTOR_SOURCE_CLOCK_MISSING")
    stamp = datetime.fromisoformat(raw)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("COLLECTOR_SOURCE_CLOCK_NAIVE")
    return stamp.astimezone(UTC)


def _time(day: str, raw: object) -> datetime:
    if not isinstance(raw, str) or HHMM.fullmatch(raw) is None:
        raise ValueError("COLLECTOR_RACE_LOCAL_START_UNATTESTED")
    local = datetime.fromisoformat(f"{day}T{raw}").replace(tzinfo=OSLO)
    if local.astimezone(UTC).astimezone(OSLO).strftime("%Y-%m-%dT%H:%M") != f"{day}T{raw}":
        raise ValueError("COLLECTOR_RACE_LOCAL_START_INVALID")
    return local.astimezone(UTC)


def prepare_source(
    archive: Path, checksum: Path, *, date_oslo: str | None = None,
) -> tuple[dict[str, object], list[SourceRace]]:
    """Validate the *entire* daily ZIP and selected NO/SE field before DB writes."""
    receipt = audit_release(archive, checksum)
    day = str(receipt["date_oslo"])
    if date_oslo is not None and day != date_oslo:
        raise ValueError("COLLECTOR_REQUESTED_DATE_MISMATCH")
    source = OriginalArchive(archive)
    # Collector receipts retain the original Actions workspace prefix, whereas
    # the immutable release ZIP deliberately omits "output/daily/". Normalize
    # *lookup paths only* in a separate manifest view; original bytes and their
    # manifest SHA-256 are never edited or re-created.
    normalized_requests: list[dict[str, object]] = []
    for record in source.manifest.get("requests", []):
        if not isinstance(record, dict):
            raise TypeError("COLLECTOR_SOURCE_REQUEST_INVALID")
        view = dict(record)
        for column in ("path", "raw_path"):
            original_path = view.get(column)
            if isinstance(original_path, str) and original_path.startswith("output/daily/"):
                relative = original_path.removeprefix("output/daily/")
                if relative not in source.names:
                    raise ValueError("COLLECTOR_ORIGINAL_RECEIPT_PATH_MISSING")
                view[column] = relative
        normalized_requests.append(view)
    source.manifest = {**source.manifest, "requests": normalized_requests}
    manifest = source.manifest
    if manifest.get("status") != "CAPTURED_UNVERIFIED":
        # Unknown new capture contracts must be reviewed, not assumed valid.
        raise ValueError("COLLECTOR_UNREVIEWED_CAPTURE_STATUS")
    prepared: list[SourceRace] = []
    seen: set[str] = set()
    for meeting in manifest["meetings"]:
        if not isinstance(meeting, dict):
            raise TypeError("COLLECTOR_INVALID_MEETING")
        listed = meeting.get("listing_source") or {}
        if listed.get("country") not in COUNTRIES or listed.get("sport_type") != "T":
            continue
        if meeting.get("is_multi_track_product") is not False:
            continue
        mid = meeting.get("meeting_id")
        if (not isinstance(mid, str) or not re.fullmatch(r"[A-Z0-9_]+_\d{4}-\d{2}-\d{2}", mid)
                or mid != listed.get("meeting_id") or meeting.get("source_date") != day):
            raise ValueError("COLLECTOR_MEETING_IDENTITY_MISMATCH")
        qa = meeting.get("startlist_pdf_audit") or {}
        if (qa.get("status") != "MATCHED_AS_OF_SNAPSHOT" or qa.get("mismatches")
                or qa.get("race_numbers_match") is not True):
            raise ValueError("COLLECTOR_PDF_STARTLIST_NOT_RECONCILED")
        received = _when(meeting.get("captured_utc"))
        _, starts_bytes = source.request(mid, "starts", f"RIKSTOTO:{mid}:1", received)
        _, pdf_bytes = source.request(mid, "pdf", f"RIKSTOTO:{mid}:1", received)
        starts = json.loads(starts_bytes).get("result")
        if not isinstance(starts, dict):
            raise TypeError("COLLECTOR_ORIGINAL_STARTS_INVALID")
        structure_path = f"{source.prefix}meetings/{mid}/structured_program.json"
        structured_bytes = source.read(structure_path)
        structured = json.loads(structured_bytes)
        parts = structured.get("races") if isinstance(structured, dict) else None
        if not isinstance(parts, list) or not parts:
            raise ValueError("COLLECTOR_PARSED_RACE_FIELD_MISSING")
        if sorted(meeting.get("pdf_race_numbers") or []) != sorted(
            part.get("race", {}).get("race_number") for part in parts
        ):
            raise ValueError("COLLECTOR_RACE_NUMBERS_DISAGREE")
        for part in parts:
            race = part["race"]
            n = race.get("race_number")
            if type(n) is not int or n <= 0 or race.get("meeting_id") != mid:
                raise ValueError("COLLECTOR_RACE_ID_INVALID")
            race_id = f"RIKSTOTO:{mid}:{n}"
            if race_id in seen:
                raise ValueError("COLLECTOR_DUPLICATE_PHYSICAL_RACE")
            seen.add(race_id)
            pdf_field = part.get("entrants")
            original_field = starts.get(str(n))
            if not isinstance(pdf_field, list) or not isinstance(original_field, list):
                raise TypeError("COLLECTOR_RACE_FIELD_UNVERIFIED")
            by_number: dict[str, dict] = {}
            for entrant in original_field:
                number = entrant.get("startNumber") if isinstance(entrant, dict) else None
                if type(number) is not int or number <= 0 or str(number) in by_number:
                    raise ValueError("COLLECTOR_ORIGINAL_FIELD_NUMBER_INVALID")
                by_number[str(number)] = entrant
            runners: list[dict[str, object]] = []
            for parsed in pdf_field:
                number = parsed.get("program_number") if isinstance(parsed, dict) else None
                if type(number) is not int or number <= 0:
                    raise ValueError("COLLECTOR_PARSED_SELECTION_INVALID")
                official = by_number.get(str(number))
                if official is None or name_key(str(parsed.get("name") or "")) != name_key(
                    str(official.get("horseName") or "")
                ) or bool(parsed.get("scratched")) != bool(official.get("isScratched")):
                    raise ValueError("COLLECTOR_STARTLIST_PDF_IDENTITY_OR_SCRATCH_CONFLICT")
                runners.append({
                    "race_id": race_id, "selection_id": str(number),
                    "horse_name": str(official["horseName"]),
                    "post_position": official.get("postPosition")
                    if type(official.get("postPosition")) is int else number,
                    "driver_or_jockey": official.get("driverName"),
                    "trainer": None, "scratched": int(bool(official.get("isScratched"))),
                })
            if len(runners) != len(by_number) or len({r["selection_id"] for r in runners}) != len(runners):
                raise ValueError("COLLECTOR_FIELD_SIZE_CONFLICT")
            start_at = _time(day, race.get("scheduled_time_local"))
            if received >= start_at:
                raise ValueError("COLLECTOR_SNAPSHOT_AFTER_RACE_START")
            if not isinstance(race.get("distance_m"), int) or race["distance_m"] <= 0:
                raise ValueError("COLLECTOR_RACE_DISTANCE_INVALID")
            card = RaceCard(
                race={
                    "race_id": race_id, "race_date": day,
                    "country": listed["country"], "track": listed["track"],
                    "race_no": n, "start_time_utc": start_at.isoformat(),
                    "discipline": "trot", "distance_m": race["distance_m"],
                    "start_method": race.get("start_method"), "race_class": None,
                    "created_at_utc": received.isoformat(),
                },
                runners=tuple(runners),
            )
            payload: dict[str, object] = {
                "schema": SCHEMA, "race_id": race_id,
                "archive_sha256": receipt["archive_sha256"],
                "manifest_sha256": receipt["manifest_sha256"],
                "release_tag": f"rikstoto-program-{day}-{receipt['run_id']}",
                "starts_original_sha256": _sha(starts_bytes),
                "program_pdf_original_sha256": _sha(pdf_bytes),
                "structured_program_sha256": _sha(structured_bytes),
                "source_observed_at_utc": received.isoformat(),
                "collector_capture_status": manifest["status"],
                "original_field": [
                    {"selection_id": r["selection_id"], "horse_name": r["horse_name"],
                     "scratched": r["scratched"], "horse_id": None,
                     "horse_identity_status": "UNATTESTED"}
                    for r in sorted(runners, key=lambda x: int(str(x["selection_id"])))
                ],
                "source_ready_snapshot": True, "model_ready": False,
                "bet_ready": False, "pit_certified": False,
                "independent_t4_attested": False,
            }
            prepared.append(SourceRace(card, mid, n, received, str(race["source_url"]), payload))
        if sum(len(row.card.runners) for row in prepared if row.meeting_id == mid) != qa.get("horses_verified"):
            raise ValueError("COLLECTOR_RECONCILED_FIELD_TOTAL_MISMATCH")
    if not prepared:
        raise ValueError("COLLECTOR_NO_VERIFIED_NO_SE_RACES")
    return receipt, prepared


def persist_source(store: SQLiteStore, races: list[SourceRace]) -> dict[str, object]:
    """One transaction: original source provenance and canonical race/runner rows."""
    statuses: list[dict[str, object]] = []
    with store.connect() as db:
        for item in races:
            card = item.card
            race_id = str(card.race["race_id"])
            text = json.dumps(item.payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            payload_id = _sha(text.encode("utf-8"))
            fields = (
                "payload_id", "provider", "category", "provider_raceday_key",
                "race_number", "product", "observed_at_utc", "source_uri", "payload_json",
            )
            values = (payload_id, "collector", CATEGORY, item.meeting_id, item.race_no,
                      "PROGRAM", item.received_at.isoformat(), item.source_uri, text)
            existing = db.execute(
                "SELECT * FROM provider_payloads WHERE payload_id=?", (payload_id,)
            ).fetchone()
            prior = db.execute(
                "SELECT payload_id FROM provider_payloads WHERE provider='collector' "
                "AND category=? AND provider_raceday_key=? AND race_number=?",
                (CATEGORY, item.meeting_id, item.race_no),
            ).fetchall()
            if existing is not None:
                if tuple(existing[field] for field in fields) != values:
                    raise ValueError("COLLECTOR_ARCHIVE_PAYLOAD_ID_CONFLICT")
                state = "SOURCE_READY_SNAPSHOT"
            else:
                # A second version is retained as research history; no mutable canonical overwrite.
                state = "REVISION_REQUIRES_REVIEW" if prior else "SOURCE_READY_SNAPSHOT"
                db.execute(
                    f"INSERT INTO provider_payloads ({','.join(fields)}) "
                    f"VALUES ({','.join('?' for _ in fields)})", values,
                )
            if state == "SOURCE_READY_SNAPSHOT":
                canonical = db.execute("SELECT * FROM races WHERE race_id=?", (race_id,)).fetchone()
                if canonical is None:
                    columns = (
                        "race_id", "race_date", "country", "track", "race_no",
                        "start_time_utc", "discipline", "distance_m",
                        "start_method", "race_class", "created_at_utc",
                    )
                    db.execute(
                        f"INSERT INTO races ({','.join(columns)}) "
                        f"VALUES ({','.join('?' for _ in columns)})",
                        tuple(card.race.get(col) for col in columns),
                    )
                else:
                    for col in ("race_date", "country", "track", "race_no",
                                "start_time_utc", "discipline", "distance_m", "start_method"):
                        if canonical[col] != card.race[col]:
                            raise ValueError("COLLECTOR_EXISTING_CANONICAL_RACE_CONFLICT")
                for runner in card.runners:
                    selected = db.execute(
                        "SELECT * FROM runners WHERE race_id=? AND selection_id=?",
                        (race_id, runner["selection_id"]),
                    ).fetchone()
                    columns = (
                        "race_id", "selection_id", "horse_name", "post_position",
                        "driver_or_jockey", "trainer", "scratched",
                    )
                    if selected is None:
                        db.execute(
                            f"INSERT INTO runners ({','.join(columns)}) "
                            f"VALUES ({','.join('?' for _ in columns)})",
                            tuple(runner.get(col) for col in columns),
                        )
                    elif any(selected[col] != runner.get(col) for col in columns):
                        raise ValueError("COLLECTOR_EXISTING_CANONICAL_RUNNER_CONFLICT")
                runner_count = db.execute(
                    "SELECT COUNT(*) FROM runners WHERE race_id=?", (race_id,)
                ).fetchone()[0]
                if runner_count != len(card.runners):
                    raise ValueError("COLLECTOR_EXISTING_CANONICAL_FIELD_SIZE_CONFLICT")
            readback = db.execute(
                "SELECT * FROM provider_payloads WHERE payload_id=?", (payload_id,)
            ).fetchone()
            if readback is None or tuple(readback[col] for col in fields) != values:
                raise ValueError("COLLECTOR_ARCHIVE_READBACK_MISMATCH")
            statuses.append({
                "race_id": race_id, "status": state,
                "source_ready": state == "SOURCE_READY_SNAPSHOT",
                "model_ready": False, "bet_ready": False,
                "runners": len(card.runners), "payload_id": payload_id,
                "identity": "PERMANENT_HORSE_ID_UNATTESTED",
                "blockers": (["LIVE_WIN_MISSING", "FUNDAMENTAL_INPUT_UNVERIFIED",
                              "PERMANENT_HORSE_ID_UNATTESTED", "PIT_NOT_QUALIFIED"]
                             if state == "SOURCE_READY_SNAPSHOT"
                             else ["SOURCE_REVISION_REQUIRES_REVIEW"]),
            })
    return {
        "schema": SCHEMA, "provider_status": "COLLECTOR_VERIFIED_ARCHIVE_RESEARCH_ONLY",
        "observed_races": len(statuses),
        "observed_runners": sum(int(s["runners"]) for s in statuses),
        "source_ready": sum(bool(s["source_ready"]) for s in statuses),
        "model_ready": 0, "bet_ready": 0,
        "revisions_needing_review": sum(
            s["status"] == "REVISION_REQUIRES_REVIEW" for s in statuses
        ),
        "records": statuses, "pit_certified": False, "bet_authorized": False,
    }


def import_source(
    store: SQLiteStore, archive: Path, checksum: Path, *, date_oslo: str | None = None,
) -> dict[str, object]:
    receipt, races = prepare_source(archive, checksum, date_oslo=date_oslo)
    result = persist_source(store, races)
    result["archive_sha256"] = receipt["archive_sha256"]
    result["manifest_sha256"] = receipt["manifest_sha256"]
    result["collector_status"] = receipt["collector_status"]
    return result
