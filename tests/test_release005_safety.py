"""RELEASE-005: primary PIT fail-closed gates and immutable, no-ticket signals."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbi.counterfactual import CounterfactualHypothesis, evaluate_counterfactual
from hbi.learning import build_learning_rows
from hbi.nightly import settle_open_shadow_tickets
from hbi.observatory import materialize_race_evaluations
from hbi.operations_report import build_operations_report
from hbi.prospective_gate import (
    qualification_index,
    qualify_prospective,
)
from hbi.provenance import record_decision_provenance
from hbi.replay_validation import run_runtime_replay_parity
from hbi.research_signal import record_win_research_signal
from hbi.storage import SQLiteStore
from hbi.t4_evidence import classify_t4_receipt

ROOT = Path(__file__).parents[1]
RACE = "test-r005-r1"
START = "2026-11-11T14:00:00+00:00"
CODE_SHA = "a" * 40
MODEL = "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL"
FUND = {"1": 0.7, "2": 0.3}
MARKET = {"1": 0.4, "2": 0.6}
COMBINED = {"1": 0.55, "2": 0.45}


def store(tmp_path):
    state = SQLiteStore(tmp_path / "state.sqlite")
    state.initialize(ROOT / "db" / "schema.sql")
    state.upsert_race({
        "race_id": RACE, "race_date": "2026-11-11", "country": "NO",
        "track": "Synthetic", "race_no": 1, "start_time_utc": START,
        "discipline": "trot", "distance_m": 2100, "start_method": "auto",
        "race_class": None, "created_at_utc": "2026-11-11T08:00:00+00:00",
    })
    return state


def frozen(state, status="WATCH"):
    state.insert_shadow_decision_run({
        "decision_run_id": "test-r005-decision",
        "race_id": RACE, "provider_raceday_key": "MO_NR_2026-11-11",
        "product": "V", "created_at_utc": "2026-11-11T13:55:40+00:00",
        "race_start_time_utc": START, "decision_status": status,
        "reason": None, "shadow_model_version": MODEL,
        "fundamental_model_version": "FUNDAMENTAL_CHAMPION_V1_1",
        "source_market_observed_at_utc": "2026-11-11T13:55:20+00:00",
        "target_minutes_to_start": 4.0,
        "actual_minutes_to_start": 260 / 60,
        "execution_latency_seconds": -20,
        "field_size": 2,
        "fundamental_probabilities_json": json.dumps(FUND),
        "market_probabilities_json": json.dumps(MARKET),
        "combined_probabilities_json": json.dumps(COMBINED),
        "ticket_count": 0,
    })
    return state.get_shadow_decision_run("test-r005-decision")


def _source(at="2026-11-11T13:55:20+00:00"):
    return {
        "source_uri": "https://www.rikstoto.no/api/official",
        "response_completed_at_utc": at,
        "body_sha256": "f" * 64,
    }


def attach(state, decision, *, commit="2026-11-11T13:55:50+00:00", race=None, model=None):
    receipt = classify_t4_receipt(
        race_id=race or RACE, race_start_utc=START,
        target_minutes=4, model_version=model or MODEL,
        decision_row=decision,
        sources={"WIN": _source(), "STARTS": _source(), "SCRATCHED": _source()},
        model_finished_at_utc="2026-11-11T13:55:35+00:00",
        decision_calculated_at_utc="2026-11-11T13:55:44+00:00",
        persist_started_at_utc="2026-11-11T13:55:46+00:00",
        persist_confirmed_at_utc=commit,
        github_sha=CODE_SHA,
    )
    with state.connect() as conn:
        conn.execute(
            "INSERT INTO system_run_manifests "
            "(run_id,run_type,started_at_utc,finished_at_utc,status,"
            "github_sha,metadata_json) VALUES (?,?,?,?,?,?,?)",
            ("test-r005-run", "WATCHER", "2026-11-11T13:54:00+00:00",
             "2026-11-11T13:56:10+00:00", "OK", CODE_SHA,
             json.dumps({"t4_attempts": [receipt]})),
        )
    return receipt


def test_verified_on_time_watch_receipt_qualifies_but_never_pit(tmp_path):
    state = store(tmp_path)
    row = frozen(state)
    receipt = attach(state, row)
    assert receipt["decision_persisted_before_t4"] is True
    result = qualify_prospective(row, qualification_index(state))
    assert result["qualified"] is True
    assert result["pit_certified"] is False
    assert result["shadow_executable"] is False
    state.settle_outcome(
        race_id=RACE, winner_selection_id="1",
        settled_at=datetime(2026, 11, 11, 14, 30, tzinfo=UTC),
    )
    assert materialize_race_evaluations(
        state, date(2026, 11, 11),
        created_at=datetime(2026, 11, 11, 15, tzinfo=UTC),
    ) == 1


@pytest.mark.parametrize("variation", [
    "missing", "late_commit", "wrong_race", "wrong_model",
])
def test_mismatched_unattested_or_late_receipt_blocks_all_consumer_promotions(
    tmp_path, variation,
):
    state = store(tmp_path)
    row = frozen(state)
    if variation != "missing":
        kwargs = {
            "late_commit": {"commit": "2026-11-11T13:56:01+00:00"},
            "wrong_race": {"race": "other-race"},
            "wrong_model": {"model": "other-model"},
        }[variation]
        attach(state, row, **kwargs)
    qualification = qualify_prospective(row, qualification_index(state))
    assert qualification["qualified"] is False
    assert qualification["pit_certified"] is False
    assert qualification["shadow_executable"] is False
    state.settle_outcome(
        race_id=RACE, winner_selection_id="1",
        settled_at=datetime(2026, 11, 11, 14, 30, tzinfo=UTC),
    )
    assert materialize_race_evaluations(
        state, date(2026, 11, 11),
        created_at=datetime(2026, 11, 11, 15, tzinfo=UTC),
    ) == 0
    assert state.fetch_table("race_research_evaluations") == []
    rows = build_learning_rows(state)
    assert rows[0]["primary_prospective_qualified"] is False
    assert rows[0]["evaluation_regime"] == "PROSPECTIVE_T4_V1"
    assert rows[0]["combined_log_loss"] is None
    assert record_decision_provenance(
        state, race_id=RACE, shadow_model_version=MODEL,
        target_minutes_to_start=4.0, policy={},
        recorded_at=datetime(2026, 11, 11, 15, tzinfo=UTC),
    ) is None
    result = evaluate_counterfactual(
        state,
        decision_run_id="test-r005-decision",
        hypothesis=CounterfactualHypothesis(
            name="synthetic", fundamental_weight=1,
            market_weight=1, material_conflict_threshold=20,
            minimum_edge=0.05, safety_margin=0.05,
        ),
    )
    assert result["status"] == "INSUFFICIENT_DATA"
    replay = run_runtime_replay_parity(state)
    assert replay["unqualified_new_regime_decisions"] == 1
    op = build_operations_report(
        state.path, date(2026, 11, 11), date(2026, 11, 11),
        now=datetime(2026, 11, 11, 15, tzinfo=UTC),
    )
    assert op["races"][0]["decisions"][0]["primary_prospective_qualified"] is False


def _assessment(*, p=0.55, odds=3.0):
    return SimpleNamespace(
        probability=p, available_price=odds, fair_odds=1 / p,
        expected_value=p * odds - 1,
        minimum_price=(1 / p) * 1.05,
    )


def record(state, assessment=None, full_probabilities=None):
    return record_win_research_signal(
        state, race_id=RACE, decision_run_id="test-r005-decision",
        selection_id="1", model_version=MODEL,
        fundamental_model_version="FUNDAMENTAL_CHAMPION_V1_1",
        fundamental=full_probabilities if full_probabilities is not None else FUND,
        market=MARKET, combined=COMBINED,
        assessment=assessment or _assessment(), minimum_edge=0.05,
        calculated_at=datetime(2026, 11, 11, 13, 55, 40, tzinfo=UTC),
        source_market_time="2026-11-11T13:55:20+00:00",
        source_receipts={"WIN": _source(), "STARTS": _source(), "SCRATCHED": _source()},
        rejected_candidates=[{"selection_id": "2", "decision": "PASS"}],
        contender_payload_id="contender:test-r005-decision",
    )


def test_signal_recorded_with_complete_fields_and_zero_tickets(tmp_path):
    state = store(tmp_path)
    recorded_at = record(state)
    assert recorded_at.tzinfo is not None
    signals = state.fetch_table("shadow_research_signals")
    assert len(signals) == 1
    signal = signals[0]
    assert signal["selection_id"] == "1"
    assert signal["horse_id_scope"] == "RACE_LOCAL_SELECTION_NOT_PERMANENT_HORSE_ID"
    assert signal["observed_win_odds"] == 3
    assert signal["p_win"] == 0.55
    assert signal["expected_value"] == pytest.approx(0.65)
    assert json.loads(signal["combined_probabilities_json"]) == COMBINED
    assert json.loads(signal["rejected_candidates_json"])[0]["selection_id"] == "2"
    assert signal["status"] == "SIGNAL_RECORDED"
    assert signal["t4_attested"] == 0
    assert signal["pit_certified"] == 0
    assert signal["shadow_ticket_created"] == 0
    assert state.open_shadow_tickets() == []
    assert len(state.fetch_table("shadow_tickets")) == 0
    # Repeated observer retries are idempotent and do not overwrite any signal.
    record(state)
    assert state.fetch_table("shadow_research_signals") == signals
    with pytest.raises(sqlite3.DatabaseError), state.connect() as conn:
        conn.execute(
            "UPDATE shadow_research_signals SET shadow_ticket_created=1"
        )


@pytest.mark.parametrize("assessment,full", [
    (_assessment(p=0.55, odds=1.0), None),
    (_assessment(p=0.0, odds=3.0) if False else None, {"1": 0.7}),
    (_assessment(p=0.99, odds=3.0), None),
])
def test_incomplete_or_inconsistent_signal_fails_closed(
    tmp_path, assessment, full,
):
    state = store(tmp_path)
    with pytest.raises(ValueError):
        record(state, assessment=assessment, full_probabilities=full)
    assert not state.fetch_table("shadow_research_signals")
    assert not state.fetch_table("shadow_tickets")


def test_nightly_ignores_research_signals(tmp_path):
    state = store(tmp_path)
    record(state)
    class NeverFetch:
        def raceday_results(self, _key):
            raise AssertionError("research signal must not be settled")
        def complete_results(self, _key, _race):
            raise AssertionError("research signal must not be settled")
    result = settle_open_shadow_tickets(state, client=NeverFetch())
    assert result.attempted == 0 if hasattr(result, "attempted") else result.settled == 0
    assert not state.fetch_table("shadow_tickets")
