from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .domain import MarketSnapshot
from .ingestion import RaceCard, RaceResult


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return parsed


def load_race_cards(path: str | Path) -> list[RaceCard]:
    """Load canonical race cards from a JSON interchange file.

    Expected shape:
    {"races": [{"race": {...}, "runners": [{...}, ...]}]}
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cards: list[RaceCard] = []
    for item in payload.get("races", []):
        cards.append(RaceCard(race=dict(item["race"]), runners=tuple(item["runners"])))
    return cards


def load_market_snapshots(path: str | Path) -> list[MarketSnapshot]:
    """Load timestamped market snapshots from canonical JSON."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        MarketSnapshot(
            race_id=item["race_id"],
            selection_id=str(item["selection_id"]),
            captured_at=_dt(item["captured_at"]),
            odds_decimal=float(item["odds_decimal"]),
            pool_size=None if item.get("pool_size") is None else float(item["pool_size"]),
            market_regime=item.get("market_regime", "UNKNOWN"),
            information_cutoff_phase=item.get("information_cutoff_phase", "UNKNOWN"),
        )
        for item in payload.get("snapshots", [])
    ]


def load_results(path: str | Path) -> list[RaceResult]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        RaceResult(
            race_id=item["race_id"],
            winner_selection_id=str(item["winner_selection_id"]),
            settled_at=_dt(item["settled_at"]),
            actual_close_price=(
                None if item.get("actual_close_price") is None
                else float(item["actual_close_price"])
            ),
        )
        for item in payload.get("results", [])
    ]
