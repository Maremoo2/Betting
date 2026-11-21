"""Software contracts, not synthetic evidence of a live field or BET."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from hbi.prewatch_shadow_handoff import completion_health, run_day
from hbi.storage import SQLiteStore


def test_measurement_uncertainty_preserves_empty_and_small_sample_limits():
    from hbi.observatory import metric_uncertainty

    assert metric_uncertainty([])["normal_approximation_95_interval"] is None
    assert metric_uncertainty([0.5])["standard_error"] is None
    summary = metric_uncertainty([1.0, 3.0])
    assert summary["physical_races"] == 2
    assert summary["mean"] == 2
    assert summary["standard_error"] == pytest.approx(1)


def test_two_distinct_unexplained_stalls_alert_but_explained_blocks_do_not():
    one = {"observed_at_utc": "2026-11-21T10:00:00+00:00", "inventory": ["r"], "races": []}
    two = dict(one, observed_at_utc="2026-11-21T10:05:00+00:00")
    assert not completion_health([one, one])["alert_required"]
    assert completion_health([two, one])["alert_required"]
    two["races"] = [{"race_id": "r", "terminal_status": "MODEL_BLOCKED", "blockers": ["NO_ID"]}]
    assert not completion_health([one, two])["alert_required"]


def test_duplicate_race_is_not_complete_health():
    one = {"observed_at_utc": "2026-11-21T10:00:00+00:00", "inventory": ["r"],
           "races": [{"race_id": "r", "terminal_status": "FULLY_ASSESSED"}] * 2}
    two = dict(one, observed_at_utc="2026-11-21T10:05:00+00:00")
    assert completion_health([one, two])["alert_required"]


def inputs(tmp_path):
    store = SQLiteStore(tmp_path / "source.sqlite")
    root = Path(__file__).parents[1]
    store.initialize(root / "db/schema.sql")
    store.apply_migrations(root / "db/migrations")
    with store.connect() as conn:
        for rid, start in [("RIKSTOTO:TEST:1", "2026-11-21T11:00:00+00:00"),
                           ("RIKSTOTO:TEST:2", "2026-11-21T09:00:00+00:00")]:
            conn.execute("INSERT INTO races(race_id,race_date,country,track,race_no,start_time_utc,"
                         "discipline,created_at_utc) VALUES (?,?,?,?,?,?,?,?)",
                         (rid, "2026-11-21", "NO", "Synthetic", int(rid[-1]), start, "trot", start))
    origin = tmp_path / "origin.json"
    origin.write_text('{}')
    return {"db": Path(store.path), "collector_root": tmp_path / "missing",
            "provenance": origin, "day": "2026-11-21",
            "decision_time": "2026-11-21T10:00:00+00:00", "out": tmp_path / "output"}


def test_every_discovered_race_remains_visible_and_source_unchanged(tmp_path):
    kwargs = inputs(tmp_path)
    before = hashlib.sha256(kwargs["db"].read_bytes()).hexdigest()
    report = run_day(**kwargs)
    assert report["counts"]["discovered"] == report["counts"]["terminal"] == 2
    assert {r["terminal_status"] for r in report["races"]} == {"ALREADY_STARTED", "SOURCE_UNAVAILABLE"}
    assert all(r["probabilities"] is None and not r["bet_authorized"] for r in report["races"])
    assert report["races"][0]["start_time_oslo"].endswith("+01:00")
    assert hashlib.sha256(kwargs["db"].read_bytes()).hexdigest() == before
    assert report == run_day(**kwargs)
    assert json.loads((kwargs["out"] / "prewatch-day.json").read_bytes()) == report


def test_conflict_never_replaces_frozen_day_and_lock_is_fail_closed(tmp_path):
    kwargs = inputs(tmp_path)
    run_day(**kwargs)
    frozen = (kwargs["out"] / "prewatch-day.json").read_bytes()
    changed = copy.copy(kwargs)
    changed["decision_time"] = "2026-11-21T10:01:00+00:00"
    with pytest.raises(ValueError, match="FROZEN_DAY_REPORT_CONFLICT"):
        run_day(**changed)
    assert (kwargs["out"] / "prewatch-day.json").read_bytes() == frozen
    (kwargs["out"] / ".writer.lock").write_text('another writer')
    with pytest.raises(FileExistsError):
        run_day(**kwargs)


def test_naive_clock_never_creates_output(tmp_path):
    kwargs = inputs(tmp_path)
    kwargs["decision_time"] = "2026-11-21T10:00:00"
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        run_day(**kwargs)
    assert not kwargs["out"].exists()
