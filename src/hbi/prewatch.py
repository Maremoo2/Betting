from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import log

from .domain import MarketSnapshot


class PreWatchAction(StrEnum):
    HOLD = "HOLD"
    REPRICE = "REPRICE"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class MaterialChangePolicy:
    probability_move_pp: float = 2.0
    relative_odds_move_pct: float = 12.5
    pool_growth_pct: float = 25.0
    late_window_minutes: float = 5.0


@dataclass(frozen=True)
class MaterialChange:
    selection_id: str
    action: PreWatchAction
    reasons: tuple[str, ...]
    probability_move_pp: float
    relative_odds_move_pct: float
    pool_growth_pct: float | None
    minutes_to_start: float | None


def assess_material_change(
    previous: MarketSnapshot,
    current: MarketSnapshot,
    *,
    race_start_at: datetime | None = None,
    policy: MaterialChangePolicy | None = None,
    material_event: str | None = None,
) -> MaterialChange:
    """Decide whether a fresh snapshot should trigger a pre-watch reprice/review.

    The rule is deliberately descriptive. A shortening price is never labelled
    "smart money" and never becomes a bet signal by itself. Thresholds are
    operational defaults and must be validated on historical point-in-time data.
    """
    policy = policy or MaterialChangePolicy()
    if previous.race_id != current.race_id or previous.selection_id != current.selection_id:
        raise ValueError("snapshots must describe the same runner in the same race")
    if current.captured_at <= previous.captured_at:
        raise ValueError("current snapshot must be newer than previous snapshot")
    if previous.odds_decimal <= 1 or current.odds_decimal <= 1:
        raise ValueError("decimal odds must be > 1")

    previous_p = 1.0 / previous.odds_decimal
    current_p = 1.0 / current.odds_decimal
    probability_move_pp = (current_p - previous_p) * 100
    relative_odds_move_pct = (current.odds_decimal / previous.odds_decimal - 1.0) * 100

    pool_growth_pct = None
    if previous.pool_size is not None and current.pool_size is not None and previous.pool_size > 0:
        pool_growth_pct = (current.pool_size / previous.pool_size - 1.0) * 100

    minutes_to_start = None
    if race_start_at is not None:
        minutes_to_start = (race_start_at - current.captured_at).total_seconds() / 60

    reasons: list[str] = []
    if abs(probability_move_pp) >= policy.probability_move_pp:
        reasons.append("probability_move")
    if abs(relative_odds_move_pct) >= policy.relative_odds_move_pct:
        reasons.append("odds_move")
    if pool_growth_pct is not None and pool_growth_pct >= policy.pool_growth_pct:
        reasons.append("pool_growth")
    if material_event:
        reasons.append(f"event:{material_event}")

    action = PreWatchAction.HOLD
    if reasons:
        action = PreWatchAction.REPRICE
        if material_event or (
            minutes_to_start is not None
            and 0 <= minutes_to_start <= policy.late_window_minutes
            and ("probability_move" in reasons or "odds_move" in reasons)
        ):
            action = PreWatchAction.REVIEW

    return MaterialChange(
        selection_id=current.selection_id,
        action=action,
        reasons=tuple(reasons),
        probability_move_pp=round(probability_move_pp, 4),
        relative_odds_move_pct=round(relative_odds_move_pct, 4),
        pool_growth_pct=None if pool_growth_pct is None else round(pool_growth_pct, 4),
        minutes_to_start=None if minutes_to_start is None else round(minutes_to_start, 3),
    )


def market_residual(fundamental_probability: float, market_probability: float) -> float:
    """Signed log residual between independent fundamental and market estimates."""
    if not 0 < fundamental_probability < 1 or not 0 < market_probability < 1:
        raise ValueError("probabilities must be in (0, 1)")
    return log(fundamental_probability / market_probability)
