from __future__ import annotations

from dataclasses import dataclass

from .domain import RejectStatus


def _unit(value: float, name: str) -> float:
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be in [0, 1]")
    return value


@dataclass(frozen=True)
class RaceDifficultyInput:
    field_size: int
    field_parity: float
    race_shape_uncertainty: float
    break_or_start_risk: float
    low_information_fraction: float
    environment_change_fraction: float


@dataclass(frozen=True)
class RaceDifficultyResult:
    difficulty_score: float
    stability_score: float
    band: str
    reject_status: RejectStatus


def score_race_difficulty(data: RaceDifficultyInput) -> RaceDifficultyResult:
    """Diagnostic race-level uncertainty score.

    This is intentionally NOT a horse probability adjustment. It is a governance
    signal for reject-option, minimum edge, staking and later calibration research.
    """
    if data.field_size < 2:
        raise ValueError("field_size must be >= 2")

    parity = _unit(data.field_parity, "field_parity")
    shape = _unit(data.race_shape_uncertainty, "race_shape_uncertainty")
    start = _unit(data.break_or_start_risk, "break_or_start_risk")
    low_info = _unit(data.low_information_fraction, "low_information_fraction")
    env = _unit(data.environment_change_fraction, "environment_change_fraction")

    field_size_component = min(max((data.field_size - 6) / 12, 0.0), 1.0)

    score = 100 * (
        0.25 * parity
        + 0.25 * shape
        + 0.15 * start
        + 0.15 * low_info
        + 0.10 * env
        + 0.10 * field_size_component
    )
    score = round(score, 2)
    stability = round(100 - score, 2)

    if score >= 75:
        band = "HIGH"
        reject = RejectStatus.REJECT
    elif score >= 55:
        band = "MEDIUM"
        reject = RejectStatus.CAUTION
    else:
        band = "LOW"
        reject = RejectStatus.CLEAR

    return RaceDifficultyResult(score, stability, band, reject)
