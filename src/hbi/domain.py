from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math


class RejectStatus(StrEnum):
    CLEAR = "CLEAR"
    CAUTION = "CAUTION"
    REJECT = "REJECT"


class Decision(StrEnum):
    BET = "BET"
    WATCH = "WATCH"
    PASS = "PASS"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class MarketSnapshot:
    race_id: str
    selection_id: str
    captured_at: datetime
    odds_decimal: float
    pool_size: float | None = None
    market_regime: str = "UNKNOWN"
    information_cutoff_phase: str = "UNKNOWN"

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        if not math.isfinite(self.odds_decimal) or self.odds_decimal <= 1:
            raise ValueError("odds_decimal must be finite and > 1")
        if self.pool_size is not None and self.pool_size < 0:
            raise ValueError("pool_size must be >= 0")


@dataclass(frozen=True)
class ProbabilityEstimate:
    race_id: str
    model_version: str
    created_at: datetime
    probabilities: dict[str, float]

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if not self.probabilities:
            raise ValueError("probabilities cannot be empty")
        if any((not math.isfinite(p)) or p <= 0 for p in self.probabilities.values()):
            raise ValueError("probabilities must be finite and > 0")
        if not math.isclose(sum(self.probabilities.values()), 1.0, abs_tol=1e-6):
            raise ValueError("full-field probabilities must sum to 1")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    race_id: str
    selection_id: str | None
    claim_type: str
    value: str
    source_uri: str
    source_published_at: datetime
    extracted_at: datetime
    confidence: float

    def __post_init__(self) -> None:
        _require_aware(self.source_published_at, "source_published_at")
        _require_aware(self.extracted_at, "extracted_at")
        if self.source_published_at > self.extracted_at:
            raise ValueError("source cannot be published after extraction")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if not self.source_uri:
            raise ValueError("source_uri is required")
