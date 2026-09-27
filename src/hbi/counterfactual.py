from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256

from .decision import DecisionPolicy
from .domain import Decision
from .engine import CombinationPolicy, evaluate_race
from .storage import SQLiteStore


@dataclass(frozen=True)
class CounterfactualHypothesis:
    name: str
    fundamental_weight: float
    market_weight: float
    material_conflict_threshold: float
    minimum_edge: float
    safety_margin: float
    stake_nok: float = 25.0
    max_bets_per_race: int = 1


def _loads_map(value: object) -> dict[str, float] | None:
    if not isinstance(value, str) or not value:
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        return None
    return {str(key): float(item) for key, item in payload.items()}


def evaluate_counterfactual(
    store: SQLiteStore,
    *,
    decision_run_id: str,
    hypothesis: CounterfactualHypothesis,
    created_at: datetime | None = None,
) -> dict[str, object]:
    decisions = {
        str(row["decision_run_id"]): row
        for row in store.fetch_table("shadow_decision_runs")
    }
    provenance = {
        str(row["decision_run_id"]): row
        for row in store.fetch_table("decision_provenance")
    }
    decision = decisions.get(decision_run_id)
    meta = provenance.get(decision_run_id)
    if decision is None:
        raise KeyError(f"unknown decision run {decision_run_id}")
    if meta is None:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "MISSING_DECISION_PROVENANCE",
            "research_only": True,
            "execution_authority": False,
        }

    fundamental = _loads_map(decision.get("fundamental_probabilities_json"))
    odds = _loads_map(meta.get("market_odds_json"))
    if fundamental is None or odds is None or set(fundamental) != set(odds):
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "MISSING_OR_MISALIGNED_FROZEN_INPUTS",
            "research_only": True,
            "execution_authority": False,
        }

    evaluated = evaluate_race(
        fundamental_probabilities=fundamental,
        market_decimal_odds=odds,
        executable_prices=odds,
        combination_policy=CombinationPolicy(
            fundamental_weight=hypothesis.fundamental_weight,
            market_weight=hypothesis.market_weight,
            material_conflict_threshold=hypothesis.material_conflict_threshold,
        ),
        decision_policy=DecisionPolicy(
            minimum_edge=hypothesis.minimum_edge,
            safety_margin=hypothesis.safety_margin,
        ),
    )
    bets = [
        (selection, assessment)
        for selection, assessment in evaluated.assessments.items()
        if assessment.decision == Decision.BET
    ]
    bets.sort(key=lambda item: item[1].expected_value, reverse=True)
    bets = bets[: hypothesis.max_bets_per_race]

    outcomes = {
        str(row["race_id"]): str(row["winner_selection_id"])
        for row in store.fetch_table("outcomes")
    }
    winner = outcomes.get(str(decision["race_id"]))
    hypothetical_pnl: float | None = None
    if winner is not None:
        hypothetical_pnl = 0.0
        for selection, assessment in bets:
            gross = (
                hypothesis.stake_nok * assessment.available_price
                if selection == winner
                else 0.0
            )
            hypothetical_pnl += gross - hypothesis.stake_nok

    result = {
        "status": "EVALUATED",
        "race_id": decision["race_id"],
        "source_decision_run_id": decision_run_id,
        "hypothesis": asdict(hypothesis),
        "selections": [selection for selection, _ in bets],
        "bet_count": len(bets),
        "combined_probabilities": evaluated.combined_probabilities,
        "model_market_conflict_score": evaluated.model_market_conflict_score,
        "winner_selection_id": winner,
        "hypothetical_pnl_nok": hypothetical_pnl,
        "research_only": True,
        "execution_authority": False,
    }
    timestamp = created_at or datetime.now(UTC)
    counterfactual_id = sha256(
        f"{decision_run_id}|{hypothesis.name}".encode()
    ).hexdigest()
    store.upsert_counterfactual_run(
        {
            "counterfactual_id": counterfactual_id,
            "race_id": decision["race_id"],
            "source_decision_run_id": decision_run_id,
            "created_at_utc": timestamp.isoformat(),
            "hypothesis_name": hypothesis.name,
            "hypothesis_json": json.dumps(asdict(hypothesis), sort_keys=True),
            "result_json": json.dumps(result, sort_keys=True),
            "research_only": 1,
            "execution_authority": 0,
        }
    )
    return result
