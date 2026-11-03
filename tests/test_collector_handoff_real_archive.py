"""Historical, immutable, authenticated original archive -> SQLite -> model gate.

The CI job downloads the *actual* 2 Nov 2026 Collector and Betting Actions
artifacts. No fabricated source files, no new model scoring, and no PIT claims.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from hbi.bet_mvp_shadow import select_fixed_cohort_races
from hbi.collector_handoff import (
    OriginalArchive,
    sha,
    verify_import,
    write_research_model_report,
)

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
            assert result["independent_identity_attested"] is False
            assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
            assert result["research_model_eligible"] is (race_id == CASES[-1][0])
            if result["research_model_eligible"]:
                assert result["research_identity_match"] == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
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
        # The frozen historical model remains untouched, even while we run
        # the UNCHANGED model entrypoint against the new isolated import DB.
        assert sha(frozen_model.read_bytes()) == FROZEN_MODEL_SHA
        conn.commit()
        model_dir = tmp_path / "new-historical-research-model"
        historical_asof = model_report["as_of_utc"]
        process = subprocess.run(
            [
                sys.executable, "-m", "hbi.bet_mvp_shadow",
                "--db", str(db),
                "--source-report", str(frozen_source),
                "--race-id", CASES[-1][0],
                "--as-of", historical_asof,
                "--run-kind", "ARCHIVED_REPLAY",
                "--out", str(model_dir),
            ], check=False, capture_output=True, text=True,
        )
        assert process.returncode == 0, process.stderr
        new_shadow = model_dir / "shadow.json"
        new_output = json.loads(new_shadow.read_bytes())
        assert new_output["run_kind"] == "ARCHIVED_REPLAY"
        assert new_output["race"]["race_id"] == CASES[-1][0]
        assert new_output["analysis_status"] == "RESEARCH_READY"
        assert new_output["model_status"] == "MODEL_READY"
        assert new_output["active_runners"] == 8
        assert abs(new_output["champion_p_sum"] - 1.0) < 1e-6
        assert abs(new_output["core004_p_sum"] - 1.0) < 1e-6
        assert new_output["bet_authority"] is False
        assert new_output["pit_status"] == "PIT_NOT_CERTIFIED"
        assert sha(new_shadow.read_bytes()) != FROZEN_MODEL_SHA
        receipt = next(r for r in results if r["race_id"] == CASES[-1][0])
        new_research = write_research_model_report(
            conn, handoff=receipt, shadow_path=new_shadow, source_db=db,
            source_report=frozen_source,
            destination=model_dir / "collector-research-report.json",
        )
        assert new_research["run_kind"] == "HISTORICAL_REPLAY"
        assert new_research["research_model_eligible"] is True
        assert new_research["research_identity_match"] == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
        assert new_research["independent_identity_attested"] is False
        assert new_research["model_input_approved"] is False
        assert new_research["pit_certified"] is False
        assert new_research["bet_authority"] is False
        assert new_research["model"]["original_shadow_json_sha256"] == sha(new_shadow.read_bytes())
        assert new_research["collector_original_sources"]["collector_starts_sha256"] == CASES[-1][4]
        assert new_research["collector_original_sources"]["collector_program_pdf_sha256"] == CASES[-1][5]
        assert new_research["sqlite_import_receipt"]["import_payload_id"] == receipt["import_payload_id"]
        assert abs(new_research["model"]["champion_p_sum"] - 1.0) < 1e-6
        assert abs(new_research["model"]["core004_p_sum"] - 1.0) < 1e-6
        assert len(new_research["model"]["runners"]) == 8

        # Negative: a missing or incorrect Collector import receipt is never
        # accepted as proof of the model's real inputs.
        from copy import deepcopy

        invalid_receipt = deepcopy(receipt)
        invalid_receipt["import_payload_id"] = "0" * 64
        with pytest.raises(ValueError, match="RESEARCH_REPORT_IMPORT_RECEIPT_MISSING"):
            write_research_model_report(
                conn, handoff=invalid_receipt, shadow_path=new_shadow,
                source_db=db, source_report=frozen_source,
                destination=model_dir / "forged-import.json",
            )
        assert not (model_dir / "forged-import.json").exists()

        # A historical probability vector can NEVER promote PIT/BET.
        for invalid_field, forged_value in (
            ("pit_status", "INDEPENDENT_PIT_CERTIFIED"),
            ("bet_authority", True),
        ):
            tampered_model = deepcopy(new_output)
            tampered_model[invalid_field] = forged_value
            tampered_path = tmp_path / f"tampered-{invalid_field}.json"
            tampered_path.write_text(json.dumps(tampered_model))
            with pytest.raises(ValueError, match="RESEARCH_REPORT_MODEL_OR_SOURCE_MISMATCH"):
                write_research_model_report(
                    conn, handoff=receipt, shadow_path=tampered_path,
                    source_db=db, source_report=frozen_source,
                    destination=model_dir / f"forged-{invalid_field}.json",
                )
        assert all(not r["cross_provider_attested"] for r in receipt["identity_evidence"])

        # Persist the genuine research replay artifacts outside the repository.
        published = os.environ.get("MVP004_EVIDENCE_DIR")
        if published:
            folder = Path(published)
            folder.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(new_shadow, folder / "shadow.json")
            shutil.copyfile(
                model_dir / "collector-research-report.json",
                folder / "collector-research-report.json",
            )
            (folder / "collector-handoff.json").write_text(json.dumps(
                {"schema": "COLLECTOR_TO_BETTING_ORIGINAL_V1", "records": results,
                 "bet_authority": False, "pit_certified": False},
                indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            (folder / "integrity-summary.json").write_text(json.dumps(
                {"schema": "MVP_INTEGRATION_004_HISTORICAL_REPLAY_V1",
                 "model_report_sha256": sha(new_shadow.read_bytes()),
                 "research_report_sha256": sha(
                     (model_dir / "collector-research-report.json").read_bytes()),
                 "frozen_reference_model_sha256": FROZEN_MODEL_SHA,
                 "collector_import_id": receipt["import_payload_id"],
                 "race_id": CASES[-1][0],
                 "research_model_eligible": True,
                 "independent_identity_attested": False,
                 "champion_p_sum": new_output["champion_p_sum"],
                 "core004_p_sum": new_output["core004_p_sum"],
                 "pit_certified": False, "bet_authority": False},
                indent=2, sort_keys=True) + "\n")

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
        "model_invocations_after_import": 1,
        "historical_replay_model_status": "MODEL_READY",
        "historical_replay_champion_p_sum": new_output["champion_p_sum"],
        "historical_replay_core004_p_sum": new_output["core004_p_sum"],
        "new_research_model_sha256": sha(new_shadow.read_bytes()),
        "pit_certified": False,
        "bet_authority": False,
    }, sort_keys=True))
