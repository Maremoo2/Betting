"""RELEASE-002: fail-closed operational T-4 timing; no strategy changes.

All clocks and races are synthetic test inputs; never prospective PIT proof.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hbi import watcher
from hbi.shadow import ShadowPolicy
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "state.sqlite")
    store.initialize(ROOT / "db" / "schema.sql")
    store.upsert_race({
        "race_id": "r1",
        "race_date": "2026-09-27", "country": "NO",
        "track": "Bjerke", "race_no": 1,
        "start_time_utc": "2026-09-27T18:00:00+00:00",
        "discipline": "trot", "distance_m": 2100,
        "start_method": "auto", "race_class": None,
        "created_at_utc": "2026-09-27T10:00:00+00:00",
    })
    return store


START = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)
CUTOFF = START - timedelta(minutes=4)
RACE = {
    "race_id": "r1",
    "provider_raceday_key": "BJ_NR_2026-09-27",
    "race_number": 1,
    "start_time_utc": START.isoformat(),
    "raw_json": '{"single_leg_products":["V"],"pools":[]}',
}


@pytest.mark.parametrize("delta_micros", [0, 1, 100_000, 1_000_000, 58_275_571])
def test_t4_hard_stop_at_and_after_boundary(tmp_path, delta_micros):
    store = _store(tmp_path)
    late = CUTOFF + timedelta(microseconds=delta_micros)
    assert watcher._reject_missed_t4(
        store, race=RACE, policy=ShadowPolicy(), observed_now=late,
    )
    decisions = store.fetch_table("shadow_decision_runs")
    assert len(decisions) == 1
    assert decisions[0]["decision_status"] == "NOT_EXECUTABLE"
    assert decisions[0]["reason"] == "T4_CUTOFF_MISSED"
    assert decisions[0]["ticket_count"] == 0
    assert decisions[0]["created_at_utc"] == late.isoformat()
    assert not store.fetch_table("shadow_tickets")

    # Repeat after the frozen decision: no mutation and no duplicates.
    again = late + timedelta(seconds=15)
    assert watcher._reject_missed_t4(
        store, race=RACE, policy=ShadowPolicy(), observed_now=again,
    )
    assert store.fetch_table("shadow_decision_runs") == decisions


def test_t4_before_cutoff_passes_only_timing_gate(tmp_path):
    store = _store(tmp_path)
    assert not watcher._reject_missed_t4(
        store, race=RACE, policy=ShadowPolicy(),
        observed_now=CUTOFF - timedelta(microseconds=1),
    )
    assert store.fetch_table("shadow_decision_runs") == []


class FakeCollector:
    def __init__(self, _store):
        self.calls: list[str] = []

    def discover(self, _now):
        self.calls.append("discover")
        return [RACE]

    def due_races(self, **_):
        self.calls.append("due")
        return [RACE]

    def collect_market(self, **_):
        self.calls.append("market")
        return 0, 0

    def collect_pool_context(self, **_):
        self.calls.append("pool")
        return 0, 0

    def collect_fundamentals(self, **_):
        self.calls.append("fundamentals")
        return 0, True, None


def setup(monkeypatch, store):
    fake = FakeCollector(store)
    monkeypatch.setattr(watcher, "_store", lambda _db: store)
    monkeypatch.setattr(watcher, "RikstotoCollector", lambda _store: fake)
    monkeypatch.setattr(watcher, "record_decision_provenance", lambda *a, **kw: None)
    return fake


def test_runner_started_after_t4_never_reprices_or_bets(monkeypatch, tmp_path):
    store = _store(tmp_path)
    collector = setup(monkeypatch, store)
    shadow = Mock(side_effect=AssertionError("late shadow decision"))
    model = Mock(side_effect=AssertionError("late model calculation"))
    monkeypatch.setattr(watcher, "run_win_shadow_decision", shadow)
    monkeypatch.setattr(watcher, "run_and_persist_fundamental", model)
    audit = watcher.run_watcher(
        db_path="IGNORED", now=CUTOFF + timedelta(seconds=1), allow_sleep=False,
    )
    assert audit.not_executable == 1
    assert audit.passes == 0
    assert audit.shadow_bets_created == 0
    assert audit.t4_attempts == []
    assert audit.cutoff_rejections == [{
        "race_id": store.fetch_table("shadow_decision_runs")[0]["race_id"],
        "race_start_utc": (CUTOFF + timedelta(minutes=4)).isoformat(),
        "cutoff_utc": CUTOFF.isoformat(),
        "observed_at_utc": (CUTOFF + timedelta(seconds=1)).isoformat(),
        "stage": "BEFORE_FINAL_SOURCE_REFRESH",
        "reason": "T4_CUTOFF_MISSED",
    }]
    assert collector.calls == ["discover", "due", "market", "pool", "fundamentals"]
    assert shadow.call_count == model.call_count == 0
    assert store.fetch_table("shadow_decision_runs")[0]["reason"] == "T4_CUTOFF_MISSED"


def clock(monkeypatch, *moments):
    real = datetime
    it = iter(moments)

    class Clock:
        @staticmethod
        def now(_tz):
            return next(it)

        @staticmethod
        def fromisoformat(text):
            return real.fromisoformat(text)

    monkeypatch.setattr(watcher, "datetime", Clock)


def test_provider_crossing_t4_blocks_model_and_shadow(monkeypatch, tmp_path):
    store = _store(tmp_path)
    fake = setup(monkeypatch, store)
    model = Mock(side_effect=AssertionError("provider was late"))
    shadow = Mock(side_effect=AssertionError("provider was late"))
    monkeypatch.setattr(watcher, "run_and_persist_fundamental", model)
    monkeypatch.setattr(watcher, "run_win_shadow_decision", shadow)
    clock(
        monkeypatch,
        CUTOFF - timedelta(seconds=80),
        CUTOFF - timedelta(seconds=50),
        CUTOFF + timedelta(microseconds=1),
        CUTOFF + timedelta(seconds=2),
    )
    audit = watcher.run_watcher(db_path="IGNORED", allow_sleep=False)
    assert audit.not_executable == 1 and audit.passes == 0
    assert audit.cutoff_rejections[0]["stage"] == "AFTER_FINAL_SOURCE_REFRESH"
    assert audit.t4_attempts == []
    assert fake.calls.count("market") == 2
    model.assert_not_called()
    shadow.assert_not_called()
    assert store.fetch_table("shadow_decision_runs")[0]["reason"] == "T4_CUTOFF_MISSED"


def test_model_crossing_t4_blocks_shadow(monkeypatch, tmp_path):
    store = _store(tmp_path)
    setup(monkeypatch, store)
    model = Mock(return_value=SimpleNamespace(shadow_eligible=True))
    shadow = Mock(side_effect=AssertionError("model completed after T4"))
    monkeypatch.setattr(watcher, "run_and_persist_fundamental", model)
    monkeypatch.setattr(watcher, "run_win_shadow_decision", shadow)
    clock(
        monkeypatch,
        CUTOFF - timedelta(seconds=100),
        CUTOFF - timedelta(seconds=60),
        CUTOFF - timedelta(seconds=20),
        CUTOFF + timedelta(microseconds=1),
        CUTOFF + timedelta(seconds=1),
    )
    audit = watcher.run_watcher(db_path="IGNORED", allow_sleep=False)
    assert audit.fundamental_runs == 1
    assert audit.cutoff_rejections[0]["stage"] == "AFTER_MODEL_STAGE"
    assert audit.t4_attempts == []
    assert audit.not_executable == 1 and audit.passes == 0
    shadow.assert_not_called()
    assert store.fetch_table("shadow_decision_runs")[0]["reason"] == "T4_CUTOFF_MISSED"


def test_before_t4_still_permits_existing_watch_no_bet(monkeypatch, tmp_path):
    store = _store(tmp_path)
    setup(monkeypatch, store)
    model = Mock(return_value=SimpleNamespace(shadow_eligible=True))
    decision = Mock(return_value=SimpleNamespace(status="WATCH", created=0))
    monkeypatch.setattr(watcher, "run_and_persist_fundamental", model)
    monkeypatch.setattr(watcher, "run_win_shadow_decision", decision)
    clock(
        monkeypatch,
        CUTOFF - timedelta(seconds=110),
        CUTOFF - timedelta(seconds=80),
        CUTOFF - timedelta(seconds=50),
        CUTOFF - timedelta(seconds=30),
        CUTOFF - timedelta(seconds=20),
    )
    audit = watcher.run_watcher(db_path="IGNORED", allow_sleep=False)
    assert audit.passes == 1 and audit.shadow_bets_created == 0
    assert audit.not_executable == 0
    assert audit.cutoff_rejections == []
    assert decision.call_count == 1
    assert decision.call_args.kwargs["decision_time"] == CUTOFF - timedelta(seconds=30)


def test_refresh_schedule_is_early_but_cutoff_remains_four_minutes():
    assert watcher.PRE_T4_REFRESH_LEAD == timedelta(seconds=60)
    assert START - timedelta(minutes=4) - watcher.PRE_T4_REFRESH_LEAD == (
        START - timedelta(minutes=5)
    )
    assert ShadowPolicy().target_minutes_to_start == 4.0
