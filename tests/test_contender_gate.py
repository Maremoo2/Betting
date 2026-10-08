import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from hbi.cli import build_parser
from hbi.contender_gate import Contender, Pricing, Quote, review_contenders

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
# Synthetic regression probability, not a prospective estimate of Emmeline.
PRICE = Pricing(.15, 1 / .15, 1.05 / .15, "BET", NOW)


def review(**changes):
    args = {
        "contenders": [Contender("5", 7.78, 12.5)], "pricing": {"5": PRICE},
        "latest_quotes": {"5": Quote(7.78, NOW)}, "decision_time": NOW,
        "race_start": NOW + timedelta(minutes=4),
    }
    args.update(changes)
    return review_contenders(**args)


def test_emmeline_cannot_disappear_unpriced():
    result = review(pricing={})
    assert not result.allowed
    assert result.winner_status == "BLOCKED"
    assert result.errors == ("UNPRICED_CONTENDER:5",)
    assert result.runners[0]["triggers"] == ["SYSTEM_SHARE_GE_8_PERCENT", "WINNER_LE_12"]
    assert review().winner_status == "BET"


@pytest.mark.parametrize("contender,trigger", [
    (Contender("5", 20, 8), "SYSTEM_SHARE_GE_8_PERCENT"),
    (Contender("5", 12, 0), "WINNER_LE_12"),
    (Contender("5", 20, 0, "documented track advantage"), "SPORTING_SIGNAL"),
    (Contender("5", 20, 0, market_discrepancy="review needed"), "MARKET_DISCREPANCY"),
    (Contender("5"), "INCOMPLETE_SCREEN_PRICE_REQUIRED"),
])
def test_independent_screen_triggers(contender, trigger):
    result = review(contenders=[contender], pricing={})
    assert not result.allowed
    assert trigger in result.runners[0]["triggers"]


def test_below_all_triggers_can_pass_without_pricing():
    assert review(contenders=[Contender("5", 12.01, 7.99)], pricing={}).allowed


@pytest.mark.parametrize("change", [
    {"p_win": float("nan")}, {"fair_odds": 5}, {"minimum_odds": 1},
    {"decision": ""}, {"priced_at": NOW + timedelta(seconds=1)},
    {"priced_at": NOW.replace(tzinfo=None)},
])
def test_incomplete_or_invalid_pricing_blocks(change):
    result = review(pricing={"5": replace(PRICE, **change)})
    assert not result.allowed
    assert "UNPRICED_CONTENDER" in result.errors[0]


def test_bet_absent_from_coupon_requires_reason_even_after_price_collapse():
    result = review(ticket_selections=set(), latest_quotes={"5": Quote(5, NOW)})
    assert not result.allowed
    assert result.runners[0]["consistency_alert"] == "BET_ABSENT_FROM_COUPON"
    assert not review(ticket_selections=set(), omission_reasons={"5": "  "}).allowed
    result = review(ticket_selections=set(), omission_reasons={"5": "Budget: single on #2"})
    assert result.allowed
    assert result.runners[0]["omission_reason"] == "Budget: single on #2"
    assert review(ticket_selections={"5"}).allowed


@pytest.mark.parametrize("quotes,start,reason", [
    ({"5": Quote(6.5, NOW)}, 4, "PRICE_BELOW_MINIMUM"),
    ({}, 4, "NO_ACCEPTABLE_LATE_QUOTE"),
    ({"5": Quote(8, NOW - timedelta(seconds=121))}, 4, "STALE_OR_FUTURE_LATE_QUOTE"),
    ({"5": Quote(8, NOW + timedelta(seconds=1))}, 4, "STALE_OR_FUTURE_LATE_QUOTE"),
    ({"5": Quote(8, NOW)}, 6, "OUTSIDE_LATE_PRICE_WINDOW"),
])
def test_mrs_dowley_price_gate_keeps_probability_and_downgrades_bet(quotes, start, reason):
    result = review(latest_quotes=quotes, race_start=NOW + timedelta(minutes=start))
    assert result.allowed
    assert result.winner_status == "WATCH"
    assert result.runners[0]["pricing"]["p_win"] == PRICE.p_win
    assert result.runners[0]["late_price_reason"] == reason


def test_minimum_price_boundary_and_started_race():
    assert review(latest_quotes={"5": Quote(PRICE.minimum_odds, NOW)}).winner_status == "BET"
    assert not review(race_start=NOW).allowed


def test_unknown_coupon_selection_and_duplicate_field_fail_closed():
    with pytest.raises(ValueError):
        review(ticket_selections={"99"})
    with pytest.raises(ValueError):
        review(contenders=[Contender("5"), Contender("5")])


def test_cli_hard_stop_writes_reviewable_report(tmp_path):
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(json.dumps({
        "race_id": "synthetic-emmeline", "active_field": [
            {"selection": "5", "winner_odds": 7.78, "system_share_percent": 12.5}],
        "pricing": {}, "latest_quotes": {}, "decision_time": NOW.isoformat(),
        "race_start": (NOW + timedelta(minutes=4)).isoformat(),
        "ticket_selections": [],
    }))
    args = build_parser().parse_args([
        "review-contenders", str(input_path), "--output", str(output_path)])
    with pytest.raises(SystemExit, match="2"):
        args.func(args)
    assert json.loads(output_path.read_text())["winner_status"] == "BLOCKED"
