"""Regression tests for write-once market provenance on frozen shadow runs."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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


def test_cannot_attach_later_odds_to_frozen_market_distribution(tmp_path):
    """Even exact source timestamps cannot launder conflicting prices."""
    store = _store(tmp_path)
    _insert_quotes(store, T0, {"1": 10.0, "2": 1.5})
    assert _record(store, T0 + timedelta(minutes=10)) is None
    assert store.fetch_table("decision_provenance") == []
    assert run_runtime_replay_parity(store)["status"] == "NO_EVIDENCE"


def test_partial_original_market_cannot_attach_provenance(tmp_path):
    store = _store(tmp_path)
    _insert_quotes(store, T0, {"1": ODDS["1"]})
    assert _record(store, T0) is None
    assert store.fetch_table("decision_provenance") == []


def test_market_timestamp_after_frozen_decision_is_rejected(tmp_path):
    store = _store(tmp_path)
    future = T0 + timedelta(minutes=1)
    with store.connect() as connection:
        connection.execute(
            "UPDATE shadow_decision_runs SET source_market_observed_at_utc=? "
            "WHERE decision_run_id='frozen-1'",
            (future.isoformat(),),
        )
    _insert_quotes(store, future, ODDS)
    assert _record(store, future) is None
    assert store.fetch_table("decision_provenance") == []


def test_valid_later_recording_still_uses_original_quotes(tmp_path):
    store = _store(tmp_path)
    _insert_quotes(store, T0, ODDS)
    _insert_quotes(store, T0 + timedelta(minutes=10), {"1": 10.0, "2": 1.5})
    assert _record(store, T0 + timedelta(minutes=11)) == "frozen-1"
    assert json.loads(store.fetch_table("decision_provenance")[0]["market_odds_json"]) == ODDS
    assert run_runtime_replay_parity(store)["status"] == "PASS"


def test_audit_retains_late_provenance_but_replays_original_prices(tmp_path):
    store = _store(tmp_path)
    _insert_quotes(store, T0, ODDS)
    _record(store, T0)
    with store.connect() as con:
        con.execute("UPDATE decision_provenance SET market_odds_json=?, recorded_at_utc=?",
                    (json.dumps({"1": 10.0, "2": 1.5}),
                     (T0 + timedelta(minutes=10)).isoformat()))
    original = store.fetch_table("decision_provenance")
    report = run_runtime_replay_parity(store)
    assert report["status"] == "PASS"
    assert len(report["provenance_differences"]) == 1
    assert store.fetch_table("decision_provenance") == original


@pytest.mark.parametrize("damage", ["missing", "partial", "changed", "future"])
def test_audit_cannot_replace_unverifiable_original_with_provenance(tmp_path, damage):
    store = _store(tmp_path)
    _insert_quotes(store, T0, ODDS)
    _record(store, T0)
    with store.connect() as con:
        if damage == "missing":
            con.execute("DELETE FROM provider_market_snapshots")
        elif damage == "partial":
            con.execute("DELETE FROM provider_market_snapshots WHERE selection_key='2'")
        elif damage == "changed":
            con.execute("UPDATE provider_market_snapshots SET odds_decimal=9 WHERE selection_key='1'")
        else:
            future = (T0 + timedelta(seconds=1)).isoformat()
            con.execute("UPDATE provider_market_snapshots SET observed_at_utc=?", (future,))
            con.execute("UPDATE shadow_decision_runs SET source_market_observed_at_utc=?", (future,))
    report = run_runtime_replay_parity(store)
    assert report["status"] == "FAIL"
    assert report["checked_decisions"] == 1
    assert report["skipped_decisions"] == 0
    assert report["mismatches"][0]["reasons"][0].startswith("original_market_unverifiable:")


def test_original_exact_v1_restore_replay_if_available():
    """No historical fixture reconstruction; an optional original-byte acceptance."""
    path = os.environ.get("MVP021_EXACT_RESTORE_DB")
    if not path:
        pytest.skip("Set MVP021_EXACT_RESTORE_DB to original artifact 13359900337 SQLite")
    db = Path(path)
    expected = "01e0432d06c04667723f528510944b16d54e1badf103cf51c07e7db0c96e5471"
    with db.open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == expected

    class ReadOnlyOriginal(SQLiteStore):
        @contextmanager
        def connect(self):
            con = sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)
            con.row_factory = sqlite3.Row
            try:
                yield con
            finally:
                con.close()

        def insert_integrity_audit(self, row):
            pass  # Audit result stays in the test; the original is read-only.

    result = run_runtime_replay_parity(ReadOnlyOriginal(db))
    assert result["status"] == "PASS"
    assert result["checked_decisions"] == 361
    assert result["skipped_decisions"] == 554
    assert len(result["provenance_differences"]) == 5
    with db.open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == expected
