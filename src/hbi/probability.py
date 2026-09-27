from __future__ import annotations

import math
from collections.abc import Mapping


def _validate_distribution(probabilities: Mapping[str, float]) -> None:
    if not probabilities:
        raise ValueError("probability distribution cannot be empty")
    if any((not math.isfinite(p)) or p <= 0 for p in probabilities.values()):
        raise ValueError("all probabilities must be finite and > 0")


def normalize(probabilities: Mapping[str, float]) -> dict[str, float]:
    _validate_distribution(probabilities)
    total = sum(probabilities.values())
    if total <= 0:
        raise ValueError("probability sum must be positive")
    return {key: value / total for key, value in probabilities.items()}


def normalize_market_odds(decimal_odds: Mapping[str, float]) -> dict[str, float]:
    """Convert decimal odds to a normalized full-field market probability.

    This removes the simple overround/takeout component by normalizing inverse odds.
    For tote markets, callers should use odds from one timestamp only.
    """
    if not decimal_odds:
        raise ValueError("odds cannot be empty")
    if any((not math.isfinite(o)) or o <= 1 for o in decimal_odds.values()):
        raise ValueError("all decimal odds must be finite and > 1")
    inverse = {selection: 1.0 / odds for selection, odds in decimal_odds.items()}
    return normalize(inverse)


def fair_odds(probability: float) -> float:
    if not 0 < probability <= 1:
        raise ValueError("probability must be in (0, 1]")
    return 1.0 / probability


def combine_probabilities(
    fundamental: Mapping[str, float],
    market: Mapping[str, float],
    *,
    fundamental_weight: float,
    market_weight: float,
) -> dict[str, float]:
    """Benter-style second-stage combination using a normalized power/log pool.

    The weights are model parameters and MUST be estimated on point-in-time,
    out-of-sample data. They are deliberately not given production defaults.

    log(score_i) = a*log(fundamental_i) + b*log(market_i)
    p_i = score_i / sum(score)
    """
    if set(fundamental) != set(market):
        raise ValueError("fundamental and market distributions must cover the same field")
    if fundamental_weight < 0 or market_weight < 0:
        raise ValueError("weights must be non-negative")
    if fundamental_weight == 0 and market_weight == 0:
        raise ValueError("at least one weight must be positive")

    f = normalize(fundamental)
    m = normalize(market)
    scores = {
        selection: math.exp(
            fundamental_weight * math.log(f[selection])
            + market_weight * math.log(m[selection])
        )
        for selection in f
    }
    return normalize(scores)
