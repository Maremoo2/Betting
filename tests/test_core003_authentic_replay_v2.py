"""Authentic, separately versioned 21 Nov replay; never substitutes old facts."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

import hbi
from hbi.collector_handoff import (
    OriginalArchive,
    sha,
    verify_import,
    write_research_model_report,
)

_spec = importlib.util.spec_from_file_location(
    "core003_replay_v2", Path(__file__).resolve().parents[1] / "scripts/core003_replay_v2.py")
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)
database_receipt = replay.database_receipt
digest = replay.digest
extract_inputs = replay.extract_inputs
load_contract = replay.load_contract
readback = replay.readback
verify_inputs = replay.verify_inputs


@pytest.fixture(scope="module")
def originals(tmp_path_factory):
    if expected_root := os.environ.get("CORE003_REPLAY_V2_EXPECT_SOURCE_ROOT"):
        assert Path(hbi.__file__).resolve().is_relative_to(Path(expected_root).resolve())
    value = os.environ.get("CORE003_REPLAY_V2_INPUT_ROOT")
    if not value:
        if os.environ.get("CORE003_REPLAY_V2_REQUIRED") == "1":
            pytest.fail("REPLAY_V2_REQUIRED_INPUTS_NOT_MOUNTED")
        pytest.skip("Authentic V2 inputs not mounted; required explicitly in CI replay step")
    root = Path(value)
    destination = tmp_path_factory.mktemp("replay-v2-originals")
    contract = extract_inputs(root, destination)
    return root, destination, contract


def test_contract_preserves_expired_original_identity():
    contract = load_contract()
    assert contract["schema"] == "CORE003_AUTHENTIC_REPLAY_V2"
    assert contract["legacy"]["status"] == "NOT_REPRODUCIBLE_SOURCE_EXPIRED"
    assert contract["legacy"]["sqlite_sha256"] == (
        "60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0"
    )
    assert contract["sqlite_sha256"] != contract["legacy"]["sqlite_sha256"]
    assert len({x["artifact_id"] for x in contract["artifacts"]}) == 4


def test_missing_original_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="REPLAY_ORIGINAL_MISSING"):
        verify_inputs(tmp_path)


def test_missing_pinned_mirror_has_no_fallback_to_other_sources(tmp_path, monkeypatch):
    contract = deepcopy(load_contract())
    contract["mirror"] = {"artifact_id": 123}
    monkeypatch.setattr(replay, "load_contract", lambda: contract)
    attempts = []

    def missing(entry, destination):
        attempts.append(entry["artifact_id"])
        raise ValueError("MIRROR_EXPIRED")

    monkeypatch.setattr(replay, "download", missing)
    with pytest.raises(ValueError, match="MIRROR_EXPIRED"):
        replay.fetch(tmp_path / "inputs")
    assert attempts == [123]


def test_unapproved_artifact_provenance_is_rejected(tmp_path, monkeypatch):
    entry = load_contract()["artifacts"][0]
    monkeypatch.setattr(replay, "gh_json", lambda endpoint: {
        "expired": False, "workflow_run": {"id": entry["run_id"] + 1},
        "digest": "sha256:" + entry["sha256"],
    })
    with pytest.raises(ValueError, match="REPLAY_ARTIFACT_PROVENANCE_MISMATCH"):
        replay.download(entry, tmp_path / "must-not-download.zip")
    assert not (tmp_path / "must-not-download.zip").exists()


@pytest.mark.parametrize("role", ["collector", "state", "model", "report"])
def test_corrupt_original_rejected_by_actual_validator(originals, tmp_path, role):
    root, _, contract = originals
    for entry in contract["artifacts"]:
        name = entry["role"] + ".zip"
        if entry["role"] == role:
            (tmp_path / name).write_bytes(b"corrupt")
        else:
            os.link(root / name, tmp_path / name)
    with pytest.raises(ValueError, match="REPLAY_ORIGINAL_SHA_MISMATCH:" + role):
        verify_inputs(tmp_path)


def test_original_manifest_member_corruption_and_source_time(originals, tmp_path):
    root, _, contract = originals
    race_id = contract["fields"][0]["race_id"]
    archive = OriginalArchive(root / "collector.zip")
    assert sha(archive.manifest_raw) == contract["manifest_sha256"]
    asof = datetime.fromisoformat(contract["as_of_utc"])
    receipt, raw = archive.request(contract["raceday"], "starts", race_id, asof)
    assert sha(raw) == receipt["sha256"]
    with pytest.raises(ValueError, match="COLLECTOR_OBSERVATION_AFTER_ASOF"):
        archive.request(contract["raceday"], "starts", race_id,
                        datetime.fromisoformat("2026-11-21T05:00:00+00:00"))
    tampered = tmp_path / "tampered-original.zip"
    with zipfile.ZipFile(root / "collector.zip") as src, zipfile.ZipFile(tampered, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            dst.writestr(name, data + b"tamper" if name == receipt["raw_path"] else data)
    invalid = OriginalArchive(tampered)
    with pytest.raises(ValueError, match="COLLECTOR_ORIGINAL_HASH_MISMATCH"):
        invalid.request(contract["raceday"], "starts", race_id, asof)


@pytest.mark.parametrize("fault,reason", [
    ("reference", "CANONICAL_RACE_OR_REFERENCE_MISSING"),
    ("field", "COLLECTOR_SQLITE_FIELD_MISMATCH"),
])
def test_original_field_and_reference_conflict_rejected(originals, tmp_path, fault, reason):
    root, extracted, contract = originals
    target = tmp_path / "invalid.sqlite"
    shutil.copyfile(extracted / "state/core003-pilot.sqlite", target)
    race_id = contract["fields"][0]["race_id"]
    with sqlite3.connect(target) as conn:
        conn.row_factory = sqlite3.Row
        if fault == "reference":
            conn.execute("DELETE FROM provider_race_refs WHERE race_id=?", (race_id,))
        else:
            conn.execute("UPDATE runners SET horse_name='INCORRECT SOURCE NAME' "
                         "WHERE race_id=? AND selection_id='1'", (race_id,))
        result = verify_import(
            conn, OriginalArchive(root / "collector.zip"), race_id,
            asof=datetime.fromisoformat(contract["as_of_utc"]), authenticated=True,
        )
        assert reason in result["blockers"], result
        assert result["model_input_approved"] is False
        assert result["research_model_eligible"] is False
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM shadow_tickets").fetchone()[0] == 0


def test_first_original_insert_and_conflicting_existing_receipt(originals, tmp_path):
    root, extracted, contract = originals
    db = tmp_path / "first-import.sqlite"
    shutil.copyfile(extracted / "state/core003-pilot.sqlite", db)
    # Only this disposable copy loses its three import receipts, deliberately
    # exercising the first-insert path with genuine, unchanged source inputs.
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        where = ("provider='collector' AND category='ORIGINAL_PROGRAM_ROSTER_V1' "
                 "AND provider_raceday_key=? AND race_number IN (4,5,6)")
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM provider_payloads WHERE " + where, (contract["raceday"],))]
        assert len(rows) == 3
        conn.execute("DELETE FROM provider_payloads WHERE " + where, (contract["raceday"],))
        for field in contract["fields"]:
            result = verify_import(
                conn, OriginalArchive(root / "collector.zip"), field["race_id"],
                asof=datetime.fromisoformat(contract["as_of_utc"]), authenticated=True,
            )
            assert result["source_imported_to_sqlite"] is True, result
        restored = [dict(row) for row in conn.execute(
            "SELECT * FROM provider_payloads WHERE " + where, (contract["raceday"],))]
        assert sorted(rows, key=lambda r: r["payload_id"]) == sorted(
            restored, key=lambda r: r["payload_id"])
        conn.execute("UPDATE provider_payloads SET payload_json='{}' WHERE payload_id=?",
                     (rows[0]["payload_id"],))
        field = next(f for f in contract["fields"]
                     if f["race_id"].endswith(":" + str(rows[0]["race_number"])))
        conflict = verify_import(
            conn, OriginalArchive(root / "collector.zip"), field["race_id"],
            asof=datetime.fromisoformat(contract["as_of_utc"]), authenticated=True,
        )
        assert "COLLECTOR_IMPORT_REVISION_CONFLICT" in conflict["blockers"]
        assert conflict["source_imported_to_sqlite"] is False
        assert conflict["research_model_eligible"] is False
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0


def test_authentic_original_import_model_parity_idempotence_and_readback(originals, tmp_path):
    root, extracted, contract = originals
    source = extracted / "state/core003-pilot.sqlite"
    initial = database_receipt(source)
    assert initial["sha256"] == contract["sqlite_sha256"]
    assert initial["counts"] == contract["counts"]
    assert len(initial["migration_ledger"]) == 10
    assert sha((extracted / "report/core003-pilot-report.json").read_bytes()) == (
        contract["report_sha256"]
    )
    frozen_source = extracted / "report/core003-pilot-report.json"
    source_report = json.loads(frozen_source.read_bytes())
    assert source_report["schema_version"] == "CORE_003_SHADOW_PILOT_V1"
    assert set(source_report["races_in_fixed_cohort"]) == {
        field["race_id"] for field in contract["fields"]
    }
    archive = OriginalArchive(root / "collector.zip")
    assert sha(archive.manifest_raw) == contract["manifest_sha256"]
    assert archive.manifest["date_oslo"] == "2026-11-21"
    db = tmp_path / "replay.sqlite"
    shutil.copyfile(source, db)
    results = []
    asof = datetime.fromisoformat(contract["as_of_utc"])
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        for field in contract["fields"]:
            result = verify_import(conn, archive, field["race_id"], asof=asof, authenticated=True)
            assert result["source_imported_to_sqlite"] is True, result
            assert result["import_record_verified"] is True
            assert len(result["runners"]) == field["listed"]
            assert sum(not row["scratched"] for row in result["runners"]) == field["active"]
            assert result["model_input_approved"] is False
            assert result["independent_identity_attested"] is False
            assert result["research_model_eligible"] is True, result
            assert result["pit_certified"] is False and result["bet_authority"] is False
            assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
            assert "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED" in result["blockers"]
            repeated = verify_import(conn, archive, field["race_id"],
                                     asof=asof, authenticated=True)
            assert repeated == result
            results.append(result)
        conn.commit()
    assert database_receipt(db) == initial  # Includes byte SHA, ledger and every pinned count.
    outputs = []
    for field, receipt in zip(contract["fields"], results, strict=True):
        frozen = json.loads((extracted / "model" / field["model_path"]).read_bytes())
        assert frozen["source_database_sha256"] == contract["sqlite_sha256"]
        assert frozen["as_of_utc"] == contract["as_of_utc"]
        assert frozen["race"]["race_id"] == field["race_id"]
        out = tmp_path / ("model-" + field["race_id"].rsplit(":", 1)[1])
        process = subprocess.run([
            sys.executable, "-m", "hbi.bet_mvp_shadow", "--db", str(db),
            "--source-report", str(frozen_source), "--race-id", field["race_id"],
            "--as-of", contract["as_of_utc"], "--run-kind", "ARCHIVED_REPLAY",
            "--out", str(out),
        ], capture_output=True, text=True, check=False)
        assert process.returncode == 0, process.stderr
        model_path = out / "shadow.json"
        model = json.loads(model_path.read_bytes())
        assert model["run_kind"] == "ARCHIVED_REPLAY"
        assert model["model_status"] == "MODEL_READY"
        # Frozen originals 5/6 already lack WIN; preserve that rejection exactly.
        assert model["analysis_status"] == frozen["analysis_status"]
        assert model["source_blocks"] == frozen["source_blocks"]
        if field["race_id"].endswith(":4"):
            assert model["analysis_status"] == "RESEARCH_READY"
        assert model["active_runners"] == field["active"]
        assert model["model_versions"] == frozen["model_versions"]
        assert model["bet_authority"] is False and model["pit_status"] == "PIT_NOT_CERTIFIED"
        for key in ("champion_p_sum", "core004_p_sum"):
            assert abs(model[key] - 1) < 1e-6
        old = {r["selection_id"]: r for r in frozen["runners"]}
        assert {r["selection_id"] for r in model["runners"]} == set(old)
        for runner in model["runners"]:
            for key in ("champion_p_win", "core004_p_win"):
                assert runner[key] == pytest.approx(old[runner["selection_id"]][key], abs=1e-12)
        projection = [{key: row[key] for key in
                       ("selection_id", "champion_p_win", "core004_p_win")}
                      for row in model["runners"]]
        outcome = {"race_id": field["race_id"], "listed": field["listed"],
                   "active": field["active"], "blockers": receipt["blockers"],
                   "probability_projection_sha256": sha(json.dumps(
                       projection, sort_keys=True).encode()),
                   "analysis_status": model["analysis_status"],
                   "source_blocks": model["source_blocks"], "model_parity": "PASS"}
        if model["analysis_status"] != "RESEARCH_READY":
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                blocked_report = out / "must-not-publish.json"
                with pytest.raises(ValueError, match="RESEARCH_REPORT_MODEL_OR_SOURCE_MISMATCH"):
                    write_research_model_report(
                        conn, handoff=receipt, shadow_path=model_path, source_db=db,
                        source_report=frozen_source, destination=blocked_report,
                    )
                assert not blocked_report.exists()
            outputs.append(outcome)
            continue
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            report = write_research_model_report(
                conn, handoff=receipt, shadow_path=model_path, source_db=db,
                source_report=frozen_source, destination=out / "collector-research-report.json",
            )
            assert report["pit_certified"] is False and report["bet_authority"] is False
            for key, value in (("import_payload_id", "0" * 64),):
                invalid = deepcopy(receipt)
                invalid[key] = value
                destination = out / "invalid-receipt.json"
                with pytest.raises(ValueError, match="RESEARCH_REPORT_IMPORT_RECEIPT_MISSING"):
                    write_research_model_report(
                        conn, handoff=invalid, shadow_path=model_path, source_db=db,
                        source_report=frozen_source, destination=destination,
                    )
                assert not destination.exists()
            for key, value in (("pit_status", "INDEPENDENT_PIT_CERTIFIED"),
                               ("bet_authority", True)):
                invalid = deepcopy(model)
                invalid[key] = value
                bad_model = out / ("forged-" + key + ".json")
                bad_model.write_text(json.dumps(invalid), encoding="utf-8")
                destination = out / ("invalid-" + key + ".json")
                with pytest.raises(ValueError, match="RESEARCH_REPORT_MODEL_OR_SOURCE_MISMATCH"):
                    write_research_model_report(
                        conn, handoff=receipt, shadow_path=bad_model, source_db=db,
                        source_report=frozen_source, destination=destination,
                    )
                assert not destination.exists()
        outputs.append(outcome)
    receipt = {"schema": contract["schema"], "legacy_status": contract["legacy"]["status"],
               "database": database_receipt(db), "fields": outputs,
               "strict_model_admissions": 0, "pit_certified": False, "bet_authority": False}
    assert receipt["database"] == initial
    (tmp_path / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    readback(tmp_path)
    assert digest(source) == contract["sqlite_sha256"]
    if published := os.environ.get("CORE003_REPLAY_V2_EVIDENCE"):
        destination = Path(published)
        destination.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(db, destination / "replay.sqlite")
        shutil.copyfile(tmp_path / "receipt.json", destination / "receipt.json")
    print("CORE003_AUTHENTIC_REPLAY_V2_PASS", json.dumps(receipt, sort_keys=True))
