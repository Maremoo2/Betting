from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from .domain import MarketSnapshot
from .provider_capability import CONTRACT, capability, resolve_field
from .providers.atg import AtgClient, AtgFetchResult
from .providers.letrot import LeTrotClient
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

    def __init__(
        self,
        store: SQLiteStore,
        client: RikstotoClient | None = None,
        atg_client: AtgClient | None = None,
        *,
        clock=None,
        capability_probe: bool = False,
        letrot_client: LeTrotClient | None = None,
    ):
        self.clock = clock or (lambda: datetime.now(UTC))
        self.capability_probe = capability_probe
        self.letrot_client = letrot_client or LeTrotClient()
        self.last_capability = None
        self.store = store
        self.client = client or RikstotoClient()
        self.atg_client = atg_client or AtgClient()

    def _audit_provider(
        self,
        fetch: FetchResult | AtgFetchResult,
        fetched_at: datetime,
        *,
        provider: str,
    ) -> None:
        self.store.record_provider_fetch(
            fetch_id=str(uuid4()),
            provider=provider,
            endpoint=fetch.url,
            fetched_at=fetched_at,
            success=fetch.success,
            status_code=fetch.status_code,
            latency_ms=fetch.latency_ms,
            error_message=fetch.error,
        )

    def _audit(self, fetch: FetchResult, fetched_at: datetime) -> None:
        self._audit_provider(fetch, fetched_at, provider=self.PROVIDER)

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

    @staticmethod
    def _starts_for_race(payload: object, race_number: int) -> list[dict[str, object]]:
        if not isinstance(payload, dict):
            return []
        result = payload.get("result")
        if not isinstance(result, dict):
            return []
        values = result.get(str(race_number), result.get(race_number))
        if not isinstance(values, list):
            return []
        return [item for item in values if isinstance(item, dict)]

    @staticmethod
    def _atg_placement(life: dict[str, object], place: int) -> int | None:
        placement = life.get("placement")
        if not isinstance(placement, dict):
            return None
        value = placement.get(str(place), placement.get(place))
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None

    def collect_fundamentals(
        self,
        *,
        raceday_key: str,
        race_number: int,
        race_id: str,
        observed_at: datetime,
        products: list[str] | None = None,
    ) -> tuple[int, bool, str | None]:
        """Capture canonical field; enrich only an entirely verified pre-race cohort."""
        del products  # availability no longer determines the fundamental source

        collection_started_at = self.clock()
        requested_at = observed_at
        starts_fetch = self.client.starts(raceday_key)
        observed_at = max(requested_at, self.clock())
        self._audit(starts_fetch, observed_at)
        starts = self._starts_for_race(starts_fetch.payload, race_number)


        scratched_fetch = self.client.scratched(raceday_key)
        observed_at = max(requested_at, self.clock())
        self._audit(scratched_fetch, observed_at)
        scratched = (
            self._scratched_for_race(scratched_fetch.payload, race_number)
            if scratched_fetch.success
            else set()
        )

        digest = hashlib.sha256(
            f"{raceday_key}|{race_number}|starts|{observed_at.isoformat()}".encode()
        ).hexdigest()
        self.store.insert_provider_payload(
            payload_id=digest,
            provider=self.PROVIDER,
            category="RACEDAY_STARTS",
            provider_raceday_key=raceday_key,
            race_number=race_number,
            observed_at=observed_at,
            source_uri=starts_fetch.url,
            payload=starts_fetch.payload if isinstance(starts_fetch.payload, dict) else {},
        )

        race_row = self.store.get_race(race_id)
        race = None if race_row is None else dict(race_row)
        country = str(race.get("country") or "") if race else ""
        track = str(race.get("track") or "") if race else ""
        discipline = str(race.get("discipline") or "") if race else ""
        atg_source: str | None = None
        race_payload = None
        resolved = None
        expected_start = datetime.fromisoformat(str(race["start_time_utc"])) if race else observed_at
        if (race and (self.capability_probe or
                capability("atg", country, discipline)["status"] == "VERIFIED")):
            try:
                calendar = self.atg_client.calendar_day(expected_start.astimezone(ZoneInfo("Europe/Stockholm")).date())
                self._audit_provider(calendar, self.clock(), provider="atg")
                resolved = self.atg_client.resolve_race(
                    calendar, track_name=track, race_number=race_number,
                    expected_start=expected_start, country=country, discipline=discipline,
                )
                if resolved is not None:
                    game = self.atg_client.race_game(resolved.race_id)
                    self._audit_provider(game, self.clock(), provider="atg")
                    race_payload = self.atg_client.race_payload(game)
                    atg_source = game.url
            except (TypeError, ValueError, KeyError):
                race_payload = None
        observed_at = max(requested_at, self.clock())
        scratch_payload = scratched_fetch.payload
        scratch_result = (scratch_payload.get("result")
                          if isinstance(scratch_payload, dict) else None)
        # Empty dict means no scratches anywhere; a malformed/missing result is unknown.
        scratch_ok = (scratched_fetch.success and isinstance(scratch_result, dict)
                      and all(isinstance(v, list) and all(type(n) is int for n in v)
                              for v in scratch_result.values()))
        raw_result = starts_fetch.payload.get("result") if isinstance(
            starts_fetch.payload, dict) else None
        raw_starts = raw_result.get(str(race_number)) if isinstance(raw_result, dict) else None
        canonical_schema_ok = isinstance(raw_starts, list) and len(raw_starts) == len(starts)
        matched, evidence = resolve_field(
            starts=starts, scratches=scratched, scratch_ok=scratch_ok and starts_fetch.success and canonical_schema_ok,
            payload=race_payload, country=country, discipline=discipline,
            race_number=race_number, expected_start=expected_start, observed_at=observed_at,
            provider_race_id=resolved.race_id if resolved else None, source_uri=atg_source,
            probe=self.capability_probe,
        )
        if country == "FR" and discipline == "trot" and matched:
            corroboration = self.letrot_client.corroborate(
                track=(race_payload.get("track") or {}).get("name", track),
                race_number=race_number, expected_start=expected_start,
                matched=matched, audit=self._audit_provider, clock=self.clock,
            )
            evidence["corroboration"] = corroboration
            if not corroboration["passed"]:
                evidence["reasons"].append("LETROT_FULL_FIELD_CORROBORATION_FAILED")
                evidence["passed"] = False
                matched = {}
        observed_at = max(requested_at, self.clock())
        cutoffs = [expected_start]
        if race_payload:
            provider_start = self.atg_client._parse_time(race_payload.get("startTime"))
            if provider_start is not None:
                cutoffs.append(provider_start)
        french_start = evidence.get("corroboration", {}).get("race_start_utc")
        if french_start:
            cutoffs.append(datetime.fromisoformat(french_start))
        expected_start = min(cutoffs)
        evidence["race_start_utc"] = expected_start.isoformat()
        evidence["collection_started_at_utc"] = collection_started_at.isoformat()
        evidence["observed_at_utc"] = observed_at.isoformat()
        if (observed_at - collection_started_at).total_seconds() > 120:
            evidence["reasons"].append("COLLECTION_WINDOW_TOO_LONG")
            evidence["passed"] = False
            matched = {}
        if observed_at >= expected_start:
            evidence["reasons"].append("FETCH_COMPLETED_AFTER_START")
            evidence["passed"] = False
            matched = {}
        self.last_capability = evidence
        self.store.insert_provider_payload(
            payload_id=str(uuid4()), provider="atg", category=CONTRACT,
            provider_raceday_key=race_id, race_number=race_number,
            observed_at=observed_at, source_uri=atg_source or starts_fetch.url, payload=evidence,
        )
        if not starts_fetch.success or not starts:
            return 0, False, starts_fetch.url

        inserted = 0
        for start in starts:
            value = start.get("startNumber")
            if value is None:
                continue
            try:
                start_number = int(value)
            except (TypeError, ValueError):
                continue
            selection_id = str(start_number)
            is_scratched = bool(start.get("isScratched")) or start_number in scratched
            horse_name = str(start.get("horseName") or selection_id)
            registration = start.get("horseRegistrationNumber")
            driver_name = start.get("driverName")

            atg_start = matched.get(selection_id)

            horse: dict[str, object] = {}
            trainer_name: str | None = None
            history_starts: int | None = None
            history_wins: int | None = None
            history_seconds: int | None = None
            history_thirds: int | None = None
            history_earnings: float | None = None
            age: int | None = None
            sex: str | None = None

            if isinstance(atg_start, dict):
                raw_horse = atg_start.get("horse")
                if isinstance(raw_horse, dict):
                    horse = raw_horse
                    raw_stats = horse.get("statistics")
                    stats = raw_stats if isinstance(raw_stats, dict) else {}
                    raw_life = stats.get("life")
                    life = raw_life if isinstance(raw_life, dict) else {}
                    try:
                        history_starts = (
                            None
                            if life.get("starts") is None
                            else int(life.get("starts"))
                        )
                    except (TypeError, ValueError):
                        history_starts = None
                    history_wins = self._atg_placement(life, 1)
                    history_seconds = self._atg_placement(life, 2)
                    history_thirds = self._atg_placement(life, 3)
                    try:
                        history_earnings = (
                            None
                            if life.get("earnings") is None
                            else float(life.get("earnings"))
                        )
                    except (TypeError, ValueError):
                        history_earnings = None
                    try:
                        age = None if horse.get("age") is None else int(horse.get("age"))
                    except (TypeError, ValueError):
                        age = None
                    sex = None if horse.get("sex") is None else str(horse.get("sex"))
                    raw_trainer = horse.get("trainer")
                    if isinstance(raw_trainer, dict):
                        trainer_name = " ".join(
                            part
                            for part in (
                                str(raw_trainer.get("firstName") or "").strip(),
                                str(raw_trainer.get("lastName") or "").strip(),
                            )
                            if part
                        ) or None

            data_quality = (
                "FULL_FIELD_HISTORY_ATG"
                if history_starts is not None and history_wins is not None
                else "FIELD_ONLY_INCOMPLETE_ENRICHMENT" if atg_source
                else "FIELD_ONLY_RIKSTOTO"
            )
            source_uri = atg_source or starts_fetch.url

            self.store.upsert_runner(
                {
                    "race_id": race_id,
                    "selection_id": selection_id,
                    "horse_name": horse_name,
                    "post_position": start_number,
                    "driver_or_jockey": driver_name,
                    "trainer": trainer_name,
                    "scratched": int(is_scratched),
                }
            )

            sanitized = {
                "capability_contract": CONTRACT,
                "cohort_observed_at_utc": observed_at.isoformat(),
                "identity": next((r for r in evidence["runners"]
                                  if r["selection_id"] == selection_id), None),
                "rikstoto": {
                    "startNumber": start_number,
                    "horseName": horse_name,
                    "horseRegistrationNumber": registration,
                    "driverName": driver_name,
                    "driverLicenseNumber": start.get("driverLicenseNumber"),
                    "extraDistance": start.get("extraDistance"),
                    "isScratched": is_scratched,
                    "raceNumber": start.get("raceNumber"),
                    "raceKey": start.get("raceKey"),
                },
                "atg_market_free": (
                    None
                    if not isinstance(atg_start, dict)
                    else {
                        "horseId": horse.get("id"),
                        "horseName": horse.get("name"),
                        "age": age,
                        "sex": sex,
                        "trainer": trainer_name,
                        "lifeStarts": history_starts,
                        "lifeWins": history_wins,
                        "lifeSeconds": history_seconds,
                        "lifeThirds": history_thirds,
                        "lifeEarnings": history_earnings,
                        "yearCrosscheck": {
                            year: {key: values.get(key) for key in ("starts", "earnings")}
                            for year, values in horse["statistics"]["years"].items()
                        },
                        "startNumber": atg_start.get("number"),
                        "distance": atg_start.get("distance"),
                    }
                ),
            }
            snapshot_id = hashlib.sha256(
                (
                    f"{race_id}|{selection_id}|{observed_at.isoformat()}|"
                    f"{json.dumps(sanitized, sort_keys=True, default=str)}"
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
                        "source_uri": source_uri,
                        "horse_name": horse_name,
                        "driver_or_jockey": driver_name,
                        "trainer": trainer_name,
                        "post_position": start_number,
                        "extra_distance_m": start.get("extraDistance"),
                        "total_earnings": history_earnings,
                        "age": age,
                        "sex": sex,
                        "record_volt": None,
                        "record_auto": None,
                        "history_total_starts": history_starts,
                        "history_total_wins": history_wins,
                        "history_total_seconds": history_seconds,
                        "history_total_thirds": history_thirds,
                        "history_total_earnings": history_earnings,
                        "current_year_starts": None,
                        "current_year_wins": None,
                        "current_year_seconds": None,
                        "current_year_thirds": None,
                        "current_year_earnings": None,
                        "scratched": int(is_scratched),
                        "data_quality": data_quality,
                        "enrichment_provider": "atg" if atg_source else None,
                        "identity_match_method": next((r["match_method"] for r in evidence["runners"]
                                                       if r["selection_id"] == selection_id), None),
                        "identity_match_confidence": next((r["match_confidence"] for r in evidence["runners"]
                                                           if r["selection_id"] == selection_id), None),
                        "full_field_history_complete": int(evidence["passed"]),
                        "raw_json": json.dumps(
                            sanitized,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
            )
        return inserted, True, starts_fetch.url

    def collect_pool_context(
        self,
        *,
        raceday_key: str,
        products: list[str],
        observed_at: datetime,
        include_historical: bool = False,
    ) -> tuple[int, int]:
        """Persist raw multi-leg/public-pool payloads when historical endpoints still work.

        These endpoints were visible in older public Rikstoto frontend source. They
        are treated as optional research inputs and never required for the core
        single-race collector.
        """
        if not include_historical:
            return 0, 0

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
