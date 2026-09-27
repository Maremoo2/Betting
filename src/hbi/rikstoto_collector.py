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
        return {"T": "trot", "G": "gallop"}.get(
            sport_type.upper(),
            sport_type.lower() or "unknown",
        )

    def discover(self, now: datetime | None = None) -> list[RikstotoRace]:
        observed = now or datetime.now(UTC)
        fetch = self.client.racedays()
        self._audit(fetch, observed)
        races = self.client.discover_races(fetch)

        for race in races:
            local_date = race.start_time_raw[:10]
            self.store.upsert_race(
                {
                    "race_id": race.race_id,
                    "race_date": local_date,
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
                ).encode()
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


    @staticmethod
    def _annual_stat(
        annual: dict[str, object],
        bucket: str,
        key: str,
    ) -> int | float | None:
        value = annual.get(bucket)
        if not isinstance(value, dict):
            return None
        item = value.get(key)
        if item is None:
            return None
        if isinstance(item, (int, float)):
            return item
        try:
            return float(item)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _scratched_for_race(payload: object, race_number: int) -> set[int]:
        if not isinstance(payload, dict):
            return set()
        result = payload.get("result")
        if not isinstance(result, dict):
            return set()
        values = result.get(str(race_number), result.get(race_number))
        if not isinstance(values, list):
            return set()
        output: set[int] = set()
        for value in values:
            try:
                output.add(int(value))
            except (TypeError, ValueError):
                continue
        return output

    def collect_fundamentals(
        self,
        *,
        raceday_key: str,
        race_number: int,
        race_id: str,
        observed_at: datetime,
        products: list[str] | None = None,
    ) -> tuple[int, bool, str | None]:
        """Collect market-free pre-race runner fundamentals from the program contract.

        The base program is used, never program/addition, because the latter can contain
        odds and investment percentages. Only runner/race facts and historical horse
        statistics are persisted into the fundamental feature store.
        """
        candidates: list[str] = []
        for product in ["V", *(products or [])]:
            code = str(product)
            if code and code not in candidates:
                candidates.append(code)

        selected_fetch: FetchResult | None = None
        selected_product: str | None = None
        selected_race: dict[str, object] | None = None

        for product in candidates:
            fetch = self.client.program(raceday_key, product)
            self._audit(fetch, observed_at)
            result = self.client.result_object(fetch)
            races = result.get("races") if isinstance(result, dict) else None
            if not fetch.success or not isinstance(races, list):
                continue
            target = next(
                (
                    race
                    for race in races
                    if isinstance(race, dict)
                    and int(race.get("raceNumber", -1)) == race_number
                ),
                None,
            )
            if isinstance(target, dict) and isinstance(target.get("starts"), list):
                selected_fetch = fetch
                selected_product = product
                selected_race = target
                break

        if selected_fetch is None or selected_race is None or selected_product is None:
            return 0, False, None

        scratched_fetch = self.client.scratched(raceday_key)
        self._audit(scratched_fetch, observed_at)
        scratched = (
            self._scratched_for_race(scratched_fetch.payload, race_number)
            if scratched_fetch.success
            else set()
        )

        digest = hashlib.sha256(
            (
                f"{raceday_key}|{race_number}|fundamentals|{selected_product}|"
                f"{observed_at.isoformat()}"
            ).encode()
        ).hexdigest()
        self.store.insert_provider_payload(
            payload_id=digest,
            provider=self.PROVIDER,
            category="PROGRAM_FUNDAMENTALS",
            provider_raceday_key=raceday_key,
            race_number=race_number,
            product=selected_product,
            observed_at=observed_at,
            source_uri=selected_fetch.url,
            payload=selected_fetch.payload if isinstance(selected_fetch.payload, dict) else {},
        )

        existing = self.store.get_race(race_id)
        if existing is not None:
            self.store.upsert_race(
                {
                    "race_id": race_id,
                    "race_date": existing["race_date"],
                    "country": existing["country"],
                    "track": existing["track"],
                    "race_no": race_number,
                    "start_time_utc": existing["start_time_utc"],
                    "discipline": existing["discipline"],
                    "distance_m": selected_race.get("distance"),
                    "start_method": selected_race.get("startMethod"),
                    "race_class": selected_race.get("raceName"),
                    "created_at_utc": existing["created_at_utc"],
                }
            )

        inserted = 0
        starts = selected_race.get("starts")
        if not isinstance(starts, list):
            return 0, False, selected_fetch.url

        for start in starts:
            if not isinstance(start, dict) or start.get("startNumber") is None:
                continue
            selection_id = str(start["startNumber"])
            try:
                start_number = int(start["startNumber"])
            except (TypeError, ValueError):
                continue
            is_scratched = start_number in scratched

            self.store.upsert_runner(
                {
                    "race_id": race_id,
                    "selection_id": selection_id,
                    "horse_name": str(start.get("horseName") or selection_id),
                    "post_position": start.get("postPosition"),
                    "driver_or_jockey": start.get("driver"),
                    "trainer": start.get("trainer"),
                    "scratched": int(is_scratched),
                }
            )

            annual_raw = start.get("horseAnnualStatistics")
            annual = annual_raw if isinstance(annual_raw, dict) else {}
            total_starts = self._annual_stat(
                annual, "total", "numberOfStarts"
            )
            total_wins = self._annual_stat(
                annual, "total", "numberOfFirstPlaces"
            )
            data_quality = (
                "KNOWN_HISTORY"
                if total_starts is not None and total_wins is not None
                else "MISSING_HISTORY"
            )
            snapshot_id = hashlib.sha256(
                (
                    f"{race_id}|{selection_id}|{observed_at.isoformat()}|"
                    f"{json.dumps(start, sort_keys=True, default=str)}"
                ).encode()
            ).hexdigest()
            inserted += int(
                self.store.insert_runner_fundamental_snapshot(
                    {
                        "snapshot_id": snapshot_id,
                        "race_id": race_id,
                        "selection_id": selection_id,
                        "observed_at_utc": observed_at.isoformat(),
                        "feature_as_of_utc": observed_at.isoformat(),
                        "source_uri": selected_fetch.url,
                        "horse_name": start.get("horseName"),
                        "driver_or_jockey": start.get("driver"),
                        "trainer": start.get("trainer"),
                        "post_position": start.get("postPosition"),
                        "extra_distance_m": start.get("extraDistance"),
                        "total_earnings": start.get("totalEarnings"),
                        "age": start.get("age"),
                        "sex": start.get("sex"),
                        "record_volt": start.get("recordVolt"),
                        "record_auto": start.get("recordAuto"),
                        "history_total_starts": total_starts,
                        "history_total_wins": total_wins,
                        "history_total_seconds": self._annual_stat(
                            annual, "total", "numberOfSecondPlaces"
                        ),
                        "history_total_thirds": self._annual_stat(
                            annual, "total", "numberOfThirdPlaces"
                        ),
                        "history_total_earnings": self._annual_stat(
                            annual, "total", "totalEarnings"
                        ),
                        "current_year_starts": self._annual_stat(
                            annual, "currentYear", "numberOfStarts"
                        ),
                        "current_year_wins": self._annual_stat(
                            annual, "currentYear", "numberOfFirstPlaces"
                        ),
                        "current_year_seconds": self._annual_stat(
                            annual, "currentYear", "numberOfSecondPlaces"
                        ),
                        "current_year_thirds": self._annual_stat(
                            annual, "currentYear", "numberOfThirdPlaces"
                        ),
                        "current_year_earnings": self._annual_stat(
                            annual, "currentYear", "totalEarnings"
                        ),
                        "scratched": int(is_scratched),
                        "data_quality": data_quality,
                        "raw_json": json.dumps(start, ensure_ascii=False, default=str),
                    }
                )
            )
        return inserted, True, selected_fetch.url

    def collect_pool_context(
        self,
        *,
        raceday_key: str,
        products: list[str],
        observed_at: datetime,
    ) -> tuple[int, int]:
        """Persist raw multi-leg/public-pool payloads when historical endpoints still work.

        These endpoints were visible in older public Rikstoto frontend source. They
        are treated as optional research inputs and never required for the core
        single-race collector.
        """
        inserted = failures = 0

        timeline = self.client.product_timeline(raceday_key)
        self._audit(timeline, observed_at)
        if timeline.success and isinstance(timeline.payload, dict):
            digest = hashlib.sha256(
                f"{raceday_key}|timeline|{observed_at.isoformat()}".encode()
            ).hexdigest()
            inserted += int(
                self.store.insert_provider_payload(
                    payload_id=digest,
                    provider=self.PROVIDER,
                    category="PRODUCT_TIMELINE",
                    provider_raceday_key=raceday_key,
                    observed_at=observed_at,
                    source_uri=timeline.url,
                    payload=timeline.payload,
                )
            )
        else:
            failures += 1

        investments = self.client.product_investments(raceday_key)
        self._audit(investments, observed_at)
        if investments.success and isinstance(investments.payload, dict):
            digest = hashlib.sha256(
                f"{raceday_key}|investments|{observed_at.isoformat()}".encode()
            ).hexdigest()
            inserted += int(
                self.store.insert_provider_payload(
                    payload_id=digest,
                    provider=self.PROVIDER,
                    category="PRODUCT_INVESTMENTS",
                    provider_raceday_key=raceday_key,
                    observed_at=observed_at,
                    source_uri=investments.url,
                    payload=investments.payload,
                )
            )
        else:
            failures += 1

        for product in sorted(set(products)):
            if product not in {"DD", "V4", "V4X", "V5", "V5A", "V5B", "V64", "V65", "V75", "V85"}:
                continue
            addition = self.client.program_addition(raceday_key, product)
            self._audit(addition, observed_at)
            if addition.success and isinstance(addition.payload, dict):
                digest = hashlib.sha256(
                    f"{raceday_key}|{product}|addition|{observed_at.isoformat()}".encode()
                ).hexdigest()
                inserted += int(
                    self.store.insert_provider_payload(
                        payload_id=digest,
                        provider=self.PROVIDER,
                        category="PROGRAM_ADDITION",
                        provider_raceday_key=raceday_key,
                        product=product,
                        observed_at=observed_at,
                        source_uri=addition.url,
                        payload=addition.payload,
                    )
                )
            else:
                failures += 1
        return inserted, failures

    def collect_market(
        self,
        *,
        raceday_key: str,
        race_number: int,
        race_id: str,
        observed_at: datetime | None = None,
        products: set[str] | None = None,
    ) -> tuple[int, int]:
        observed = observed_at or datetime.now(UTC)
        enabled = products or {"V", "P", "TV", "T"}
        fetchers = {
            "V": self.client.win_odds,
            "P": self.client.place_odds,
            "TV": self.client.twin_odds,
            "T": self.client.triple_odds,
        }
        calls = tuple(
            (product, fetchers[product](raceday_key, race_number))
            for product in ("V", "P", "TV", "T")
            if product in enabled
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
