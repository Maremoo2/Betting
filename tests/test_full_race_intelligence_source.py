"""All-physical-race auto-sidecar and immutable source-link safeguards."""
from __future__ import annotations

import hashlib
import json
import runpy
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
scanner = runpy.run_path(str(ROOT / "scripts/full_race_intelligence_core003_readonly.py"))
original = runpy.run_path(str(ROOT / "scripts/full_race_intelligence_readonly.py"))


def test_automatic_scanner_lists_all_upcoming_physical_races_without_pseudo_bets(tmp_path):
    db = tmp_path / "pilot.sqlite"
    connection = sqlite3.connect(db)
    connection.executescript("""
        CREATE TABLE races (
            race_id TEXT, track TEXT, race_no INTEGER,
            start_time_utc TEXT, discipline TEXT
        );
        CREATE TABLE runners (
            race_id TEXT, selection_id TEXT, horse_name TEXT, scratched INTEGER
        );
    """)
    future = "RIKSTOTO:S2_NR_2026-11-06:4"
    past = "RIKSTOTO:S2_NR_2026-11-06:1"
    connection.executemany(
        "INSERT INTO races VALUES (?,?,?,?,?)",
        [(future,"Färjestad",4,"2026-11-06T18:30:00+00:00","trot"),
         (past,"Färjestad",1,"2026-11-06T18:00:00+00:00","trot")],
    )
    for rid in (future,past):
        connection.executemany(
            "INSERT INTO runners VALUES (?,?,?,?)",
            [(rid,"1","First",0),(rid,"2","Second",0)],
        )
    connection.commit()
    connection.close()
    result = scanner["analyze"](
        db,tmp_path / "no-source-models",
        cutoff=datetime(2026,11,6,18,10,tzinfo=UTC),
    )
    assert result["all_physical_races_discovered"] == 1
    assert result["fully_modelled_frozen_research_fields"] == 0
    assert result["no_provider_calls"] is True
    assert result["source_database_read_only"] is True
    race = result["races"][0]
    assert race["physical_race_id"] == future
    assert race["full_field_model_valid"] is False
    assert race["decision"] == "NOT_EXECUTABLE"
    assert all(x["p_win"] is None for x in race["runners"])


def test_no_unverified_model_bytes_from_archive(tmp_path):
    root = tmp_path / "models"
    folder = root / "race-001"
    folder.mkdir(parents=True)
    (folder / "shadow.json").write_text("{}")
    (root / "cohort-index.json").write_text(json.dumps({
        "schema":"BET_MVP_002_FIXED_COHORT_INDEX_V1",
        "bet_authority":False,
        "processed":[{
            "race_id":"RIKSTOTO:S2_NR_2026-11-06:4",
            "directory":"bet-mvp-shadow/race-001",
            "report_sha256":"0" * 64,
        }],
    }))
    with pytest.raises(ValueError,match="MODEL_SOURCE_SHA_MISMATCH"):
        scanner["frozen_models"](root)


def test_original_response_sha_and_clock_bound_to_exact_receipt(tmp_path):
    folder = tmp_path
    (folder / "originals").mkdir()
    raw = b'{"result":[]}'
    sha = hashlib.sha256(raw).hexdigest()
    (folder / "originals" / (sha+".json")).write_bytes(raw)
    receipt = {
        "request_path":"/game/S2_NR_2026-11-06/betdistribution/winodds/4",
        "http_status":200,"success":True,
        "original_relative_path":"originals/"+sha+".json",
        "response_sha256":sha,
        "response_completed_utc":"2026-11-06T18:13:10+00:00",
    }
    source = {"original_receipts":[receipt]}
    assert original["_receipt"](folder,source,receipt["request_path"])["response_sha256"] == sha
    (folder / "originals" / (sha+".json")).write_bytes(b"tampered")
    with pytest.raises(ValueError,match="ORIGINAL_BYTES_SHA_MISMATCH"):
        original["_receipt"](folder,source,receipt["request_path"])


def test_no_cross_report_fundamental_reuse_when_original_source_sha_differs():
    bogus = {
        "schema":"WEEKEND_AUTHENTIC_CHAMPION_V1_1_RESEARCH_V1",
        "bet_authority":False,
        "actual_model_version":"FUNDAMENTAL_CHAMPION_V1_1",
        "original_report_sha256":"a"*64,
        "rounds":{},
    }
    with pytest.raises(ValueError,match="FROZEN_RESEARCH_SOURCE_NOT_ATTESTED"):
        original["_models"](json.dumps(bogus).encode(), "b"*64)
