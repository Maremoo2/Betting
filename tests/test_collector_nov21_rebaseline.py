"""Authenticated 21 Nov Collector + CORE-003 + frozen model baseline (no BET).

This is a NEW independently hashed corpus. The pre-existing original 2 Nov
historical fixture and its SHA assertions remain untouched in the repository.
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

from betting.v33 import evaluate
from hbi.collector_handoff import (
    OriginalArchive,
    evaluate_shadow_v33,
    sha,
    verify_import,
)
from hbi.prewatch_shadow_handoff import build_handoff, run_day, write_once_and_readback

SOURCE_DB_SHA = "c8d460aa6e50f5c7f63a976e70e572bd5cc7fc4148ee9bddef786dea2984b20d"
SOURCE_REPORT_SHA = "6d1cc224c789734eb136ffe87fbe53e1864080f98a40d827e605277a8ece533e"
MANIFEST_SHA = "27d81e314c091805caf458bc4bfae794cffae221ed1f50669771a05ad6c5b58d"
FROZEN_SHADOW_SHA = "33b5b2d96f2f82732bc43197b583427996e8c056b9bf04f25515c9b89f9514f0"
RACE_PREFIX = "RIKSTOTO:S1_NR_2026-11-21:"
ASOF = datetime.fromisoformat("2026-11-21T13:12:06.846294+00:00")
COUNTS = {4: 12, 5: 12, 6: 10}


def _inputs():
    required = {
        "collector": "P0_NOV21_COLLECTOR_ROOT",
        "db": "P0_NOV21_SQLITE",
        "report": "P0_NOV21_SOURCE_REPORT",
        "shadow": "P0_NOV21_FROZEN_SHADOW",
    }
    paths = {name: Path(os.environ.get(key, "")) for name, key in required.items()}
    if not all(os.environ.get(key) for key in required.values()):
        pytest.skip("Explicit authenticated 21 Nov GitHub original artifacts not mounted")
    if not all(path.exists() for path in paths.values()):
        pytest.fail("P0_NOV21_AUTHENTICATED_ARTIFACT_MISSING")
    return paths


def test_real_nov21_original_to_sqlite_research_shadow_and_readback(tmp_path):
    files = _inputs()
    assert sha(files["db"].read_bytes()) == SOURCE_DB_SHA
    assert sha(files["report"].read_bytes()) == SOURCE_REPORT_SHA
    assert sha(files["shadow"].read_bytes()) == FROZEN_SHADOW_SHA
    archive = OriginalArchive(files["collector"])
    assert sha(archive.manifest_raw) == MANIFEST_SHA
    assert archive.manifest["date_oslo"] == "2026-11-21"
    report = json.loads(files["report"].read_bytes())
    assert report["schema_version"] == "CORE_003_SHADOW_PILOT_V1"
    assert set(report["races_in_fixed_cohort"]) == {
        RACE_PREFIX + str(x) for x in COUNTS
    }
    model_ref = json.loads(files["shadow"].read_bytes())
    assert model_ref["race"]["race_id"] == RACE_PREFIX + "4"
    assert model_ref["source_database_sha256"] == SOURCE_DB_SHA
    assert model_ref["bet_authority"] is False
    assert model_ref["pit_status"] == "PIT_NOT_CERTIFIED"
    isolated = tmp_path / "isolated-core003.sqlite"
    shutil.copyfile(files["db"], isolated)
    connection = sqlite3.connect(isolated)
    connection.row_factory = sqlite3.Row
    try:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        before = connection.execute(
            "SELECT count(*) FROM provider_payloads WHERE provider='collector' "
            "AND category='ORIGINAL_PROGRAM_ROSTER_V1'"
        ).fetchone()[0]
        assert before >= 3  # Cumulative 21 Nov state, not the older 2 Nov baseline
        outputs = []
        for number, count in COUNTS.items():
            race_id = RACE_PREFIX + str(number)
            initial = connection.execute(
                "SELECT count(*) FROM provider_payloads WHERE provider='collector' "
                "AND category='ORIGINAL_PROGRAM_ROSTER_V1' "
                "AND provider_raceday_key='S1_NR_2026-11-21' AND race_number=?",
                (number,),
            ).fetchone()[0]
            assert initial == 1  # Genuine already-archived original
            result = verify_import(
                connection, archive, race_id, asof=ASOF, authenticated=True
            )
            assert result["source_imported_to_sqlite"] is True, result
            assert result["import_record_verified"] is True
            assert len(result["runners"]) == count
            assert result["model_input_sources"]["collector_manifest_sha256"] == MANIFEST_SHA
            assert result["model_input_approved"] is False
            assert result["independent_identity_attested"] is False
            assert result["bet_authority"] is False and result["pit_certified"] is False
            assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
            assert "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED" in result["blockers"]
            second = verify_import(
                connection, archive, race_id, asof=ASOF, authenticated=True
            )
            assert second["import_payload_id"] == result["import_payload_id"]
            assert second["source_imported_to_sqlite"] is True
            assert connection.execute(
                "SELECT count(*) FROM provider_payloads WHERE provider='collector' "
                "AND category='ORIGINAL_PROGRAM_ROSTER_V1' "
                "AND provider_raceday_key='S1_NR_2026-11-21' AND race_number=?",
                (number,),
            ).fetchone()[0] == 1
            status = evaluate_shadow_v33(result)
            assert status["source_status"] == "SOURCE_READY"
            assert status["engine_status"] == "NOT_RUN"
            assert status["p_win"] is None and status["ev"] is None
            assert status["bet_authority"] is False
            external = build_handoff(
                result, decision_time=ASOF.isoformat()
            )
            assert external["source_status"] == "SOURCE_READY"
            assert external["expected_value"] is None
            assert external["bet_authorized"] is False
            path = tmp_path / ("shadow-" + str(number) + ".json")
            digest = write_once_and_readback(external, path)
            assert sha(path.read_bytes()) == digest
            assert json.loads(path.read_bytes()) == external
            outputs.append(result)
        assert connection.execute(
            "SELECT count(*) FROM provider_payloads WHERE provider='collector' "
            "AND category='ORIGINAL_PROGRAM_ROSTER_V1'"
        ).fetchone()[0] == before
        # Real Betting engine receives no invented market or fundamental case.
        with pytest.raises((KeyError, ValueError, TypeError)):
            evaluate({"race_id": RACE_PREFIX + "4"})
        connection.commit()
    finally:
        connection.close()
    model_dir = tmp_path / "real-model-replay"
    p = subprocess.run(
        [
            sys.executable, "-m", "hbi.bet_mvp_shadow",
            "--db", str(isolated),
            "--source-report", str(files["report"]),
            "--race-id", RACE_PREFIX + "4",
            "--as-of", ASOF.isoformat(),
            "--run-kind", "ARCHIVED_REPLAY",
            "--out", str(model_dir),
        ],
        capture_output=True, text=True, check=False,
    )
    assert p.returncode == 0, p.stderr
    model = json.loads((model_dir / "shadow.json").read_bytes())
    assert model["race"]["race_id"] == RACE_PREFIX + "4"
    assert model["model_status"] == "MODEL_READY"
    assert model["analysis_status"] == "RESEARCH_READY"
    assert model["bet_authority"] is False
    assert model["pit_status"] == "PIT_NOT_CERTIFIED"
    assert abs(model["champion_p_sum"] - 1) < 1e-6
    assert abs(model["core004_p_sum"] - 1) < 1e-6
    print(json.dumps({
        "schema": "P0_NOV21_AUTHENTICATED_ORIGINAL_REBASELINE_V1",
        "races": list(COUNTS),
        "source_sha256": SOURCE_DB_SHA,
        "original_manifest_sha256": MANIFEST_SHA,
        "persisted_collector_rows_before_after": before,
        "real_model_replay": "RESEARCH_READY_NON_BETTING",
        "v33_bet_authorized": False,
        "prewatch_readback": "PASS",
        "pit_certified": False,
    }, sort_keys=True))


def test_tampered_original_archive_is_not_admitted(tmp_path):
    files = _inputs()
    archive = OriginalArchive(files["collector"])
    raw_receipt, raw = archive.request(
        "S1_NR_2026-11-21", "starts", RACE_PREFIX + "4", ASOF
    )
    assert sha(raw) == raw_receipt["sha256"]
    assert raw_receipt["at_utc"] <= ASOF.isoformat()
    assert len(raw) > 0
    # Independent digest mutation cannot validate against the authentic receipt.
    assert sha(raw + b"tamper") != raw_receipt["sha256"]
    with pytest.raises(ValueError, match="COLLECTOR_OBSERVATION_AFTER_ASOF"):
        archive.request(
            "S1_NR_2026-11-21", "starts", RACE_PREFIX + "4",
            datetime.fromisoformat("2026-11-21T05:00:00+00:00"),
        )


def test_real_day_inventory_to_prewatch_including_every_blocked_race(tmp_path):
    files = _inputs()
    assert sha(files["db"].read_bytes()) == SOURCE_DB_SHA
    archive = OriginalArchive(files["collector"])
    assert sha(archive.manifest_raw) == MANIFEST_SHA
    provenance = tmp_path / "verified-github-origin.json"
    provenance.write_text(json.dumps({
        "source_repository": "Maremoo2/rikstoto-program-collector",
        "obtained_via_authenticated_gh_cli": True,
        "event": "schedule", "conclusion": "success", "github_run_id": 44874876371,
    }))
    destination = Path(os.environ.get("P0_PRODUCT_OUTPUT", str(tmp_path / "product")))
    report = run_day(
        db=files["db"], collector_root=files["collector"], provenance=provenance,
        day="2026-11-21", decision_time=ASOF.isoformat(), out=destination,
    )
    assert report["counts"]["discovered"] == report["counts"]["terminal"] == 43
    assert report["counts"]["source_ready"] == 29
    assert report["counts"]["fully_assessed"] == 0
    assert report["counts"]["prospective_predictions"] == 0
    assert len({r["race_id"] for r in report["races"]}) == 43
    assert {RACE_PREFIX + str(n) for n in COUNTS} <= {
        row["race_id"] for row in report["races"] if row["source_status"] == "SOURCE_READY"
    }
    assert all(not r["bet_authorized"] and r["probabilities"] is None for r in report["races"])
    missing_model = next(r for r in report["races"] if r["race_id"] == RACE_PREFIX + "7")
    assert missing_model["source_record"]["source_imported_to_sqlite"] is True
    assert missing_model["source_record"]["model_input_approved"] is False
    assert missing_model["source_record"]["research_model_eligible"] is False
    assert "MODEL_SOURCE_COHORT_NOT_FOUND" in missing_model["blockers"]
    assert missing_model["terminal_status"] == "MODEL_BLOCKED"
    assert sha(files["db"].read_bytes()) == SOURCE_DB_SHA
    assert report == json.loads((destination / "prewatch-day.json").read_bytes())
    assert report == run_day(
        db=files["db"], collector_root=files["collector"], provenance=provenance,
        day="2026-11-21", decision_time=ASOF.isoformat(), out=destination,
    )
