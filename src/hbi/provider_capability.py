"""Market-free, full-field provider contract; no probabilistic/fuzzy identity joins."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from .providers.atg import AtgClient

CONTRACT = "FULL_FIELD_ONLY_V1"
MATRIX = Path(__file__).with_name("provider_coverage.json")


def capability(provider: str, country: str, discipline: str) -> dict:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))["combinations"]
    return next(
        (
            r
            for r in rows
            if (r["provider"], r["country"], r["discipline"]) == (provider, country, discipline)
        ),
        {"status": "UNVERIFIED"},
    )


def name_key(value: object) -> str:
    return AtgClient._normalize_name(str(value or ""))


def integer(value: object) -> bool:
    return type(value) is int and value >= 0


def validate_lifetime(horse: dict) -> str | None:
    stats = horse.get("statistics")
    life = stats.get("life") if isinstance(stats, dict) else None
    if not isinstance(life, dict):
        return "MISSING_LIFETIME"
    placement = life.get("placement")
    if not isinstance(placement, dict):
        return "MISSING_PLACEMENTS"
    counts = [life.get("starts"), *(placement.get(str(i)) for i in (1, 2, 3))]
    if not all(integer(v) for v in counts) or sum(counts[1:]) > counts[0]:
        return "INVALID_LIFETIME_COUNTS"
    earnings = life.get("earnings")
    if type(earnings) not in (int, float) or not math.isfinite(earnings) or earnings < 0:
        return "INVALID_LIFETIME_EARNINGS"
    if counts[0] == 0 and earnings != 0:
        return "ZERO_STARTS_WITH_EARNINGS"
    years = stats.get("years")
    if not isinstance(years, dict) or not years:
        return "MISSING_YEAR_CROSSCHECK"
    for metric in ("starts", "earnings"):
        values = [y.get(metric) for y in years.values() if isinstance(y, dict)]
        if (
            len(values) != len(years)
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values)
            or sum(values) > life[metric]
        ):
            return "LIFETIME_BELOW_YEAR_TOTALS"
    if (
        not integer(horse.get("age"))
        or horse["age"] < 1
        or not isinstance(horse.get("sex"), str)
        or horse.get("sex") not in {"horse", "stallion", "gelding", "mare"}
    ):
        return "MISSING_DEMOGRAPHICS"
    trainer = horse.get("trainer")
    if not isinstance(trainer, dict) or not trainer.get("lastName"):
        return "MISSING_TRAINER"
    return None


def resolve_field(
    *,
    starts: list,
    scratches: set[int],
    scratch_ok: bool,
    payload: dict | None,
    country: str,
    discipline: str,
    race_number: int,
    expected_start: datetime,
    observed_at: datetime,
    provider_race_id: str | None,
    source_uri: str | None,
    probe: bool = False,
) -> tuple[dict[str, dict], dict]:
    """Return enrichment only for an entirely valid canonical active field.

    Confidence is a deterministic evidence grade, not a calibrated probability.
    ATG horse.id and Rikstoto registration numbers are different namespaces.
    Unique normalized name AND program number are required within an exact race.
    """
    reasons = []
    evidence = {
        "contract": CONTRACT,
        "provider": "atg",
        "country": country,
        "discipline": discipline,
        "provider_race_id": provider_race_id,
        "source_uri": source_uri,
        "observed_at_utc": observed_at.isoformat(),
        "source_published_at_utc": None,
        "timestamp_basis": "FETCH_COMPLETED",
        "race_start_utc": expected_start.isoformat(),
        "runners": [],
        "probe_only": probe,
        "reasons": reasons,
    }
    if capability("atg", country, discipline)["status"] != "VERIFIED" and not probe:
        reasons.append("PROVIDER_COUNTRY_NOT_VERIFIED")
    if not scratch_ok:
        reasons.append("SCRATCH_STATE_UNAVAILABLE")
    if observed_at >= expected_start:
        reasons.append("NOT_PRE_RACE")
    canonical = []
    for s in starts:
        if (
            not isinstance(s, dict)
            or not integer(s.get("startNumber"))
            or s["startNumber"] < 1
            or not name_key(s.get("horseName"))
            or type(s.get("isScratched")) is not bool
            or s.get("raceNumber") != race_number
        ):
            reasons.append("CANONICAL_FIELD_SCHEMA")
            continue
        if not s["isScratched"] and s["startNumber"] not in scratches:
            canonical.append(s)
    numbers = [
        s.get("startNumber")
        for s in starts
        if isinstance(s, dict) and integer(s.get("startNumber"))
    ]
    if len(numbers) != len(set(numbers)):
        reasons.append("DUPLICATE_CANONICAL_NUMBER")
    names = Counter(name_key(s["horseName"]) for s in canonical)
    if any(n > 1 for n in names.values()):
        reasons.append("AMBIGUOUS_CANONICAL_NAME")
    evidence["active_selections"] = sorted(str(s["startNumber"]) for s in canonical)
    if len(canonical) < 2:
        reasons.append("INSUFFICIENT_ACTIVE_FIELD")
    candidates = []
    if not isinstance(payload, dict):
        reasons.append("NO_PROVIDER_RACE")
    else:
        track = payload.get("track")
        track = track if isinstance(track, dict) else {}
        provider_start = AtgClient._parse_time(payload.get("startTime"))
        if (
            payload.get("id") != provider_race_id
            or payload.get("sport") != discipline
            or track.get("countryCode") != country
            or payload.get("status") != "upcoming"
            or provider_start is None
            or provider_start <= observed_at
            or abs((provider_start - expected_start).total_seconds()) > 300
        ):
            reasons.append("PROVIDER_RACE_IDENTITY_OR_TIME")
        entries = payload.get("starts")
        if not isinstance(entries, list) or any(not isinstance(s, dict) for s in entries):
            reasons.append("PROVIDER_FIELD_SCHEMA")
        else:
            if any("scratched" in s and type(s["scratched"]) is not bool for s in entries):
                reasons.append("INVALID_PROVIDER_SCRATCH_STATE")
            candidates = [s for s in entries if s.get("scratched") is not True]
    provider_numbers = [s.get("number") for s in candidates]
    if (
        any(not integer(n) or n < 1 for n in provider_numbers)
        or len({n for n in provider_numbers if integer(n)}) != len(provider_numbers)
        or set(provider_numbers) != {s["startNumber"] for s in canonical}
    ):
        reasons.append("ACTIVE_FIELD_MISMATCH")
    provider_names = Counter(
        name_key((s.get("horse") or {}).get("name"))
        for s in candidates
        if isinstance(s.get("horse"), dict)
    )
    matched = {}
    for s in canonical:
        number = str(s["startNumber"])
        key = name_key(s["horseName"])
        matches = [
            p
            for p in candidates
            if p.get("number") == s["startNumber"]
            and isinstance(p.get("horse"), dict)
            and name_key(p["horse"].get("name")) == key
        ]
        runner = {
            "selection_id": number,
            "horse_name": s["horseName"],
            "rikstoto_registration": s.get("horseRegistrationNumber"),
            "match_method": "UNIQUE_NAME_AND_PROGRAM_NUMBER",
            "match_confidence": 0.0,
            "schema_ok": False,
            "reason": None,
        }
        if len(matches) != 1 or names[key] != 1 or provider_names[key] != 1:
            runner["reason"] = "IDENTITY_NOT_UNIQUE_OR_MISMATCH"
        else:
            p = matches[0]
            runner["match_confidence"] = 1.0
            runner["provider_horse_id"] = p["horse"].get("id")
            runner["reason"] = validate_lifetime(p["horse"])
            runner["schema_ok"] = runner["reason"] is None
            if runner["schema_ok"]:
                matched[number] = p
        evidence["runners"].append(runner)
    if len(matched) != len(canonical):
        reasons.append("INCOMPLETE_RUNNER_HISTORY_OR_IDENTITY")
    evidence["passed"] = not reasons
    evidence["matched_complete_runners"] = len(matched)
    evidence["active_runners"] = len(canonical)
    return (matched if not reasons else {}), evidence


def full_field_gate(store, race_id: str, rows: list[dict], decision_time: datetime) -> str | None:
    """Canonical live decisions require a fresh successful cohort, never mixed snapshots."""
    if not race_id.startswith("RIKSTOTO:"):
        return None  # offline research fixtures do not claim live provider capability
    with store.connect() as connection:
        result = connection.execute(
            "SELECT payload_json FROM provider_payloads WHERE category=? "
            "AND provider_raceday_key=? AND observed_at_utc<=? "
            "ORDER BY observed_at_utc DESC, rowid DESC LIMIT 1",
            (CONTRACT, race_id, decision_time.isoformat()),
        ).fetchone()
    if result is None:
        return "FULL_FIELD_ONLY_NO_EVIDENCE"
    try:
        e = json.loads(result[0])
        observed = datetime.fromisoformat(e["observed_at_utc"])
        if (
            e["passed"] is not True
            or e.get("probe_only")
            or capability(e["provider"], e["country"], e["discipline"])["status"] != "VERIFIED"
            or not 0 <= (decision_time - observed).total_seconds() <= 600
            or decision_time >= datetime.fromisoformat(e["race_start_utc"])
        ):
            return "FULL_FIELD_ONLY_FAILED_OR_STALE"
        if e["country"] == "FR" and not e.get("corroboration", {}).get("passed"):
            return "FULL_FIELD_ONLY_MISSING_CORROBORATION"
        active = [r for r in rows if not r.get("scratched")]
        if (
            set(e["active_selections"]) != {r["selection_id"] for r in active}
            or any(r["feature_as_of_utc"] != e["observed_at_utc"] for r in active)
            or any(r["data_quality"] != "FULL_FIELD_HISTORY_ATG" for r in active)
        ):
            return "FULL_FIELD_ONLY_COHORT_MISMATCH"
    except (KeyError, TypeError, ValueError):
        return "FULL_FIELD_ONLY_INVALID_EVIDENCE"
    return None
