"""PREWATCH-004B4: deterministic real-original full-field research audit (NO BET).

Selects one race by maximum minimum available PDF rows across active runners.
Source/roster observations are not independent verified official results or PIT.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from .prewatch004_pack import _write_once, digest
from .prewatch004b2_original_binding import make_day_unresolved_report
from .prewatch004b3_flexible_pilot import evaluate
from .prewatch004b_features import make_feature_day_packs

SCHEMA = "PREWATCH004B4_ONE_RACE_FULLFIELD_RESEARCH_V1"


def select_race(contexts: list[dict[str, Any]], identity: dict[str, Any]) -> dict[str, Any]:
    """All-active-field audit; cannot silently omit a runner or promote raw results."""
    day = evaluate(contexts, identity)
    scored = []
    for context in contexts:
        active = [r for r in context["runners"] if not r["scratched"]]
        if not active:
            continue
        counts = [r["source_history_count"] for r in active]
        scored.append((min(counts), sum(counts), len(active), context["race_id"], context))
    if not scored:
        raise ValueError("004B4_NO_ACTIVE_RACES")
    _, _, _, _, race = min(scored, key=lambda x: (-x[0], -x[1], -x[2], x[3]))
    ids = {(r["race_id"], r["selection_id"]): r for r in identity["horse_observations"]}
    runners = []
    for r in race["runners"]:
        if r["scratched"]:
            runners.append({"selection_id": r["selection_id"], "horse_name": r["horse_name"],
                            "scratched": True, "research_only": True})
            continue
        bound = ids[(race["race_id"], r["selection_id"])]
        rows = r["research_source_extractions"]
        if (bound["identity_status"] != "IDENTITY_UNRESOLVED"
                or bound["pit_status"] != "PIT_UNPROVEN"
                or r["model_eligible"] is not False
                or any(q["verified_official_result"] is not False
                       or q["pit_certified"] is not False for q in rows)):
            raise ValueError("004B4_UNATTESTED_ORIGINAL_PROMOTION")
        runners.append({
            "selection_id": r["selection_id"],
            "horse_name": r["horse_name"],
            "scratched": False,
            "pdf_raw_history_rows": len(rows),
            "research_semantic_candidate_rows": sum(
                q["semantic_status"] == "PARTIAL" for q in rows
            ),
            "raw_row_sha256": [q["raw_sha256"] for q in rows],
            "identity_status": bound["identity_status"],
            "pit_status": bound["pit_status"],
            "verified_official_results": bound["verified_original_results_admitted"],
            "model_eligible": False, "research_only": True,
        })
    active = [r for r in runners if not r["scratched"]]
    return {
        "schema": SCHEMA,
        "source_run_id": day["source_run_id"],
        "archive_sha256": day["source_original_archive_sha256"],
        "race_id": race["race_id"],
        "race": race["race"],
        "selection_method": "MAX_MIN_PDF_RAW_ROWS_THEN_TOTAL_THEN_FIELD_SIZE_THEN_RACE_ID",
        "listed_count": len(runners),
        "active_count": len(active),
        "scratched_count": len(runners) - len(active),
        "active_raw_ge3": sum(x["pdf_raw_history_rows"] >= 3 for x in active),
        "active_raw_ge5": sum(x["pdf_raw_history_rows"] >= 5 for x in active),
        "active_with_independently_verified_historical_results": 0,
        "active_with_attested_permanent_identity": 0,
        "active_with_pit_qualified_history": 0,
        "strict_model_eligible": 0,
        "flexible_model_eligible": 0,
        "p_win": "NOT_ESTIMABLE",
        "bet_candidates": "NOT_ESTIMABLE",
        "status": "BLOCKED_IDENTITY_AND_PIT_NOT_PDF_COVERAGE",
        "runners": runners,
        "bet_authorized": False,
    }


def run(archive: Path, checksum: Path, day: str, output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="prewatch004b4-") as work:
        root = Path(work)
        coverage = make_feature_day_packs(archive, checksum, root / "features", day=day)
        identities = make_day_unresolved_report(
            archive, checksum, root / "identity.json", date_oslo=day
        )
        contexts = []
        for ref in coverage["files"]:
            content = (root / "features" / ref["filename"]).read_bytes()
            if digest(content) != ref["sha256"]:
                raise ValueError("004B4_ORIGINAL_FEATURE_SHA_MISMATCH")
            contexts.append(json.loads(content))
        result = select_race(contexts, identities)
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_once(
            output, (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                     + "\n").encode("utf-8")
        )
        return result


def main() -> None:
    p = argparse.ArgumentParser(description="004B4 original-bound one-race full field NO BET")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--checksum", type=Path, required=True)
    p.add_argument("--date-oslo", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = run(a.archive, a.checksum, a.date_oslo, a.output)
    print(json.dumps({k: v for k, v in result.items() if k != "runners"}, sort_keys=True))


if __name__ == "__main__":
    main()
