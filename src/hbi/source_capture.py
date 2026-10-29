"""DATA-005W: bounded, read-only, original HTTP-entity-body evidence capture.

Research-only; no user credentials, no betting APIs, no historical PIT backfill.
An Actions runner clock is not a cryptographic timestamp or publication proof.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

MAX_BYTES = 2_000_000
TIMEOUT = 10
OSLO = ZoneInfo("Europe/Oslo")
ATG_CALENDAR = "https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/"
ATG_GAME = "https://www.atg.se/services/racinginfo/v1/api/games/"
RIKSTOTO = "https://www.rikstoto.no/api/"
TARGETS = (
    ("momarken", "MO_NR_2026-11-01", "2026-11-01", "Momarken", 2),
    ("bjerke", "BJ_NR_2026-10-31", "2026-10-31", "Bjerke", 2),
)
HEADERS = ("Date", "ETag", "Last-Modified", "Content-Type", "Content-Length", "Content-Encoding")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_BLOCKED")


def allowed_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if parsed.fragment or (parsed.query and parsed.hostname != "horse-betting-info.prod.c1.atg.cloud"):
            return False
        if parsed.hostname == "www.rikstoto.no":
            return bool(re.fullmatch(
                r"/api/(racedays/|racedays/(?:MO_NR_2026-11-01|BJ_NR_2026-10-31)/(?:starts|scratched|raceInfo)|game/program/(?:MO_NR_2026-11-01|BJ_NR_2026-10-31)/V|results/racedays/(?:MO_NR_2026-11-01|BJ_NR_2026-10-31)/raceresults|results/raceDays/(?:MO_NR_2026-11-01|BJ_NR_2026-10-31)/2/completeresults)", parsed.path))
        if parsed.hostname == "horse-betting-info.prod.c1.atg.cloud":
            return bool(re.fullmatch(r"/api-public/v0/calendar/day/2026-(?:10-31|11-01)", parsed.path)) and parsed.query == "headToHeadEnabled=true"
        if parsed.hostname == "www.atg.se":
            return bool(re.fullmatch(r"/services/racinginfo/v1/api/games/vinnare_2026-(?:10-31|11-01)_[0-9]+_2", parsed.path))
        return False
    except ValueError:
        return False


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


@dataclass
class ResponseEvidence:
    label: str
    url: str
    request_started_at_utc: str
    response_completed_at_utc: str
    status_code: int | None
    response_headers: dict[str, str]
    original_body_sha256: str | None
    original_body_size: int | None
    body_path: str | None
    parsed_json: bool
    error: str | None
    observation_kind: str = "RUNNER_OBSERVED_NOT_SOURCE_PUBLISHED"
    replayable_raw_body_in_artifact: bool = False


def fetch_original(label: str, url: str, root: Path, opener=None) -> tuple[ResponseEvidence, object | None]:
    if not allowed_url(url):
        raise ValueError("URL_NOT_ALLOWLISTED")
    if not re.fullmatch(r"[a-z0-9_-]{2,55}", label):
        raise ValueError("UNSAFE_LABEL")
    opener = opener or urllib.request.build_opener(NoRedirect())
    begin = utc_now()
    data = None
    status = None
    header_values: dict[str, str] = {}
    err = None
    parsed = None
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "HBI-readonly-PIT-evidence/0.1"}, method="GET")
        with opener.open(request, timeout=TIMEOUT) as response:
            status = response.status
            header_values = {k: str(response.headers.get(k))[:512] for k in HEADERS if response.headers.get(k) is not None}
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                data = None
                err = "BODY_TOO_LARGE_NOT_ARCHIVED"
            else:
                try:
                    parsed = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    err = "RESPONSE_NOT_JSON"
    except urllib.error.HTTPError as exc:
        status = exc.code
        err = f"HTTP_STATUS_{status}"
        # Only 2xx responses are archived; error responses are not source evidence.
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        err = f"FETCH_FAILED:{type(exc).__name__}"
    completed = utc_now()
    body_rel = None
    hash_ = None
    if data is not None and status is not None and 200 <= status < 300:
        dest = root / "raw"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{label}.body"
        path.write_bytes(data)
        body_rel = f"raw/{label}.body"
        hash_ = hashlib.sha256(data).hexdigest()
    e = ResponseEvidence(
        label=label, url=url, request_started_at_utc=begin,
        response_completed_at_utc=completed, status_code=status,
        response_headers=header_values, original_body_sha256=hash_,
        original_body_size=len(data) if hash_ else None, body_path=body_rel,
        parsed_json=parsed is not None, error=err,
        replayable_raw_body_in_artifact=bool(hash_ and parsed is not None),
    )
    return e, parsed


def _parse_time(s: object) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=OSLO)
        return t.astimezone(UTC)
    except ValueError:
        return None


def resolve_atg(calendar: object, track: str, number: int, expected: datetime | None, *, date: str) -> tuple[str | None, str]:
    if not isinstance(calendar, dict) or not isinstance(calendar.get("tracks"), list):
        return None, "ATG_CALENDAR_SCHEMA_UNKNOWN"
    matches = []
    for t in calendar["tracks"]:
        if not isinstance(t, dict) or t.get("countryCode") != "NO" or t.get("sport") != "trot":
            continue
        if str(t.get("name", "")).casefold() != track.casefold():
            continue
        for race in t.get("races", []):
            if not isinstance(race, dict):
                continue
            if race.get("number") != number or not race.get("id"):
                continue
            start = _parse_time(race.get("startTime"))
            if start is None or start.astimezone(OSLO).date().isoformat() != date:
                continue
            if expected is None or abs((start - expected).total_seconds()) > 300:
                continue
            id_ = str(race["id"])
            if re.fullmatch(r"2026-(?:10-31|11-01)_[0-9]+_2", id_):
                matches.append(id_)
    if len(matches) == 1:
        return matches[0], "EXACT_TRACK_COUNTRY_RACE_AND_5MIN_CLOCK_MATCH"
    return None, "NO_UNIQUE_ATG_RACE_OR_CLOCK_MATCH"


def _starts(payload: object, race: int) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    starts = result.get(str(race))
    if not isinstance(starts, list):
        return []
    return [x for x in starts if isinstance(x, dict)]


def _atg_starts(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    races = payload.get("races")
    if not isinstance(races, list) or len(races) != 1 or not isinstance(races[0], dict):
        return []
    starts = races[0].get("starts")
    return [x for x in starts if isinstance(x, dict)] if isinstance(starts, list) else []


def capture(out: Path, stage: str = "pre") -> dict:
    if stage not in ("pre", "post"):
        raise ValueError("INVALID_STAGE")
    out.mkdir(parents=True, exist_ok=True)
    observations: list[ResponseEvidence] = []
    raw_by_label: dict[str, object] = {}
    def add(label: str, url: str) -> None:
        event, payload = fetch_original(label, url, out)
        observations.append(event)
        raw_by_label[label] = payload

    add("rikstoto_racedays", RIKSTOTO + "racedays/")
    for prefix, key, date, track, number in TARGETS:
        add(f"{prefix}_starts", RIKSTOTO + f"racedays/{key}/starts")
        add(f"{prefix}_scratched", RIKSTOTO + f"racedays/{key}/scratched")
        add(f"{prefix}_raceinfo", RIKSTOTO + f"racedays/{key}/raceInfo")
        if prefix == "momarken":
            add(f"{prefix}_program_v", RIKSTOTO + f"game/program/{key}/V")
        add(f"{prefix}_calendar", ATG_CALENDAR + f"{date}?headToHeadEnabled=true")

    discovered = raw_by_label.get("rikstoto_racedays")
    report = {}
    all_races = discovered.get("result") if isinstance(discovered, dict) else None
    for prefix, key, date, track, number in TARGETS:
        matched_rikstoto = []
        if isinstance(all_races, list):
            for day in all_races:
                if not isinstance(day, dict) or day.get("raceDayKey") != key:
                    continue
                for race in day.get("races", []) or []:
                    if isinstance(race, dict) and race.get("raceNumber") == number:
                        matched_rikstoto.append(race)
        expected = _parse_time(matched_rikstoto[0].get("startTime")) if len(matched_rikstoto)==1 else None
        atg_id, link_reason = resolve_atg(raw_by_label.get(f"{prefix}_calendar"), track, number, expected, date=date)
        if atg_id:
            add(f"{prefix}_atg_game", ATG_GAME + "vinnare_" + atg_id)
        starters = _starts(raw_by_label.get(f"{prefix}_starts"), number)
        active = [x for x in starters if not x.get("isScratched")]
        atg_starters = _atg_starts(raw_by_label.get(f"{prefix}_atg_game"))
        ids = [x.get("horse", {}).get("id") for x in atg_starters if isinstance(x.get("horse"), dict)]
        history_summary = [x for x in atg_starters if isinstance(x.get("horse"), dict) and isinstance(x.get("horse", {}).get("statistics", {}).get("life"), dict)]
        report[prefix] = {
            "race_id": f"RIKSTOTO:{key}:{number}", "start_time_in_racedays_utc": expected.isoformat() if expected else None,
            "racedays_match_count": len(matched_rikstoto),
            "canonical_starter_count": len(starters), "not_marked_scratched_in_starts_count": len(active),
            "atg_provider_race_id": atg_id, "atg_link_reason": link_reason,
            "atg_starter_count": len(atg_starters), "atg_horse_id_available_count": sum(x is not None for x in ids),
            "atg_lifetime_summary_count": len(history_summary),
            "full_history_per_previous_start_available": False,
            "is_pre_start_capture": bool(expected and all(
                datetime.fromisoformat(e.response_completed_at_utc) < expected
                for e in observations if e.label.startswith(prefix + "_")
            )),
            "complete_pit_evidence": False,
            "bet_authorized": False,
        }
        if stage == "post":
            add(f"{prefix}_raceday_result", RIKSTOTO + f"results/racedays/{key}/raceresults")
            add(f"{prefix}_complete_result", RIKSTOTO + f"results/raceDays/{key}/{number}/completeresults")
    manifest = {
        "schema_version": "DATA005W_RAW_HTTP_RESEARCH_V1",
        "stage": stage, "generated_at_utc": utc_now(), "clock_basis": "GITHUB_RUNNER_UTC_NOT_NOTARIZED",
        "rights": "PUBLIC_INFORMATION_TRANSIENT_RESEARCH_RETAIN_14_DAYS",
        "records": [asdict(e) for e in observations], "race_assessments": report,
        "all_raw_files_included": all(e.body_path and (out/e.body_path).is_file() for e in observations if e.status_code is not None and 200 <= e.status_code < 300),
        "research_only": True, "model_eligible": False, "bet_authorized": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({"captures":len(observations),"http_ok":sum(e.status_code == 200 for e in observations),"valid_json":sum(e.parsed_json for e in observations),"races":report},ensure_ascii=False,indent=2,sort_keys=True), encoding="utf-8")
    return manifest


def verify(root: Path) -> list[str]:
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    errors = []
    for e in data["records"]:
        if e["body_path"]:
            target = (root / e["body_path"]).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                errors.append(f"MISSING_OR_ESCAPED_RAW:{e['label']}")
            elif hashlib.sha256(target.read_bytes()).hexdigest() != e["original_body_sha256"]:
                errors.append(f"SHA256_MISMATCH:{e['label']}")
        elif e["replayable_raw_body_in_artifact"]:
            errors.append(f"REPLAYABLE_WITHOUT_RAW:{e['label']}")
    return errors


def main() -> int:
    out = Path(os.getenv("HBI_PIT_CAPTURE_PATH", "pit-capture"))
    stage = os.getenv("HBI_PIT_CAPTURE_STAGE", "pre")
    result = capture(out, stage)
    errs = verify(out)
    print(json.dumps({"stage":stage,"summary":result["race_assessments"],"captures":len(result["records"]),"verify_errors":errs,"status_counts":{str(i):sum(x["status_code"]==i for x in result["records"]) for i in {x["status_code"] for x in result["records"]}}},indent=2,ensure_ascii=False))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
