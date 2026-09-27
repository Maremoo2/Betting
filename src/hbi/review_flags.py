from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReviewFlagType(StrEnum):
    TRIP_TROUBLE = "TRIP_TROUBLE"
    EQUIPMENT_CHANGE = "EQUIPMENT_CHANGE"
    DRIVER_JOCKEY_CHANGE = "DRIVER_JOCKEY_CHANGE"
    SCRATCH = "SCRATCH"
    WEATHER_CHANGE = "WEATHER_CHANGE"
    TRACK_CHANGE = "TRACK_CHANGE"
    HEALTH_OR_TRAINING_SIGNAL = "HEALTH_OR_TRAINING_SIGNAL"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ReviewFlag:
    race_id: str
    flag_type: ReviewFlagType
    source_uri: str
    source_published_at_utc: str
    selection_id: str | None = None
    note: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.source_uri:
            raise ValueError("source_uri is required")


def requires_reprice(flag: ReviewFlag) -> bool:
    """All structured pre-race exceptions force a fresh probability review.

    This does not prescribe the direction or size of a probability adjustment.
    The evidence must be interpreted by a validated feature/model or human review.
    """
    return True
