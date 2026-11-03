"""MVP-009: publish fail-closed V3.3 gap diagnostics from immutable CORE-003 reports.

Reads the already-frozen cohort index, model bytes and PIT attestation; never
reads or writes the SQLite state, calls providers, prices bets or certifies PIT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .mvp008_decision_audit import audit

SCHEMA = "MVP009_AUTOMATIC_DECISION_AUDIT_INDEX_V1"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_original(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("ORIGINAL_INPUT_UNAVAILABLE_OR_SYMLINK")
    return path.read_bytes()


def generate(*, cohort_index: Path, attestation_index: Path, output_dir: Path) -> dict:
    """One exclusive derived output tree. Every failed row is recorded, never promoted."""
    output_dir.mkdir(parents=True, exist_ok=False)
    outcome = {
        "schema": SCHEMA, "authority": "READ_ONLY_DIAGNOSTIC_NO_BET",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "cohort_index_source": str(cohort_index), "cohort_index_original_sha256": None,
        "attestation_index_source": str(attestation_index),
        "attestation_index_original_sha256": None,
        "records": [], "errors": [], "model_reports_expected": 0,
        "model_reports_diagnosed": 0, "pit_certified_by_this_audit": False,
        "bet_authority": False,
    }
    try:
        model_index_raw = _read_original(cohort_index)
        model_index = json.loads(model_index_raw)
        outcome["cohort_index_original_sha256"] = sha(model_index_raw)
        if not isinstance(model_index, dict) or model_index.get("schema") != "BET_MVP_002_FIXED_COHORT_INDEX_V1":
            raise ValueError("FROZEN_COHORT_INDEX_SCHEMA_MISMATCH")
        if model_index.get("bet_authority") is not False:
            raise ValueError("FROZEN_COHORT_UNEXPECTED_BET_AUTHORITY")
        processed = model_index.get("processed")
        if not isinstance(processed, list):
            raise TypeError("FROZEN_COHORT_PROCESSED_NOT_LIST")
        outcome["model_reports_expected"] = len(processed)
    except (OSError, ValueError, TypeError) as exc:
        outcome["errors"].append({"reason": "COHORT_INDEX_UNAVAILABLE_OR_INVALID",
                                  "error": str(exc)})
        processed = []

    try:
        attestation_raw = _read_original(attestation_index)
        attestation = json.loads(attestation_raw)
        if not isinstance(attestation, dict) or attestation.get("schema") != "PIT_T4_ATTESTATION_INDEX_V1":
            raise ValueError("PIT_ATTESTATION_INDEX_SCHEMA_MISMATCH")
        outcome["attestation_index_original_sha256"] = sha(attestation_raw)
    except (OSError, ValueError, TypeError) as exc:
        attestation_raw = None
        outcome["errors"].append({"reason": "PIT_ATTESTATION_INDEX_UNAVAILABLE_OR_INVALID",
                                  "error": str(exc)})

    used_races: set[str] = set()
    used_dirs: set[str] = set()
    for entry in processed:
        race_id = entry.get("race_id") if isinstance(entry, dict) else None
        directory = entry.get("directory") if isinstance(entry, dict) else None
        try:
            if (not isinstance(race_id, str) or not race_id or race_id in used_races
                    or not isinstance(directory, str)):
                raise ValueError("DUPLICATE_OR_INVALID_COHORT_RACE")
            # The CORE-003 producer fixes this exact path contract; never follow
            # a caller-controlled absolute or parent-relative artifact path.
            name = Path(directory).name
            if (directory != (cohort_index.parent.name + "/" + name)
                    or not re.fullmatch(r"race-[0-9]{3,}", name)
                    or name in used_dirs):
                raise ValueError("UNSAFE_OR_DUPLICATE_FROZEN_MODEL_PATH")
            used_races.add(race_id)
            used_dirs.add(name)
            frozen_path = cohort_index.parent / name / "shadow.json"
            frozen_raw = _read_original(frozen_path)
            original_sha = entry.get("report_sha256")
            if not isinstance(original_sha, str) or sha(frozen_raw) != original_sha:
                raise ValueError("FROZEN_MODEL_SHA256_MISMATCH")
            frozen = json.loads(frozen_raw)
            if frozen.get("race", {}).get("race_id") != race_id:
                raise ValueError("FROZEN_MODEL_RACE_ID_MISMATCH")
            report = audit(frozen_raw, attestation_raw)
            if report.get("bet_authority") is not False or report.get("v33_evaluator_called") is not False:
                raise ValueError("UNEXPECTED_DECISION_AUTHORITY")
            out_name = name + ".json"
            serialized = (json.dumps(report, indent=2, ensure_ascii=False,
                                     sort_keys=True, allow_nan=False) + "\n").encode()
            with (output_dir / out_name).open("xb") as fd:
                fd.write(serialized)
            outcome["records"].append({
                "race_id": race_id, "frozen_model_original_sha256": original_sha,
                "diagnostic_path": out_name, "diagnostic_sha256": sha(serialized),
                "runners": report["runners_in_report"], "active": report["active_runners"],
                "market_full_field": report["market_full_field_verified_by_report"],
                "status": "BLOCKED", "blockers": report["global_blockers"],
                "attestation_matched": report["attestation"]["matched"],
                "bet_authority": False,
            })
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            outcome["errors"].append({"race_id": race_id,
                                      "reason": "MODEL_DIAGNOSTIC_UNAVAILABLE_OR_INVALID",
                                      "error": str(exc)})
    outcome["model_reports_diagnosed"] = len(outcome["records"])
    outcome["status"] = (
        "BLOCKED_NO_FROZEN_MODELS" if not outcome["model_reports_expected"]
        else "BLOCKED_PARTIAL_DIAGNOSTIC" if outcome["errors"]
        else "DIAGNOSTIC_COMPLETE_RESEARCH_ONLY"
    )
    with (output_dir / "index.json").open("x", encoding="utf-8") as fd:
        json.dump(outcome, fd, indent=2, ensure_ascii=False, sort_keys=True,
                  allow_nan=False)
        fd.write("\n")
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-index", type=Path, required=True)
    parser.add_argument("--attestation-index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = generate(cohort_index=args.cohort_index,
                      attestation_index=args.attestation_index, output_dir=args.output_dir)
    print(json.dumps({"schema": result["schema"],
                      "expected": result["model_reports_expected"],
                      "diagnosed": result["model_reports_diagnosed"],
                      "errors": len(result["errors"]), "bet_authority": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
