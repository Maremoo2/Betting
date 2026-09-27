from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from hbi.schedule import evaluate_schedule


def test_summer_utc_conversion_hits_oslo_09():
    decision = evaluate_schedule(datetime(2026, 7, 1, 7, 0, tzinfo=UTC))
    assert decision.should_run
    assert decision.mode == "MORNING_DISCOVERY"
    assert decision.local_time.hour == 9


def test_winter_utc_conversion_hits_oslo_09():
    decision = evaluate_schedule(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))
    assert decision.should_run
    assert decision.mode == "MORNING_DISCOVERY"
    assert decision.local_time.hour == 9


def test_watch_window_includes_21_oslo():
    oslo = ZoneInfo("Europe/Oslo")
    decision = evaluate_schedule(datetime(2026, 9, 27, 21, 0, tzinfo=oslo))
    assert decision.should_run
    assert decision.mode == "HOURLY_WATCH"


def test_outside_window_skips():
    oslo = ZoneInfo("Europe/Oslo")
    decision = evaluate_schedule(datetime(2026, 9, 27, 22, 0, tzinfo=oslo))
    assert not decision.should_run
    assert decision.mode == "SKIP"
