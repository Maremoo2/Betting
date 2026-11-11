"""RELEASE-004 negative and positive clocks; synthetic, never PIT evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hbi.shadow import ShadowPolicy, run_win_shadow_decision
from hbi.storage import SQLiteStore
from hbi.t4_evidence import SCHEMA, classify_t4_receipt

BASE = datetime(2026, 11, 11, 13, 56, tzinfo=UTC)


def stamp(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def _record():
    return {
        "race_id": "R1",
        "created_at_utc": stamp(-50),
        "decision_status": "WATCH",
        "shadow_model_version": "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL",
    }


def _source(seconds=-45):
    return {
        "source_uri": "https://www.rikstoto.no/api/example",
        "response_completed_at_utc": stamp(seconds),
        "body_sha256": "a" * 64,
    }


def _inputs():
    return {
        "race_id": "R1", "race_start_utc": stamp(240),
        "target_minutes": 4.0,
        "model_version": "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL",
        "decision_row": _record(),
        "sources": {
            "WIN": _source(-45),
            "STARTS": _source(-80),
            "SCRATCHED": _source(-60),
        },
        "model_finished_at_utc": stamp(-30),
        "decision_calculated_at_utc": stamp(-20),
        "persist_started_at_utc": stamp(-15),
        "persist_confirmed_at_utc": stamp(-10),
    }


def test_complete_synthetic_timing_receipt_is_not_pit():
    proof = classify_t4_receipt(**_inputs())
    assert proof["schema"] == SCHEMA
    assert proof["decision_persisted_before_t4"] is True
    assert proof["pit_certified"] is False
    assert proof["shadow_executable"] is False
    assert proof["readback_row_sha256"]
    assert proof["reasons"] == []


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("model_finished_at_utc", stamp(1), "MODEL_FINISHED_AT_OR_AFTER_T4"),
    ("decision_calculated_at_utc", stamp(1), "DECISION_CALCULATED_AT_OR_AFTER_T4"),
    ("persist_started_at_utc", stamp(1), "PERSIST_STARTED_AT_OR_AFTER_T4"),
    ("persist_confirmed_at_utc", stamp(1), "PERSIST_CONFIRMED_AT_OR_AFTER_T4"),
    ("persist_confirmed_at_utc", None, "PERSIST_CONFIRMED_UNATTESTED"),
    ("persist_confirmed_at_utc", "2026-11-11T13:55:59",
     "PERSIST_CONFIRMED_UNATTESTED"),
    ("persist_confirmed_at_utc", stamp(-70), "RUNTIME_CLOCK_ORDER_INVALID"),
    ("decision_row", None, "DECISION_READBACK_MISSING_OR_WRONG_RACE"),
])
def test_missing_or_late_stage_fails_closed(field, value, reason):
    inp = _inputs()
    inp[field] = value
    proof = classify_t4_receipt(**inp)
    assert not proof["decision_persisted_before_t4"]
    assert reason in proof["reasons"]
    assert not proof["shadow_executable"]


@pytest.mark.parametrize("name", ["WIN", "STARTS", "SCRATCHED"])
def test_provider_response_after_t4_never_qualifies(name):
    inp = _inputs()
    inp["sources"][name] = _source(0)
    proof = classify_t4_receipt(**inp)
    assert not proof["decision_persisted_before_t4"]
    assert f"{name}_AT_OR_AFTER_T4" in proof["reasons"]


@pytest.mark.parametrize("name", ["WIN", "STARTS", "SCRATCHED"])
def test_missing_provider_hash_never_qualifies(name):
    inp = _inputs()
    inp["sources"][name] = _source()
    inp["sources"][name]["body_sha256"] = None
    proof = classify_t4_receipt(**inp)
    assert f"{name}_SOURCE_COMPLETION_UNATTESTED" in proof["reasons"]
    assert not proof["decision_persisted_before_t4"]


def test_inconsistent_original_frozen_timestamp_fails_closed():
    inp = _inputs()
    inp["decision_row"]["created_at_utc"] = stamp(2)
    proof = classify_t4_receipt(**inp)
    assert "FROZEN_CLOCK_AFTER_CALCULATION" in proof["reasons"]
    assert not proof["decision_persisted_before_t4"]


def test_unsupported_shadow_bet_requires_separate_ticket_protocol():
    inp = _inputs()
    inp["decision_row"]["decision_status"] = "SHADOW_BET"
    proof = classify_t4_receipt(**inp)
    assert "DECISION_NOT_PASS_OR_WATCH" in proof["reasons"]
    assert not proof["shadow_executable"]


ROOT = Path(__file__).parents[1]


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(ROOT / "db" / "schema.sql")
    store.upsert_race({
        "race_id": "r1", "race_date": "2026-09-27",
        "country": "NO", "track": "Bjerke", "race_no": 1,
        "start_time_utc": "2026-09-27T18:00:00+00:00",
        "discipline": "trot", "distance_m": 2100,
        "start_method": "auto", "race_class": None,
        "created_at_utc": "2026-09-27T10:00:00+00:00",
    })
    return store


def _add_market_and_model(store):
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    earlier = datetime(2026, 9, 27, 17, 50, tzinfo=UTC)
    for selection, odds, prob in [("1", 3.0, 0.7), ("2", 2.0, 0.3)]:
        store.insert_provider_market_snapshot(
            snapshot_id=f"s-{selection}", provider="rikstoto",
            race_id="r1", product="V", selection_key=selection,
            observed_at=observed, provider_updated_at=observed,
            source_uri="https://example/win", odds_decimal=odds,
        )
        store.insert_prediction(
            prediction_id=f"p-{selection}", race_id="r1",
            selection_id=selection, created_at=earlier,
            model_name="fundamental", model_version="test",
            layer="FUNDAMENTAL", probability=prob, feature_as_of=earlier,
        )


def test_guarded_shadow_never_creates_paper_ticket_before_attestation(tmp_path):
    store = _store(tmp_path)
    _add_market_and_model(store)
    when = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    times = iter([
        datetime(2026, 9, 27, 17, 55, 50, tzinfo=UTC),
        datetime(2026, 9, 27, 17, 55, 51, tzinfo=UTC),
        datetime(2026, 9, 27, 17, 55, 52, tzinfo=UTC),
        datetime(2026, 9, 27, 17, 55, 53, tzinfo=UTC),
    ])
    result = run_win_shadow_decision(
        store, race_id="r1", provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=datetime(2026, 9, 27, 18, tzinfo=UTC),
        decision_time=when,
        policy=ShadowPolicy(material_conflict_threshold=100),
        t4_cutoff=datetime(2026, 9, 27, 17, 57, tzinfo=UTC),
        wall_clock=lambda: next(times),
    )
    # A synthetic 17:57 guard permits the normal 17:56 quote window.
    # Whatever the model's value verdict, no executable paper ticket is written.
    assert result.status in {"WATCH", "T4_PENDING_ATTESTATION"}
    assert not store.fetch_table("shadow_tickets")


def test_guarded_shadow_rejects_late_entry_and_is_immutable(tmp_path):
    store = _store(tmp_path)
    cutoff = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    result = run_win_shadow_decision(
        store, race_id="r1", provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=datetime(2026, 9, 27, 18, tzinfo=UTC),
        decision_time=cutoff - timedelta(seconds=10),
        t4_cutoff=cutoff,
        wall_clock=lambda: cutoff,
    )
    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == "T4_DECISION_ENTRY_LATE"
    assert store.fetch_table("shadow_decision_runs")[0]["decision_status"] == "NOT_EXECUTABLE"
    assert not store.fetch_table("shadow_tickets")
