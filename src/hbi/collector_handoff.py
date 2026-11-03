"""MVP-INTEGRATION-002: original Collector program -> existing HBI SQLite input gate.

No model coefficients, market odds, betting rules or PIT authority live here.
An archived morning program is not a prospective T-4 observation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from .core_pit_roster_verification import (
    good_fundamentals,
    latest_cohort,
    parse_atg_identity,
    parse_rikstoto_roster,
    parse_time,
)

SCHEMA = "COLLECTOR_TO_BETTING_ORIGINAL_V1"
OSLO = ZoneInfo("Europe/Oslo")
SOURCE_REPO = "Maremoo2/rikstoto-program-collector"
CATEGORIES = ("RACEDAY_STARTS", "FULL_FIELD_ONLY_V1")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def name_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class OriginalArchive:
    """Read only an existing unmodified GitHub Actions artifact or its ZIP."""
    def __init__(self, root: Path):
        self.root = Path(root)
        self.zipped = zipfile.ZipFile(root) if root.is_file() else None
        names = self.zipped.namelist() if self.zipped else [
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
        ] if root.is_dir() else []
        self.names = set(names)
        manifests = [p for p in names if p.endswith("/manifest.json")]
        if len(manifests) != 1:
            raise ValueError("COLLECTOR_MANIFEST_MISSING_OR_AMBIGUOUS")
        self.manifest_name = manifests[0]
        self.prefix = self.manifest_name[:-len("manifest.json")]
        self.manifest_raw = self.read(self.manifest_name)
        self.manifest = json.loads(self.manifest_raw)

    def read(self, path: str) -> bytes:
        part = PurePosixPath(path)
        if (not path or part.is_absolute() or ".." in part.parts
                or path not in self.names):
            raise ValueError("COLLECTOR_ORIGINAL_FILE_MISSING_OR_UNSAFE")
        if self.zipped:
            return self.zipped.read(path)
        target = self.root.joinpath(*part.parts)
        if target.is_symlink() or not target.is_file():
            raise ValueError("COLLECTOR_ORIGINAL_FILE_MISSING_OR_UNSAFE")
        return target.read_bytes()

    def request(self, key: str, role: str, race_id: str, cutoff: datetime):
        urls = {
            "starts": f"https://www.rikstoto.no/api/racedays/{key}/starts",
            "pdf": f"https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/{key}",
        }
        matches = [
            row for row in self.manifest.get("requests", [])
            if isinstance(row, dict) and row.get("url") == urls[role]
        ]
        if len(matches) != 1:
            raise ValueError("COLLECTOR_SOURCE_RECEIPT_MISSING_OR_AMBIGUOUS")
        record = matches[0]
        timestamp = parse_time(record.get("at_utc"))
        if timestamp is None or timestamp > cutoff:
            raise ValueError("COLLECTOR_OBSERVATION_AFTER_ASOF_OR_UNKNOWN")
        field = "raw_path" if role == "starts" else "path"
        path = record.get(field)
        if (not isinstance(path, str)
                or not path.startswith(self.prefix + "meetings/" + key + "/")):
            raise ValueError("COLLECTOR_SOURCE_PATH_WRONG_MEETING")
        raw = self.read(path)
        if not isinstance(record.get("sha256"), str) or sha(raw) != record["sha256"]:
            raise ValueError("COLLECTOR_ORIGINAL_HASH_MISMATCH")
        if role == "pdf" and not raw.startswith(b"%PDF"):
            raise ValueError("COLLECTOR_NOT_ORIGINAL_PDF")
        return record, raw


def pdf_field(pdf_bytes: bytes, number: int, runners: dict, date: str) -> str:
    """Independently bind the *physical* PDF race page and all runner names."""
    import fitz

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        pages = [page.get_text() for page in document]
    labels_by_page = []
    for text in pages:
        # Only the first 14 lines may identify a physical race. Never
        # interpret historic race numbers deeper in a horse's form as headers.
        header = text.splitlines()[:14]
        labels = []
        for line in header:
            line = line.strip()
            if line.isascii() and line.isdecimal():
                labels.append(int(line))
            else:
                label = re.fullmatch(
                    r"(?:L[oø]p|Lopp)\s+(\d+)", line, re.IGNORECASE
                )
                if label is not None:
                    labels.append(int(label.group(1)))
        # Continuation pages can contain isolated numeric form fields in
        # their first lines. A new physical race page must also carry its
        # own START KL clock; otherwise it cannot delimit a race.
        if not re.search(
            r"\\bSTART\\s+KL\\.?\\s*\\d{1,2}:\\d{2}\\b", text, re.IGNORECASE
        ):
            labels = []
        labels_by_page.append(labels)
    matches = [
        i for i, labels in enumerate(labels_by_page)
        if labels and set(labels) == {number}
    ]
    if len(matches) != 1:
        raise ValueError("COLLECTOR_PDF_PHYSICAL_RACE_AMBIGUOUS")
    first = matches[0]
    last = first + 1
    # An original physical race can continue on subsequent unheaded pages.
    # Never read through the next physical race header, even if it happens
    # to contain the sought runner's name or program number.
    while last < len(pages) and not labels_by_page[last]:
        last += 1
    text = "\n".join(pages[first:last])
    starts = re.findall(r"\bSTART\s+KL\.?\s*(\d{1,2}:\d{2})\b", text, re.IGNORECASE)
    if len(starts) != 1:
        raise ValueError("COLLECTOR_PDF_RACE_CLOCK_UNVERIFIED")
    for start_number, row in runners.items():
        pattern = rf"(?mi)^\s*{int(start_number)}\s+{re.escape(row['name'])}(?=[,\s]|$)"
        if not re.search(pattern, text):
            raise ValueError("COLLECTOR_PDF_FIELD_MISMATCH")
    hh, mm = [int(x) for x in starts[0].split(":")]
    naive = datetime.fromisoformat(date + f"T{hh:02d}:{mm:02d}:00")
    candidates = {
        naive.replace(tzinfo=OSLO, fold=i).astimezone(UTC) for i in (0, 1)
    }
    if len(candidates) != 1:
        raise ValueError("COLLECTOR_PDF_AMBIGUOUS_DST_CLOCK")
    return next(iter(candidates)).isoformat()


def _latest_source(conn, provider: str, category: str, key: str, race_no: int, asof: datetime):
    rows = conn.execute(
        "SELECT observed_at_utc,payload_json FROM provider_payloads "
        "WHERE provider=? AND category=? AND provider_raceday_key=? AND race_number=?",
        (provider, category, key, race_no),
    ).fetchall()
    accepted = []
    for row in rows:
        instant = parse_time(row["observed_at_utc"])
        if instant is None:
            raise ValueError("SOURCE_REVISION_CLOCK_UNKNOWN")
        if instant <= asof:
            accepted.append((instant, row["payload_json"]))
    if not accepted:
        raise ValueError("MODEL_SOURCE_COHORT_NOT_FOUND")
    # Revisions with conflicting payloads at the same instant are never resolved by sorting.
    latest = max(t for t, _ in accepted)
    candidates = {body for stamp, body in accepted if stamp == latest}
    if len(candidates) != 1:
        raise ValueError("SOURCE_SAME_INSTANT_REVISION_CONFLICT")
    return json.loads(next(iter(candidates))), accepted


def _registered(val):
    return (isinstance(val, str) and bool(val.strip())
            and not val.upper().startswith(("TMP", "TEMP", "UNKNOWN")))



def _persist_original_roster(
    conn: sqlite3.Connection, *, race_id: str, raceday_key: str,
    race_number: int, observed_at: str, source_uri: str,
    original_field: list[dict], source_checksums: dict,
) -> tuple[bool, str]:
    """One immutable Collector source row per *physical* race, not per raceday.

    The raceday-wide raw starts SHA remains unmodified in source_checksums.
    Existing different versions are a hard conflict; they are never
    overwritten, OR IGNORE'd, or treated as successful imports.
    """
    # Store only immutable Collector provenance in the original row.
    # ATG diagnostics belong in the per-run handoff report and may evolve.
    original_source = {
        key: value for key, value in source_checksums.items()
        if key.startswith("collector_")
    }
    payload = {
        "schema": SCHEMA,
        "race_id": race_id,
        "original_field": original_field,
        "source_checksums": original_source,
        "identity_provenance": "RIKSTOTO_ORIGINAL_STARTS_ONLY",
        "source_publication_attested": False,
        "pit_certified": False,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    payload_id = sha(json.dumps(
        ["COLLECTOR_ORIGINAL_PROGRAM_ROSTER_V1", race_id,
         source_checksums["collector_starts_sha256"],
         source_checksums["collector_program_pdf_sha256"],
         source_checksums["collector_manifest_sha256"]],
        separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8"))
    existing = conn.execute(
        "SELECT payload_id, observed_at_utc, source_uri, payload_json "
        "FROM provider_payloads "
        "WHERE provider='collector' AND category='ORIGINAL_PROGRAM_ROSTER_V1' "
        "AND provider_raceday_key=? AND race_number=?",
        (raceday_key, race_number),
    ).fetchall()
    if existing:
        identical = (
            len(existing) == 1
            and existing[0]["payload_id"] == payload_id
            and existing[0]["observed_at_utc"] == observed_at
            and existing[0]["source_uri"] == source_uri
            and existing[0]["payload_json"] == canonical
        )
        if not identical:
            raise ValueError("COLLECTOR_IMPORT_REVISION_CONFLICT")
        return True, payload_id

    try:
        cur = conn.execute(
            "INSERT INTO provider_payloads "
            "(payload_id,provider,category,provider_raceday_key,race_number,product,"
            "observed_at_utc,source_uri,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (payload_id, "collector", "ORIGINAL_PROGRAM_ROSTER_V1",
             raceday_key, race_number, None, observed_at, source_uri, canonical),
        )
    except sqlite3.IntegrityError as exc:
        # A same-instant uniqueness collision or PK conflict is not success.
        raise ValueError("COLLECTOR_IMPORT_KEY_OR_REVISION_CONFLICT") from exc
    if cur.rowcount != 1:
        raise ValueError("COLLECTOR_IMPORT_INSERT_NOT_CONFIRMED")
    reread = conn.execute(
        "SELECT observed_at_utc,source_uri,payload_json FROM provider_payloads "
        "WHERE payload_id=? AND provider='collector' "
        "AND category='ORIGINAL_PROGRAM_ROSTER_V1' "
        "AND provider_raceday_key=? AND race_number=?",
        (payload_id, raceday_key, race_number),
    ).fetchone()
    if (reread is None or reread["observed_at_utc"] != observed_at
            or reread["source_uri"] != source_uri or reread["payload_json"] != canonical):
        raise ValueError("COLLECTOR_IMPORT_READBACK_MISMATCH")
    return True, payload_id



def verify_import(conn: sqlite3.Connection, archive: OriginalArchive, race_id: str,
                  *, asof: datetime, authenticated: bool) -> dict:
    """Read original source, match all current SQL inputs, then admit or block.

    Returns a source report even for TMP races. Only FULLY_VERIFIED may update
    canonical runner fields; ATG history columns are NEVER imported from PDF.
    """
    response = {
        "race_id": race_id, "status": "BLOCKED", "blockers": [],
        "source_imported_to_sqlite": False, "model_input_approved": False,
        "research_model_eligible": False,
        "research_identity_match": "NOT_VERIFIED",
        "independent_identity_attested": False,
        "research_model_scope": "RESEARCH_ONLY_NO_BET_OR_PIT",
        "bet_authority": False, "pit_certified": False,
        "runners": [], "model_input_sources": {},
    }
    blocks: set[str] = set()
    try:
        race = conn.execute("SELECT * FROM races WHERE race_id=?", (race_id,)).fetchone()
        refs = conn.execute(
            "SELECT * FROM provider_race_refs WHERE race_id=? AND provider='rikstoto'",
            (race_id,),
        ).fetchall()
        if race is None or len(refs) != 1:
            raise ValueError("CANONICAL_RACE_OR_REFERENCE_MISSING")
        key = str(refs[0]["provider_raceday_key"])
        number = int(race["race_no"])
        if race_id != f"RIKSTOTO:{key}:{number}" or refs[0]["race_number"] != number:
            raise ValueError("COLLECTOR_RACE_REFERENCE_CONFLICT")
        scheduled = parse_time(race["start_time_utc"])
        if scheduled is None or asof >= scheduled:
            raise ValueError("MODEL_ASOF_NOT_BEFORE_START")
        manifest = archive.manifest
        if (manifest.get("date_oslo") != key[-10:]
                or manifest.get("date_oslo") != str(race["race_date"])
                or not authenticated):
            raise ValueError("COLLECTOR_ORIGIN_OR_DAY_NOT_VERIFIED")
        matches = [
            m for m in manifest.get("meetings", [])
            if m.get("meeting_id") == key and m.get("is_multi_track_product") is False
        ]
        if len(matches) != 1:
            raise ValueError("COLLECTOR_PHYSICAL_MEETING_AMBIGUOUS")
        audit = matches[0].get("startlist_pdf_audit") or {}
        if (audit.get("status") != "MATCHED_AS_OF_SNAPSHOT"
                or number not in audit.get("verified_race_numbers", [])
                or audit.get("mismatches")):
            raise ValueError("COLLECTOR_PDF_STARTLIST_AUDIT_NOT_VERIFIED")
        start_receipt, start_raw = archive.request(key, "starts", race_id, asof)
        pdf_receipt, pdf_raw = archive.request(key, "pdf", race_id, asof)
        original, error = parse_rikstoto_roster(start_raw.decode("utf-8"), number, key)
        if error or original is None:
            raise ValueError("COLLECTOR_" + (error or "INVALID_FIELD"))
        pdf_clock = pdf_field(pdf_raw, number, original["all"], manifest["date_oslo"])
        if parse_time(pdf_clock) != scheduled:
            raise ValueError("COLLECTOR_PDF_START_CLOCK_CONFLICT")
        response["model_input_sources"] = {
            "collector_starts_sha256": sha(start_raw),
            "collector_program_pdf_sha256": sha(pdf_raw),
            "collector_manifest_sha256": sha(archive.manifest_raw),
            "collector_starts_observed_at_utc": start_receipt["at_utc"],
            "collector_pdf_observed_at_utc": pdf_receipt["at_utc"],
            "collector_pdf_clock_utc": pdf_clock,
            "collector_starts_uri": start_receipt["url"],
            "collector_pdf_uri": pdf_receipt["url"],
        }
        response["runners"] = [
            {"start_number": int(k), "horse_name": v["name"], "scratched": v["scratched"],
             "registration_number": v["reg"], "identity_grade": (
                 "SOURCE_REGISTRATION_CANDIDATE" if _registered(v["reg"]) else "TMP_OR_UNKNOWN"
             )}
            for k, v in sorted(original["all"].items(), key=lambda item: int(item[0]))
        ]
        # The archived ORIGINAL is the source input. Validate against the current
        # live roster and its retained /starts versions before admitting it.
        current = conn.execute(
            "SELECT selection_id,horse_name,scratched FROM runners WHERE race_id=?",
            (race_id,),
        ).fetchall()
        seen = set()
        if len(current) != len(original["all"]):
            blocks.add("COLLECTOR_SQLITE_FIELD_MISMATCH")
        for row in current:
            sid = str(row["selection_id"])
            if sid in seen or sid not in original["all"] or type(row["scratched"]) is not int:
                blocks.add("COLLECTOR_SQLITE_FIELD_MISMATCH")
                continue
            seen.add(sid)
            expected = original["all"][sid]
            if (name_key(row["horse_name"]) != name_key(expected["name"])
                    or row["scratched"] not in (0, 1)
                    or bool(row["scratched"]) != expected["scratched"]):
                blocks.add("COLLECTOR_SQLITE_FIELD_MISMATCH")
        if seen != set(original["all"]):
            blocks.add("COLLECTOR_SQLITE_FIELD_MISMATCH")
        live_payload, live_versions = _latest_source(
            conn, "rikstoto", "RACEDAY_STARTS", key, number, asof
        )
        live_field, err = parse_rikstoto_roster(json.dumps(live_payload), number, key)
        if err or live_field is None or live_field["all"] != original["all"]:
            blocks.add("COLLECTOR_LIVE_ROSTER_REVISION_CONFLICT")
        for _, raw_json in live_versions:
            parsed, err = parse_rikstoto_roster(raw_json, number, key)
            if err or parsed is None or parsed["all"] != original["all"]:
                blocks.add("COLLECTOR_RETAINED_ROSTER_REVISION_CONFLICT")
        identity, _ = _latest_source(
            conn, "atg", "FULL_FIELD_ONLY_V1", race_id, number, asof
        )
        ok, reason = parse_atg_identity(identity, original["active"], original["all"])
        if not ok:
            blocks.add("COLLECTOR_ATG_" + str(reason))
        # The ATG source currently supplies horse.id in a different namespace.
        # resolve_field() only compares unique name and program number, and
        # echoes Rikstoto's registration into its derived ATG evidence row.
        # Neither that echo nor a claimed EXACT_REGISTRATION string is an
        # independently observed ATG-issued registration cross-reference.
        # Preserve both identifiers and timestamps, but NEVER promote the join.
        atg_by_number = {
            str(row.get("selection_id")): row
            for row in identity.get("runners", []) if isinstance(row, dict)
        } if isinstance(identity, dict) and isinstance(identity.get("runners"), list) else {}
        response["identity_evidence"] = [
            {
                "start_number": int(number),
                "rikstoto": {
                    "registration_number": original["all"][number]["reg"],
                    "source_uri": start_receipt["url"],
                    "observed_at_utc": start_receipt["at_utc"],
                    "raw_sha256": sha(start_raw),
                },
                "atg": {
                    "horse_id": atg_by_number.get(number, {}).get("provider_horse_id"),
                    "source_uri": identity.get("source_uri") if isinstance(identity, dict) else None,
                    "observed_at_utc": identity.get("observed_at_utc") if isinstance(identity, dict) else None,
                    "provider_race_id": identity.get("provider_race_id") if isinstance(identity, dict) else None,
                    "derived_match_method": atg_by_number.get(number, {}).get("match_method"),
                    "canonical_registration_echo_untrusted": atg_by_number.get(number, {}).get("rikstoto_registration"),
                },
                "independent_cross_provider_identifier": None,
                "cross_provider_attested": False,
            }
            for number in sorted(original["all"], key=int)
        ]
        response["model_input_sources"]["atg_evidence_source_uri"] = (
            identity.get("source_uri") if isinstance(identity, dict) else None
        )
        response["model_input_sources"]["atg_evidence_observed_at_utc"] = (
            identity.get("observed_at_utc") if isinstance(identity, dict) else None
        )
        blocks.add("IDENTITY_CROSS_PROVIDER_NOT_ATTESTED")
        fundamentals, cohort_time = latest_cohort(
            conn, "runner_fundamental_snapshots", race_id, asof
        )
        if not good_fundamentals(fundamentals, original["active"], original["all"]):
            blocks.add("COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE")
        response["model_input_sources"]["atg_fundamental_observed_at_utc"] = cohort_time
        # Lower-trust research admission: every source and all snapshot clocks
        # must be verified, while exact cross-provider identity stays BLOCKED.
        if ok:
            atg_names = [name_key(r.get("horse_name")) for r in identity["runners"]]
            original_names = [name_key(row["name"]) for row in original["all"].values()]
            if (len(set(original_names)) != len(original_names)
                    or len(set(atg_names)) != len(atg_names)):
                blocks.add("RESEARCH_ATG_NAME_NOT_UNIQUE")
            if any(
                row.get("match_method") != "UNIQUE_NAME_AND_PROGRAM_NUMBER"
                or row.get("match_confidence") != 1.0
                for row in identity["runners"]
            ):
                blocks.add("RESEARCH_ATG_MATCH_METHOD_NOT_VERIFIED")
            atg_time = parse_time(identity.get("observed_at_utc"))
            retained_latest = max(t for t, _ in _latest_source(
                conn, "atg", "FULL_FIELD_ONLY_V1", race_id, number, asof
            )[1])
            if (
                identity.get("provider") != "atg"
                or identity.get("country") != race["country"]
                or identity.get("discipline") != race["discipline"]
                or not isinstance(identity.get("provider_race_id"), str)
                or re.fullmatch(
                    rf"{re.escape(str(race['race_date']))}_[0-9]+_{number}",
                    identity.get("provider_race_id") or "",
                ) is None
                or identity.get("source_uri") != (
                    "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_"
                    + str(identity.get("provider_race_id"))
                )
                or identity.get("timestamp_basis") != "FETCH_COMPLETED"
                or parse_time(identity.get("race_start_utc")) != scheduled
                or atg_time is None or atg_time != retained_latest
                or atg_time > asof
                or not isinstance(identity.get("collection_started_at_utc"), str)
            ):
                blocks.add("RESEARCH_ATG_RACE_OR_CLOCK_NOT_VERIFIED")
            if cohort_time != (atg_time.isoformat() if atg_time else None):
                blocks.add("RESEARCH_ATG_HISTORY_COHORT_NOT_MATCHED")
            for row in fundamentals:
                try:
                    observed = parse_time(row["observed_at_utc"])
                    feature_time = parse_time(row["feature_as_of_utc"])
                    if (
                        observed is None or feature_time is None
                        or observed != atg_time
                        or feature_time > asof
                        or row["source_uri"] != identity["source_uri"]
                    ):
                        blocks.add("RESEARCH_ATG_HISTORY_CLOCK_OR_SOURCE_CONFLICT")
                    keys = set(row.keys())  # sqlite3.Row membership tests values, not keys.
                    if str(row["selection_id"]) in original["active"] and (
                        "identity_match_method" not in keys
                        or row["identity_match_method"] != "UNIQUE_NAME_AND_PROGRAM_NUMBER"
                        or "identity_match_confidence" not in keys
                        or row["identity_match_confidence"] != 1.0
                    ):
                        blocks.add("RESEARCH_ATG_HISTORY_IDENTITY_METHOD_UNVERIFIED")
                except (KeyError, ValueError, TypeError):
                    blocks.add("RESEARCH_ATG_HISTORY_CLOCK_OR_SOURCE_CONFLICT")
            if not any(code.startswith("RESEARCH_ATG_") for code in blocks):
                response["research_identity_match"] = "UNIQUE_NAME_AND_PROGRAM_NUMBER"
        if not all(_registered(v["reg"]) for v in original["all"].values()):
            blocks.add("COLLECTOR_TMP_IDENTITY_NOT_ADMITTED")
        reg = [v["reg"] for v in original["all"].values()]
        if len(reg) != len(set(reg)):
            blocks.add("COLLECTOR_REGISTRATION_COLLISION")
        # Immutable evidence is importable even when the independent ATG
        # identity join is blocked. No prior row can be silently ignored.
        imported, import_id = _persist_original_roster(
            conn, race_id=race_id, raceday_key=key, race_number=number,
            observed_at=start_receipt["at_utc"], source_uri=start_receipt["url"],
            original_field=response["runners"],
            source_checksums=response["model_input_sources"],
        )
        response["source_imported_to_sqlite"] = imported
        response["import_payload_id"] = import_id
        response["import_record_verified"] = imported
        strict_only = {"IDENTITY_CROSS_PROVIDER_NOT_ATTESTED", "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED"}
        if (
            imported and ok
            and response["research_identity_match"] == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
            and not (blocks - strict_only)
        ):
            response["research_model_eligible"] = True
            response["status"] = "RESEARCH_ONLY_MODEL_ELIGIBLE"
        if not blocks:
            # Reassert canonical roster from the verified original, rather than
            # silently treating independent CORE-003 GETs as the Collector input.
            for member in response["runners"]:
                conn.execute(
                    "UPDATE runners SET horse_name=?,post_position=?,scratched=? "
                    "WHERE race_id=? AND selection_id=?",
                    (member["horse_name"], member["start_number"], int(member["scratched"]),
                     race_id, str(member["start_number"])),
                )
            response["model_input_approved"] = True
            response["status"] = "MODEL_INPUT_VERIFIED_RESEARCH_ONLY"
    except (ValueError, TypeError, KeyError, UnicodeError, OSError, sqlite3.Error) as exc:
        blocks.add(str(exc) if isinstance(exc, ValueError) and str(exc).isupper()
                   else "COLLECTOR_SOURCE_VALIDATION_ERROR")
    response["blockers"] = sorted(blocks)
    return response



def write_research_model_report(
    conn: sqlite3.Connection, *, handoff: dict, shadow_path: Path,
    source_db: Path, source_report: Path, destination: Path,
) -> dict:
    """Bind unchanged Champion/CORE-004 frozen output to verified Collector input.

    Only research_model_eligible allows this report. Does not authorize,
    modify, or emulate either existing PIT or betting hard gate.
    """
    if (
        handoff.get("research_model_eligible") is not True
        or handoff.get("model_input_approved") is not False
        or handoff.get("independent_identity_attested") is not False
        or handoff.get("bet_authority") is not False
        or handoff.get("pit_certified") is not False
        or handoff.get("research_identity_match") != "UNIQUE_NAME_AND_PROGRAM_NUMBER"
        or handoff.get("source_imported_to_sqlite") is not True
        or handoff.get("import_record_verified") is not True
    ):
        raise ValueError("RESEARCH_REPORT_IMPORT_GATE_NOT_VERIFIED")
    frozen_bytes = shadow_path.read_bytes()
    model = json.loads(frozen_bytes)
    race_id = handoff["race_id"]
    if (
        model.get("race", {}).get("race_id") != race_id
        or model.get("run_kind") not in {"ARCHIVED_REPLAY", "PROSPECTIVE_ATTEMPT"}
        or model.get("bet_authority") is not False
        or model.get("pit_status") != "PIT_NOT_CERTIFIED"
        or model.get("model_status") != "MODEL_READY"
        or model.get("analysis_status") != "RESEARCH_READY"
        or model.get("source_database_sha256") != sha(source_db.read_bytes())
        or model.get("collector_source_evidence", {}).get("sha256") != sha(source_report.read_bytes())
    ):
        raise ValueError("RESEARCH_REPORT_MODEL_OR_SOURCE_MISMATCH")
    asof = parse_time(model.get("as_of_utc"))
    if asof is None or asof >= parse_time(model["race"]["start_time_utc"]):
        raise ValueError("RESEARCH_REPORT_INVALID_ANALYSIS_CLOCK")
    source = handoff["model_input_sources"]
    if (
        any(parse_time(source.get(k)) is None or parse_time(source[k]) > asof
            for k in ("collector_starts_observed_at_utc",
                      "collector_pdf_observed_at_utc",
                      "atg_evidence_observed_at_utc",
                      "atg_fundamental_observed_at_utc"))
    ):
        raise ValueError("RESEARCH_REPORT_SOURCE_AFTER_AS_OF")
    original = {str(r["start_number"]): r for r in handoff["runners"]}
    outputs = model.get("runners")
    if (
        not isinstance(outputs, list) or len(outputs) != len(original)
        or {str(r.get("selection_id")) for r in outputs} != set(original)
    ):
        raise ValueError("RESEARCH_REPORT_FIELD_NOT_COMPLETE")
    for row in outputs:
        identity = original[str(row["selection_id"])]
        if (
            name_key(row.get("horse_name")) != name_key(identity["horse_name"])
            or row.get("scratched") is not identity["scratched"]
        ):
            raise ValueError("RESEARCH_REPORT_FIELD_IDENTITY_CONFLICT")
    active = [r for r in outputs if not r["scratched"]]
    if not active:
        raise ValueError("RESEARCH_REPORT_EMPTY_ACTIVE_FIELD")
    for name, key in (("champion", "champion_p_win"), ("core004", "core004_p_win")):
        probs = [r.get(key) for r in active]
        if (
            any(type(p) not in (int, float) or not math.isfinite(p)
                or p < 0 or p > 1 for p in probs)
            or abs(sum(probs) - 1) > 1e-6
            or abs(float(model.get(name + "_p_sum", -1)) - 1) > 1e-6
        ):
            raise ValueError("RESEARCH_REPORT_MODEL_PROBABILITIES_INVALID")
    rows = conn.execute(
        "SELECT * FROM provider_payloads "
        "WHERE payload_id=? AND provider='collector' "
        "AND category='ORIGINAL_PROGRAM_ROSTER_V1'",
        (handoff["import_payload_id"],),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("RESEARCH_REPORT_IMPORT_RECEIPT_MISSING")
    imported = json.loads(rows[0]["payload_json"])
    expected_collector_source = {
        k: v for k, v in source.items() if k.startswith("collector_")
    }
    if (
        imported.get("race_id") != race_id
        or imported.get("original_field") != handoff["runners"]
        or imported.get("source_checksums") != expected_collector_source
        or rows[0]["provider_raceday_key"] != race_id.split(":")[1]
        or int(rows[0]["race_number"]) != int(race_id.rsplit(":", 1)[1])
        or rows[0]["observed_at_utc"] != source["collector_starts_observed_at_utc"]
        or rows[0]["source_uri"] != source["collector_starts_uri"]
    ):
        raise ValueError("RESEARCH_REPORT_IMPORT_RECEIPT_CONFLICT")
    report = {
        "schema": "COLLECTOR_RESEARCH_ONLY_MODEL_REPORT_V1",
        "run_kind": ("HISTORICAL_REPLAY" if model["run_kind"] == "ARCHIVED_REPLAY"
                     else "RESEARCH_ONLY_PROSPECTIVE_ATTEMPT"),
        "race_id": race_id,
        "model_as_of_utc": model["as_of_utc"],
        "original_field": handoff["runners"],
        "research_identity_match": handoff["research_identity_match"],
        "research_identity_evidence": handoff["identity_evidence"],
        "independent_identity_attested": False,
        "model_input_approved": False,
        "research_model_eligible": True,
        "collector_original_sources": {
            k: v for k, v in source.items() if k.startswith("collector_")
        },
        "atg_research_sources": {
            k: v for k, v in source.items() if k.startswith("atg_")
        },
        "sqlite_import_receipt": {
            "import_payload_id": handoff["import_payload_id"],
            "source_imported_to_sqlite": True,
            "import_record_verified": True,
            "source_database_sha256": model["source_database_sha256"],
        },
        "model_source_report_sha256": sha(source_report.read_bytes()),
        "model": {
            "original_shadow_json_sha256": sha(frozen_bytes),
            "model_versions": model["model_versions"],
            "analysis_status": model["analysis_status"],
            "model_status": model["model_status"],
            "field_size": model["field_size"],
            "active_runners": model["active_runners"],
            "champion_p_sum": model["champion_p_sum"],
            "core004_p_sum": model["core004_p_sum"],
            "runners": [
                {"selection_id": r["selection_id"],
                 "horse_name": r["horse_name"], "scratched": r["scratched"],
                 "champion_p_win": r["champion_p_win"],
                 "core004_p_win": r["core004_p_win"]}
                for r in outputs
            ],
        },
        "pit_certified": False,
        "pit_status": "PIT_NOT_CERTIFIED",
        "bet_authority": False,
        "bet_eligible": False,
        "allowed_use": "RESEARCH_ONLY_NOT_VALIDATED_FOR_BETTING",
    }
    if destination.exists():
        raise ValueError("RESEARCH_REPORT_DESTINATION_ALREADY_EXISTS")
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True,
                   allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report



def run_import(db: Path, root: Path, provenance: Path, source_report: Path,
               out: Path, *, asof: datetime | None = None) -> dict:
    """Write only to the existing isolated CORE-003 SQLite, never hbi-state."""
    source = json.loads(source_report.read_text(encoding="utf-8"))
    ids = source.get("races_in_fixed_cohort")
    if not isinstance(ids, list) or len(ids) != len(set(ids)):
        raise ValueError("CORE003_FIXED_COHORT_INVALID")
    when = asof or datetime.now(UTC)
    if when.tzinfo is None:
        raise ValueError("ASOF_MUST_BE_AWARE")
    records = []
    archive = None
    authenticated = False
    try:
        origin = json.loads(provenance.read_text(encoding="utf-8"))
        authenticated = (origin.get("source_repository") == SOURCE_REPO
                         and origin.get("obtained_via_authenticated_gh_cli") is True
                         and origin.get("event") == "schedule"
                         and origin.get("conclusion") == "success"
                         and type(origin.get("github_run_id")) is int
                         and origin["github_run_id"] > 0)
        if authenticated:
            archive = OriginalArchive(root)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile):
        pass
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        for race_id in ids:
            if archive is None:
                records.append({
                    "race_id": race_id, "status": "BLOCKED",
                    "blockers": ["COLLECTOR_AUTHENTICATED_ARCHIVE_UNAVAILABLE"],
                    "source_imported_to_sqlite": False, "model_input_approved": False,
                    "research_model_eligible": False, "research_identity_match": "NOT_VERIFIED",
                    "independent_identity_attested": False,
                    "bet_authority": False, "pit_certified": False,
                })
                continue
            record = verify_import(
                conn, archive, race_id, asof=when, authenticated=authenticated
            )
            records.append(record)
        conn.commit()
    finally:
        conn.close()
        if archive is not None and archive.zipped is not None:
            archive.zipped.close()
    output = {
        "schema": SCHEMA, "as_of_utc": when.astimezone(UTC).isoformat(),
        "source_report_sha256": sha(source_report.read_bytes()),
        "collector_archive_required": True, "records": records,
        "bet_authority": False, "pit_certified": False,
    }
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--collector-root", type=Path, required=True)
    parser.add_argument("--collector-provenance", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run_import(
        args.db, args.collector_root, args.collector_provenance,
        args.source_report, args.out
    )
    print(json.dumps({
        "total": len(result["records"]),
        "originals_imported": sum(r["source_imported_to_sqlite"] for r in result["records"]),
        "model_input_approved": sum(r["model_input_approved"] for r in result["records"]),
        "research_model_eligible": sum(r["research_model_eligible"] for r in result["records"]),
        "bet_authority": False,
    }))


if __name__ == "__main__":
    main()
