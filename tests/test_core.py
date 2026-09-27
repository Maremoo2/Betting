from datetime import datetime, timedelta, timezone

import pytest

from hbi.domain import MarketSnapshot, RejectStatus
from hbi.evaluation import log_loss, multiclass_brier
from hbi.market_path import calculate_market_path
from hbi.point_in_time import PointInTimeRecord, PointInTimeViolation, validate_record
from hbi.probability import combine_probabilities, normalize_market_odds
from hbi.race_difficulty import RaceDifficultyInput, score_race_difficulty


def test_market_normalization_sums_to_one():
    p = normalize_market_odds({"a": 2.0, "b": 4.0, "c": 8.0})
    assert sum(p.values()) == pytest.approx(1.0)


def test_combined_probability_sums_to_one():
    combined = combine_probabilities(
        {"a": 0.5, "b": 0.3, "c": 0.2},
        {"a": 0.4, "b": 0.35, "c": 0.25},
        fundamental_weight=1.0,
        market_weight=1.0,
    )
    assert sum(combined.values()) == pytest.approx(1.0)
    assert set(combined) == {"a", "b", "c"}


def test_point_in_time_rejects_future_source():
    now = datetime.now(timezone.utc)
    with pytest.raises(PointInTimeViolation):
        validate_record(
            PointInTimeRecord(
                name="trainer_form",
                feature_as_of=now - timedelta(minutes=1),
                source_published_at=now + timedelta(minutes=1),
                decision_time=now,
            )
        )


def test_high_difficulty_can_reject_without_touching_probabilities():
    result = score_race_difficulty(
        RaceDifficultyInput(
            field_size=15,
            field_parity=0.95,
            race_shape_uncertainty=0.95,
            break_or_start_risk=0.9,
            low_information_fraction=0.8,
            environment_change_fraction=0.8,
        )
    )
    assert result.reject_status == RejectStatus.REJECT
    assert result.difficulty_score >= 75


def test_market_path_uses_probability_direction():
    t0 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    metrics = calculate_market_path(
        [
            MarketSnapshot("r1", "h1", t0, 6.0, 1000),
            MarketSnapshot("r1", "h1", t0 + timedelta(minutes=5), 4.0, 2000),
        ]
    )
    assert metrics.odds_move_pct < 0
    assert metrics.implied_probability_move_pp > 0
    assert metrics.pool_growth_pct == pytest.approx(100.0)


def test_evaluation_metrics_reward_correct_probability():
    good = {"a": 0.8, "b": 0.2}
    bad = {"a": 0.2, "b": 0.8}
    assert log_loss(good, "a") < log_loss(bad, "a")
    assert multiclass_brier(good, "a") < multiclass_brier(bad, "a")
