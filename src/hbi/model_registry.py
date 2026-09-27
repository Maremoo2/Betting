from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModelRole(StrEnum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class ModelVersion:
    model_name: str
    version: str
    role: ModelRole
    training_cutoff: str
    feature_set_version: str
    calibration_version: str
    notes: str = ""


def can_promote(
    *,
    champion_log_loss: float,
    challenger_log_loss: float,
    champion_brier: float,
    challenger_brier: float,
    untouched_n: int,
    minimum_n: int = 500,
) -> bool:
    """Conservative first-pass promotion gate.

    Economic metrics should be checked separately. This gate only prevents a
    challenger from promotion unless predictive calibration metrics improve on
    a sufficiently large untouched sample.
    """
    return (
        untouched_n >= minimum_n
        and challenger_log_loss < champion_log_loss
        and challenger_brier < champion_brier
    )
