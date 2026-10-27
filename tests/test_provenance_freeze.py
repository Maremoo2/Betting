"""Regression tests for write-once market provenance on frozen shadow runs."""
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hbi.decision import DecisionPolicy
from hbi.engine import CombinationPolicy, evaluate_race
from hbi.provenance import record_decision_provenance
from hbi.replay_validation import run_runtime_replay_parity
from hbi.shadow import ShadowPolicy
from hbi.storage import SQLiteStore

SCHEMA = Path(__file__).parents[1] / "db" / "schema.sql"
T0 = datetime(2026, 10, 27, 17, 56, tzinfo=UTC)
RACE = "p0-provenance-race"
ODDS = {"1": 2.5, "2": 3.5}
FUNDAMENTAL = {"1": 0.6, "2": 0.4}


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race({
        "race_id": RACE,
        "race_date": "2026-10-27",
        "country": "NO",
        "track": "Test only",
        "race_no": 1,
        "start_time_utc": "2026-10-27T18:00:00+00:00",
        "discipline": "trot",
        "distance_m": 2140,
        "start_method": "auto",
        "race_class": None,
        "created_at_utc": "2026-10-27T16:00:00+00:00",
    })
    result = evaluate_race(
        fundamental_probabilities=FUNDAMENTAL,
        market_decimal_odds=ODDS,
        executable_prices=ODDS,
        combination_policy=CombinationPolicy(1.0, 1.0, 20.0),
        decision_policy=DecisionPolicy(0.05, 0.05),
    )
    store.insert_shadow_decision_run({
        "decision_run_id": "frozen-1",
        "race_id": RACE,
        "provider_raceday_key": "TEST_2026-10-27",
        "product": "V",
        "created_at_utc": T0.isoformat(),
        "race_start_time_utc": "2026-10-27T18:00:00+00:00",
        "decision_status": "WATCH",
        "reason": "TEST_ONLY",
        "shadow_model_version": ShadowPolicy().model_version,
        "source_market_observed_at_utc": T0.isoformat(),
        "target_minutes_to_start": 4.0,
        "fundamental_probabilities_json": json.dumps(
            result.fundamental_probabilities, sort_keys=True
        ),
        "market_probabilities_json": json.dumps(
            result.market_probabilities, sort_keys=True
        ),
        "combined_probabilities_json": json.dumps(
            result.combined_probabilities, sort_keys=True
        ),
        "model_market_conflict_score": result.model_market_conflict_score,
        "ticket_count": 0,
    })
    return store


def _insert_quotes(store, at, odds):
    for selection, price in odds.items():
        store.insert_provider_market_snapshot(
            snapshot_id=f"{at.isoformat()}:{selection}",
            provider="rikstoto",
            race_id=RACE,
            product="V",
            selection_key=selection,
            observed_at=at,
            provider_updated_at=at,
            source_uri="https://example.test/win",
            odds_decimal=price,
        )


def _record(store, at):
    return record_decision_provenance(
        store,
        race_id=RACE,
        shadow_model_version=ShadowPolicy().model_version,
        target_minutes_to_start=4.0,
        policy=asdict(ShadowPolicy()),
        recorded_at=at,
    )


def test_frozen_odds_survive_later_snapshot_and_repeated_watcher(tmp_path):
    store = _store(tmp_path)
    _insert_quotes(store, T0, ODDS)
    later = T0 + timedelta(seconds=45)
    _insert_quotes(store, later, {"1": 10.0, "2": 1.5})
    assert _record(store, later) == "frozen-1"
    before = store.fetch_table("decision_provenance")
    assert len(before) == 1
    assert json.loads(before[0]["market_odds_json"]) == ODDS
    assert before[0]["recorded_at_utc"] == later.isoformat()
    assert _record(store, later + timedelta(seconds=10)) == "frozen-1"
    assert store.fetch_table("decision_provenance") == before
    report = run_runtime_replay_parity(store)
    assert report["status"] == "PASS"
    assert report["checked_decisions"] == 1
    assert report["mismatches"] == []


def test_existing_provenance_cannot_be_overwritten(tmp_path):
    store = _store(tmp_path)
    _insert_quotes(store, T0, ODDS)
    assert _record(store, T0) == "frozen-1"
    before = store.fetch_table("decision_provenance")
    store.upsert_decision_provenance({
        **before[0],
        "market_odds_json": json.dumps({"1": 10.0, "2": 1.5}),
        "recorded_at_utc": (T0 + timedelta(hours=1)).isoformat(),
    })
    assert store.fetch_table("decision_provenance") == before


def test_missing_original_market_never_promotes_later_quote(tmp_path):
    store = _store(tmp_path)
    _insert_quotes(store, T0 + timedelta(minutes=1), {"1": 5.0, "2": 2.0})
    assert _record(store, T0 + timedelta(minutes=1)) is None
    assert store.fetch_table("decision_provenance") == []
    assert run_runtime_replay_parity(store)["status"] == "NO_EVIDENCE"
