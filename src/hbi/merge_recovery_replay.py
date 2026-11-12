"""MERGE-RECOVERY-001: new independently attributable Collector original replay.

NOT a reconstruction of expired 2026-11-02 core003-pilot-state; never claims
historical PIT equivalence. Uses a different authenticated original source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .cloud_run002_import import import_source
from .cloud_run003_model import assess_and_run
from .storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[2]


def _db_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replay(
    archive: Path, checksum: Path, state: Path, report_path: Path,
    *, expected_source_sha: str,
) -> dict[str, object]:
    """Real-source source-provenance/field/SQLite replay, fail-closed model gate."""
    if len(expected_source_sha) != 64 or _db_sha(archive) != expected_source_sha:
        raise ValueError("REPLAY_AUTHENTIC_ORIGINAL_ARCHIVE_SHA_MISMATCH")
    if state.exists():
        raise ValueError("REPLAY_REQUIRES_NEW_CLEAN_SQLITE")
    store = SQLiteStore(state)
    store.initialize(ROOT / "db/schema.sql")
    store.apply_migrations(ROOT / "db/migrations")
    first = import_source(store, archive, checksum, date_oslo="2026-11-12")
    with store.connect() as db:
        initial = {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("races", "runners", "provider_payloads", "predictions", "shadow_tickets")
        }
        source_ids = {
            str(r[0]) for r in db.execute(
                "SELECT payload_id FROM provider_payloads WHERE provider='collector'"
            )
        }
    second = import_source(store, archive, checksum, date_oslo="2026-11-12")
    with store.connect() as db:
        repeated = {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in initial
        }
        repeated_ids = {
            str(r[0]) for r in db.execute(
                "SELECT payload_id FROM provider_payloads WHERE provider='collector'"
            )
        }
    if (
        first["observed_races"] != 30 or first["observed_runners"] != 321
        or first["source_ready"] != 30 or first["model_ready"] or first["bet_ready"]
        or initial != repeated or initial["races"] != 30 or initial["runners"] != 321
        or initial["provider_payloads"] != 30 or initial["predictions"] or initial["shadow_tickets"]
        or source_ids != repeated_ids or len(source_ids) != 30
        or second["records"] != first["records"]
    ):
        raise ValueError("REPLAY_DETERMINISM_OR_FULL_FIELD_COUNTS_MISMATCH")
    # Deliberately retrospective: no time-travel model admission. The frozen
    # gate has to reject all old races and cannot create p(win) or bets.
    gate = assess_and_run(
        store, first["records"], now=datetime.now(UTC),
    )
    if gate["p_win_computed"] or gate["model_input_complete"] or gate["bet_ready"]:
        raise ValueError("REPLAY_RETROSPECTIVE_MODEL_PROMOTION_FORBIDDEN")
    store.checkpoint()
    with store.connect() as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        state_rows = db.execute(
            "SELECT race_id, COUNT(*) FROM runners GROUP BY race_id ORDER BY race_id"
        ).fetchall()
    if integrity != "ok" or foreign_keys or len(state_rows) != 30:
        raise ValueError("REPLAY_SQLITE_INTEGRITY_OR_FIELD_COVERAGE_FAILED")
    report = {
        "schema": "MERGE_RECOVERY_001_INDEPENDENT_NEW_REPLAY_V1",
        "original_source_sha256": expected_source_sha,
        "source_manifest_sha256": first["manifest_sha256"],
        "source_date_oslo": "2026-11-12",
        "distinct_source_races": initial["races"],
        "distinct_source_starters": initial["runners"],
        "distinct_immutable_source_receipts": len(source_ids),
        "second_import_idempotent": True,
        "full_field_counts_validated_against_original_pdf_and_starts": True,
        "race_field_counts": {row[0]: row[1] for row in state_rows},
        "sqlite_integrity_check": integrity,
        "sqlite_sha256": _db_sha(state),
        "model_admission_rejected_retrospective": True,
        "p_win_calculated": 0,
        "historical_original_2026_11_02_recovered": False,
        "historical_original_evidence_status": "IRRECOVERABLE_HISTORICAL_EVIDENCE",
        "pit_certified": False, "auto_bet": False, "bet_authorized": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--sha256", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--expected-original-sha256", required=True)
    a = p.parse_args()
    result = replay(a.archive, a.sha256, a.state, a.report,
                    expected_source_sha=a.expected_original_sha256)
    print(json.dumps({k: result[k] for k in (
        "distinct_source_races", "distinct_source_starters",
        "distinct_immutable_source_receipts", "second_import_idempotent",
        "sqlite_integrity_check", "p_win_calculated", "pit_certified",
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
