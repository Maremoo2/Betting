from __future__ import annotations

from dataclasses import dataclass

from .domain import Decision, RejectStatus
from .probability import fair_odds


@dataclass(frozen=True)
class DecisionPolicy:
    """Explicit value thresholds.

    No defaults are provided because thresholds must be validated prospectively.
    """

    minimum_edge: float
    safety_margin: float

    def __post_init__(self) -> None:
        if self.minimum_edge < 0:
            raise ValueError("minimum_edge must be >= 0")
        if self.safety_margin < 0:
            raise ValueError("safety_margin must be >= 0")


@dataclass(frozen=True)
class ValueAssessment:
    decision: Decision
    probability: float
    fair_odds: float
    minimum_price: float
    available_price: float
    expected_value: float
    edge_over_fair: float
    reject_reason: str | None


def assess_value(
    *,
    probability: float,
    available_price: float,
    policy: DecisionPolicy,
    reject_status: RejectStatus = RejectStatus.CLEAR,
    unresolved_market_conflict: bool = False,
) -> ValueAssessment:
    """Translate a calibrated probability and executable price into BET/WATCH/PASS.

    This function does not size stakes or place bets. Race-level rejection and
    unresolved model/market conflict can veto an otherwise positive nominal edge.
    """
    if not 0 < probability <= 1:
        raise ValueError("probability must be in (0, 1]")
    if available_price <= 1:
        raise ValueError("available_price must be > 1")

    fair = fair_odds(probability)
    minimum_price = fair * (1 + policy.safety_margin)
    ev = probability * available_price - 1.0
    edge = available_price / fair - 1.0

    reject_reason = None
    if reject_status == RejectStatus.REJECT:
        decision = Decision.PASS
        reject_reason = "race_reject_option"
    elif unresolved_market_conflict:
        decision = Decision.WATCH if ev > 0 else Decision.PASS
        reject_reason = "unresolved_model_market_conflict"
    elif available_price >= minimum_price and ev >= policy.minimum_edge:
        decision = Decision.BET
    elif ev > 0:
        decision = Decision.WATCH
    else:
        decision = Decision.PASS

    return ValueAssessment(
        decision=decision,
        probability=probability,
        fair_odds=fair,
        minimum_price=minimum_price,
        available_price=available_price,
        expected_value=ev,
        edge_over_fair=edge,
        reject_reason=reject_reason,
    )
