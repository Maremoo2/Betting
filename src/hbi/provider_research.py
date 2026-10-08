"""Read-only discovery diagnostics. This command never updates the capability registry."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .provider_capability import validate_lifetime
from .providers.atg import AtgClient
from .providers.letrot import EmbeddedData
from .providers.rikstoto import RikstotoClient


def public_page(url: str) -> tuple[dict, str]:
    observed = datetime.now(UTC).isoformat()
    result = {"url": url, "observed_at_utc": observed, "method": "GET"}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "HBI-shadow-research/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            page = response.read(2_000_000).decode("utf-8", errors="replace")
            final = urllib.parse.urlsplit(response.url)
            result.update(
                status=response.status,
                final_host=final.hostname,
                redirected=final.hostname != urllib.parse.urlsplit(url).hostname,
            )
            if result["redirected"] or "Sign in to your account" in page:
                result["outcome"] = "AUTHENTICATION_REQUIRED"
            else:
                result["outcome"] = "PUBLIC_HTML_ONLY_NOT_A_VERIFIED_HISTORY_CONTRACT"
            return result, page
    except (urllib.error.URLError, TimeoutError) as exc:
        result.update(status=getattr(exc, "code", None), outcome="FETCH_FAILED")
        return result, ""


def research() -> dict:
    now = datetime.now(UTC)
    result = {
        "observed_at_utc": now.isoformat(),
        "atg_candidates": [],
        "french_probes": [],
        "registry_modified": False,
    }
    rik = RikstotoClient()
    races = rik.discover_races(rik.racedays())
    dates = sorted({r.start_time.date() for r in races if r.start_time > now})[:7]
    atg = AtgClient()
    seen = set()
    for day in dates:
        calendar = atg.calendar_day(day)
        if not calendar.success or not isinstance(calendar.payload, dict):
            result["atg_candidates"].append({"date": str(day), "error": "CALENDAR_FAILED"})
            continue
        for track in calendar.payload.get("tracks", []):
            pair = (track.get("countryCode"), track.get("sport"))
            if pair in seen:
                continue
            candidates = [r for r in track.get("races", []) if r.get("status") == "upcoming"]
            if not candidates:
                continue
            seen.add(pair)
            ref = candidates[0]
            fetch = atg.race_game(ref["id"])
            payload = atg.race_payload(fetch) or {}
            starts = payload.get("starts") or []
            active = [s for s in starts if not s.get("scratched")]
            errors = [validate_lifetime(s.get("horse") or {}) for s in active]
            result["atg_candidates"].append(
                {
                    "country": pair[0],
                    "discipline": pair[1],
                    "track": track["name"],
                    "race_id": ref["id"],
                    "source_uri": fetch.url,
                    "observed_at_utc": datetime.now(UTC).isoformat(),
                    "active_runners": len(active),
                    "complete_schema_runners": errors.count(None),
                    "schema_errors": sorted({e for e in errors if e}),
                    "canonical_future_meetings": sorted(
                        {
                            r.raceday_name
                            for r in races
                            if r.country_code == pair[0] and r.start_time > now
                        }
                    ),
                    "outcome": "SCHEMA_PROBE_ONLY_NO_FULL_FIELD_APPROVAL",
                }
            )
    tomorrow = (now + timedelta(days=1)).date()
    record, page = public_page(f"https://www.letrot.com/courses/{tomorrow}")
    result["french_probes"].append(record)
    links = re.findall(r'href="(/courses/\d{4}-\d{2}-\d{2}/\d+/\d+)"', page)
    if links:
        record, race_page = public_page("https://www.letrot.com" + links[0])
        result["french_probes"].append(record)
        try:
            parser = EmbeddedData("race-detail", ":payload")
            parser.feed(race_page)
            runner = parser.values[0]["race"]["partants"][0]
            record, horse_page = public_page("https://www.letrot.com" + runner["horseUrl"])
            parser = EmbeddedData("horse-main", ":horse")
            parser.feed(horse_page)
            horse = parser.values[0]
            record.update(
                career_starts=horse.get("nbCourses"),
                career_wins=horse.get("nbVictoire"),
                outcome="PUBLIC_CAREER_COUNTS_CORROBORATION_CANDIDATE",
            )
            result["french_probes"].append(record)
        except (ValueError, IndexError, KeyError, TypeError):
            result["french_probes"].append({"outcome": "LETROT_HORSE_SCHEMA_UNAVAILABLE"})
    record, page = public_page("https://www.france-galop.com/fr/courses/demain")
    result["french_probes"].append(record)
    for pattern in (
        r'href="(/fr/courses/reunion/[^" ]+)"',
        r'href="(/fr/course/detail/[^" ]+)"',
        r'href="(/fr/cheval/[^" ]+)"',
    ):
        links = re.findall(pattern, page)
        if not links:
            break
        record, page = public_page("https://www.france-galop.com" + links[0])
        result["french_probes"].append(record)
        if record["outcome"] == "AUTHENTICATION_REQUIRED":
            break
    return result


def main() -> None:
    report = research()
    path = Path(os.getenv("HBI_PROVIDER_RESEARCH_PATH", "provider-research.json"))
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
