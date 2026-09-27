from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .domain import MarketSnapshot
from .ingestion import RaceCard, RaceDataProvider, RaceResult
from .prewatch import MaterialChange, MaterialChangePolicy, PreWatchAction, assess_material_change
from .storage import SQLiteStore


@dataclass(frozen=True)
class SnapshotProcessResult:
    inserted: bool
    material_change: MaterialChange | None
    event_id: str | None


class HBIPipeline:
    """Application service coordinating ingestion, persistence and pre-watch.

    It contains no provider-specific scraping logic. Providers feed canonical
    RaceCard / MarketSnapshot objects into this service.
    """

    def __init__(self, store: SQLiteStore, *, prewatch_policy: MaterialChangePolicy | None = None):
        self.store = store
        self.prewatch_policy = prewatch_policy or MaterialChangePolicy()

    def persist_race_card(self, card: RaceCard) -> None:
        self.store.upsert_race(card.race)
        for runner in card.runners:
            self.store.upsert_runner(runner)

    def ingest_race_provider(self, provider: RaceDataProvider, start: datetime, end: datetime) -> int:
        cards = provider.race_cards(start, end)
        for card in cards:
            self.persist_race_card(card)
        return len(cards)

    def process_snapshot(
        self,
        snapshot: MarketSnapshot,
        *,
        race_start_at: datetime | None = None,
        source_uri: str | None = None,
        material_event: str | None = None,
        policy_version: str = "v1",
    ) -> SnapshotProcessResult:
        if race_start_at is None:
            race = self.store.get_race(snapshot.race_id)
            if race is not None:
                race_start_at = datetime.fromisoformat(race["start_time_utc"])

        previous_row = self.store.latest_market_snapshot(
            snapshot.race_id,
            snapshot.selection_id,
            before=snapshot.captured_at,
        )
        inserted = self.store.insert_market_snapshot(snapshot, source_uri=source_uri)
        if not inserted or previous_row is None:
            return SnapshotProcessResult(inserted=inserted, material_change=None, event_id=None)

        previous = MarketSnapshot(
            race_id=previous_row["race_id"],
            selection_id=previous_row["selection_id"],
            captured_at=datetime.fromisoformat(previous_row["captured_at_utc"]),
            odds_decimal=float(previous_row["odds_decimal"]),
            pool_size=previous_row["pool_size"],
            market_regime=previous_row["market_regime"],
            information_cutoff_phase=previous_row["information_cutoff_phase"],
        )
        change = assess_material_change(
            previous,
            snapshot,
            race_start_at=race_start_at,
            policy=self.prewatch_policy,
            material_event=material_event,
        )
        event_id = None
        if change.action != PreWatchAction.HOLD:
            event_id = self.store.insert_prewatch_event(
                race_id=snapshot.race_id,
                captured_at=snapshot.captured_at,
                change=change,
                policy_version=policy_version,
            )
        return SnapshotProcessResult(inserted=inserted, material_change=change, event_id=event_id)

    def settle(self, result: RaceResult) -> None:
        self.store.settle_outcome(
            race_id=result.race_id,
            winner_selection_id=result.winner_selection_id,
            settled_at=result.settled_at,
            actual_close_price=result.actual_close_price,
        )
