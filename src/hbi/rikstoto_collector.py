from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .domain import MarketSnapshot
from .provider_capabilities import enrichment_candidates
from .providers.atg import AtgClient, AtgFetchResult
from .providers.pmu import PmuClient, PmuFetchResult
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
        pmu_client: PmuClient | None = None,
    ):
        self.store = store
        self.client = client or RikstotoClient()
        self.atg_client = atg_client or AtgClient()
        self.pmu_client = pmu_client or PmuClient()

    def _audit_provider(
        self,
        fetch: FetchResult | AtgFetchResult | PmuFetchResult,
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

    @staticmethod
    def _normalize_identity(value: object) -> str:
        return "".join(ch.upper() for ch in str(value or "") if ch.isalnum())

    @classmethod
    def _atg_runner_maps(
        cls,
        race_payload: dict[str, object],
    ) -> tuple[
        dict[str, dict[str, object]],
        dict[tuple[str, int], dict[str, object]],
    ]:
        by_registration: dict[str, dict[str, object]] = {}
        by_name_start: dict[tuple[str, int], dict[str, object]] = {}
        duplicate_registration: set[str] = set()
        duplicate_name_start: set[tuple[str, int]] = set()
        starts = race_payload.get("starts")
        if not isinstance(starts, list):
            return by_registration, by_name_start

        for start in starts:
            if not isinstance(start, dict):
                continue
            horse = start.get("horse")
            if not isinstance(horse, dict):
                continue
            registration = cls._normalize_identity(horse.get("id"))
            if registration:
                if registration in by_registration:
                    duplicate_registration.add(registration)
                else:
                    by_registration[registration] = start

            try:
                start_number = int(start.get("number"))
            except (TypeError, ValueError):
                continue
            name = cls._normalize_identity(horse.get("name"))
            if name:
                key = (name, start_number)
                if key in by_name_start:
                    duplicate_name_start.add(key)
                else:
                    by_name_start[key] = start

        for key in duplicate_registration:
            by_registration.pop(key, None)
        for key in duplicate_name_start:
            by_name_start.pop(key, None)
        return by_registration, by_name_start

    @classmethod
    def _match_atg_runner(
        cls,
        *,
        rikstoto_start: dict[str, object],
        by_registration: dict[str, dict[str, object]],
        by_name_start: dict[tuple[str, int], dict[str, object]],
    ) -> tuple[dict[str, object] | None, str | None, float | None]:
        registration = cls._normalize_identity(
            rikstoto_start.get("horseRegistrationNumber")
        )
        if registration and registration in by_registration:
            return by_registration[registration], "REGISTRATION_ID", 1.0

        try:
            start_number = int(rikstoto_start.get("startNumber"))
        except (TypeError, ValueError):
            return None, None, None
        name = cls._normalize_identity(rikstoto_start.get("horseName"))
        if name:
            match = by_name_start.get((name, start_number))
            if match is not None:
                return match, "NAME_AND_START_NUMBER", 0.98
        return None, None, None

    @classmethod
    def _extract_atg_market_free(
        cls,
        start: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not isinstance(start, dict):
            return None
        horse = start.get("horse")
        if not isinstance(horse, dict):
            return None
        stats = horse.get("statistics")
        if not isinstance(stats, dict):
            return None
        life = stats.get("life")
        if not isinstance(life, dict):
            return None

        try:
            history_starts = int(life.get("starts"))
            history_wins = cls._atg_placement(life, 1)
            history_seconds = cls._atg_placement(life, 2)
            history_thirds = cls._atg_placement(life, 3)
            history_earnings = float(life.get("earnings"))
            age = int(horse.get("age"))
        except (TypeError, ValueError):
            return None
        sex_raw = horse.get("sex")
        sex = None if sex_raw is None else str(sex_raw).strip()
        trainer = horse.get("trainer")
        if not isinstance(trainer, dict):
            return None
        trainer_name = " ".join(
            part
            for part in (
                str(trainer.get("firstName") or "").strip(),
                str(trainer.get("lastName") or "").strip(),
            )
            if part
        )
        if (
            history_wins is None
            or history_seconds is None
            or history_thirds is None
            or history_starts < 0
            or history_wins < 0
            or history_seconds < 0
            or history_thirds < 0
            or history_wins > history_starts
            or not sex
            or not trainer_name
        ):
            return None

        return {
            "horse_id": horse.get("id"),
            "horse_name": horse.get("name"),
            "age": age,
            "sex": sex,
            "trainer": trainer_name,
            "history_starts": history_starts,
            "history_wins": history_wins,
            "history_seconds": history_seconds,
            "history_thirds": history_thirds,
            "history_earnings": history_earnings,
            "start_number": start.get("number"),
            "distance": start.get("distance"),
        }

    def _atg_enrichment(
        self,
        *,
        race: dict[str, object],
        race_number: int,
        observed_at: datetime,
    ) -> tuple[
        str | None,
        dict[str, dict[str, object]],
        dict[tuple[str, int], dict[str, object]],
    ]:
        country = str(race.get("country") or "")
        try:
            start_time = datetime.fromisoformat(str(race["start_time_utc"]))
        except (TypeError, ValueError):
            return None, {}, {}

        calendar = self.atg_client.calendar_day(start_time.date())
        self._audit_provider(calendar, observed_at, provider="atg")
        resolved = self.atg_client.resolve_race(
            calendar,
            country_code=country,
            track_name=str(race.get("track") or ""),
            race_number=race_number,
            expected_start=start_time,
        )
        if resolved is None:
            return None, {}, {}

        game = self.atg_client.race_game(resolved.race_id)
        self._audit_provider(game, observed_at, provider="atg")
        race_payload = self.atg_client.race_payload(game)
        if race_payload is None:
            return None, {}, {}
        by_registration, by_name_start = self._atg_runner_maps(race_payload)
        return game.url, by_registration, by_name_start

    @classmethod
    def _pmu_runner_map(
        cls,
        rows: list[dict[str, object]],
    ) -> dict[tuple[str, int], dict[str, object]]:
        output: dict[tuple[str, int], dict[str, object]] = {}
        duplicates: set[tuple[str, int]] = set()
        for row in rows:
            name = cls._normalize_identity(row.get("nom"))
            try:
                start_number = int(row.get("numPmu"))
            except (TypeError, ValueError):
                continue
            key = (name, start_number)
            if not name:
                continue
            if key in output:
                duplicates.add(key)
            else:
                output[key] = row
        for key in duplicates:
            output.pop(key, None)
        return output

    @classmethod
    def _match_pmu_runner(
        cls,
        *,
        rikstoto_start: dict[str, object],
        by_name_start: dict[tuple[str, int], dict[str, object]],
    ) -> tuple[dict[str, object] | None, str | None, float | None]:
        try:
            start_number = int(rikstoto_start.get("startNumber"))
        except (TypeError, ValueError):
            return None, None, None
        name = cls._normalize_identity(rikstoto_start.get("horseName"))
        if not name:
            return None, None, None
        match = by_name_start.get((name, start_number))
        if match is None:
            return None, None, None
        return match, "NAME_AND_START_NUMBER", 0.99

    @staticmethod
    def _pmu_earnings(row: dict[str, object]) -> float | None:
        gains = row.get("gainsParticipant")
        if not isinstance(gains, dict):
            return None
        value = gains.get("gainsCarriere")
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_pmu_market_free(
        cls,
        row: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not isinstance(row, dict):
            return None
        try:
            history_starts = int(row.get("nombreCourses"))
            history_wins = int(row.get("nombreVictoires"))
            history_seconds = int(row.get("nombrePlacesSecond"))
            history_thirds = int(row.get("nombrePlacesTroisieme"))
            age = int(row.get("age"))
        except (TypeError, ValueError):
            return None
        earnings = cls._pmu_earnings(row)
        sex = str(row.get("sexe") or "").strip()
        trainer = str(row.get("entraineur") or "").strip()
        if (
            earnings is None
            or history_starts < 0
            or history_wins < 0
            or history_seconds < 0
            or history_thirds < 0
            or history_wins > history_starts
            or history_wins + history_seconds + history_thirds > history_starts
            or age <= 0
            or not sex
            or not trainer
        ):
            return None
        return {
            "horse_id": row.get("idCheval"),
            "horse_name": row.get("nom"),
            "age": age,
            "sex": sex,
            "trainer": trainer,
            "history_starts": history_starts,
            "history_wins": history_wins,
            "history_seconds": history_seconds,
            "history_thirds": history_thirds,
            "history_earnings": earnings,
            "start_number": row.get("numPmu"),
        }

    def _pmu_enrichment(
        self,
        *,
        race: dict[str, object],
        race_number: int,
        observed_at: datetime,
    ) -> tuple[str | None, dict[tuple[str, int], dict[str, object]]]:
        try:
            start_time = datetime.fromisoformat(str(race["start_time_utc"]))
        except (TypeError, ValueError):
            return None, {}

        programme = self.pmu_client.programme(start_time.date())
        self._audit_provider(programme, observed_at, provider="pmu")
        resolved = self.pmu_client.resolve_race(
            programme,
            country_code=str(race.get("country") or ""),
            track_name=str(race.get("track") or ""),
            race_number=race_number,
        )
        if resolved is None:
            return None, {}

        participants = self.pmu_client.participants(
            start_time.date(),
            resolved.reunion_number,
            resolved.race_number,
        )
        self._audit_provider(participants, observed_at, provider="pmu")
        rows = self.pmu_client.participant_rows(participants)
        if not rows:
            return None, {}
        return participants.url, self._pmu_runner_map(rows)

    def _try_provider(
        self,
        *,
        provider: str,
        race: dict[str, object],
        race_number: int,
        observed_at: datetime,
        active_starts: list[dict[str, object]],
    ) -> tuple[
        bool,
        str | None,
        dict[str, tuple[dict[str, object], str, float]],
        dict[str, dict[str, object]],
    ]:
        matched: dict[str, tuple[dict[str, object], str, float]] = {}
        diagnostics: dict[str, dict[str, object]] = {}

        if provider == "atg":
            source, by_registration, by_name_start = self._atg_enrichment(
                race=race,
                race_number=race_number,
                observed_at=observed_at,
            )
            if source is None:
                return False, None, matched, diagnostics
            for start in active_starts:
                selection = str(start.get("startNumber"))
                raw, method, confidence = self._match_atg_runner(
                    rikstoto_start=start,
                    by_registration=by_registration,
                    by_name_start=by_name_start,
                )
                extracted = self._extract_atg_market_free(raw)
                diagnostics[selection] = {
                    "matched": raw is not None,
                    "method": method,
                    "confidence": confidence,
                    "completeContract": extracted is not None,
                }
                if (
                    extracted is not None
                    and method is not None
                    and confidence is not None
                    and confidence >= 0.98
                ):
                    matched[selection] = (extracted, method, confidence)
            return len(matched) == len(active_starts), source, matched, diagnostics

        if provider == "pmu":
            source, by_name_start = self._pmu_enrichment(
                race=race,
                race_number=race_number,
                observed_at=observed_at,
            )
            if source is None:
                return False, None, matched, diagnostics
            for start in active_starts:
                selection = str(start.get("startNumber"))
                raw, method, confidence = self._match_pmu_runner(
                    rikstoto_start=start,
                    by_name_start=by_name_start,
                )
                extracted = self._extract_pmu_market_free(raw)
                diagnostics[selection] = {
                    "matched": raw is not None,
                    "method": method,
                    "confidence": confidence,
                    "completeContract": extracted is not None,
                }
                if (
                    extracted is not None
                    and method is not None
                    and confidence is not None
                    and confidence >= 0.98
                ):
                    matched[selection] = (extracted, method, confidence)
            return len(matched) == len(active_starts), source, matched, diagnostics

        return False, None, matched, diagnostics

    def collect_fundamentals(
        self,
        *,
        raceday_key: str,
        race_number: int,
        race_id: str,
        observed_at: datetime,
        products: list[str] | None = None,
    ) -> tuple[int, bool, str | None]:
        """Capture Rikstoto field and expose only complete one-provider enrichment."""
        del products

        starts_fetch = self.client.starts(raceday_key)
        self._audit(starts_fetch, observed_at)
        starts = self._starts_for_race(starts_fetch.payload, race_number)
        if not starts_fetch.success or not starts:
            return 0, False, starts_fetch.url

        scratched_fetch = self.client.scratched(raceday_key)
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
            payload=(
                starts_fetch.payload
                if isinstance(starts_fetch.payload, dict)
                else {}
            ),
        )

        staged: list[dict[str, object]] = []
        for start in starts:
            try:
                start_number = int(start.get("startNumber"))
            except (TypeError, ValueError):
                continue
            is_scratched = bool(start.get("isScratched")) or start_number in scratched
            staged.append(
                {
                    "start": start,
                    "start_number": start_number,
                    "selection_id": str(start_number),
                    "horse_name": str(start.get("horseName") or start_number),
                    "registration": start.get("horseRegistrationNumber"),
                    "driver_name": start.get("driverName"),
                    "is_scratched": is_scratched,
                }
            )

        active_starts = [
            item["start"]
            for item in staged
            if not bool(item["is_scratched"]) and isinstance(item["start"], dict)
        ]
        race_row = self.store.get_race(race_id)
        race = None if race_row is None else dict(race_row)
        selected_provider: str | None = None
        selected_source: str | None = None
        selected_matches: dict[
            str,
            tuple[dict[str, object], str, float],
        ] = {}
        attempts: dict[str, dict[str, dict[str, object]]] = {}

        if race is not None and active_starts:
            candidates = enrichment_candidates(
                country=str(race.get("country") or ""),
                discipline=str(race.get("discipline") or ""),
            )
            for candidate in candidates:
                complete, source, matches, diagnostics = self._try_provider(
                    provider=candidate.provider,
                    race=race,
                    race_number=race_number,
                    observed_at=observed_at,
                    active_starts=active_starts,
                )
                attempts[candidate.provider] = diagnostics
                if complete:
                    selected_provider = candidate.provider
                    selected_source = source
                    selected_matches = matches
                    break

        full_field_complete = (
            bool(active_starts)
            and selected_provider is not None
            and len(selected_matches) == len(active_starts)
        )
        inserted = 0

        for item in staged:
            start = item["start"]
            assert isinstance(start, dict)
            selection = str(item["selection_id"])
            match = selected_matches.get(selection)
            extracted = (
                match[0]
                if full_field_complete
                and match is not None
                and not bool(item["is_scratched"])
                else None
            )
            safe = extracted if isinstance(extracted, dict) else {}
            match_method = None if match is None else match[1]
            match_confidence = None if match is None else match[2]
            trainer_name = safe.get("trainer")
            source_uri = (
                selected_source
                if full_field_complete and selected_source
                else starts_fetch.url
            )

            if bool(item["is_scratched"]):
                data_quality = "SCRATCHED"
            elif full_field_complete and selected_provider is not None:
                data_quality = f"FULL_FIELD_HISTORY_{selected_provider.upper()}"
            elif attempts:
                data_quality = "FIELD_ONLY_INCOMPLETE_ENRICHMENT"
            else:
                data_quality = "FIELD_ONLY_RIKSTOTO"

            self.store.upsert_runner(
                {
                    "race_id": race_id,
                    "selection_id": selection,
                    "horse_name": item["horse_name"],
                    "post_position": item["start_number"],
                    "driver_or_jockey": item["driver_name"],
                    "trainer": trainer_name,
                    "scratched": int(bool(item["is_scratched"])),
                }
            )

            sanitized = {
                "rikstoto": {
                    "startNumber": item["start_number"],
                    "horseName": item["horse_name"],
                    "horseRegistrationNumber": item["registration"],
                    "driverName": item["driver_name"],
                    "driverLicenseNumber": start.get("driverLicenseNumber"),
                    "extraDistance": start.get("extraDistance"),
                    "isScratched": bool(item["is_scratched"]),
                    "raceNumber": start.get("raceNumber"),
                    "raceKey": start.get("raceKey"),
                },
                "enrichment": {
                    "provider": selected_provider,
                    "fullFieldHistoryComplete": full_field_complete,
                    "identityMatchMethod": match_method,
                    "identityMatchConfidence": match_confidence,
                    "marketFree": extracted,
                    "attempts": {
                        provider: diagnostics.get(selection)
                        for provider, diagnostics in attempts.items()
                    },
                },
            }
            snapshot_id = hashlib.sha256(
                (
                    f"{race_id}|{selection}|{observed_at.isoformat()}|"
                    f"{json.dumps(sanitized, sort_keys=True, default=str)}"
                ).encode()
            ).hexdigest()
            inserted += int(
                self.store.insert_runner_fundamental_snapshot(
                    {
                        "snapshot_id": snapshot_id,
                        "race_id": race_id,
                        "selection_id": selection,
                        "observed_at_utc": observed_at.isoformat(),
                        "feature_as_of_utc": observed_at.isoformat(),
                        "source_uri": source_uri,
                        "horse_name": item["horse_name"],
                        "driver_or_jockey": item["driver_name"],
                        "trainer": trainer_name,
                        "post_position": item["start_number"],
                        "extra_distance_m": start.get("extraDistance"),
                        "total_earnings": safe.get("history_earnings"),
                        "age": safe.get("age"),
                        "sex": safe.get("sex"),
                        "record_volt": None,
                        "record_auto": None,
                        "history_total_starts": safe.get("history_starts"),
                        "history_total_wins": safe.get("history_wins"),
                        "history_total_seconds": safe.get("history_seconds"),
                        "history_total_thirds": safe.get("history_thirds"),
                        "history_total_earnings": safe.get("history_earnings"),
                        "current_year_starts": None,
                        "current_year_wins": None,
                        "current_year_seconds": None,
                        "current_year_thirds": None,
                        "current_year_earnings": None,
                        "scratched": int(bool(item["is_scratched"])),
                        "data_quality": data_quality,
                        "enrichment_provider": selected_provider,
                        "identity_match_method": match_method,
                        "identity_match_confidence": match_confidence,
                        "full_field_history_complete": int(full_field_complete),
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
