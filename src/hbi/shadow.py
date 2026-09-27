from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from .decision import DecisionPolicy
from .domain import Decision
from .engine import CombinationPolicy, evaluate_race
from .storage import SQLiteStore


@dataclass(frozen=True)
class ShadowPolicy:
    """Research-only shadow execution policy.

    Defaults are a baseline for paper trading, not validated production parameters.
    They must never be reused for real-money execution without prospective validation.
    """

    model_version: str = "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL"
    fundamental_layer: str = "FUNDAMENTAL"
    fundamental_weight: float = 1.0
    market_weight: float = 1.0
    material_conflict_threshold: float = 20.0
    minimum_edge: float = 0.05
    safety_margin: float = 0.05
    single_win_stake_nok: float = 25.0
    target_minutes_to_start: float = 4.0
    max_win_bets_per_race: int = 1


@dataclass(frozen=True)
class ShadowRunResult:
    race_id: str
    created: int
    status: str
    reason: str | None = None


def _dedupe_key(race_id: str, product: str, selection: str, model_version: str) -> str:
    return sha256(f"{race_id}|{product}|{selection}|{model_version}".encode()).hexdigest()


def run_win_shadow_decision(
    store: SQLiteStore,
    *,
    race_id: str,
    provider_raceday_key: str,
    race_start_at: datetime,
    decision_time: datetime | None = None,
    policy: ShadowPolicy | None = None,
) -> ShadowRunResult:
    current = decision_time or datetime.now(UTC)
    rules = policy or ShadowPolicy()
    rows = store.latest_provider_market(race_id, "V")
    if not rows:
        return _record_not_executable(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            decision_time=current,
            race_start_at=race_start_at,
            policy=rules,
            reason="NO_WIN_MARKET_SNAPSHOT",
        )

    market_odds = {
        str(row["selection_key"]): float(row["odds_decimal"])
        for row in rows
        if row.get("odds_decimal") is not None and float(row["odds_decimal"]) > 1
    }
    fundamental_run = store.latest_fundamental_model_run(race_id, before=current)
    if fundamental_run is not None and not bool(fundamental_run["shadow_eligible"]):
        reason = str(fundamental_run.get("reason") or "FUNDAMENTAL_NOT_SHADOW_ELIGIBLE")
        return _record_not_executable(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            decision_time=current,
            race_start_at=race_start_at,
            policy=rules,
            reason=reason,
        )

    fundamental = store.latest_predictions(
        race_id,
        layer=rules.fundamental_layer,
        before=current,
    )
    if not fundamental:
        return _record_not_executable(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            decision_time=current,
            race_start_at=race_start_at,
            policy=rules,
            reason="NO_FUNDAMENTAL_PREDICTIONS",
        )

    common = set(market_odds) & set(fundamental)
    if len(common) != len(market_odds) or len(common) != len(fundamental):
        return _record_not_executable(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            decision_time=current,
            race_start_at=race_start_at,
            policy=rules,
            reason="INCOMPLETE_FULL_FIELD_ALIGNMENT",
        )

    evaluated = evaluate_race(
        fundamental_probabilities=fundamental,
        market_decimal_odds=market_odds,
        executable_prices=market_odds,
        combination_policy=CombinationPolicy(
            fundamental_weight=rules.fundamental_weight,
            market_weight=rules.market_weight,
            material_conflict_threshold=rules.material_conflict_threshold,
        ),
        decision_policy=DecisionPolicy(
            minimum_edge=rules.minimum_edge,
            safety_margin=rules.safety_margin,
        ),
    )
    candidates = [
        (selection, assessment)
        for selection, assessment in evaluated.assessments.items()
        if assessment.decision == Decision.BET
    ]
    candidates.sort(key=lambda item: item[1].expected_value, reverse=True)
    candidates = candidates[: rules.max_win_bets_per_race]

    if not candidates:
        return ShadowRunResult(race_id=race_id, created=0, status="PASS", reason="NO_VALUE_BET")

    actual_minutes = (race_start_at - current).total_seconds() / 60
    ideal_time = race_start_at - timedelta(minutes=rules.target_minutes_to_start)
    latency = (current - ideal_time).total_seconds()
    snapshot_time = str(rows[0]["observed_at_utc"])

    created = 0
    for selection, assessment in candidates:
        ticket = {
            "ticket_id": str(uuid4()),
            "dedupe_key": _dedupe_key(
                race_id,
                "V",
                selection,
                rules.model_version,
            ),
            "created_at_utc": current.isoformat(),
            "decision_time_utc": current.isoformat(),
            "race_id": race_id,
            "provider": "rikstoto",
            "provider_raceday_key": provider_raceday_key,
            "product": "V",
            "decision": "BET",
            "status": "SHADOW_BET",
            "selections_json": json.dumps([selection]),
            "stake_nok": rules.single_win_stake_nok,
            "row_price_nok": None,
            "number_of_rows": 1,
            "available_price": assessment.available_price,
            "fair_odds": assessment.fair_odds,
            "estimated_edge": assessment.edge_over_fair,
            "expected_value": assessment.expected_value,
            "model_version": rules.model_version,
            "source_snapshot_time_utc": snapshot_time,
            "target_minutes_to_start": rules.target_minutes_to_start,
            "actual_minutes_to_start": actual_minutes,
            "execution_latency_seconds": latency,
            "reject_reason": assessment.reject_reason,
            "notes": (
                "Paper bet only. Equal log-pool combination is an explicitly "
                "unvalidated shadow baseline."
            ),
        }
        created += int(store.create_shadow_ticket(ticket))
    return ShadowRunResult(race_id=race_id, created=created, status="SHADOW_BET")


def _record_not_executable(
    store: SQLiteStore,
    *,
    race_id: str,
    raceday_key: str,
    decision_time: datetime,
    race_start_at: datetime,
    policy: ShadowPolicy,
    reason: str,
) -> ShadowRunResult:
    key = _dedupe_key(race_id, "V", f"NONE:{reason}", policy.model_version)
    created = store.create_shadow_ticket(
        {
            "ticket_id": str(uuid4()),
            "dedupe_key": key,
            "created_at_utc": decision_time.isoformat(),
            "decision_time_utc": decision_time.isoformat(),
            "race_id": race_id,
            "provider": "rikstoto",
            "provider_raceday_key": raceday_key,
            "product": "V",
            "decision": "PASS",
            "status": "NOT_EXECUTABLE",
            "selections_json": "[]",
            "stake_nok": 0.0,
            "row_price_nok": None,
            "number_of_rows": 0,
            "available_price": None,
            "fair_odds": None,
            "estimated_edge": None,
            "expected_value": None,
            "model_version": policy.model_version,
            "source_snapshot_time_utc": None,
            "target_minutes_to_start": policy.target_minutes_to_start,
            "actual_minutes_to_start": (
                race_start_at - decision_time
            ).total_seconds()
            / 60,
            "execution_latency_seconds": (
                decision_time
                - (race_start_at - timedelta(minutes=policy.target_minutes_to_start))
            ).total_seconds(),
            "reject_reason": reason,
            "notes": "No shadow stake was simulated.",
        }
    )
    return ShadowRunResult(
        race_id=race_id,
        created=int(created),
        status="NOT_EXECUTABLE",
        reason=reason,
    )
