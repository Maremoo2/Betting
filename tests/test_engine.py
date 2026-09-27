import pytest

from hbi.decision import DecisionPolicy
from hbi.domain import Decision, RejectStatus
from hbi.engine import CombinationPolicy, evaluate_race


def test_engine_keeps_full_field_layers_normalized():
    result = evaluate_race(
        fundamental_probabilities={"a": 0.50, "b": 0.30, "c": 0.20},
        market_decimal_odds={"a": 2.2, "b": 3.5, "c": 6.0},
        executable_prices={"a": 2.2, "b": 3.5, "c": 6.0},
        combination_policy=CombinationPolicy(
            fundamental_weight=1.0,
            market_weight=1.0,
            material_conflict_threshold=100.0,
        ),
        decision_policy=DecisionPolicy(minimum_edge=0.05, safety_margin=0.02),
    )
    assert sum(result.fundamental_probabilities.values()) == pytest.approx(1.0)
    assert sum(result.market_probabilities.values()) == pytest.approx(1.0)
    assert sum(result.combined_probabilities.values()) == pytest.approx(1.0)


def test_material_conflict_blocks_direct_bet():
    result = evaluate_race(
        fundamental_probabilities={"a": 0.80, "b": 0.20},
        market_decimal_odds={"a": 4.0, "b": 1.5},
        executable_prices={"a": 5.0, "b": 1.5},
        combination_policy=CombinationPolicy(
            fundamental_weight=1.0,
            market_weight=0.1,
            material_conflict_threshold=10.0,
        ),
        decision_policy=DecisionPolicy(minimum_edge=0.01, safety_margin=0.0),
    )
    assert result.model_market_conflict_score >= 10
    assert result.assessments["a"].decision != Decision.BET


def test_race_reject_option_vetoes_all_bets():
    result = evaluate_race(
        fundamental_probabilities={"a": 0.55, "b": 0.45},
        market_decimal_odds={"a": 2.2, "b": 2.4},
        executable_prices={"a": 3.0, "b": 2.4},
        combination_policy=CombinationPolicy(
            fundamental_weight=1.0,
            market_weight=1.0,
            material_conflict_threshold=100.0,
        ),
        decision_policy=DecisionPolicy(minimum_edge=0.01, safety_margin=0.0),
        reject_status=RejectStatus.REJECT,
    )
    assert all(
        assessment.decision == Decision.PASS
        for assessment in result.assessments.values()
    )
