"""Synthetic SQLite paper records only. Never authentic race or betting evidence."""
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.storage import SQLiteStore


@pytest.fixture
def state(tmp_path):
    store = SQLiteStore(tmp_path / "synthetic-paper.sqlite")
    root = Path(__file__).parents[1]
    store.initialize(root / "db/schema.sql")
    store.upsert_race({
        "race_id": "SYNTHETIC", "race_date": "2026-11-22", "country": "NO",
        "track": "TEST_ONLY", "race_no": 1, "start_time_utc": "2026-11-22T18:00:00+00:00",
        "discipline": "trot", "created_at_utc": "2026-11-22T10:00:00+00:00",
    })
    return store


def decision():
    return {
        "decision_run_id": "synthetic-run", "race_id": "SYNTHETIC",
        "provider_raceday_key": "TEST", "product": "V",
        "created_at_utc": "2026-11-22T17:55:00+00:00",
        "race_start_time_utc": "2026-11-22T18:00:00+00:00", "decision_status": "PASS",
        "shadow_model_version": "TEST_ONLY", "target_minutes_to_start": 4,
        "ticket_count": 0, "field_size": 2,
        "fundamental_probabilities_json": '{"1":0.5,"2":0.5}',
    }


def ticket():
    return {
        "ticket_id": "synthetic-ticket", "dedupe_key": "synthetic-intent",
        "created_at_utc": "2026-11-22T17:55:00+00:00",
        "decision_time_utc": "2026-11-22T17:55:00+00:00", "race_id": "SYNTHETIC",
        "provider": "TEST_ONLY", "product": "V", "decision": "BET",
        "status": "SHADOW_BET", "selections_json": '["1"]', "stake_nok": 25,
        "model_version": "TEST_ONLY",
    }


def test_identical_decision_retry_returns_false_without_rewriting(state):
    row = decision()
    assert state.insert_shadow_decision_run(row)
    before = state.fetch_table("shadow_decision_runs")
    assert state.insert_shadow_decision_run(row) is False
    assert state.fetch_table("shadow_decision_runs") == before


def test_same_decision_key_with_other_probability_vector_is_explicit_conflict(state):
    row = decision()
    state.insert_shadow_decision_run(row)
    before = state.fetch_table("shadow_decision_runs")
    with pytest.raises(ValueError, match="SHADOW_DECISION_RUN_PAYLOAD_CONFLICT"):
        state.insert_shadow_decision_run(dict(
            row, fundamental_probabilities_json='{"1":0.7,"2":0.3}'))
    assert state.fetch_table("shadow_decision_runs") == before


def test_natural_decision_key_cannot_silently_hide_a_different_run_identity(state):
    row = decision()
    state.insert_shadow_decision_run(row)
    with pytest.raises(ValueError, match="SHADOW_DECISION_RUN_PAYLOAD_CONFLICT"):
        state.insert_shadow_decision_run(dict(row, decision_run_id="other-run"))
    assert len(state.fetch_table("shadow_decision_runs")) == 1


def test_ticket_dedupe_accepts_same_intent_with_fresh_request_uuid(state):
    row = ticket()
    assert state.create_shadow_ticket(row)
    assert state.create_shadow_ticket(row) is False
    assert state.create_shadow_ticket(dict(row, ticket_id="retry-uuid")) is False
    assert len(state.fetch_table("shadow_tickets")) == 1


@pytest.mark.parametrize("identity", ["synthetic-ticket", "retry-uuid"])
def test_ticket_key_cannot_hide_changed_stake(state, identity):
    row = ticket()
    state.create_shadow_ticket(row)
    before = state.fetch_table("shadow_tickets")
    with pytest.raises(ValueError, match="SHADOW_TICKET_PAYLOAD_CONFLICT"):
        state.create_shadow_ticket(dict(row, ticket_id=identity, stake_nok=50))
    assert state.fetch_table("shadow_tickets") == before


def test_retry_does_not_reverse_existing_settlement(state):
    row = ticket()
    state.create_shadow_ticket(row)
    state.settle_shadow_ticket(
        ticket_id=row["ticket_id"], settled_at=datetime(2026, 11, 22, 19, tzinfo=UTC),
        gross_return_nok=0, net_pnl_nok=-25, settlement_source_uri="test-only://result",
        result={"fixture": "SYNTHETIC_UNIT_TEST_ONLY"},
    )
    before = state.fetch_table("shadow_tickets")
    assert state.create_shadow_ticket(row) is False
    assert state.fetch_table("shadow_tickets") == before
    assert before[0]["status"] == "SETTLED"


@pytest.mark.parametrize("kind", ["decision", "ticket"])
def test_invalid_required_fields_cannot_be_reported_as_idempotent_retry(state, kind):
    row = decision() if kind == "decision" else ticket()
    row["created_at_utc"] = None
    insert = state.insert_shadow_decision_run if kind == "decision" else state.create_shadow_ticket
    with pytest.raises(sqlite3.IntegrityError):
        insert(row)
    assert state.fetch_table("shadow_decision_runs") == []
    assert state.fetch_table("shadow_tickets") == []
