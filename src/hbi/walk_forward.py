from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean

from .benchmark import RaceEvaluation, evaluate_against_market


@dataclass(frozen=True)
class EvaluatedRace:
    race_id: str
    race_time: datetime
    winner: str
    model_probabilities: dict[str, float]
    market_probabilities: dict[str, float]


@dataclass(frozen=True)
class EvaluationWindow:
    start: datetime
    end: datetime
    n: int
    model_log_loss: float
    market_log_loss: float
    model_brier: float
    market_brier: float

    @property
    def model_beats_market(self) -> bool:
        return (
            self.model_log_loss < self.market_log_loss
            and self.model_brier < self.market_brier
        )


def evaluate_window(
    races: list[EvaluatedRace],
    *,
    start: datetime,
    end: datetime,
) -> EvaluationWindow:
    selected = [race for race in races if start <= race.race_time < end]
    if not selected:
        raise ValueError("evaluation window contains no races")

    evaluations: list[RaceEvaluation] = [
        evaluate_against_market(
            race.race_id,
            race.winner,
            race.model_probabilities,
            race.market_probabilities,
        )
        for race in selected
    ]
    return EvaluationWindow(
        start=start,
        end=end,
        n=len(evaluations),
        model_log_loss=mean(item.model_log_loss for item in evaluations),
        market_log_loss=mean(item.market_log_loss for item in evaluations),
        model_brier=mean(item.model_brier for item in evaluations),
        market_brier=mean(item.market_brier for item in evaluations),
    )


def aggregate_windows(windows: list[EvaluationWindow]) -> dict[str, float | int]:
    if not windows:
        raise ValueError("at least one window is required")
    total_n = sum(window.n for window in windows)
    return {
        "windows": len(windows),
        "races": total_n,
        "model_log_loss": sum(window.model_log_loss * window.n for window in windows) / total_n,
        "market_log_loss": sum(window.market_log_loss * window.n for window in windows) / total_n,
        "model_brier": sum(window.model_brier * window.n for window in windows) / total_n,
        "market_brier": sum(window.market_brier * window.n for window in windows) / total_n,
        "windows_beating_market": sum(window.model_beats_market for window in windows),
    }
