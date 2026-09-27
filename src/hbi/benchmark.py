from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean

from .evaluation import log_loss, multiclass_brier


@dataclass(frozen=True)
class RaceEvaluation:
    race_id: str
    winner: str
    model_log_loss: float
    market_log_loss: float
    model_brier: float
    market_brier: float

    @property
    def beats_market_log_loss(self) -> bool:
        return self.model_log_loss < self.market_log_loss

    @property
    def beats_market_brier(self) -> bool:
        return self.model_brier < self.market_brier


def evaluate_against_market(
    race_id: str,
    winner: str,
    model_probabilities: dict[str, float],
    market_probabilities: dict[str, float],
) -> RaceEvaluation:
    if set(model_probabilities) != set(market_probabilities):
        raise ValueError("model and market must cover the same field")
    return RaceEvaluation(
        race_id=race_id,
        winner=winner,
        model_log_loss=log_loss(model_probabilities, winner),
        market_log_loss=log_loss(market_probabilities, winner),
        model_brier=multiclass_brier(model_probabilities, winner),
        market_brier=multiclass_brier(market_probabilities, winner),
    )


def aggregate_market_benchmark(evaluations: list[RaceEvaluation]) -> dict[str, float | int]:
    if not evaluations:
        raise ValueError("at least one evaluation is required")
    return {
        "n": len(evaluations),
        "model_log_loss": mean(item.model_log_loss for item in evaluations),
        "market_log_loss": mean(item.market_log_loss for item in evaluations),
        "model_brier": mean(item.model_brier for item in evaluations),
        "market_brier": mean(item.market_brier for item in evaluations),
        "log_loss_wins": sum(item.beats_market_log_loss for item in evaluations),
        "brier_wins": sum(item.beats_market_brier for item in evaluations),
    }


def closing_line_value(decision_price: float, closing_price: float) -> float:
    """Log price-ratio CLV. Positive means the decision captured a higher price than close."""
    if decision_price <= 1 or closing_price <= 1:
        raise ValueError("decimal prices must be > 1")
    return math.log(decision_price / closing_price)
