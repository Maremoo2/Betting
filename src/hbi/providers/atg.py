from __future__ import annotations

import json
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any


@dataclass(frozen=True)
class AtgFetchResult:
    url: str
    payload: Any | None
    success: bool
    status_code: int | None
    latency_ms: float
    error: str | None = None


@dataclass(frozen=True)
class AtgRaceRef:
    race_id: str
    track_name: str
    race_number: int
    start_time: datetime | None


class AtgClient:
    """Read-only client for public ATG racing information.

    The client is used only to enrich Swedish runners with market-free pre-race
    horse/trainer/history facts. Pool odds and betting percentages are intentionally
    ignored by the fundamental adapter.
    """

    CALENDAR_API = "https://horse-betting-info.prod.c1.atg.cloud/api-public/v0"
    GAME_API = "https://www.atg.se/services/racinginfo/v1/api/games"

    def __init__(self, *, timeout: float = 15.0):
        self.timeout = timeout

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Accept": "application/json, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.atg.se/",
            "Origin": "https://www.atg.se",
        }

    def _fetch(self, url: str) -> AtgFetchResult:
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return AtgFetchResult(
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
            return AtgFetchResult(
                url=url,
                payload=None,
                success=False,
                status_code=status,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )

    def calendar_day(self, race_date: date) -> AtgFetchResult:
        return self._fetch(
            f"{self.CALENDAR_API}/calendar/day/{race_date.isoformat()}"
            "?headToHeadEnabled=true"
        )

    def race_game(self, race_id: str) -> AtgFetchResult:
        return self._fetch(f"{self.GAME_API}/vinnare_{race_id}")

    @staticmethod
    def _normalize_name(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        ascii_value = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
        return "".join(ch.lower() for ch in ascii_value if ch.isalnum())

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    def resolve_race(
        self,
        calendar: AtgFetchResult,
        *,
        track_name: str,
        race_number: int,
        expected_start: datetime | None = None,
    ) -> AtgRaceRef | None:
        if not calendar.success or not isinstance(calendar.payload, dict):
            return None
        target_track = self._normalize_name(track_name)
        candidates: list[AtgRaceRef] = []
        for track in calendar.payload.get("tracks") or []:
            if not isinstance(track, dict) or track.get("countryCode") != "SE":
                continue
            name = str(track.get("name") or "")
            if self._normalize_name(name) != target_track:
                continue
            for race in track.get("races") or []:
                if not isinstance(race, dict):
                    continue
                try:
                    number = int(race.get("number"))
                except (TypeError, ValueError):
                    continue
                if number != race_number or not race.get("id"):
                    continue
                candidates.append(
                    AtgRaceRef(
                        race_id=str(race["id"]),
                        track_name=name,
                        race_number=number,
                        start_time=self._parse_time(race.get("startTime")),
                    )
                )

        if not candidates:
            return None
        if expected_start is None or len(candidates) == 1:
            return candidates[0]
        expected = expected_start.astimezone(UTC)
        return min(
            candidates,
            key=lambda item: (
                abs((item.start_time - expected).total_seconds())
                if item.start_time is not None
                else float("inf")
            ),
        )

    @staticmethod
    def race_payload(fetch: AtgFetchResult) -> dict[str, Any] | None:
        if not fetch.success or not isinstance(fetch.payload, dict):
            return None
        races = fetch.payload.get("races")
        if not isinstance(races, list) or not races or not isinstance(races[0], dict):
            return None
        return races[0]
