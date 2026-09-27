from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RejectStatus(StrEnum):
    CLEAR = "CLEAR"
    CAUTION = "CAUTION"
    REJECT = "REJECT"


class Decision(StrEnum):
    BET = "BET"
    WATCH = "WATCH"
    PASS = "PASS"


@dataclass(frozen=True)
class MarketSnapshot:
    race_id: str
    selection_id: str
    captured_at: datetime
    odds_decimal: float
    pool_size: float | None = None
    market_regime: str = "UNKNOWN"
    information_cutoff_phase: str = "UNKNOWN"


@dataclass(frozen=True)
class ProbabilityEstimate:
    race_id: str
    model_version: str
    created_at: datetime
    probabilities: dict[str, float]


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
