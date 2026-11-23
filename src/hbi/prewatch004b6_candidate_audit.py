"""004B6: audit genuine M7B2B PIT-tagged source candidates, never authorize BET.

Reuses immutable original M7B2B source replay. A positive PIT value in the
older scoped evidence contract is NOT an approval for a horse performance
feature or a current target's verified historical result.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .history_availability import run as original_replay

SCHEMA = "PREWATCH004B6_NINE_GENUINE_CANDIDATE_AUDIT_V1"
CANDIDATES = (
    "M7A1-041", "M7A1-042", "M7A1-045", "M7A1-046", "M7A1-047",
    "M7A1-048", "M7A1-049", "M7A1-055", "M7A1-060",
)
BLOCKERS = frozenset({
    "HISTORICAL_HORSE_IDENTITY_NOT_APPROVED",
    "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED",
    "PIT_NOT_APPROVED",
})
TARGET_RESEARCH_ONLY = "BLOCKED_TARGET_HISTORY_ADMISSION"


def audit(report: dict[str, Any]) -> dict[str, Any]:
    """Count verified historical source *scope*, not model admissions."""
    if (report.get("schema") != "M7B2B_GATE_REPORT_V1"
            or report.get("model_eligible") is not False):
        raise ValueError("004B6_M7B2B_ORIGINAL_REPLAY_NOT_ATTESTED")
    decisions = report.get("cutoff_observations")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("004B6_REAL_CUTOFF_OBSERVATIONS_REQUIRED")
    t4 = [d for d in decisions if d.get("cutoff_minutes") == 4]
    indexed = {d["observation_id"]: d for d in t4}
    if len(indexed) != len(t4) or len(t4) != 51:
        raise ValueError("004B6_T4_UNEXPECTED_OR_DUPLICATE_COHORT")
    rows = []
    for observation_id in CANDIDATES:
        d = indexed.get(observation_id)
        if not isinstance(d, dict):
            raise TypeError("004B6_MISSING_REAL_CANDIDATE:" + observation_id)
        reasons = d.get("exclusion_reasons")
        if (d.get("historical_result_chain_pit_decision") != "PIT_VERIFIED"
                or d.get("A_E_research") is not True
                or not isinstance(reasons, list)
                or not BLOCKERS.issubset(set(reasons))
                or d.get("model_eligible") is not False):
            raise ValueError("004B6_PREVIOUS_SCOPED_RESEARCH_CHANGED:" + observation_id)
        pdf = d.get("pdf_pit_decision", {})
        original = d.get("pdf_contract", {})
        if (pdf.get("pit_decision") != "PIT_VERIFIED"
                or original.get("model_eligible") is not False
                or original.get("origin") != "ORIGINAL_ARCHIVED_BYTES"
                or original.get("purpose") != "AS_OBSERVED_INPUT_EVIDENCE"):
            raise ValueError("004B6_SOURCE_ORIGINAL_PIT_INVALID:" + observation_id)
        version = original.get("source_version", {})
        if not all(version.get(key) for key in ("url", "sha256", "archive_sha256", "member", "observed_at")):
            raise ValueError("004B6_ORIGINAL_REFERENCE_MISSING:" + observation_id)
        if (original.get("source_snapshot_at") != original.get("first_observed_at")
                or original["source_snapshot_at"] != version["observed_at"]):
            raise ValueError("004B6_ORIGINAL_CAPTURE_TIME_NOT_BOUND:" + observation_id)
        rows.append({
            "observation_id": observation_id,
            "target_cutoff_utc": d["decision_cutoff_at"],
            "source_version": {
                "url": version["url"], "sha256": version["sha256"],
                "archive_sha256": version["archive_sha256"], "member": version["member"],
                "observed_at": version["observed_at"],
            },
            "source_pdf_pit": pdf["pit_decision"],
            "historical_chain_pit_legacy_research_scope": d["historical_result_chain_pit_decision"],
            "A_E_research": d["A_E_research"],
            "blockers": sorted(reasons),
            "stable_horse_id_admitted_for_model": False,
            "official_historical_performance_feature_admitted": False,
            "model_eligible": False,
            "bet_authorized": False,
            "admission_status": TARGET_RESEARCH_ONLY,
        })
    all_pit = [d for d in t4 if d["historical_result_chain_pit_decision"] == "PIT_VERIFIED"]
    all_ae = [d for d in all_pit if d["A_E_research"]]
    if len(all_pit) != 18 or len(all_ae) != len(CANDIDATES):
        raise ValueError("004B6_LEGACY_COHORT_RECONCILIATION_CHANGED")
    if {d["observation_id"] for d in all_ae} != set(CANDIDATES):
        raise ValueError("004B6_POSITIVE_CANDIDATE_SET_CHANGED")
    reasons = Counter(b for row in rows for b in row["blockers"])
    return {
        "schema": SCHEMA,
        "source": "M7B2B_PINNED_OFFICIAL_ORIGINAL_REPLAY",
        "physical_target": "EXPOSED_2026_PREVIOUS_COHORT_NOT_2026_11_23_FARJESTAD",
        "T_minus_4_total_historical_chains": len(t4),
        "T_minus_4_legacy_scoped_source_pit": len(all_pit),
        "T_minus_4_A_E_research_candidates": len(rows),
        "blocker_counts": dict(sorted(reasons.items())),
        "candidate_audits": rows,
        "genuine_new_target_historical_PIT_admissions": 0,
        "genuine_new_model_eligible_horses": 0,
        "full_field_model_eligible": 0,
        "bet_authorized": False,
        "status": TARGET_RESEARCH_ONLY,
        "next_action": "INDEPENDENTLY_REVIEW_EXACT_TARGET_HORSE_IDENTITY_AND_PRE_CUTOFF_OFFICIAL_RESULT_ORIGINAL; NO RETROACTIVE_TIMESTAMP",
    }


def run(root: Path, output: Path) -> dict[str, Any]:
    reports = original_replay(root)
    result = audit(reports["M7B2B_GATE_REPORT.json"])
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    if output.exists():
        if output.read_bytes() != serialized:
            raise ValueError("004B6_EXISTING_REPORT_MISMATCH")
    else:
        output.write_bytes(serialized)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="PREWATCH004B6 authentic 9 candidate research-only audit")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.output)
    print(json.dumps({
        k: v for k, v in result.items() if k != "candidate_audits"
    }, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
