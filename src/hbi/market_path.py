from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .domain import MarketSnapshot


@dataclass(frozen=True)
class MarketPathMetrics:
    selection_id: str
    start_at: datetime
    end_at: datetime
    odds_move_pct: float
    implied_probability_move_pp: float
    implied_probability_velocity_pp_per_min: float
    pool_growth_pct: float | None


def _implied_probability(odds: float) -> float:
    if odds <= 1:
        raise ValueError("decimal odds must be > 1")
    return 1.0 / odds


def calculate_market_path(snapshots: list[MarketSnapshot]) -> MarketPathMetrics:
    """Calculate path metrics for one selection across two or more snapshots."""
    if len(snapshots) < 2:
        raise ValueError("at least two snapshots are required")
    selection_ids = {snapshot.selection_id for snapshot in snapshots}
    if len(selection_ids) != 1:
        raise ValueError("all snapshots must refer to the same selection")

    ordered = sorted(snapshots, key=lambda snapshot: snapshot.captured_at)
    first, last = ordered[0], ordered[-1]
    elapsed_min = (last.captured_at - first.captured_at).total_seconds() / 60
    if elapsed_min <= 0:
        raise ValueError("snapshot timestamps must span positive time")

    p0 = _implied_probability(first.odds_decimal)
    p1 = _implied_probability(last.odds_decimal)
    odds_move = (last.odds_decimal / first.odds_decimal - 1.0) * 100
    probability_move_pp = (p1 - p0) * 100
    velocity = probability_move_pp / elapsed_min

    pool_growth = None
    if first.pool_size is not None and last.pool_size is not None and first.pool_size > 0:
        pool_growth = (last.pool_size / first.pool_size - 1.0) * 100

    return MarketPathMetrics(
        selection_id=first.selection_id,
        start_at=first.captured_at,
        end_at=last.captured_at,
        odds_move_pct=round(odds_move, 4),
        implied_probability_move_pp=round(probability_move_pp, 4),
        implied_probability_velocity_pp_per_min=round(velocity, 4),
        pool_growth_pct=None if pool_growth is None else round(pool_growth, 4),
    )
