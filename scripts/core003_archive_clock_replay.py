"""Run current CORE-003 research metric against a pinned, immutable pilot snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from hbi.core_shadow_pilot import _aggregate, _readiness


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def analyze(db_path: Path, prior_report_path: Path) -> dict:
    before = digest(db_path)
    prior_raw = prior_report_path.read_bytes()
    prior = json.loads(prior_raw)
    if prior.get("schema_version") != "CORE_003_SHADOW_PILOT_V1":
        raise ValueError("Not a canonical CORE-003 pilot report")
    races = prior.get("races_in_fixed_cohort")
    if not isinstance(races, list) or len(races) != len(set(races)) or not races:
        raise ValueError("Pilot must have a nonempty unique physical-race cohort")
    asof = datetime.fromisoformat(prior["finished_at_utc"])
    if asof.utcoffset() is None:
        raise ValueError("Naive as-of is forbidden")
    uri = "file:" + quote(str(db_path.resolve())) + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        records = [_readiness(conn, race_id, asof) for race_id in races]
    if digest(db_path) != before:
        raise RuntimeError("Immutable pilot SQLite changed during E2E")
    updated = _aggregate(records)
    old = prior["after"]
    return {
        "schema": "CORE003_CLOCK_CONSERVATIVE_ARCHIVE_E2E_V1",
        "authority": "SOURCE_RESEARCH_ONLY_NOT_PIT_OR_BET",
        "db_sha256": before,
        "input_report_sha256": hashlib.sha256(prior_raw).hexdigest(),
        "db_unchanged": True,
        "asof_utc": asof.isoformat(),
        "races_in_same_cohort": len(races),
        "original_races_full_sources": old["races_full_sources"],
        "conservative_races_full_sources": updated["races_full_sources"],
        "conservative_earlier_source_clock_races": updated["races_with_earlier_source_clock"],
        "false_positive_ready_removed": (
            old["races_full_sources"] - updated["races_full_sources"]
        ),
        "race_readiness": records,
        "roster_pit_verified": False,
        "prospective_t4_success_proven": False,
        "model_promotion_authority": False,
        "betting_authority": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--prior-report", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() in {args.db.resolve(), args.prior_report.resolve()}:
        p.error("Output cannot overwrite immutable input artifacts")
    result = analyze(args.db, args.prior_report)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({
        "cohort": result["races_in_same_cohort"],
        "original_complete": result["original_races_full_sources"],
        "conservative_complete": result["conservative_races_full_sources"],
        "clock_conflicts": result["conservative_earlier_source_clock_races"],
        "pit_certified": result["roster_pit_verified"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
