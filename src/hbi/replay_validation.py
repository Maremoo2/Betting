from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from hashlib import sha256

from .decision import DecisionPolicy
from .engine import CombinationPolicy, evaluate_race
from .storage import SQLiteStore


def _loads_map(value: object) -> dict[str, float] | None:
    if not isinstance(value, str) or not value:
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        return None
    return {str(key): float(item) for key, item in payload.items()}


def _close_maps(
    left: dict[str, float],
    right: dict[str, float],
    *,
    tolerance: float = 1e-12,
) -> bool:
    return set(left) == set(right) and all(
        math.isclose(left[key], right[key], rel_tol=0.0, abs_tol=tolerance)
        for key in left
    )


def run_runtime_replay_parity(store: SQLiteStore) -> dict[str, object]:
    decisions = {
        str(row["decision_run_id"]): row
        for row in store.fetch_table("shadow_decision_runs")
    }
    provenance = {
        str(row["decision_run_id"]): row
        for row in store.fetch_table("decision_provenance")
    }

    checked = 0
    skipped = 0
    mismatches: list[dict[str, object]] = []

    for decision_id, row in decisions.items():
        meta = provenance.get(decision_id)
        fundamental = _loads_map(row.get("fundamental_probabilities_json"))
        stored_combined = _loads_map(row.get("combined_probabilities_json"))
        if meta is None or fundamental is None or stored_combined is None:
            skipped += 1
            continue

        odds = _loads_map(meta.get("market_odds_json"))
        combination_raw = meta.get("combination_policy_json")
        decision_raw = meta.get("decision_policy_json")
        if odds is None or not isinstance(combination_raw, str) or not isinstance(
            decision_raw,
            str,
        ):
            skipped += 1
            continue

        combination_payload = json.loads(combination_raw)
        decision_payload = json.loads(decision_raw)
        result = evaluate_race(
            fundamental_probabilities=fundamental,
            market_decimal_odds=odds,
            executable_prices=odds,
            combination_policy=CombinationPolicy(
                fundamental_weight=float(combination_payload["fundamental_weight"]),
                market_weight=float(combination_payload["market_weight"]),
                material_conflict_threshold=float(
                    combination_payload["material_conflict_threshold"]
                ),
            ),
            decision_policy=DecisionPolicy(
                minimum_edge=float(decision_payload["minimum_edge"]),
                safety_margin=float(decision_payload["safety_margin"]),
            ),
        )
        checked += 1

        reasons: list[str] = []
        if not _close_maps(result.combined_probabilities, stored_combined):
            reasons.append("combined_probability_mismatch")
        stored_conflict = row.get("model_market_conflict_score")
        if stored_conflict is not None and not math.isclose(
            result.model_market_conflict_score,
            float(stored_conflict),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            reasons.append("conflict_score_mismatch")

        replay_status = (
            "SHADOW_BET"
            if any(item.decision.value == "BET" for item in result.assessments.values())
            else "PASS"
        )
        stored_status = str(row.get("decision_status"))
        if stored_status in {"SHADOW_BET", "PASS"} and replay_status != stored_status:
            reasons.append(
                f"decision_status_mismatch:{stored_status}:{replay_status}"
            )

        if reasons:
            mismatches.append(
                {
                    "decision_run_id": decision_id,
                    "race_id": row["race_id"],
                    "reasons": reasons,
                }
            )

    status = "FAIL" if mismatches else ("PASS" if checked else "NO_EVIDENCE")
    generated_at = datetime.now(UTC)
    report = {
        "schema_version": "HBI_RUNTIME_REPLAY_PARITY_V1",
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "checked_decisions": checked,
        "skipped_decisions": skipped,
        "mismatches": mismatches,
        "interpretation": (
            "NO_EVIDENCE means the audit is implemented but no provenance-complete "
            "frozen decision has accumulated yet."
        ),
    }
    audit_id = sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    store.insert_integrity_audit(
        {
            "audit_id": audit_id,
            "audit_type": "RUNTIME_REPLAY_PARITY",
            "generated_at_utc": generated_at.isoformat(),
            "status": status,
            "checked_rows": checked,
            "failures": len(mismatches),
            "warnings": skipped,
            "report_json": json.dumps(report, sort_keys=True),
            "github_sha": os.getenv("GITHUB_SHA"),
        }
    )
    return report
