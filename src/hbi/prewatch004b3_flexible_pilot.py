"""PREWATCH-004B3: original-bound STRICT/FLEXIBLE feasibility (research, NO BET).

A source-rich PDF row is never a verified historical race. This module
measures recoverable coverage without fabricating model probabilities.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .prewatch004_pack import _write_once, digest
from .prewatch004b2_original_binding import make_day_unresolved_report
from .prewatch004b_features import make_feature_day_packs

SCHEMA = "PREWATCH004B3_FLEXIBLE_FEASIBILITY_V1"
NOT_ESTIMABLE = "NOT_ESTIMABLE"


def evaluate(contexts: list[dict[str, Any]], identity: dict[str, Any]) -> dict[str, Any]:
    """Conservative observed coverage only, no probability or BET model."""
    if identity.get("schema") != "PREWATCH004B2_DAY_IDENTITY_COVERAGE_V1":
        raise ValueError("004B3_IDENTITY_SCHEMA_MISMATCH")
    if identity.get("model_eligible") is not False or identity.get("bet_authorized") is not False:
        raise ValueError("004B3_UNAUTHORIZED_IDENTITY_PROMOTION")
    if not contexts or len({x["race_id"] for x in contexts}) != len(contexts):
        raise ValueError("004B3_DUPLICATE_OR_EMPTY_RACES")
    if len({x["source_run_id"] for x in contexts}) != 1:
        raise ValueError("004B3_SOURCE_RUN_CONFLICT")
    roster = [(x["race_id"], r["selection_id"]) for x in contexts for r in x["runners"] if not r["scratched"]]
    if len(roster) != len(set(roster)):
        raise ValueError("004B3_DUPLICATE_ACTIVE_SELECTION")
    observations = identity.get("horse_observations")
    if not isinstance(observations, list):
        raise ValueError("004B3_MISSING_IDENTITY_OBSERVATIONS")
    indexed = {(r["race_id"], r["selection_id"]): r for r in observations}
    if len(indexed) != len(observations) or set(indexed) != set(roster):
        raise ValueError("004B3_FULL_FIELD_IDENTITY_MISMATCH")
    if (identity.get("physical_races") != len(contexts)
            or identity.get("active_runners") != len(roster)
            or identity.get("listed_runners") != sum(len(x["runners"]) for x in contexts)
            or identity.get("source_run_id") != contexts[0]["source_run_id"]):
        raise ValueError("004B3_DAY_COUNTS_OR_SOURCE_CONFLICT")
    if any(x.get("pit_certified") is not False or x.get("bet_authorized") is not False
           for x in contexts):
        raise ValueError("004B3_SOURCE_AUTHORITY_CONFLICT")
    active = [r for x in contexts for r in x["runners"] if not r["scratched"]]
    if any(r.get("model_eligible") is not False or r.get("pit_eligible") is not False
           or r.get("bet_authorized") is not False for r in active):
        raise ValueError("004B3_UNAUTHORIZED_FEATURE_PROMOTION")
    if any(indexed[(x["race_id"], r["selection_id"])].get("identity_status") != "IDENTITY_UNRESOLVED"
           or indexed[(x["race_id"], r["selection_id"])].get("pit_status") != "PIT_UNPROVEN"
           or indexed[(x["race_id"], r["selection_id"])].get("model_eligible") is not False
           for x in contexts for r in x["runners"] if not r["scratched"]):
        raise ValueError("004B3_UNATTESTED_IDENTITY_OR_PIT")
    tiers = Counter()
    for r in active:
        n = r.get("source_history_count")
        if type(n) is not int or n < 0 or n != len(r.get("research_source_extractions", [])):
            raise ValueError("004B3_SOURCE_HISTORY_COUNT_CONFLICT")
        for threshold in (1, 3, 5, 10):
            if n >= threshold:
                tiers[f"pdf_raw_ge{threshold}"] += 1
    # The PDF thresholds are potential extraction workload, not modeling authority.
    return {
        "schema": SCHEMA,
        "source_run_id": identity["source_run_id"],
        "source_original_archive_sha256": identity["source_original_archive_sha256"],
        "physical_races": len(contexts),
        "listed_runners": identity["listed_runners"],
        "active_runners": len(active),
        "source_only_full_field_races": len(contexts),
        "research_pdf_row_tiers": {f"pdf_raw_ge{n}": tiers[f"pdf_raw_ge{n}"] for n in (1, 3, 5, 10)},
        "strict": {"model_eligible_horses": 0, "model_eligible_full_races": 0,
                   "reason": "NO_ATTESTED_COMPLETE_LAST5_AND_PIT"},
        "flexible": {"model_eligible_horses": 0, "model_eligible_full_races": 0,
                     "reason": "NO_IDENTITY_AND_PIT_QUALIFIED_PARTIAL_HISTORY"},
        "comparison": {key: NOT_ESTIMABLE for key in
                       ("brier", "log_loss", "calibration", "p_win", "fair_odds",
                        "minimum_bet_odds", "market_ev", "bet_candidates", "roi")},
        "research_bets_issued": 0,
        "model_trained": False,
        "bet_authorized": False,
        "status": "BLOCKED_REAL_HISTORICAL_ADMISSION",
    }


def run(archive: Path, checksum: Path, day: str, output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="prewatch004b3-") as td:
        root = Path(td)
        feature_dir = root / "features"
        coverage = make_feature_day_packs(archive, checksum, feature_dir, day=day)
        identity = make_day_unresolved_report(archive, checksum, root / "identity.json", date_oslo=day)
        contexts = []
        for item in coverage["files"]:
            raw = (feature_dir / item["filename"]).read_bytes()
            if digest(raw) != item["sha256"]:
                raise ValueError("004B3_FEATURE_CONTEXT_SHA_CONFLICT")
            contexts.append(json.loads(raw))
        result = evaluate(contexts, identity)
        result["research_semantic_rows"] = coverage["history_semantic_rows_total"]
        result["raw_prior_pdf_lines"] = coverage["history_raw_rows_total"]
        payload = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_once(output, payload)
        return result


def main() -> None:
    p = argparse.ArgumentParser(description="004B3 source-bound STRICT vs FLEXIBLE (NO BET)")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--checksum", type=Path, required=True)
    p.add_argument("--date-oslo", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(run(a.archive, a.checksum, a.date_oslo, a.output), sort_keys=True))


if __name__ == "__main__":
    main()
