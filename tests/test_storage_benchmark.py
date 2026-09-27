from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.benchmark import closing_line_value, evaluate_against_market
from hbi.domain import MarketSnapshot
from hbi.storage import SQLiteStore

SCHEMA = Path(__file__).parents[1] / "db" / "schema.sql"


def race_record():
    return {
        "race_id": "r1",
        "race_date": "2026-09-27",
        "country": "SE",
        "track": "Test",
        "race_no": 1,
        "start_time_utc": "2026-09-27T18:00:00+00:00",
        "discipline": "trot",
        "distance_m": 2140,
        "start_method": "auto",
        "race_class": "test",
        "created_at_utc": "2026-09-27T12:00:00+00:00",
    }


def test_snapshot_insert_is_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race(race_record())
    snapshot = MarketSnapshot(
        "r1",
        "1",
        datetime(2026, 9, 27, 17, 55, tzinfo=UTC),
        4.0,
        10000,
    )
    assert store.insert_market_snapshot(snapshot)
    assert not store.insert_market_snapshot(snapshot)
    assert store.count("market_snapshots") == 1


def test_frozen_prediction_cannot_be_rewritten(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race(race_record())
    created = datetime(2026, 9, 27, 17, 50, tzinfo=UTC)
    kwargs = {
        "prediction_id": "p1",
        "race_id": "r1",
        "selection_id": "1",
        "created_at": created,
        "model_name": "fundamental",
        "model_version": "v1",
        "layer": "FUNDAMENTAL",
        "probability": 0.25,
        "feature_as_of": created,
    }
    store.insert_prediction(**kwargs)
    with pytest.raises(ValueError):
        store.insert_prediction(**{**kwargs, "probability": 0.40})


def test_prediction_rejects_future_feature(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race(race_record())
    created = datetime(2026, 9, 27, 17, 50, tzinfo=UTC)
    with pytest.raises(ValueError):
        store.insert_prediction(
            prediction_id="p1",
            race_id="r1",
            selection_id="1",
            created_at=created,
            model_name="fundamental",
            model_version="v1",
            layer="FUNDAMENTAL",
            probability=0.25,
            feature_as_of=datetime(2026, 9, 27, 17, 51, tzinfo=UTC),
        )


def test_market_is_mandatory_comparison_baseline():
    evaluation = evaluate_against_market(
        "r1",
        "a",
        {"a": 0.60, "b": 0.25, "c": 0.15},
        {"a": 0.45, "b": 0.30, "c": 0.25},
    )
    assert evaluation.beats_market_log_loss
    assert evaluation.beats_market_brier


def test_positive_clv_means_better_price_than_close():
    assert closing_line_value(6.0, 5.0) > 0
    assert closing_line_value(4.0, 5.0) < 0
