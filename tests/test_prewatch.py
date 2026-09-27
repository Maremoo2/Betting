from datetime import datetime, timedelta, timezone

import pytest

from hbi.domain import MarketSnapshot
from hbi.prewatch import PreWatchAction, assess_material_change, market_residual


def test_large_late_move_triggers_review():
    t0 = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    start = t0 + timedelta(minutes=6)
    result = assess_material_change(
        MarketSnapshot("r1", "h1", t0, 6.0, 10000),
        MarketSnapshot("r1", "h1", t0 + timedelta(minutes=2), 4.5, 14000),
        race_start_at=start,
    )
    assert result.action == PreWatchAction.REVIEW
    assert "probability_move" in result.reasons
    assert "odds_move" in result.reasons
    assert "pool_growth" in result.reasons


def test_small_move_holds():
    t0 = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    result = assess_material_change(
        MarketSnapshot("r1", "h1", t0, 4.0, 10000),
        MarketSnapshot("r1", "h1", t0 + timedelta(minutes=2), 3.95, 10500),
    )
    assert result.action == PreWatchAction.HOLD
    assert result.reasons == ()


def test_material_event_forces_review_without_directional_assumption():
    t0 = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    result = assess_material_change(
        MarketSnapshot("r1", "h1", t0, 4.0, 10000),
        MarketSnapshot("r1", "h1", t0 + timedelta(minutes=1), 4.0, 10100),
        material_event="driver_change",
    )
    assert result.action == PreWatchAction.REVIEW
    assert "event:driver_change" in result.reasons


def test_market_residual_direction():
    assert market_residual(0.30, 0.20) > 0
    assert market_residual(0.20, 0.30) < 0
    with pytest.raises(ValueError):
        market_residual(0, 0.2)
