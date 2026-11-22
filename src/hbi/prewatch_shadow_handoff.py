"""Fail-closed V3.3.13 Pre-Watch transport for existing Collector reports.

No probability model, EV calculation, Champion mutation or betting authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "PREWATCH_SHADOW_HANDOFF_V3313_V1"
OSLO = ZoneInfo("Europe/Oslo")


def _clock(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("TIMEZONE_AWARE_DECISION_TIME_REQUIRED")
    return stamp


def _sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def build_handoff(
    source: dict, *, decision_time: str,
    model_run: dict | None = None, win_snapshot: dict | None = None,
) -> dict:
    """Represent actual collector_handoff evidence, never infer an EV or BET.

    This consumes collector_handoff.verify_import() output. Even independently
    verified model/market inputs still require the existing betting.v33 review.
    """
    decision_at = _clock(decision_time)
    race_id = source.get("race_id")
    if not isinstance(race_id, str) or not race_id:
        raise ValueError("CANONICAL_RACE_ID_REQUIRED")
    rows = source.get("runners") or []
    if not isinstance(rows, list):
        raise TypeError("RUNNER_ROWS_INVALID")
    selections = [str(row["start_number"]) for row in rows]
    if len(selections) != len(set(selections)):
        raise ValueError("DUPLICATE_START_NUMBER")
    active = [str(row["start_number"]) for row in rows if row.get("scratched") is False]
    provenance = {
        key: value for key, value in (source.get("model_input_sources") or {}).items()
        if key.startswith("collector_")
    }
    blockers = {str(code) for code in source.get("blockers", [])}
    required_hashes = (
        "collector_starts_sha256",
        "collector_program_pdf_sha256",
        "collector_manifest_sha256",
    )
    source_ready = (
        source.get("source_imported_to_sqlite") is True
        and len(active) >= 2
        and all(_sha(provenance.get(key)) for key in required_hashes)
    )
    if not source_ready:
        blockers.add("SOURCE_IMPORT_NOT_VERIFIED")
    model_ready = (
        source.get("model_input_approved") is True
        and source.get("independent_identity_attested") is True
        and model_run is not None
        and model_run.get("shadow_eligible") is True
        and model_run.get("status") == "READY"
        and model_run.get("calibration_verified") is True
    )
    if not model_ready:
        blockers.add("MODEL_INPUT_OR_CALIBRATION_UNVERIFIED")
    market_ready = False
    if win_snapshot is not None:
        try:
            quote_at = _clock(win_snapshot["observed_at"])
            odds = win_snapshot["odds"]
            market_ready = (
                quote_at <= decision_at
                and win_snapshot.get("race_id") == race_id
                and win_snapshot.get("source_verified") is True
                and win_snapshot.get("full_field_verified") is True
                and set(odds) == set(active)
                and all(
                    type(price) in (int, float) and math.isfinite(price) and price > 1
                    for price in odds.values()
                )
            )
        except (KeyError, ValueError, TypeError):
            market_ready = False
    if not market_ready:
        blockers.add("COMPLETE_WIN_MARKET_UNVERIFIED")
    blockers.add("EXISTING_V33_REVIEW_NOT_EXECUTED")
    return {
        "schema": SCHEMA,
        "race_id": race_id,
        "decision_time": decision_at.isoformat(),
        "listed_runners": len(rows),
        "active_field": active,
        "source_status": "SOURCE_READY" if source_ready else "DATA_BLOCKED",
        "fundamental_status": (
            "READY_FOR_ENGINE_REVIEW" if model_ready else "MODEL_UNCALIBRATED"
        ),
        "market_status": "SOURCE_VERIFIED" if market_ready else "MARKET_PENDING",
        "shadow_status": (
            "NEEDS_EXISTING_V33_REVIEW" if model_ready and market_ready
            else "DATA_BLOCKED"
        ),
        "model_version": model_run.get("model_version") if model_run else None,
        "model_calibration_verified": bool(model_ready),
        "probabilities": None,
        "expected_value": None,
        "bet_authorized": False,
        "execution": "SHADOW_ONLY",
        "champion_changed": False,
        "blockers": sorted(blockers),
        "source_checksums": provenance,
    }


def write_once_and_readback(report: dict, target: Path) -> str:
    """Local append-only-by-file transport; no writes to canonical HBI state."""
    target = Path(target)
    raw = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")
    with target.open("xb") as output:
        output.write(raw)
    if target.read_bytes() != raw:
        raise OSError("SHADOW_REPORT_READBACK_CONFLICT")
    return hashlib.sha256(raw).hexdigest()


def completion_health(reports: list[dict]) -> dict:
    """Two distinct, ordered runs; explained blockers are completed observations."""
    unique = {}
    for report in reports:
        digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
        unique[digest] = report
    ordered = sorted(unique.values(), key=lambda r: _clock(r["observed_at_utc"]))
    stalls = []
    for report in ordered:
        expected = set(report["inventory"])
        records = report["races"]
        actual = [r["race_id"] for r in records]
        explained = all(r.get("terminal_status") and (
            r["terminal_status"] == "FULLY_ASSESSED" or r.get("blockers")
        ) for r in records)
        stalls.append(bool(expected) and (
            len(actual) != len(set(actual)) or set(actual) != expected or not explained
        ))
    alert = len(stalls) >= 2 and all(stalls[-2:])
    return {"status": "P0_COMPLETION_STALL_TWO_RUNS" if alert else "NO_COMPLETION_STALL",
            "distinct_runs": len(ordered), "alert_required": alert,
            "incomplete_observations": sum(stalls),
            "notification_delivery": "NOT_ACTIVATED", "bet_authority": False}


def _terminal(source: dict, transport: dict, start: str | None, when: datetime) -> str:
    if source.get("out_of_scope") is True:
        return "OUT_OF_SCOPE"
    if start and _clock(start) <= when:
        return "ALREADY_STARTED"
    if any(code.startswith("COLLECTOR_AUTHENTICATED_ARCHIVE_UNAVAILABLE")
           for code in source.get("blockers", [])):
        return "SOURCE_UNAVAILABLE"
    if transport["source_status"] != "SOURCE_READY":
        return "DATA_BLOCKED"
    return "MODEL_BLOCKED"


def day_markdown(report: dict) -> str:
    lines = ["# Betting V3.3.13 Shadow — " + report["date_oslo"], "",
             "Evidence: " + report["evidence_mode"],
             "MODEL_NOT_CALIBRATED; NO BET; Champion V3.3.12 unchanged.", "",
             "| Track | Race | Start Europe/Oslo | Terminal status | Blockers |",
             "|---|---|---|---|---|"]
    for r in report["races"]:
        cells = [r.get("track") or "UNKNOWN", r["race_id"],
                 r.get("start_time_oslo") or "UNKNOWN", r["terminal_status"],
                 ", ".join(r["blockers"])]
        lines.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ")
                                       for c in cells) + " |")
    lines += ["", "Terminal inventory coverage: " + str(report["counts"]["terminal"])
              + "/" + str(report["counts"]["discovered"]),
              "This counts explained blocks, not completed betting assessments.", ""]
    return "\n".join(lines)


def run_day(*, db: Path, collector_root: Path, provenance: Path, day: str,
            decision_time: str, out: Path, previous: list[dict] | None = None) -> dict:
    """Existing importer -> existing Shadow transport, on an isolated DB copy only.

    No provider traffic, scheduler, model fitting, settlement or production writes.
    Observation time labels an offline replay, never a prospective prediction.
    """
    from .collector_handoff import (
        OriginalArchive,
        append_shadow_events,
        evaluate_shadow_v33,
        pdf_field,
        sha,
        verify_import,
    )
    from .core_pit_roster_verification import parse_rikstoto_roster
    from .observatory import build_evaluation_summary
    from .storage import SQLiteStore

    date.fromisoformat(day)
    when = _clock(decision_time)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lock = out / ".writer.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write("Isolated Shadow writer; remove only after verifying no running writer.\n")
    archive = None
    try:
        prior_file = out / "prewatch-day.json"
        executed_at = (
            json.loads(prior_file.read_bytes())["observed_at_utc"] if prior_file.exists()
            else datetime.now(UTC).isoformat()
        )
        _clock(executed_at)
        original_sha = sha(db.read_bytes())
        if Path(str(db) + "-wal").exists():
            raise ValueError("IMMUTABLE_SQLITE_SNAPSHOT_REQUIRED")
        isolated = out / "isolated.sqlite"
        if db.resolve() == isolated.resolve():
            raise ValueError("SOURCE_DATABASE_MUST_REMAIN_SEPARATE")
        binding = out / "source-binding.json"
        expected_binding = {"source_database_sha256": original_sha}
        if binding.exists():
            if json.loads(binding.read_bytes()) != expected_binding:
                raise ValueError("ISOLATED_SOURCE_DATABASE_CONFLICT")
        else:
            if isolated.exists():
                raise ValueError("ISOLATED_DATABASE_WITHOUT_SOURCE_BINDING")
            write_once_and_readback(expected_binding, binding)
        if not isolated.exists():
            shutil.copyfile(db, isolated)
        try:
            origin_raw = provenance.read_bytes()
            origin = json.loads(origin_raw)
            if not isinstance(origin, dict):
                origin = {}
        except (OSError, ValueError):
            origin_raw, origin = b"", {}
        authenticated = (
            origin.get("source_repository") == "Maremoo2/rikstoto-program-collector"
            and origin.get("obtained_via_authenticated_gh_cli") is True
            and origin.get("event") == "schedule" and origin.get("conclusion") == "success"
            and type(origin.get("github_run_id")) is int
            and origin["github_run_id"] > 0
        )
        archive_error = "COLLECTOR_AUTHENTICATED_ARCHIVE_UNAVAILABLE"
        if authenticated:
            try:
                archive = OriginalArchive(collector_root)
            except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
                archive_error += ":" + type(exc).__name__
        conn = sqlite3.connect(isolated)
        conn.row_factory = sqlite3.Row
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLITE_INTEGRITY_FAILURE")
            inventory = {r["race_id"]: dict(r) for r in conn.execute(
                "SELECT * FROM races WHERE race_date=?", (day,)
            )}
            # Never lose a Collector-discovered race just because SQLite lacks it.
            if archive is not None and archive.manifest.get("date_oslo") == day:
                for meeting in archive.manifest.get("meetings", []):
                    listing = meeting.get("listing_source") or {}
                    for number in meeting.get("race_numbers", []):
                        rid = f"RIKSTOTO:{meeting['meeting_id']}:{number}"
                        inventory.setdefault(rid, {
                            "race_id": rid, "track": listing.get("track"),
                            "country": listing.get("country"), "race_no": number,
                            "start_time_utc": None, "discipline": listing.get("sport_type"),
                        })
            composites = {
                m["meeting_id"] for m in (archive.manifest.get("meetings", []) if archive else [])
                if m.get("is_multi_track_product") is True
            }
            records = []
            for rid, race in sorted(inventory.items()):
                parts = rid.split(":")
                if len(parts) != 3:
                    source = {"race_id": rid, "blockers": ["CANONICAL_RACE_REFERENCE_INVALID"]}
                elif parts[1] in composites:
                    source = {"race_id": rid, "blockers": ["COMPOSITE_PRODUCT_NOT_PHYSICAL_RACE"],
                              "out_of_scope": True}
                elif archive is None or archive.manifest.get("date_oslo") != day:
                    source = {"race_id": rid, "blockers": [archive_error],
                              "source_imported_to_sqlite": False}
                else:
                    conn.execute("SAVEPOINT single_race")
                    try:
                        source = verify_import(conn, archive, rid, asof=when,
                                               authenticated=authenticated)
                        conn.execute("RELEASE single_race")
                    except (ValueError, TypeError, KeyError, sqlite3.Error,
                            OSError, zipfile.BadZipFile) as exc:
                        conn.execute("ROLLBACK TO single_race")
                        conn.execute("RELEASE single_race")
                        source = {"race_id": rid, "blockers": ["SYSTEM_ERROR:" + type(exc).__name__]}
                transport = build_handoff(source, decision_time=when.isoformat())
                archived_roster = source.get("runners") or []
                archived_roster_hashes = source.get("model_input_sources") or {}
                # The model gate correctly rejects a past start. Still expose
                # independently hashed, earlier programme rows as diagnostics;
                # never feed them back into model admission or certify PIT.
                if (not archived_roster and archive is not None and len(parts) == 3
                        and archive.manifest.get("date_oslo") == day
                        and parts[1] not in composites):
                    try:
                        starts_receipt, starts = archive.request(parts[1], "starts", rid, when)
                        pdf_receipt, pdf = archive.request(parts[1], "pdf", rid, when)
                        roster, error = parse_rikstoto_roster(
                            starts.decode("utf-8"), int(parts[2]), parts[1]
                        )
                        if error or roster is None:
                            raise ValueError("ARCHIVED_ROSTER_INVALID")
                        pdf_field(pdf, int(parts[2]), roster["all"], day)
                        archived_roster = [
                            {"start_number": int(sid), "horse_name": horse["name"],
                             "scratched": horse["scratched"],
                             "registration_number": horse["reg"]}
                            for sid, horse in sorted(roster["all"].items(), key=lambda x: int(x[0]))
                        ]
                        archived_roster_hashes = {
                            "collector_starts_sha256": sha(starts),
                            "collector_program_pdf_sha256": sha(pdf),
                            "collector_manifest_sha256": sha(archive.manifest_raw),
                            "collector_starts_observed_at_utc": starts_receipt["at_utc"],
                            "collector_pdf_observed_at_utc": pdf_receipt["at_utc"],
                            "collector_starts_uri": starts_receipt["url"],
                            "collector_pdf_uri": pdf_receipt["url"],
                        }
                    except (ValueError, TypeError, KeyError, OSError, UnicodeError):
                        archived_roster = []
                # Exercise the real existing gate, not a hand-written replacement.
                # Missing independent model/case evidence must remain NOT_RUN.
                runtime_gate = evaluate_shadow_v33(source)
                if runtime_gate.get("engine_blocker"):
                    transport["blockers"] = sorted(set(transport["blockers"]) | {
                        runtime_gate["engine_blocker"]
                    })
                start = race.get("start_time_utc")
                try:
                    local_start = _clock(start).astimezone(OSLO).isoformat() if start else None
                    terminal = _terminal(source, transport, start, when)
                except (ValueError, TypeError):
                    local_start, terminal = None, "DATA_BLOCKED"
                    transport["blockers"].append("CANONICAL_START_CLOCK_INVALID")
                records.append(transport | {
                    "terminal_status": terminal, "track": race.get("track"),
                    "country": race.get("country"), "discipline": race.get("discipline"),
                    "start_time_utc": start, "start_time_oslo": local_start,
                    "start_time_evidence": source.get("start_time_evidence"),
                    "source_record": source, "model_status": "MODEL_NOT_CALIBRATED",
                    "runtime_gate": runtime_gate,
                    "archived_roster_diagnostic_only": archived_roster,
                    "archived_roster_sources": archived_roster_hashes,
                })
            conn.commit()
        finally:
            conn.close()
        counts = Counter(r["terminal_status"] for r in records)
        measurement = build_evaluation_summary(SQLiteStore(isolated), date.fromisoformat(day))
        report = {
            "schema": "PREWATCH_SHADOW_DAY_V3313_V1", "date_oslo": day,
            "observed_at_utc": executed_at,
            "analysis_as_of_utc": when.astimezone(UTC).isoformat(),
            "evidence_mode": "OFFLINE_ARCHIVED_REPLAY_NOT_PROSPECTIVE",
            "inventory": sorted(inventory), "races": sorted(records, key=lambda r: (
                r.get("start_time_utc") or "9999", r["race_id"])),
            "counts": {"discovered": len(inventory), "terminal": len(records),
                       "source_ready": sum(r["source_status"] == "SOURCE_READY" for r in records),
                       "fully_assessed": 0, "prospective_predictions": 0,
                       "listed_horses_observed": sum(
                           len(r["archived_roster_diagnostic_only"]) for r in records
                       ),
                       "by_status": dict(counts)},
            "coverage_by_country": dict(Counter(r.get("country") or "UNKNOWN" for r in records)),
            "primary_pit_measurement": measurement,
            "model_calibration_status": "MODEL_NOT_CALIBRATED",
            "source_database_sha256": original_sha,
            "source_provenance_sha256": sha(origin_raw) if origin_raw else None,
            "collector_manifest_sha256": sha(archive.manifest_raw) if archive else None,
            "bet_authority": False, "champion_changed": False,
            "production_activated": False,
        }
        report["health"] = completion_health([*(previous or []), report])
        encoded = [
            (json.dumps(r, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
            for r in report["races"]
        ]
        report["event_log_sha256"] = sha(b"".join(encoded))
        if sha(db.read_bytes()) != original_sha:
            raise ValueError("SOURCE_DATABASE_CHANGED_DURING_REPLAY")
        # Exclusive writes and exact retry equivalence; no frozen report replacement.
        target = out / "prewatch-day.json"
        if target.exists():
            if json.loads(target.read_bytes()) != report:
                raise ValueError("FROZEN_DAY_REPORT_CONFLICT")
        else:
            write_once_and_readback(report, target)
        log = out / "prewatch-events.jsonl"
        expected_log = b"".join(encoded)
        if log.exists():
            if log.is_symlink() or log.read_bytes() != expected_log:
                raise ValueError("FROZEN_DAY_EVENT_LOG_CONFLICT")
        else:
            append_shadow_events(log, report["races"])
        if log.read_bytes() != expected_log:
            raise OSError("DAY_EVENT_LOG_READBACK_FAILURE")
        if report["health"]["alert_required"]:
            alert = out / "health-alert.json"
            if not alert.exists():
                write_once_and_readback(report["health"], alert)
            elif json.loads(alert.read_bytes()) != report["health"]:
                raise ValueError("FROZEN_DAY_HEALTH_ALERT_CONFLICT")
        md = out / "prewatch-day.md"
        text = day_markdown(report)
        if md.exists():
            if md.read_text(encoding="utf-8") != text:
                raise ValueError("FROZEN_DAY_MARKDOWN_CONFLICT")
        else:
            with md.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        if json.loads(target.read_bytes()) != report or md.read_text(encoding="utf-8") != text:
            raise OSError("DAY_REPORT_READBACK_FAILURE")
        return report
    finally:
        if archive is not None and archive.zipped is not None:
            archive.zipped.close()
        lock.unlink()


def main() -> None:
    """Convert an existing collector_handoff.run_import report to gated Shadow JSON."""
    import argparse

    parser = argparse.ArgumentParser(description="Read-only Pre-Watch Shadow transport")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collector-report", type=Path)
    mode.add_argument("--day")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--collector-root", type=Path)
    parser.add_argument("--collector-provenance", type=Path)
    parser.add_argument("--previous-report", type=Path, action="append", default=[])
    parser.add_argument("--decision-time", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.day:
        if not all((args.db, args.collector_root, args.collector_provenance)):
            parser.error("--day requires --db, --collector-root, --collector-provenance")
        run_day(db=args.db, collector_root=args.collector_root,
                provenance=args.collector_provenance, day=args.day,
                decision_time=args.decision_time, out=args.out,
                previous=[json.loads(p.read_bytes()) for p in args.previous_report])
        return
    source = json.loads(args.collector_report.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or not isinstance(source.get("records"), list):
        raise TypeError("EXISTING_COLLECTOR_REPORT_REQUIRED")
    events = [
        build_handoff(row, decision_time=args.decision_time)
        for row in source["records"]
    ]
    output = {
        "schema": "PREWATCH_SHADOW_BATCH_V3313_V1",
        "source_report_sha256": hashlib.sha256(
            args.collector_report.read_bytes()
        ).hexdigest(),
        "races": events,
        "bet_authorized": False,
        "champion_changed": False,
    }
    write_once_and_readback(output, args.out)


if __name__ == "__main__":
    main()
