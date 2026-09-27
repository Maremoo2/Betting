from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .domain import MarketSnapshot


@dataclass(frozen=True)
class RaceCard:
    race: dict[str, object]
    runners: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class RaceResult:
    race_id: str
    winner_selection_id: str
    settled_at: datetime
    actual_close_price: float | None = None


class RaceDataProvider(Protocol):
    """Adapter contract for ATG/Rikstoto/other approved race data sources."""

    def race_cards(self, start: datetime, end: datetime) -> list[RaceCard]: ...

    def result(self, race_id: str) -> RaceResult | None: ...


class MarketDataProvider(Protocol):
    """Adapter contract for timestamped tote/exchange/odds feeds."""

    def snapshots(self, race_id: str, captured_at: datetime) -> list[MarketSnapshot]: ...
