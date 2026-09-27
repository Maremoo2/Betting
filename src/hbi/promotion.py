from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .governance import promotion_blockers


@dataclass(frozen=True)
class PromotionMetrics:
    forward_races: int
    champion_log_loss: float
    challenger_log_loss: float
    market_log_loss: float
    champion_brier: float
    challenger_brier: float
    market_brier: float
    champion_calibration_error: float | None = None
    challenger_calibration_error: float | None = None
    replicated_across_required_slices: bool = False


@dataclass(frozen=True)
class PromotionAssessment:
    status: str
    blockers: tuple[str, ...]
    recommendation_only: bool = True
    manual_approval_required: bool = True
    execution_authority: bool = False


def assess_challenger_for_manual_review(
    *,
    governance: dict[str, Any],
    metrics: PromotionMetrics,
    minimum_forward_races: int | None = None,
) -> PromotionAssessment:
    blockers = promotion_blockers(governance)
    policy = governance.get("promotion_policy") or {}
    required_n = int(
        minimum_forward_races
        if minimum_forward_races is not None
        else policy.get("minimum_forward_races", 500)
    )

    if metrics.forward_races < required_n:
        blockers.append(
            f"insufficient_forward_races:{metrics.forward_races}:{required_n}"
        )
    if metrics.challenger_log_loss >= metrics.champion_log_loss:
        blockers.append("challenger_log_loss_not_better_than_champion")
    if metrics.challenger_brier >= metrics.champion_brier:
        blockers.append("challenger_brier_not_better_than_champion")
    if metrics.challenger_log_loss >= metrics.market_log_loss:
        blockers.append("challenger_log_loss_not_better_than_market")
    if metrics.challenger_brier >= metrics.market_brier:
        blockers.append("challenger_brier_not_better_than_market")

    if (
        metrics.challenger_calibration_error is not None
        and metrics.champion_calibration_error is not None
        and metrics.challenger_calibration_error
        > metrics.champion_calibration_error
    ):
        blockers.append("challenger_calibration_worse_than_champion")

    if not metrics.replicated_across_required_slices:
        blockers.append("replication_not_demonstrated")

    return PromotionAssessment(
        status=(
            "READY_FOR_MANUAL_REVIEW"
            if not blockers
            else "DO_NOT_PROMOTE"
        ),
        blockers=tuple(sorted(set(blockers))),
    )
