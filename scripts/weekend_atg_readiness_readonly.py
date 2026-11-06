"""Bounded original-backed ATG full-field readiness check: never score or bet.

Only the existing approved ATG calendar/game endpoints, AtgClient race resolver
and FULL_FIELD_ONLY_V1 identity/history contract are used. No fallback sources,
matching heuristic, model invocation or new scheduler.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from hbi.provider_capability import name_key, resolve_field, validate_lifetime
from hbi.providers.atg import AtgClient, AtgFetchResult

SCHEMA = "WEEKEND_ATG_AUTHENTIC_SOURCE_DIAGNOSTIC_V1"
MAX_BYTES = 3_000_000
TRACKS = {
    "FARJESTAD_V64": ("Färjestad", "SE"),
    "BERGSAKER_V85": ("Bergsåker", "SE"),
    "KLOSTERSKOGEN_V75": ("Klosterskogen", "NO"),
}


def _original(folder: Path, report: dict, path: str) -> dict:
    receipts = [r for r in report["original_receipts"] if r["request_path"] == path]
    if len(receipts) != 1 or receipts[0].get("http_status") != 200:
        raise ValueError("REQUIRED_RIKSTOTO_ORIGINAL_UNAVAILABLE")
    receipt = receipts[0]
    sha = receipt["response_sha256"]
    if receipt.get("original_relative_path") != f"originals/{sha}.json":
        raise ValueError("ORIGINAL_RIKSTOTO_PATH_NOT_VERIFIED")
    body = (folder / f"originals/{sha}.json").read_bytes()
    if hashlib.sha256(body).hexdigest() != sha:
        raise ValueError("ORIGINAL_RIKSTOTO_SHA_MISMATCH")
    clock = datetime.fromisoformat(receipt["response_completed_utc"])
    if clock.utcoffset() is None:
        raise ValueError("ORIGINAL_RIKSTOTO_UTC_UNVERIFIED")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise TypeError("ORIGINAL_RIKSTOTO_RESPONSE_NOT_OBJECT")
    return result


def _get_original(url: str, folder: Path) -> tuple[AtgFetchResult, dict]:
    """Single unauthenticated public original response; no retries or bypass."""
    started = datetime.now(UTC)
    request = urllib.request.Request(
        url, headers=AtgClient._headers(), method="GET",
    )
    payload = None
    raw = None
    status = None
    error = None
    headers = {}
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            status = response.status
            headers = dict(response.headers)
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("ATG_ORIGINAL_BODY_TOO_LARGE")
            payload = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            ValueError, json.JSONDecodeError) as exc:
        status = exc.code if isinstance(exc, urllib.error.HTTPError) else status
        error = type(exc).__name__ + ":" + str(exc)
        payload = None
        raw = None
    completed = datetime.now(UTC)
    receipt = {
        "url": url, "request_started_utc": started.isoformat(),
        "response_completed_utc": completed.isoformat(),
        "http_status": status, "source_published_at_utc": None,
        "http_date_unverified": headers.get("Date"),
        "response_sha256": None, "raw_original_path": None,
        "success": payload is not None and status == 200,
        "error": error,
    }
    if receipt["success"] and raw is not None:
        digest = hashlib.sha256(raw).hexdigest()
        original = folder / f"{digest}.json"
        if original.exists() and original.read_bytes() != raw:
            raise ValueError("ORIGINAL_ATG_SHA_COLLISION")
        if not original.exists():
            with original.open("xb") as stream:
                stream.write(raw)
        receipt["response_sha256"] = digest
        receipt["raw_original_path"] = str(original.name)
    result = AtgFetchResult(
        url=url, payload=payload, success=receipt["success"],
        status_code=status, latency_ms=(completed - started).total_seconds() * 1000,
        error=error,
    )
    return result, receipt


def audit(original_capture: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    originals = output / "atg-originals"
    originals.mkdir()
    source = json.loads((original_capture / "weekend-race-intelligence.json").read_bytes())
    if (source.get("schema") != "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
            or source.get("bet_authority") is not False
            or source.get("new_model_invocations") != 0):
        raise ValueError("UNQUALIFIED_RIKSTOTO_SOURCE_REPORT")
    receipts, rounds = [], {}
    for game in source["weekend_rounds"]:
        if game["name"] not in TRACKS:
            continue
        track, country = TRACKS[game["name"]]
        if not game["legs"]:
            rounds[game["name"]] = {"status": "NO_AUTHORITATIVE_LEGS", "legs": []}
            continue
        key = game["source_raceday_keys"][0]
        starts = _original(original_capture, source, f"/racedays/{key}/starts")
        scratch = _original(original_capture, source, f"/racedays/{key}/scratched")
        scratched_result = scratch.get("result")
        source_start = starts.get("result")
        if not isinstance(source_start, dict) or not isinstance(scratched_result, dict):
            raise TypeError("RACEDAY_ORIGINAL_STARTS_SCRATCHES_INVALID")
        # One official ATG calendar read per country/track, not per horse.
        expected_date = ("2026-11-06" if game["name"] == "FARJESTAD_V64"
                         else "2026-11-07")
        date = game.get("race_date") or expected_date
        if date != expected_date:
            raise ValueError("ATG_RESEARCH_DATE_NOT_ALLOWED")
        cal_url = (f"{AtgClient.CALENDAR_API}/calendar/day/"
                   f"{date}?headToHeadEnabled=true")
        calendar, calendar_receipt = _get_original(cal_url, originals)
        receipts.append(calendar_receipt)
        client = AtgClient(timeout=12)
        results = []
        for leg in game["legs"]:
            n = leg["race_no"]
            physical = f"RIKSTOTO:{key}:{n}"
            if physical != leg["physical_race_id"]:
                raise ValueError("RACEDAY_PHYSICAL_JOIN_MISMATCH")
            roster = source_start.get(str(n))
            if not isinstance(roster, list):
                raise TypeError("MISSING_ORIGINAL_RACE_ROSTER")
            original_scratch = scratched_result.get(str(n), [])
            if not isinstance(original_scratch, list):
                raise TypeError("SCRATCH_ORIGINAL_NOT_LIST")
            scratched = set()
            for v in original_scratch:
                number = v.get("startNumber") if isinstance(v, dict) else v
                if type(number) is not int:
                    raise TypeError("INVALID_ORIGINAL_SCRATCH_NUMBER")
                scratched.add(number)
            canonical_active = [r for r in roster if
                                r.get("isScratched") is False]
            if ({r["startNumber"] for r in roster if r.get("isScratched")} != scratched
                    or len(canonical_active) != leg["active_runners"]):
                raise ValueError("ORIGINAL_CANONICAL_SCRATCH_CONFLICT")
            start = datetime.fromisoformat(leg["race_start_utc"])
            if start.utcoffset() is None:
                raise ValueError("START_UTC_UNVERIFIED")
            resolved = client.resolve_race(
                calendar, track_name=track, race_number=n, expected_start=start,
                country=country, discipline="trot",
            )
            atg_id = resolved.race_id if resolved is not None else None
            game_receipt = None
            payload = None
            fetch_completed = datetime.now(UTC)
            if resolved is not None:
                game_url = f"{AtgClient.GAME_API}/vinnare_{atg_id}"
                fetched, game_receipt = _get_original(game_url, originals)
                receipts.append(game_receipt)
                payload = client.race_payload(fetched)
                fetch_completed = datetime.fromisoformat(game_receipt["response_completed_utc"])
            matched, evidence = resolve_field(
                starts=roster, scratches=scratched, scratch_ok=True,
                payload=payload, country=country, discipline="trot",
                race_number=n, expected_start=start, observed_at=fetch_completed,
                provider_race_id=atg_id,
                source_uri=game_receipt["url"] if game_receipt else None,
                probe=False,
            )
            independent_history = []
            if payload:
                for item in payload.get("starts", []):
                    if not isinstance(item, dict):
                        continue
                    horse = item.get("horse")
                    if not isinstance(horse, dict):
                        continue
                    no = item.get("number")
                    canonical = next(
                        (r for r in canonical_active
                         if r["startNumber"] == no
                         and name_key(r["horseName"]) == name_key(horse.get("name"))),
                        None,
                    )
                    if canonical is not None and validate_lifetime(horse) is None:
                        independent_history.append(no)
            counts = len(set(independent_history))
            status = ("ATG_FULL_FIELD_HISTORY_CONTRACT" if matched
                      else "BLOCKED_ATG_FIELD_OR_HISTORY")
            results.append({
                "leg": leg["leg"], "race_no": n, "physical_race_id": physical,
                "source_start_utc": start.astimezone(UTC).isoformat(),
                "active_runners": len(canonical_active),
                "atg_race_id": atg_id,
                "atg_calendar_http": calendar_receipt["http_status"],
                "atg_game_http": game_receipt["http_status"] if game_receipt else None,
                "atg_valid_lifetime_name_number_matches": counts,
                "atg_full_field_match_count": len(matched),
                "source_contract_status": status,
                "source_gate_reasons": evidence["reasons"],
                "independent_registration_attested": 0,
                "identity_note": "ATG IDs and RIKSTOTO TMP registration are distinct namespaces",
                "model_assessed_runners": 0, "pit_certified": False,
                "model_eligible": False, "bet_authority": False,
            })
        rounds[game["name"]] = {
            "status": "READ_ONLY_ATG_SOURCE_PROBE",
            "legs": results,
        }
    result = {
        "schema": SCHEMA, "completed_utc": datetime.now(UTC).isoformat(),
        "bet_authority": False, "model_invocations": 0,
        "pit_certified": False, "frozen_strategy_changed": False,
        "original_atg_receipts": receipts,
        "original_rikstoto_report_source_as_of_utc": source["source_as_of_utc"],
        "rounds": rounds,
        "limitation": (
            "A current ATG name/number full-field history contract does not "
            "independently attest a permanent Rikstoto registration, PIT, "
            "frozen model prediction, or an executable betting signal."
        ),
    }
    with (output / "atg-readiness.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.original_capture, args.output)
    print(json.dumps({
        "schema": result["schema"],
        "legs": {k: len(v["legs"]) for k, v in result["rounds"].items()},
        "bet_authority": False, "pit_certified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
