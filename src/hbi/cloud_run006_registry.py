"""CLOUD-RUN-006: real horse registration evidence from verified Collector originals.

Official registries: DNT Sportssystemet (NO) and Svensk Travsport Sportappen
(SE). Neither is assumed to offer an approved machine API. This adapter joins
genuine source-native registration IDs to existing HBI horses, rejects temporary
IDs and conflicts, and journals registry lookup requirements. It cannot attest
an independent registry identity without an original authorized registry record.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .cloud_run001_archive import audit_release
from .collector_handoff import name_key
from .storage import SQLiteStore

SCHEMA = "CLOUD_RUN006_REGISTRATION_CANDIDATE_V1"
MEETING = re.compile(r"(S1_NR|S2_NR|ST_NR)_\d{4}-\d{2}-\d{2}\Z")
REGISTRATION = re.compile(r"[0-9]{12,18}\Z")
FAKE_PREFIXES = ("TMP", "TEMP", "UNKNOWN")


def reconcile_from_original(
    store: SQLiteStore, archive: Path, checksum: Path,
    *, date_oslo: str = "2026-11-12",
) -> dict[str, object]:
    """Verify first; no network requests, no fake official attestations."""
    receipt = audit_release(archive, checksum)
    if receipt["date_oslo"] != date_oslo:
        raise ValueError("REGISTRY_ARCHIVE_WRONG_DATE")
    records: list[dict[str, object]] = []
    reg_owners: dict[str, set[tuple[str, str]]] = defaultdict(set)
    with zipfile.ZipFile(archive) as zf, store.connect() as db:
        matches = [
            name for name in zf.namelist()
            if name.endswith("/starts.raw.json")
            and name.startswith(f"{date_oslo}/{receipt['run_id']}/meetings/")
            and MEETING.fullmatch(name.split("/")[-2]) is not None
        ]
        if len(matches) != 3:
            raise ValueError("REGISTRY_GENUINE_NO_SE_MEETING_COVERAGE_MISSING")
        for path in sorted(matches):
            meeting = path.split("/")[-2]
            raw = zf.read(path)
            raw_sha = hashlib.sha256(raw).hexdigest()
            result = json.loads(raw).get("result")
            if not isinstance(result, dict):
                raise ValueError("REGISTRY_ORIGINAL_STARTS_SCHEMA_INVALID")
            for number, entrants in result.items():
                if not number.isdecimal() or not isinstance(entrants, list):
                    raise ValueError("REGISTRY_ORIGINAL_RACE_FIELD_INVALID")
                race_id = f"RIKSTOTO:{meeting}:{int(number)}"
                canonical = {
                    row["selection_id"]: row for row in db.execute(
                        "SELECT selection_id, horse_name FROM runners WHERE race_id=?",
                        (race_id,),
                    )
                }
                if len(canonical) != len(entrants):
                    raise ValueError("REGISTRY_CANONICAL_FULL_FIELD_CONFLICT")
                seen: set[str] = set()
                for entrant in entrants:
                    if not isinstance(entrant, dict):
                        raise TypeError("REGISTRY_ORIGINAL_RUNNER_INVALID")
                    selection = entrant.get("startNumber")
                    if type(selection) is not int or selection < 1:
                        raise ValueError("REGISTRY_SELECTION_INVALID")
                    sid = str(selection)
                    if sid in seen or sid not in canonical:
                        raise ValueError("REGISTRY_DUPLICATE_OR_FOREIGN_SELECTION")
                    seen.add(sid)
                    name = entrant.get("horseName")
                    if (not isinstance(name, str) or not name.strip()
                            or name_key(name) != name_key(canonical[sid]["horse_name"])):
                        raise ValueError("REGISTRY_SOURCE_HORSE_NAME_CONFLICT")
                    original_registration = entrant.get("horseRegistrationNumber")
                    registration = (
                        original_registration.strip()
                        if isinstance(original_registration, str) else None
                    )
                    temporary = (
                        not registration
                        or registration.upper().startswith(FAKE_PREFIXES)
                    )
                    plausible = (
                        not temporary
                        and REGISTRATION.fullmatch(registration) is not None
                    )
                    status = (
                        "OFFICIAL_REGISTRY_LOOKUP_REQUIRED" if plausible
                        else "REJECTED_TEMPORARY_OR_INVALID"
                    )
                    entry = {
                        "schema": SCHEMA,
                        "race_id": race_id,
                        "selection_id": sid,
                        "horse_name": name,
                        "rikstoto_registration": registration,
                        "registration_country": "NO" if meeting.startswith("ST") else "SE",
                        "registry_authority": (
                            "DNT_SPORTSSYSTEMET" if meeting.startswith("ST")
                            else "SVENSK_TRAVSPORT_SPORTAPPEN"
                        ),
                        "source_url": f"https://www.rikstoto.no/api/racedays/{meeting}/starts",
                        "original_startlist_sha256": raw_sha,
                        "original_archive_sha256": receipt["archive_sha256"],
                        "source_version": receipt["run_id"],
                        "status": status,
                        "permanent_horse_id": None,
                        "independent_registry_source_sha256": None,
                        "attested": False, "pit_certified": False, "bet_authorized": False,
                    }
                    if plausible:
                        reg_owners[registration].add((race_id, sid))
                    records.append(entry)
        # Cross-race reuse of genuine permanent registration MAY be valid for one
        # horse but cannot identify different horses without registry confirmation.
        ambiguous = {
            reg for reg, uses in reg_owners.items()
            if len({
                name_key(row["horse_name"]) for row in records
                if row["rikstoto_registration"] == reg
            }) > 1
        }
        for entry in records:
            if entry["rikstoto_registration"] in ambiguous:
                entry["status"] = "REJECTED_CONFLICT"
            encoded = json.dumps(
                entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                allow_nan=False,
            )
            item_sha = hashlib.sha256(encoded.encode()).hexdigest()
            key = entry["race_id"].split(":")[1]
            values = (
                item_sha, "rikstoto-original", SCHEMA,
                key, int(entry["race_id"].rsplit(":", 1)[-1]),
                entry["selection_id"], datetime.now(UTC).isoformat(),
                entry["source_url"], encoded,
            )
            existing = db.execute(
                "SELECT payload_json FROM provider_payloads WHERE payload_id=?", (item_sha,)
            ).fetchone()
            if existing is not None:
                if existing[0] != encoded:
                    raise ValueError("REGISTRY_JOURNAL_HASH_CONFLICT")
                continue
            cols = ("payload_id", "provider", "category", "provider_raceday_key",
                    "race_number", "product", "observed_at_utc", "source_uri", "payload_json")
            db.execute(
                f"INSERT INTO provider_payloads ({','.join(cols)}) "
                f"VALUES ({','.join('?' for _ in cols)})", values,
            )
    return {
        "schema": SCHEMA,
        "observed_real_horses": len(records),
        "registry_lookup_candidates": sum(
            r["status"] == "OFFICIAL_REGISTRY_LOOKUP_REQUIRED" for r in records
        ),
        "temporary_or_invalid": sum(
            r["status"] == "REJECTED_TEMPORARY_OR_INVALID" for r in records
        ),
        "conflicts": sum(r["status"] == "REJECTED_CONFLICT" for r in records),
        "independently_attested": 0,
        "genuine_source_archive_sha256": receipt["archive_sha256"],
        "source_horses_journaled": len(records),
        "official_registry_api_access_confirmed": False,
        "pit_certified": False,
        "bet_authorized": False,
    }
