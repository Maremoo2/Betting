from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .domain import MarketSnapshot
from .providers.rikstoto import FetchResult, RikstotoClient, RikstotoRace
from .storage import SQLiteStore


@dataclass(frozen=True)
class CollectionSummary:
    races_discovered: int = 0
    races_due: int = 0
    snapshots_inserted: int = 0
    fetch_failures: int = 0


class RikstotoCollector:
    PROVIDER = "rikstoto"

    def __init__(self, store: SQLiteStore, client: RikstotoClient | None = None):
        self.store = store
        self.client = client or RikstotoClient()

    def _audit(self, fetch: FetchResult, fetched_at: datetime) -> None:
        self.store.record_provider_fetch(
            fetch_id=str(uuid4()),
            provider=self.PROVIDER,
            endpoint=fetch.url,
            fetched_at=fetched_at,
            success=fetch.success,
            status_code=fetch.status_code,
            latency_ms=fetch.latency_ms,
            error_message=fetch.error,
        )

    @staticmethod
    def _discipline(sport_type: str) -> str:
        return {"T": "trot", "G": "gallop"}.get(sport_type.upper(), sport_type.lower() or "unknown")

    def discover(self, now: datetime | None = None) -> list[RikstotoRace]:
        observed = now or datetime.now(UTC)
        fetch = self.client.racedays()
        self._audit(fetch, observed)
        races = self.client.discover_races(fetch)

        for race in races:
            local_date = race.start_time.astimezone(self.client.parse_timestamp(race.start_time_raw).tzinfo)
            self.store.upsert_race(
                {
                    "race_id": race.race_id,
                    "race_date": local_date.date().isoformat(),
                    "country": race.country_code or "UNKNOWN",
                    "track": race.raceday_name or race.track_code,
                    "race_no": race.race_number,
                    "start_time_utc": race.start_time.isoformat(),
                    "discipline": self._discipline(race.sport_type),
                    "distance_m": None,
                    "start_method": race.start_method,
                    "race_class": None,
                    "created_at_utc": observed.isoformat(),
                }
            )
            self.store.upsert_provider_race_ref(
                provider=self.PROVIDER,
                provider_raceday_key=race.raceday_key,
                race_number=race.race_number,
                race_id=race.race_id,
                provider_track_code=race.track_code,
                provider_start_time_raw=race.start_time_raw,
                discovered_at=observed,
                raw={
                    "pools": list(race.pools),
                    "single_leg_products": list(race.single_leg_products),
                    "progress_status": race.progress_status,
                },
            )
        return races

    def due_races(
        self,
        *,
        now: datetime | None = None,
        min_minutes: float = 2.0,
        max_minutes: float = 8.0,
    ) -> list[dict[str, object]]:
        current = now or datetime.now(UTC)
        start = current + timedelta(minutes=min_minutes)
        end = current + timedelta(minutes=max_minutes)
        return self.store.provider_races_between(start, end)

    @staticmethod
    def _provider_updated_at(
        client: RikstotoClient,
        item: dict[str, object],
    ) -> datetime | None:
        value = item.get("lastUpdated")
        if not isinstance(value, str) or not value:
            return None
        try:
            return client.parse_timestamp(value)
        except ValueError:
            return None

    @staticmethod
    def _selection_key(product: str, item: dict[str, object]) -> str | None:
        if product in {"V", "P"}:
            value = item.get("startNumber")
            return None if value is None else str(value)
        if product == "TV":
            first, second = item.get("startNumber1"), item.get("startNumber2")
            return None if first is None or second is None else f"{first}-{second}"
        if product == "T":
            values = (item.get("startNumber1"), item.get("startNumber2"), item.get("startNumber3"))
            return None if any(value is None for value in values) else "-".join(map(str, values))
        return None

    def _store_fetch_rows(
        self,
        *,
        race_id: str,
        product: str,
        fetch: FetchResult,
        observed_at: datetime,
    ) -> int:
        self._audit(fetch, observed_at)
        if not fetch.success:
            return 0

        inserted = 0
        for item in self.client.result_list(fetch):
            selection_key = self._selection_key(product, item)
            if selection_key is None:
                continue
            provider_updated_at = self._provider_updated_at(self.client, item)
            digest = hashlib.sha256(
                (
                    f"{race_id}|{product}|{selection_key}|{observed_at.isoformat()}|"
                    f"{json.dumps(item, sort_keys=True)}"
                ).encode("utf-8")
            ).hexdigest()
            odds = item.get("odds")
            min_odds = item.get("minOdds")
            max_odds = item.get("maxOdds")
            was_inserted = self.store.insert_provider_market_snapshot(
                snapshot_id=digest,
                provider=self.PROVIDER,
                race_id=race_id,
                product=product,
                selection_key=selection_key,
                observed_at=observed_at,
                provider_updated_at=provider_updated_at,
                source_uri=fetch.url,
                odds_decimal=None if odds is None else float(odds),
                min_odds=None if min_odds is None else float(min_odds),
                max_odds=None if max_odds is None else float(max_odds),
                raw=item,
            )
            inserted += int(was_inserted)

            if product == "V" and odds is not None:
                try:
                    self.store.insert_market_snapshot(
                        MarketSnapshot(
                            race_id=race_id,
                            selection_id=selection_key,
                            captured_at=observed_at,
                            odds_decimal=float(odds),
                            market_regime="RIKSTOTO_TOTE",
                            information_cutoff_phase="LIVE",
                        ),
                        source_uri=fetch.url,
                    )
                except ValueError:
                    pass
        return inserted

    def collect_market(
        self,
        *,
        raceday_key: str,
        race_number: int,
        race_id: str,
        observed_at: datetime | None = None,
    ) -> tuple[int, int]:
        observed = observed_at or datetime.now(UTC)
        calls = (
            ("V", self.client.win_odds(raceday_key, race_number)),
            ("P", self.client.place_odds(raceday_key, race_number)),
            ("TV", self.client.twin_odds(raceday_key, race_number)),
            ("T", self.client.triple_odds(raceday_key, race_number)),
        )
        inserted = failures = 0
        for product, fetch in calls:
            if not fetch.success:
                failures += 1
            inserted += self._store_fetch_rows(
                race_id=race_id,
                product=product,
                fetch=fetch,
                observed_at=observed,
            )
        return inserted, failures

    def collect_due(self, now: datetime | None = None) -> CollectionSummary:
        current = now or datetime.now(UTC)
        races = self.discover(current)
        due = self.due_races(now=current)
        snapshots = failures = 0
        for race in due:
            inserted, failed = self.collect_market(
                raceday_key=str(race["provider_raceday_key"]),
                race_number=int(race["race_number"]),
                race_id=str(race["race_id"]),
                observed_at=current,
            )
            snapshots += inserted
            failures += failed
        return CollectionSummary(
            races_discovered=len(races),
            races_due=len(due),
            snapshots_inserted=snapshots,
            fetch_failures=failures,
        )
