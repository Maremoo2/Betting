from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hbi.fundamental import (
    FundamentalChampionPolicy,
    MarketFreeFundamentalChampionV1,
    run_and_persist_fundamental,
)
from hbi.storage import SQLiteStore

SCHEMA = Path(__file__).parents[1] / "db" / "schema.sql"


def _row(
    selection: str,
    *,
    starts: int | None,
    wins: int | None,
    feature_time: datetime,
    scratched: bool = False,
):
    return {
        "selection_id": selection,
        "history_total_starts": starts,
        "history_total_wins": wins,
        "feature_as_of_utc": feature_time.isoformat(),
        "scratched": int(scratched),
    }


def _race(store: SQLiteStore):
    store.upsert_race(
        {
            "race_id": "r1",
            "race_date": "2026-09-27",
            "country": "NO",
            "track": "Bjerke",
            "race_no": 1,
            "start_time_utc": "2026-09-27T18:00:00+00:00",
            "discipline": "trot",
            "distance_m": 2100,
            "start_method": "auto",
            "race_class": "test",
            "created_at_utc": "2026-09-27T12:00:00+00:00",
        }
    )


def test_champion_v1_is_market_free_and_normalized():
    model = MarketFreeFundamentalChampionV1()
    created = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    rows = [
        _row("1", starts=20, wins=8, feature_time=created - timedelta(minutes=1)),
        _row("2", starts=20, wins=2, feature_time=created - timedelta(minutes=1)),
        _row("3", starts=0, wins=0, feature_time=created - timedelta(minutes=1)),
    ]

    run = model.estimate(race_id="r1", rows=rows, created_at=created)

    assert sum(run.probabilities.values()) == pytest.approx(1.0)
    assert run.probabilities["1"] > run.probabilities["2"]
    assert set(run.probabilities) == {"1", "2", "3"}
    assert run.shadow_eligible
    assert run.history_coverage == pytest.approx(1.0)


def test_missing_history_is_shrunk_to_uniform_and_can_gate_shadow():
    model = MarketFreeFundamentalChampionV1(
        FundamentalChampionPolicy(minimum_history_coverage=0.80)
    )
    created = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    rows = [
        _row("1", starts=10, wins=4, feature_time=created),
        _row("2", starts=None, wins=None, feature_time=created),
        _row("3", starts=None, wins=None, feature_time=created),
    ]

    run = model.estimate(race_id="r1", rows=rows, created_at=created)

    assert sum(run.probabilities.values()) == pytest.approx(1.0)
    assert not run.shadow_eligible
    assert run.reason == "LOW_HISTORY_COVERAGE"
    assert run.history_coverage == pytest.approx(1 / 3)


def test_scratched_runner_is_removed_from_probability_field():
    model = MarketFreeFundamentalChampionV1()
    created = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    rows = [
        _row("1", starts=20, wins=8, feature_time=created),
        _row("2", starts=20, wins=2, feature_time=created),
        _row("3", starts=50, wins=30, feature_time=created, scratched=True),
    ]

    run = model.estimate(race_id="r1", rows=rows, created_at=created)

    assert set(run.probabilities) == {"1", "2"}
    assert sum(run.probabilities.values()) == pytest.approx(1.0)


def test_champion_rejects_future_feature_timestamp():
    model = MarketFreeFundamentalChampionV1()
    created = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    rows = [
        _row("1", starts=10, wins=3, feature_time=created + timedelta(seconds=1)),
        _row("2", starts=10, wins=2, feature_time=created),
    ]

    with pytest.raises(ValueError):
        model.estimate(race_id="r1", rows=rows, created_at=created)


def test_run_and_persist_creates_frozen_full_field_predictions(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    _race(store)
    created = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    for selection, starts, wins in (("1", 20, 8), ("2", 20, 2)):
        store.insert_runner_fundamental_snapshot(
            {
                "snapshot_id": f"f-{selection}",
                "race_id": "r1",
                "selection_id": selection,
                "observed_at_utc": created.isoformat(),
                "feature_as_of_utc": created.isoformat(),
                "source_uri": "https://example/program",
                "horse_name": f"Horse {selection}",
                "history_total_starts": starts,
                "history_total_wins": wins,
                "scratched": 0,
                "data_quality": "KNOWN_HISTORY",
            }
        )

    run = run_and_persist_fundamental(
        store,
        race_id="r1",
        created_at=created,
    )

    assert run.shadow_eligible
    predictions = store.latest_predictions(
        "r1",
        layer="FUNDAMENTAL",
        before=created,
    )
    assert sum(predictions.values()) == pytest.approx(1.0)
    assert predictions["1"] > predictions["2"]
    assert store.count("fundamental_model_runs") == 1
    assert store.count("model_versions") == 1
