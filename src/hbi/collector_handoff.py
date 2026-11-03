"""MVP-INTEGRATION-002: original Collector program -> existing HBI SQLite input gate.

No model coefficients, market odds, betting rules or PIT authority live here.
An archived morning program is not a prospective T-4 observation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
        matches = []
        for page in document:
            text = page.get_text()
            first_line = text.splitlines()[0].strip() if text.splitlines() else ""
            if first_line == str(number) or re.fullmatch(
                rf"(?:L[oø]p|Lopp)\s+{number}", first_line, re.IGNORECASE
            ):
                matches.append(text)
    if len(matches) != 1:
        raise ValueError("COLLECTOR_PDF_PHYSICAL_RACE_AMBIGUOUS")
    text = matches[0]
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


def verify_import(conn: sqlite3.Connection, archive: OriginalArchive, race_id: str,
                  *, asof: datetime, authenticated: bool) -> dict:
    """Read original source, match all current SQL inputs, then admit or block.

    Returns a source report even for TMP races. Only FULLY_VERIFIED may update
    canonical runner fields; ATG history columns are NEVER imported from PDF.
    """
    response = {
        "race_id": race_id, "status": "BLOCKED", "blockers": [],
        "source_imported_to_sqlite": False, "model_input_approved": False,
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
        fundamentals, cohort_time = latest_cohort(
            conn, "runner_fundamental_snapshots", race_id, asof
        )
        if not good_fundamentals(fundamentals, original["active"], original["all"]):
            blocks.add("COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE")
        response["model_input_sources"]["atg_fundamental_observed_at_utc"] = cohort_time
        if not all(_registered(v["reg"]) for v in original["all"].values()):
            blocks.add("COLLECTOR_TMP_IDENTITY_NOT_ADMITTED")
        reg = [v["reg"] for v in original["all"].values()]
        if len(reg) != len(set(reg)):
            blocks.add("COLLECTOR_REGISTRATION_COLLISION")
        # Source ingestion is independent of model admission. All exact original
        # file hashes are retained in an existing provider_payloads row.
        payload = {
            "schema": SCHEMA,
            "race_id": race_id,
            "original_field": response["runners"],
            "source_checksums": response["model_input_sources"],
            "identity_conflicts": sorted(blocks),
            "source_publication_attested": False,
            "pit_certified": False,
        }
        conn.execute(
            "INSERT OR IGNORE INTO provider_payloads "
            "(payload_id,provider,category,provider_raceday_key,race_number,product,"
            "observed_at_utc,source_uri,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (sha(start_raw), "collector", "ORIGINAL_PROGRAM_ROSTER_V1",
             key, number, None, start_receipt["at_utc"], start_receipt["url"],
             json.dumps(payload, sort_keys=True)),
        )
        response["source_imported_to_sqlite"] = True
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
        "bet_authority": False,
    }))


if __name__ == "__main__":
    main()
