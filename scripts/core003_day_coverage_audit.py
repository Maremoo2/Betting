"""Whole-day, no-cherry-picking CORE-003 source/PIT coverage from one immutable archive.

This script reports all archived trotting race *references* in an interval, including
FUTURE, BLOCKED, incomplete and non-Rikstoto-provider cases. It does not
certify PIT, predict winners, place bets, alter source or migrate production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

from hbi.core_pit_roster_verification import audit_race, parse_time


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity_kind(race_id: str, country: str, track: str) -> str:
    """A composite X1/multi-track reference is not a verified physical race.

    Keep it in the archive ledger instead of silently dropping it or
    letting it inflate the single-track physical race denominator.
    """
    if (
        race_id.startswith("RIKSTOTO:X1_NR_")
        or country == "UNKNOWN"
        or "/" in track
    ):
        return "UNRESOLVED_COMPOSITE_OR_UNLOCATED"
    return "SINGLE_TRACK_CANDIDATE"


def _summary(records: list[dict]) -> dict:
    count = Counter(r["terminal_status"] for r in records)
    blockers = Counter(code for r in records for code in r["blockers"])
    assessed = [r for r in records if r["terminal_status"] != "FUTURE"]
    return {
        "races_total": len(records),
        "single_track_candidates": sum(
            r["race_identity_kind"] == "SINGLE_TRACK_CANDIDATE" for r in records
        ),
        "unresolved_composite_or_unlocated_refs": sum(
            r["race_identity_kind"] == "UNRESOLVED_COMPOSITE_OR_UNLOCATED"
            for r in records
        ),
        "races_t4_elapsed": len(assessed),
        "races_future_not_at_t4": count["FUTURE"],
        "source_observed_not_attested": count["SOURCE_OBSERVED_UNATTESTED"],
        "blocked": count["BLOCKED"],
        "raw_input_ready": sum(r["raw_input_ready"] for r in assessed),
        "pit_certified": 0,
        "clock_conflicts": sum(r["clock_disagreement_seconds"] not in (None, 0)
                               for r in assessed),
        "blockers": dict(sorted(blockers.items())),
    }


def analyze(db: Path, *, start_date: str, end_date: str, asof: str) -> dict:
    left, right = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if right < left:
        raise ValueError("End date precedes start date")
    if (right - left).days > 31:
        raise ValueError("Maximum cohort window is 32 calendar days")
    instant = parse_time(asof)
    if instant is None:
        raise ValueError("Explicit timezone-aware asof required")
    if not db.is_file():
        raise FileNotFoundError(db)
    before = sha256(db)
    uri = "file:" + quote(str(db.resolve())) + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        rows = conn.execute(
            "SELECT race_id,race_date,country,track FROM races "
            "WHERE race_date BETWEEN ? AND ? AND lower(discipline)='trot' "
            "ORDER BY race_date,country,track,race_id",
            (start_date, end_date),
        ).fetchall()
        if not rows:
            raise ValueError("NO_RACES_IN_EXPLICIT_COHORT")
        ids = [str(row["race_id"]) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_PHYSICAL_RACE_IN_DENOMINATOR")
        output = []
        for row in rows:
            race_id = str(row["race_id"])
            reviewed = audit_race(conn, race_id, asof=instant)
            status = reviewed["status"]
            if status not in {"FUTURE", "BLOCKED", "SOURCE_OBSERVED_UNATTESTED"}:
                raise ValueError("Unrecognized terminal research status")
            output.append({
                "race_id": race_id,
                "race_date": row["race_date"],
                "country": row["country"] or "UNKNOWN",
                "track": row["track"] or "UNKNOWN",
                "race_identity_kind": identity_kind(
                    race_id, row["country"] or "UNKNOWN",
                    row["track"] or "UNKNOWN",
                ),
                "terminal_status": status,
                "raw_input_ready": bool(reviewed.get("raw_input_ready_at_cutoff", False)),
                "pit_certified": False,
                "clock_disagreement_seconds": reviewed.get("clock_disagreement_seconds"),
                "blockers": sorted(set(reviewed["blockers"])),
                "source_snapshots": reviewed.get("source_snapshots", {}),
            })
    finally:
        conn.close()
    after = sha256(db)
    if before != after:
        raise RuntimeError("Archived SQLite changed during read-only analysis")
    by_date_country: dict[str, list[dict]] = defaultdict(list)
    by_date_track: dict[str, list[dict]] = defaultdict(list)
    for item in output:
        by_date_country[f"{item['race_date']}|{item['country']}"].append(item)
        by_date_track[f"{item['race_date']}|{item['country']}|{item['track']}"].append(item)
    total = _summary(output)
    if total["races_total"] != sum(
        _summary(rows)["races_total"] for rows in by_date_country.values()
    ):
        raise RuntimeError("Group totals do not match complete physical-race denominator")
    return {
        "schema": "CORE003_WHOLE_DAY_SOURCE_COVERAGE_V1",
        "authority": "RESEARCH_ONLY_NO_PIT_CERTIFICATE_NO_BET",
        "cohort": {"from": start_date, "to": end_date, "asof_utc": instant.isoformat()},
        "source_db_sha256": before,
        "source_db_unchanged": True,
        "summary": total,
        "single_track_is_physical_race_proven": False,
        "unresolved_references_retained_in_denominator": True,
        "country_days": {k: _summary(v) for k, v in sorted(by_date_country.items())},
        "track_days": {k: _summary(v) for k, v in sorted(by_date_track.items())},
        "races": output,
        "model_promotion_authority": False,
        "betting_authority": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--from", dest="start_date", required=True)
    p.add_argument("--to", dest="end_date", required=True)
    p.add_argument("--asof", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.resolve() == a.db.resolve():
        p.error("Refusing to overwrite input SQLite")
    report = analyze(a.db, start_date=a.start_date, end_date=a.end_date, asof=a.asof)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
