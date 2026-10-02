"""Public LeTROT corroboration of French ATG lifetime counts (GET only)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .atg import AtgClient, AtgFetchResult


class EmbeddedData(HTMLParser):
    def __init__(self, tag: str, attribute: str):
        super().__init__()
        self.tag = tag
        self.attribute = attribute
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag == self.tag and self.attribute in dict(attrs):
            self.values.append(json.loads(dict(attrs)[self.attribute]))


class LeTrotClient:
    BASE = "https://www.letrot.com"
    MAX_PAGE_BYTES = 8_000_000

    def fetch(self, path: str, tag: str, attribute: str) -> AtgFetchResult:
        if not re.fullmatch(r"/(?:courses|stats/chevaux)/[A-Za-z0-9/_-]+", path):
            raise ValueError("LeTROT path outside public allowlist")
        url = self.BASE + path
        started = time.perf_counter()
        status = None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "HBI-shadow-research/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                status = response.status
                if not response.url.startswith(self.BASE + "/"):
                    raise ValueError("External redirect; no public history contract")
                parser = EmbeddedData(tag, attribute)
                raw = response.read(self.MAX_PAGE_BYTES + 1)
                if len(raw) > self.MAX_PAGE_BYTES:
                    raise ValueError("Public page exceeds bounded response size")
                parser.feed(raw.decode("utf-8"))
                parser.close()
                if len(parser.values) != 1 or not isinstance(parser.values[0], dict):
                    raise ValueError("Missing or ambiguous embedded public schema")
                return AtgFetchResult(
                    url, parser.values[0], True, status, (time.perf_counter() - started) * 1000
                )
        except (urllib.error.URLError, TimeoutError, ValueError, UnicodeError) as exc:
            return AtgFetchResult(
                url,
                None,
                False,
                getattr(exc, "code", status),
                (time.perf_counter() - started) * 1000,
                str(exc),
            )

    def corroborate(
        self,
        *,
        track: str,
        race_number: int,
        expected_start: datetime,
        matched: dict[str, dict],
        audit,
        clock,
    ) -> dict:
        evidence = {"provider": "letrot", "passed": False, "runners": [], "reason": None}

        def fetch(path, tag, attr):
            result = self.fetch(path, tag, attr)
            audit(result, clock(), provider="letrot")
            if not result.success:
                raise ValueError("PUBLIC_FETCH_OR_SCHEMA_FAILED")
            return result

        try:
            day = expected_start.astimezone(ZoneInfo("Europe/Paris")).date().isoformat()
            calendar = fetch(f"/courses/{day}", "meeting-day", ":program")
            meetings = [
                m
                for m in calendar.payload["meetings"]
                if AtgClient._normalize_name(m["nomHippodrome"]) == AtgClient._normalize_name(track)
            ]
            if len(meetings) != 1:
                raise ValueError("MEETING_IDENTITY_NOT_UNIQUE")
            code = meetings[0]["numHippodrome"]
            page = fetch(f"/courses/{day}/{code}/{race_number}", "race-detail", ":payload")
            race = page.payload["race"]
            start = (
                datetime.fromisoformat(race["heure"]["date"])
                .replace(tzinfo=ZoneInfo(race["heure"]["timezone"]))
                .astimezone(UTC)
            )
            if (
                race["statut"] != "INCOMING"
                or race["numCourse"] != race_number
                or race["dateCourse"] != day
                or race["discipline"] not in {"A", "M"}
                or AtgClient._normalize_name(race["nomHippodrome"])
                != AtgClient._normalize_name(track)
                or abs((start - expected_start).total_seconds()) > 300
                or clock() >= start
            ):
                raise ValueError("RACE_IDENTITY_OR_TIME_MISMATCH")
            evidence["race_start_utc"] = start.isoformat()
            runners = [r for r in race["partants"] if r["nonPartant"] is False]
            if any(type(r["nonPartant"]) is not bool for r in race["partants"]):
                raise ValueError("INVALID_SCRATCH_STATE")
            if (
                len(runners) != len(matched)
                or {str(r["leavingNumber"]) for r in runners} != set(matched)
                or len({r["id"] for r in runners}) != len(runners)
            ):
                raise ValueError("FULL_FIELD_MISMATCH")
            for runner in runners:
                number = str(runner["leavingNumber"])
                horse = matched[number]["horse"]
                if AtgClient._normalize_name(runner["name"]) != AtgClient._normalize_name(
                    horse["name"]
                ):
                    raise ValueError("RUNNER_IDENTITY_MISMATCH")
                page = fetch(runner["horseUrl"], "horse-main", ":horse")
                h = page.payload
                life = horse["statistics"]["life"]
                good = (
                    h["numCheval"] == runner["id"]
                    and AtgClient._normalize_name(h["nomCheval"])
                    == AtgClient._normalize_name(horse["name"])
                    and type(h["nbCourses"]) is int
                    and type(h["nbVictoire"]) is int
                    and h["nbCourses"] == life["starts"]
                    and h["nbVictoire"] == life["placement"]["1"]
                    and h["annee"] == expected_start.year - horse["age"]
                )
                evidence["runners"].append(
                    {
                        "selection_id": number,
                        "horse_id": h.get("numCheval"),
                        "source_uri": page.url,
                        "observed_at_utc": clock().isoformat(),
                        "career_starts": h.get("nbCourses"),
                        "career_wins": h.get("nbVictoire"),
                        "atg_career_starts": life["starts"],
                        "atg_career_wins": life["placement"]["1"],
                        "passed": good,
                    }
                )
                if not good:
                    raise ValueError("LIFETIME_OR_IDENTITY_DISAGREEMENT")
            evidence["passed"] = True
        except (ValueError, TypeError, KeyError, AttributeError):
            evidence["reason"] = "LETROT_FULL_FIELD_CORROBORATION_FAILED"
        return evidence
