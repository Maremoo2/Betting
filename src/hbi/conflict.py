from __future__ import annotations

from collections.abc import Mapping

from .probability import normalize


def total_variation_conflict(
    fundamental: Mapping[str, float],
    market: Mapping[str, float],
) -> float:
    """Return a 0-100 distribution-level model/market conflict score.

    Total variation distance is 0 when the distributions are identical and 1
    when they are maximally separated. This is a diagnostic only: a high score
    is not evidence of value and should trigger investigation/shrinkage logic.
    """
    if set(fundamental) != set(market):
        raise ValueError("fundamental and market distributions must cover the same field")
    f = normalize(fundamental)
    m = normalize(market)
    distance = 0.5 * sum(abs(f[key] - m[key]) for key in f)
    return round(100 * distance, 4)


def selection_log_ratio_conflict(
    fundamental_probability: float,
    market_probability: float,
) -> float:
    """Signed log probability ratio for one selection.

    Positive values mean the fundamental model is above the market; negative
    values mean it is below. This is descriptive, not an edge score.
    """
    if not 0 < fundamental_probability < 1:
        raise ValueError("fundamental_probability must be in (0, 1)")
    if not 0 < market_probability < 1:
        raise ValueError("market_probability must be in (0, 1)")
    import math

    return math.log(fundamental_probability / market_probability)
