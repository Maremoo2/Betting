from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any
import unicodedata


@dataclass(frozen=True)
class PmuRaceRef:
    reunion_number: int
    race_number: int
    track_name: str
    country_code: str | None


@dataclass(frozen=True)
class PmuFetchResult:
    url: str
    payload: Any | None
    success: bool
    status_code: int | None
    latency_ms: float
    error: str | None = None


class PmuClient:
    """Read-only PMU Turfinfo client used only for pre-race research enrichment."""

    BASE_URL = "https://online.turfinfo.api.pmu.fr/rest/client/61/programme"

    def __init__(self, *, timeout: float = 20.0):
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
        }

    @staticmethod
    def _date_code(race_date: date) -> str:
        return race_date.strftime("%d%m%Y")

    def _fetch(self, path: str) -> PmuFetchResult:
        separator = "&" if "?" in path else "?"
        url = f"{self.BASE_URL}/{path}{separator}" + urllib.parse.urlencode(
            {"specialisation": "INTERNET"}
        )
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return PmuFetchResult(
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
            return PmuFetchResult(
                url=url,
                payload=None,
                success=False,
                status_code=status,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )

    def programme(self, race_date: date) -> PmuFetchResult:
        return self._fetch(self._date_code(race_date))

    def participants(
        self,
        race_date: date,
        reunion_number: int,
        race_number: int,
    ) -> PmuFetchResult:
        return self._fetch(
            f"{self._date_code(race_date)}/R{reunion_number}/C{race_number}/participants"
        )

    def performances(
        self,
        race_date: date,
        reunion_number: int,
        race_number: int,
    ) -> PmuFetchResult:
        return self._fetch(
            f"{self._date_code(race_date)}/R{reunion_number}/C{race_number}/"
            "performances-detaillees/pretty"
        )

    @staticmethod
    def reunions(fetch: PmuFetchResult) -> list[dict[str, object]]:
        if not fetch.success or not isinstance(fetch.payload, dict):
            return []
        root = fetch.payload.get("programme")
        if isinstance(root, dict):
            values = root.get("reunions")
        else:
            values = fetch.payload.get("reunions")
        if not isinstance(values, list):
            return []
        return [item for item in values if isinstance(item, dict)]

    @staticmethod
    def _normalize_name(value: object) -> str:
        raw = unicodedata.normalize("NFKD", str(value or ""))
        ascii_value = "".join(
            ch for ch in raw if not unicodedata.combining(ch)
        )
        return "".join(
            ch.lower() for ch in ascii_value if ch.isalnum()
        )

    @staticmethod
    def _track_name(reunion: dict[str, object]) -> str:
        value = reunion.get("hippodrome")
        if isinstance(value, dict):
            return str(
                value.get("libelleCourt")
                or value.get("libelleLong")
                or value.get("libelle")
                or ""
            )
        return str(value or reunion.get("libelle") or "")

    @staticmethod
    def _country_code(reunion: dict[str, object]) -> str | None:
        value = reunion.get("pays")
        if isinstance(value, dict):
            raw = value.get("code") or value.get("codeIso") or value.get("libelleCourt")
        else:
            raw = value
        if raw is None:
            return None
        return str(raw).upper()

    def resolve_race(
        self,
        programme: PmuFetchResult,
        *,
        country_code: str,
        track_name: str,
        race_number: int,
    ) -> PmuRaceRef | None:
        target_track = self._normalize_name(track_name)
        target_country = country_code.upper()
        candidates: list[PmuRaceRef] = []

        for reunion in self.reunions(programme):
            track = self._track_name(reunion)
            if self._normalize_name(track) != target_track:
                continue
            country = self._country_code(reunion)
            if country is not None and country != target_country:
                continue
            try:
                reunion_number = int(reunion.get("numOfficiel"))
            except (TypeError, ValueError):
                continue
            courses = reunion.get("courses")
            if not isinstance(courses, list):
                continue
            for course in courses:
                if not isinstance(course, dict):
                    continue
                try:
                    number = int(course.get("numOrdre"))
                except (TypeError, ValueError):
                    continue
                if number == race_number:
                    candidates.append(
                        PmuRaceRef(
                            reunion_number=reunion_number,
                            race_number=number,
                            track_name=track,
                            country_code=country,
                        )
                    )

        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def participant_rows(fetch: PmuFetchResult) -> list[dict[str, object]]:
        if not fetch.success:
            return []
        if isinstance(fetch.payload, dict):
            values = fetch.payload.get("participants")
        else:
            values = fetch.payload
        if not isinstance(values, list):
            return []
        return [item for item in values if isinstance(item, dict)]

    @staticmethod
    def performance_rows(fetch: PmuFetchResult) -> list[dict[str, object]]:
        if not fetch.success:
            return []
        if isinstance(fetch.payload, dict):
            values = fetch.payload.get("participants")
        else:
            values = fetch.payload
        if not isinstance(values, list):
            return []
        return [item for item in values if isinstance(item, dict)]
