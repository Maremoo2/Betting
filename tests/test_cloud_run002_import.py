"""CLOUD-RUN-002: existing SQLite only; source tests never grant BET/PIT."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.cloud_run002_import import SourceRace, persist_source
from hbi.ingestion import RaceCard
from hbi.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"
STAMP = datetime(2026, 11, 12, 6, 20, tzinfo=UTC)


def store(tmp_path):
    db = SQLiteStore(tmp_path / "hbi.sqlite")
    db.initialize(SCHEMA)
    db.apply_migrations(MIGRATIONS)
    return db


def race(number=1, name="ORIGINAL HORSE", sha="a" * 64):
    race_id = f"RIKSTOTO:S1_NR_2026-11-12:{number}"
    return SourceRace(
        card=RaceCard(
            race={
                "race_id": race_id, "race_date": "2026-11-12",
                "country": "SE", "track": "Örebro", "race_no": number,
                "start_time_utc": "2026-11-12T11:20:00+00:00",
                "discipline": "trot", "distance_m": 2100,
                "start_method": "Autostart", "race_class": None,
                "created_at_utc": STAMP.isoformat(),
            },
            runners=({
                "race_id": race_id, "selection_id": "1", "horse_name": name,
                "post_position": 1, "driver_or_jockey": "DRIVER",
                "trainer": None, "scratched": 0,
            },),
        ),
        meeting_id="S1_NR_2026-11-12", race_no=number,
        received_at=STAMP,
        source_uri="https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/S1_NR_2026-11-12",
        payload={
            "schema": "CLOUD_RUN002_COLLECTOR_SOURCE_V1",
            "race_id": race_id, "archive_sha256": sha,
            "source_ready_snapshot": True, "model_ready": False,
            "bet_ready": False, "pit_certified": False,
            "identity_status": "UNATTESTED", "horse_name": name,
        },
    )


def test_real_canonical_tables_and_idempotent_second_run(tmp_path):
    db = store(tmp_path)
    first = persist_source(db, [race()])
    before = {name: db.fetch_table(name) for name in
              ("races", "runners", "provider_payloads")}
    second = persist_source(db, [race()])
    assert first == second
    assert {name: db.fetch_table(name) for name in before} == before
    assert first["source_ready"] == 1
    assert first["model_ready"] == first["bet_ready"] == 0
    assert db.fetch_table("predictions") == []
    assert db.fetch_table("shadow_decision_runs") == []


def test_new_version_is_append_only_and_does_not_promote(tmp_path):
    db = store(tmp_path)
    old = race()
    persist_source(db, [old])
    newer = replace(
        race(sha="b" * 64, name="CHANGED HORSE"),
        received_at=datetime(2026, 11, 12, 6, 21, tzinfo=UTC),
    )
    report = persist_source(db, [newer])
    assert report["source_ready"] == 0
    assert report["revisions_needing_review"] == 1
    assert len(db.fetch_table("provider_payloads")) == 2
    assert db.fetch_table("runners")[0]["horse_name"] == "ORIGINAL HORSE"
    assert report["records"][0]["status"] == "REVISION_REQUIRES_REVIEW"


def test_existing_payload_id_with_different_bytes_is_conflict(tmp_path):
    db = store(tmp_path)
    persist_source(db, [race()])
    with db.connect() as conn:
        conn.execute("UPDATE provider_payloads SET payload_json='{}'")
    with pytest.raises(ValueError, match="PAYLOAD_ID_CONFLICT"):
        persist_source(db, [race()])


def test_conflicting_existing_race_fails_closed_and_rolls_back(tmp_path):
    db = store(tmp_path)
    one = race(1)
    persist_source(db, [one])
    conflict = replace(one, card=RaceCard(
        race=dict(one.card.race, start_time_utc="2026-11-12T10:20:00+00:00"),
        runners=one.card.runners,
    ))
    with pytest.raises(ValueError, match="EXISTING_CANONICAL_RACE_CONFLICT"):
        persist_source(db, [race(2), conflict])
    assert len(db.fetch_table("races")) == 1
    assert len(db.fetch_table("provider_payloads")) == 1


def test_new_source_cannot_authorize_bet_or_permanent_identity(tmp_path):
    db = store(tmp_path)
    result = persist_source(db, [race()])
    assert all(not r["model_ready"] and not r["bet_ready"] for r in result["records"])
    assert result["pit_certified"] is False
    assert result["bet_authorized"] is False
    assert db.fetch_table("shadow_tickets") == []
