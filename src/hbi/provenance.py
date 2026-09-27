from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .governance import governance_hash, load_governance
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
GOVERNANCE = ROOT / "docs" / "research_governance.json"


def record_decision_provenance(
    store: SQLiteStore,
    *,
    race_id: str,
    shadow_model_version: str,
    target_minutes_to_start: float,
    policy: dict[str, Any],
    recorded_at: datetime,
) -> str | None:
    decisions = [
        row
        for row in store.fetch_table("shadow_decision_runs")
        if str(row.get("race_id")) == race_id
        and str(row.get("product")) == "V"
        and str(row.get("shadow_model_version")) == shadow_model_version
        and float(row.get("target_minutes_to_start") or -1)
        == float(target_minutes_to_start)
    ]
    if not decisions:
        return None
    decisions.sort(
        key=lambda row: str(row.get("created_at_utc") or ""),
        reverse=True,
    )
    decision = decisions[0]

    market_rows = store.latest_provider_market(race_id, "V")
    odds = {
        str(row["selection_key"]): float(row["odds_decimal"])
        for row in market_rows
        if row.get("odds_decimal") is not None and float(row["odds_decimal"]) > 1
    }
    governance = load_governance(GOVERNANCE)
    store.upsert_decision_provenance(
        {
            "decision_run_id": decision["decision_run_id"],
            "market_odds_json": (
                None if not odds else json.dumps(odds, sort_keys=True)
            ),
            "combination_policy_json": json.dumps(
                {
                    "fundamental_weight": policy["fundamental_weight"],
                    "market_weight": policy["market_weight"],
                    "material_conflict_threshold": policy[
                        "material_conflict_threshold"
                    ],
                },
                sort_keys=True,
            ),
            "decision_policy_json": json.dumps(
                {
                    "minimum_edge": policy["minimum_edge"],
                    "safety_margin": policy["safety_margin"],
                    "single_win_stake_nok": policy["single_win_stake_nok"],
                    "max_win_bets_per_race": policy["max_win_bets_per_race"],
                },
                sort_keys=True,
            ),
            "code_sha": os.getenv("GITHUB_SHA"),
            "governance_hash": governance_hash(governance),
            "recorded_at_utc": recorded_at.isoformat(),
        }
    )
    return str(decision["decision_run_id"])
