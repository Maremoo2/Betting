"""Historical, immutable, authenticated original archive -> SQLite -> model gate.

The CI job downloads the *actual* 2 Nov 2026 Collector and Betting Actions
artifacts. No fabricated source files, no new model scoring, and no PIT claims.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from hbi.bet_mvp_shadow import select_fixed_cohort_races
from hbi.collector_handoff import OriginalArchive, sha, verify_import

COLLECTOR_ZIP_SHA_NOT_USED = (
    "The workflow downloads original artifact CONTENTS, not the archival ZIP."
)
SOURCE_DB_SHA = "60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0"
FROZEN_MODEL_SHA = "dea4abdf8fed71c137274100153bfaec2323d608faec4072a569b4728cc789fe"
SOURCE_REPORT_SHA = None  # The archived report is original; never fabricate a hash.
CASES = (
    ("RIKSTOTO:OR_NR_2026-11-02:1", "2026-11-02T17:50:00+00:00", 7, 0,
     "df29a5a3837fcbefe736620cdeec095bd2d2473c58179808bb7bd2b880ffd1c9",
     "fca69ea5843756c38ff3cae143c65e7ee4705a543afc284555ea960783920f5d"),
    ("RIKSTOTO:OR_NR_2026-11-02:2", "2026-11-02T18:10:00+00:00", 9, 0,
     "df29a5a3837fcbefe736620cdeec095bd2d2473c58179808bb7bd2b880ffd1c9",
     "fca69ea5843756c38ff3cae143c65e7ee4705a543afc284555ea960783920f5d"),
    ("RIKSTOTO:S2_NR_2026-11-02:10", "2026-11-02T20:19:01.595581+00:00", 8, 8,
     "a4d1432357bf7006a9cc1983afc6b46f09bb3f483c6a286971eb7a8fb3cf260b",
     "6ef632537a00d527381641702d1d8a1f58f428ed0e0a7847f10b3c3bb3fc3bd6"),
)


def _original_paths() -> tuple[Path, Path, Path, Path]:
    env = ("MVP003_COLLECTOR_ROOT", "MVP003_ORIGINAL_SQLITE",
           "MVP003_ORIGINAL_SHADOW", "MVP003_ORIGINAL_SOURCE_REPORT")
    values = [os.environ.get(k) for k in env]
    if not all(values):
        pytest.skip("Actual GitHub original artifacts not mounted; use pinned CI E2E step")
    paths = tuple(Path(x) for x in values)
    if not all(x.exists() for x in paths):
        pytest.fail("ORIGINAL_GITHUB_ARCHIVE_DOWNLOAD_INCOMPLETE")
    return paths


def test_authenticated_original_three_races_to_sqlite_and_frozen_model_gate(tmp_path):
    root, frozen_db, frozen_model, frozen_source = _original_paths()
    assert sha(frozen_db.read_bytes()) == SOURCE_DB_SHA
    assert sha(frozen_model.read_bytes()) == FROZEN_MODEL_SHA
    source_report = json.loads(frozen_source.read_bytes())
    model_report = json.loads(frozen_model.read_bytes())
    assert model_report["race"]["race_id"] == CASES[-1][0]
    assert model_report["model_status"] == "MODEL_READY"  # Pre-PR frozen research only
    assert source_report["schema_version"] == "CORE_003_SHADOW_PILOT_V1"

    # All original hashes, fields, physical clocks and cutoff checks are
    # performed by the exact production candidate, never by a mock parser.
    archive = OriginalArchive(root)
    db = tmp_path / "copy-of-archived-core003.sqlite"
    shutil.copyfile(frozen_db, db)
    results = []
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        for race_id, as_of, count, tmp_count, starts_sha, pdf_sha in CASES:
            result = verify_import(
                conn, archive, race_id,
                asof=datetime.fromisoformat(as_of), authenticated=True,
            )
            assert result["source_imported_to_sqlite"] is True, result
            assert result["import_record_verified"] is True
            assert result["model_input_sources"]["collector_starts_sha256"] == starts_sha
            assert result["model_input_sources"]["collector_program_pdf_sha256"] == pdf_sha
            assert len(result["runners"]) == count
            assert sum(r["identity_grade"] == "TMP_OR_UNKNOWN" for r in result["runners"]) == tmp_count
            assert result["model_input_approved"] is False
            assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
            assert result["bet_authority"] is False and result["pit_certified"] is False
            if tmp_count:
                assert "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED" in result["blockers"]
            results.append(result)

        rows = conn.execute(
            "SELECT payload_id,race_number,payload_json FROM provider_payloads "
            "WHERE provider='collector' AND category='ORIGINAL_PROGRAM_ROSTER_V1' "
            "ORDER BY provider_raceday_key,race_number"
        ).fetchall()
        assert len(rows) == 3
        assert len({row["payload_id"] for row in rows}) == 3
        assert sorted(r["race_number"] for r in rows) == [1, 2, 10]
        original_hashes = [
            json.loads(row["payload_json"])["source_checksums"]["collector_starts_sha256"]
            for row in rows
        ]
        assert original_hashes.count(CASES[0][4]) == 2

        # Original source re-import must prove identical readback, no duplication.
        for race_id, as_of, *_ in CASES:
            same = verify_import(
                conn, archive, race_id,
                asof=datetime.fromisoformat(as_of), authenticated=True,
            )
            assert same["source_imported_to_sqlite"] is True
            assert same["import_record_verified"] is True
        assert conn.execute(
            "SELECT COUNT(*) FROM provider_payloads WHERE provider='collector'"
        ).fetchone()[0] == 3

        # Exact historical source report: Halmstad was eligible for model
        # processing pre-PR, but the new verified input gate MUST now block.
        frozen_asof = datetime.fromisoformat(model_report["report_created_at_utc"])
        selection = select_fixed_cohort_races(conn, source_report, frozen_asof)
        assert CASES[-1][0] in [x["race_id"] for x in selection["eligible"]]
        assert not any(r["model_input_approved"] for r in results)
        assert not [
            row for row in selection["eligible"]
            if next((r["model_input_approved"] for r in results
                     if r["race_id"] == row["race_id"]), False)
        ]
        # The frozen historical model remains untouched. This is a BLOCKED
        # integration, not a retrospective recalculation or live certification.
        assert sha(frozen_model.read_bytes()) == FROZEN_MODEL_SHA

    print(json.dumps({
        "schema": "MVP_INTEGRATION_003_REAL_ORIGINAL_E2E_V1",
        "source": "authenticated_GitHub_Actions_originals_2026_11_02",
        "frozen_source_db_sha256": SOURCE_DB_SHA,
        "frozen_model_report_sha256": FROZEN_MODEL_SHA,
        "races": [
            {"race_id": result["race_id"], "original_horses": len(result["runners"]),
             "original_starts_sha256": result["model_input_sources"]["collector_starts_sha256"],
             "import_payload_id": result["import_payload_id"],
             "source_imported_to_sqlite": result["source_imported_to_sqlite"],
             "model_input_approved": result["model_input_approved"],
             "blockers": result["blockers"]}
            for result in results
        ],
        "stored_collector_records": 3,
        "model_invocations_after_import": 0,
        "pit_certified": False,
        "bet_authority": False,
    }, sort_keys=True))
