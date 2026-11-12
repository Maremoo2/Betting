"""CLOUD-RUN-003: no fabricated model, and authorized schedule only."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.cloud_run003_discovery import resolve_daily_run
from hbi.cloud_run003_model import assess_and_run
from hbi.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-12"
RUN = {
    "databaseId": 43167334463, "event": "schedule", "headBranch": "main",
    "headSha": "0d860759e8065f50e9fd9f3371fa22438cfca1fc",
    "status": "completed", "conclusion": "success",
    "createdAt": "2026-11-12T06:19:29Z",
}
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)


def test_discover_dynamic_authorized_source_oslo_day():
    result = resolve_daily_run([RUN], current=NOW)
    assert result["run_id"] == RUN["databaseId"]
    assert result["day_oslo"] == DAY
    assert result["bet_authorized"] is False
    assert result["source_archive_verified"] is False


def test_discovery_rejects_manual_failed_or_wrong_day():
    for change in ({"event": "workflow_dispatch"}, {"conclusion": "failure"},
                   {"headBranch": "research"}, {"createdAt": "2026-11-11T06:19:29Z"}):
        with pytest.raises(ValueError, match="AUTHORIZED_RUN_UNAVAILABLE"):
            resolve_daily_run([{**RUN, **change}], current=NOW)


def test_discovery_newest_authorized_only():
    newer = {**RUN, "databaseId": RUN["databaseId"] + 1,
             "createdAt": "2026-11-12T09:19:29Z"}
    assert resolve_daily_run([RUN, newer], date_oslo=DAY, current=NOW)["run_id"] == newer["databaseId"]


def test_naive_discovery_clock_is_rejected():
    with pytest.raises(ValueError, match="CLOCK_NAIVE"):
        resolve_daily_run([RUN], current=datetime(2026, 11, 12, 12))


def test_model_input_gate_rejects_real_source_without_verified_history(tmp_path):
    store = SQLiteStore(tmp_path / "isolated.sqlite")
    store.initialize(ROOT / "db/schema.sql")
    store.apply_migrations(ROOT / "db/migrations")
    with store.connect() as db:
        db.execute(
            "INSERT INTO races (race_id,race_date,country,track,race_no,"
            "start_time_utc,discipline,created_at_utc) VALUES (?,?,?,?,?,?,?,?)",
            ("RIKSTOTO:S1_NR_2026-11-12:1", DAY, "SE", "Örebro", 1,
             "2026-11-12T13:00:00+00:00", "trot", NOW.isoformat()),
        )
        for selection in ("1", "2"):
            db.execute("INSERT INTO runners (race_id,selection_id,horse_name,scratched)"
                       " VALUES (?,?,?,0)",
                       ("RIKSTOTO:S1_NR_2026-11-12:1", selection, f"TEST {selection}"))
    result = assess_and_run(store, [
        {"race_id": "RIKSTOTO:S1_NR_2026-11-12:1",
         "source_ready": True, "payload_id": "research-only", "status": "SOURCE_READY_SNAPSHOT"}
    ], now=NOW)
    assert result["evaluated_races"] == 1
    assert result["model_input_complete"] == result["p_win_computed"] == 0
    assert "FULL_FIELD_FUNDAMENTAL_COHORT_MISSING" in result["records"][0]["reasons"]
    assert result["records"][0]["p_win"] is None
    assert store.fetch_table("predictions") == []
    assert store.fetch_table("shadow_tickets") == []
