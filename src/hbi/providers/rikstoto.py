from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")


class EndpointConfidence(StrEnum):
    USER_VERIFIED = "USER_VERIFIED"
    OPEN_SOURCE_OBSERVED = "OPEN_SOURCE_OBSERVED"
    HISTORICAL_FRONTEND_INFERRED = "HISTORICAL_FRONTEND_INFERRED"


@dataclass(frozen=True)
class FetchResult:
    url: str
    payload: Any | None
    success: bool
    status_code: int | None
    latency_ms: float
    error: str | None = None


@dataclass(frozen=True)
class RikstotoRace:
    raceday_key: str
    raceday_name: str
    track_code: str
    country_code: str
    sport_type: str
    race_number: int
    start_time: datetime
    start_time_raw: str
    start_method: str | None
    progress_status: str | None
    pools: tuple[str, ...]
    single_leg_products: tuple[str, ...]

    @property
    def race_id(self) -> str:
        return f"RIKSTOTO:{self.raceday_key}:{self.race_number}"


class RikstotoClient:
    """Read-only client for public Rikstoto endpoints.

    No authentication, account access, ticket submission or wagering endpoints are
    implemented. Endpoint provenance is documented in docs/RIKSTOTO_PROVIDER.md.
    """

    BASE_URL = "https://www.rikstoto.no"
    API = f"{BASE_URL}/api"

    ENDPOINTS: ClassVar[dict[str, EndpointConfidence]] = {
        "/settings/urls": EndpointConfidence.USER_VERIFIED,
        "/racedays/": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/results/racedays/{from}/{to}/list": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/game/{raceday}/betdistribution/winodds/{race}": (
            EndpointConfidence.OPEN_SOURCE_OBSERVED
        ),
        "/game/{raceday}/betdistribution/placeodds/{race}": (
            EndpointConfidence.OPEN_SOURCE_OBSERVED
        ),
        "/game/{raceday}/odds/tv/{race}": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/game/{raceday}/odds/t/{race}": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/racedays/{raceday}/scratched": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/racedays/{raceday}/raceInfo": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/results/racedays/{raceday}/raceresults": EndpointConfidence.OPEN_SOURCE_OBSERVED,
        "/results/raceDays/{raceday}/{race}/completeresults": (
            EndpointConfidence.OPEN_SOURCE_OBSERVED
        ),
        "/game/producttimeline/racedays/{raceday}": (
            EndpointConfidence.HISTORICAL_FRONTEND_INFERRED
        ),
        "/game/producttimeline/racedays/{raceday}/investment": (
            EndpointConfidence.HISTORICAL_FRONTEND_INFERRED
        ),
        "/game/program/{raceday}/{product}": (
            EndpointConfidence.HISTORICAL_FRONTEND_INFERRED
        ),
        "/game/program/{raceday}/{product}/addition": (
            EndpointConfidence.HISTORICAL_FRONTEND_INFERRED
        ),
    }

    def __init__(self, *, timeout: float = 15.0, user_agent: str = "HBI-shadow-research/1.0"):
        self.timeout = timeout
        self.user_agent = user_agent

    def _fetch(self, path: str) -> FetchResult:
        url = path if path.startswith("http") else f"{self.API}{path}"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
            method="GET",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body)
                return FetchResult(
                    url=url,
                    payload=payload,
                    success=True,
                    status_code=response.status,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            return FetchResult(
                url=url,
                payload=None,
                success=False,
                status_code=status,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )

    @staticmethod
    def result_list(fetch: FetchResult) -> list[dict[str, Any]]:
        if not fetch.success or not isinstance(fetch.payload, dict):
            return []
        result = fetch.payload.get("result")
        return result if isinstance(result, list) else []

    @staticmethod
    def result_object(fetch: FetchResult) -> dict[str, Any]:
        if not fetch.success or not isinstance(fetch.payload, dict):
            return {}
        result = fetch.payload.get("result")
        return result if isinstance(result, dict) else {}

    @staticmethod
    def parse_timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=OSLO)
        return parsed.astimezone(UTC)

    def settings_urls(self) -> FetchResult:
        return self._fetch("/settings/urls")

    def racedays(self) -> FetchResult:
        return self._fetch("/racedays/")

    def result_racedays(self, start: date, end: date) -> FetchResult:
        return self._fetch(f"/results/racedays/{start.isoformat()}/{end.isoformat()}/list")

    def win_odds(self, raceday_key: str, race_number: int) -> FetchResult:
        return self._fetch(f"/game/{raceday_key}/betdistribution/winodds/{race_number}")

    def place_odds(self, raceday_key: str, race_number: int) -> FetchResult:
        return self._fetch(f"/game/{raceday_key}/betdistribution/placeodds/{race_number}")

    def twin_odds(self, raceday_key: str, race_number: int) -> FetchResult:
        return self._fetch(f"/game/{raceday_key}/odds/tv/{race_number}")

    def triple_odds(self, raceday_key: str, race_number: int) -> FetchResult:
        return self._fetch(f"/game/{raceday_key}/odds/t/{race_number}")

    def scratched(self, raceday_key: str) -> FetchResult:
        return self._fetch(f"/racedays/{raceday_key}/scratched")

    def race_info(self, raceday_key: str) -> FetchResult:
        return self._fetch(f"/racedays/{raceday_key}/raceInfo")

    def raceday_results(self, raceday_key: str) -> FetchResult:
        return self._fetch(f"/results/racedays/{raceday_key}/raceresults")

    def complete_results(self, raceday_key: str, race_number: int) -> FetchResult:
        return self._fetch(f"/results/raceDays/{raceday_key}/{race_number}/completeresults")

    def product_timeline(self, raceday_key: str) -> FetchResult:
        return self._fetch(f"/game/producttimeline/racedays/{raceday_key}")

    def product_investments(self, raceday_key: str) -> FetchResult:
        return self._fetch(f"/game/producttimeline/racedays/{raceday_key}/investment")

    def program(self, raceday_key: str, product: str) -> FetchResult:
        return self._fetch(f"/game/program/{raceday_key}/{product}")

    def program_addition(self, raceday_key: str, product: str) -> FetchResult:
        return self._fetch(f"/game/program/{raceday_key}/{product}/addition")

    def discover_races(self, fetch: FetchResult | None = None) -> list[RikstotoRace]:
        response = fetch or self.racedays()
        tracks = self.result_list(response)
        races: list[RikstotoRace] = []

        for track in tracks:
            raceday_key = str(track.get("raceDayKey", ""))
            if not raceday_key:
                continue
            pools_by_race: dict[int, set[str]] = {}
            for pool in track.get("pools") or []:
                product = str(pool.get("product", ""))
                for race_number in pool.get("raceNumbers") or []:
                    pools_by_race.setdefault(int(race_number), set()).add(product)

            single_by_race: dict[int, set[str]] = {}
            for product in track.get("singleLegProducts") or []:
                race_number = product.get("raceNumber")
                code = product.get("product")
                if race_number is not None and code:
                    single_by_race.setdefault(int(race_number), set()).add(str(code))

            for race in track.get("races") or []:
                race_number = int(race["raceNumber"])
                start_raw = str(race["startTime"])
                races.append(
                    RikstotoRace(
                        raceday_key=raceday_key,
                        raceday_name=str(track.get("raceDayName", "")),
                        track_code=str(track.get("trackCode", "")),
                        country_code=str(track.get("countryIsoCode", "")),
                        sport_type=str(track.get("sportType", "")),
                        race_number=race_number,
                        start_time=self.parse_timestamp(start_raw),
                        start_time_raw=start_raw,
                        start_method=(
                            None if race.get("startMethod") is None else str(race.get("startMethod"))
                        ),
                        progress_status=(
                            None
                            if race.get("progressStatus") is None
                            else str(race.get("progressStatus"))
                        ),
                        pools=tuple(sorted(pools_by_race.get(race_number, set()))),
                        single_leg_products=tuple(sorted(single_by_race.get(race_number, set()))),
                    )
                )
        return races
