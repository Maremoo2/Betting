from datetime import datetime, timedelta, timezone

from hbi.decision import DecisionPolicy, assess_value
from hbi.domain import Decision, RejectStatus
from hbi.walk_forward import EvaluatedRace, aggregate_windows, evaluate_window


def test_value_gate_separates_bet_watch_pass():
    policy = DecisionPolicy(minimum_edge=0.05, safety_margin=0.05)

    bet = assess_value(probability=0.25, available_price=5.0, policy=policy)
    watch = assess_value(probability=0.25, available_price=4.1, policy=policy)
    passed = assess_value(probability=0.25, available_price=3.5, policy=policy)

    assert bet.decision == Decision.BET
    assert watch.decision == Decision.WATCH
    assert passed.decision == Decision.PASS


def test_reject_option_vetoes_nominal_value():
    policy = DecisionPolicy(minimum_edge=0.05, safety_margin=0.05)
    result = assess_value(
        probability=0.25,
        available_price=6.0,
        policy=policy,
        reject_status=RejectStatus.REJECT,
    )
    assert result.decision == Decision.PASS
    assert result.reject_reason == "race_reject_option"


def test_unresolved_conflict_never_directly_bets():
    policy = DecisionPolicy(minimum_edge=0.05, safety_margin=0.05)
    result = assess_value(
        probability=0.25,
        available_price=6.0,
        policy=policy,
        unresolved_market_conflict=True,
    )
    assert result.decision == Decision.WATCH


def test_walk_forward_window_compares_model_to_market():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    races = [
        EvaluatedRace(
            race_id="r1",
            race_time=t0 + timedelta(days=1),
            winner="a",
            model_probabilities={"a": 0.7, "b": 0.3},
            market_probabilities={"a": 0.55, "b": 0.45},
        ),
        EvaluatedRace(
            race_id="r2",
            race_time=t0 + timedelta(days=2),
            winner="b",
            model_probabilities={"a": 0.25, "b": 0.75},
            market_probabilities={"a": 0.4, "b": 0.6},
        ),
    ]
    window = evaluate_window(
        races,
        start=t0,
        end=t0 + timedelta(days=10),
    )
    summary = aggregate_windows([window])
    assert window.n == 2
    assert window.model_beats_market
    assert summary["windows_beating_market"] == 1
