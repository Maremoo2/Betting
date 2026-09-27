from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .conflict import total_variation_conflict
from .decision import DecisionPolicy, ValueAssessment, assess_value
from .domain import RejectStatus
from .probability import combine_probabilities, normalize, normalize_market_odds


@dataclass(frozen=True)
class CombinationPolicy:
    fundamental_weight: float
    market_weight: float
    material_conflict_threshold: float

    def __post_init__(self) -> None:
        if self.fundamental_weight < 0 or self.market_weight < 0:
            raise ValueError("combination weights must be non-negative")
        if self.fundamental_weight == 0 and self.market_weight == 0:
            raise ValueError("at least one combination weight must be positive")
        if not 0 <= self.material_conflict_threshold <= 100:
            raise ValueError("material_conflict_threshold must be in [0, 100]")


@dataclass(frozen=True)
class RaceDecisionResult:
    fundamental_probabilities: dict[str, float]
    market_probabilities: dict[str, float]
    combined_probabilities: dict[str, float]
    model_market_conflict_score: float
    assessments: dict[str, ValueAssessment]


def evaluate_race(
    *,
    fundamental_probabilities: Mapping[str, float],
    market_decimal_odds: Mapping[str, float],
    executable_prices: Mapping[str, float],
    combination_policy: CombinationPolicy,
    decision_policy: DecisionPolicy,
    reject_status: RejectStatus = RejectStatus.CLEAR,
) -> RaceDecisionResult:
    """Run the V3.2 probability -> market -> value decision chain for one race.

    Fundamental inputs are normalized but are expected to be generated without
    market features. The market is an explicit baseline/information layer. A
    material unresolved distribution conflict never becomes an automatic BET.
    """
    if set(fundamental_probabilities) != set(market_decimal_odds):
        raise ValueError("fundamental probabilities and market odds must cover the same field")
    if set(executable_prices) != set(market_decimal_odds):
        raise ValueError("executable prices must cover the same field")

    fundamental = normalize(fundamental_probabilities)
    market = normalize_market_odds(market_decimal_odds)
    conflict = total_variation_conflict(fundamental, market)
    combined = combine_probabilities(
        fundamental,
        market,
        fundamental_weight=combination_policy.fundamental_weight,
        market_weight=combination_policy.market_weight,
    )

    unresolved_conflict = conflict >= combination_policy.material_conflict_threshold
    assessments = {
        selection: assess_value(
            probability=combined[selection],
            available_price=executable_prices[selection],
            policy=decision_policy,
            reject_status=reject_status,
            unresolved_market_conflict=unresolved_conflict,
        )
        for selection in combined
    }

    return RaceDecisionResult(
        fundamental_probabilities=fundamental,
        market_probabilities=market,
        combined_probabilities=combined,
        model_market_conflict_score=conflict,
        assessments=assessments,
    )
