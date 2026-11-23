"""PREWATCH-004B5: audit preserved original evidence, not model admission (NO BET).

Three separate conclusions:
(1) pre-cutoff source capture, (2) independently verified retrospective
official result, (3) fully attested target-specific PIT history. No shortcut
from either of the first two to the third.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .history_availability import run as historical_availability_run
from .mvp023b_performance_features import run_authentic_research
from .prewatch004_pack import _write_once, digest
from .prewatch004b2_original_binding import make_day_unresolved_report
from .prewatch004b4_fullfield_pilot import select_race
from .prewatch004b_features import make_feature_day_packs

SCHEMA = "PREWATCH004B5_PIT_EVIDENCE_RECOVERY_V1"
BLOCKED = "BLOCKED_NO_INDEPENDENT_PRE_CUTOFF_HISTORY_IDENTITY_RECEIPTS"


def instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("004B5_CLOCK_REQUIRED")
    when = datetime.fromisoformat(value)
    if when.utcoffset() is None:
        raise ValueError("004B5_OFFSET_AWARE_CLOCK_REQUIRED")
    return when.astimezone(UTC)


def source_window(source_observed: str, race_start: str, *, cutoff_minutes: int = 4) -> dict[str, Any]:
    """Prove original capture timing only; does not prove PIT history semantics."""
    observed, start = instant(source_observed), instant(race_start)
    cutoff = start - timedelta(minutes=cutoff_minutes)
    return {
        "observed_at_utc": observed.isoformat(),
        "race_start_utc": start.isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "source_captured_before_cutoff": observed < cutoff,
        "historical_original_pit_verified": False,
        "meaning": "ORIGINAL_SOURCE_CAPTURE_TIME_ONLY_NOT_RESULT_PIT",
    }


def assemble(fullfield: dict[str, Any], source: dict[str, Any],
             retrospective: dict[str, Any], availability: dict[str, Any]) -> dict[str, Any]:
    if (fullfield.get("schema") != "PREWATCH004B4_ONE_RACE_FULLFIELD_RESEARCH_V1"
            or fullfield.get("bet_authorized") is not False
            or fullfield.get("active_with_attested_permanent_identity") != 0
            or fullfield.get("active_with_pit_qualified_history") != 0):
        raise ValueError("004B5_FULLFIELD_REVIEW_NOT_SOURCE_ONLY")
    if source.get("archive_sha256") != fullfield["archive_sha256"]:
        raise ValueError("004B5_ORIGINAL_ARCHIVE_SHA_CONFLICT")
    observation = source_window(source["observed_at_utc"], fullfield["race"]["start_time_utc"])
    if retrospective.get("evidence_mode") != "SOURCE_REPLAYED_NO_2026":
        raise ValueError("004B5_RETROSPECTIVE_NOT_AUTHENTIC_REPLAY")
    if (retrospective.get("source_observations") != 7
            or retrospective.get("historical_asof_verified_horses") != 0
            or retrospective.get("bet_authority") is not False):
        raise ValueError("004B5_UNEXPECTED_RETROSPECTIVE_SCOPE")
    if (availability.get("schema") != "M7B2B_GATE_REPORT_V1"
            or availability.get("model_eligible") is not False):
        raise ValueError("004B5_UNREVIEWED_M7B2B_REPORT")
    if len(fullfield["runners"]) != fullfield["listed_count"]:
        raise ValueError("004B5_FULLFIELD_DENOMINATOR_CONFLICT")
    per_horse = []
    for row in fullfield["runners"]:
        if row["scratched"]:
            per_horse.append({
                "selection_id": row["selection_id"], "horse_name": row["horse_name"],
                "scratched": True, "status": "SCRATCHED_EXCLUDED",
            })
            continue
        if (row["identity_status"] != "IDENTITY_UNRESOLVED"
                or row["pit_status"] != "PIT_UNPROVEN"
                or row["verified_official_results"] != 0
                or row["model_eligible"] is not False):
            raise ValueError("004B5_UNATTESTED_HISTORY_PREMATURELY_ACCEPTED")
        per_horse.append({
            "selection_id": row["selection_id"], "horse_name": row["horse_name"],
            "scratched": False, "permanent_horse_identity": None,
            "original_pdf_history_lines": row["pdf_raw_history_rows"],
            "original_pdf_history_row_sha256": row["raw_row_sha256"],
            "retrospective_official_starts_attested_for_this_target": 0,
            "pit_verified_prior_starts": 0,
            "identity_status": row["identity_status"],
            "history_pit_status": row["pit_status"],
            "program_source_captured_before_cutoff": observation["source_captured_before_cutoff"],
            "blocker": "NO_REGISTER_BOUND_ID_AND_OFFICIAL_HISTORY_VERSION_OBSERVED_BEFORE_CUTOFF",
            "model_eligible": False,
        })
    a = availability["cutoffs"]
    cutoffs = {k: {
        "pdf_source_pit_verified_M7B2B_research": a[k]["pdf_pit_verified"],
        "official_history_chain_pit_counts_M7B2B": a[k]["chain_pit_counts"],
    } for k in sorted(a, key=int)}
    legacy_candidates = [
        {
            "observation_id": d["observation_id"],
            "cutoff_minutes": d["cutoff_minutes"],
            "legacy_chain_status": d["historical_result_chain_pit_decision"],
            "legacy_A_E_research": d["A_E_research"],
            "exclusion_reasons": d["exclusion_reasons"],
            "new_target_history_PIT_admitted": False,
        }
        for d in availability.get("cutoff_observations", [])
        if d["cutoff_minutes"] == 4
        and d["historical_result_chain_pit_decision"] == "PIT_VERIFIED"
    ]
    return {
        "schema": SCHEMA,
        "legacy_pit_candidate_rows_Tminus4_not_new_admissions": legacy_candidates,
        "race_id": fullfield["race_id"],
        "race": fullfield["race"],
        "source_original_archive_sha256": fullfield["archive_sha256"],
        "source_run_id": fullfield["source_run_id"],
        "source_program_pdf_sha256": source["program_pdf_original_sha256"],
        "source_clock": observation,
        "listed_runners": fullfield["listed_count"],
        "active_runners": fullfield["active_count"],
        "active_with_five_pdf_raw_lines": fullfield["active_raw_ge5"],
        "nov23_individually_attested_historical_result_rows": 0,
        "nov23_fullfield_historical_PIT_verified_horses": 0,
        "retrospective_no2026_official_source_observations": retrospective["source_observations"],
        "retrospective_no2026_unique_horses_for_target": retrospective["unique_horses_for_target"],
        "retrospective_no2026_original_result_pit_horses": retrospective["historical_asof_verified_horses"],
        "m7b2b_existing_original_research": {
            "observations": availability["observations"],
            "cutoff_evidence": cutoffs,
            "scope": "SEPARATE_PREVIOUS_COHORT_NOT_NOV23_FIELD",
        },
        "field": per_horse,
        "first_genuine_historical_pit_admission": False,
        "production_pit_certified": False,
        "model_eligible": False,
        "bet_authorized": False,
        "status": BLOCKED,
    }


def run(archive: Path, checksum: Path, *, day: str, root: Path,
        output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="prewatch004b5-") as td:
        temp = Path(td)
        coverage = make_feature_day_packs(archive, checksum, temp / "contexts", day=day)
        identity = make_day_unresolved_report(
            archive, checksum, temp / "identity.json", date_oslo=day
        )
        contexts = []
        for file in coverage["files"]:
            raw = (temp / "contexts" / file["filename"]).read_bytes()
            if digest(raw) != file["sha256"]:
                raise ValueError("004B5_FEATURE_ORIGINAL_SHA_CONFLICT")
            contexts.append(json.loads(raw))
        selected = select_race(contexts, identity)
        source = next(x["source"] for x in contexts if x["race_id"] == selected["race_id"])
        retrospective = run_authentic_research(root)
        reports = historical_availability_run(root)
        result = assemble(selected, source, retrospective, reports["M7B2B_GATE_REPORT.json"])
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2)
                   + "\n").encode("utf-8")
        _write_once(output, payload)
        return result


def main() -> None:
    p = argparse.ArgumentParser(description="B5 genuine evidence recovery NO MODEL NO BET")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--checksum", type=Path, required=True)
    p.add_argument("--date-oslo", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = run(a.archive, a.checksum, day=a.date_oslo, root=a.root, output=a.output)
    print(json.dumps({k: v for k, v in result.items() if k != "field"},
                     sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
