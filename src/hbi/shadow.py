from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from .decision import DecisionPolicy
from .domain import Decision
from .eligibility import evaluate_win_eligibility
from .engine import CombinationPolicy, evaluate_race
from .governance import governance_hash, load_governance
from .probability import normalize_market_odds
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
GOVERNANCE_PATH = ROOT / "docs" / "research_governance.json"


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


def _decision_run_id(race_id: str, product: str, model_version: str, target: float) -> str:
    return sha256(f"{race_id}|{product}|{model_version}|T-{target:g}".encode()).hexdigest()


def _timing(
    race_start_at: datetime,
    decision_time: datetime,
    target_minutes: float,
) -> tuple[float, float]:
    actual_minutes = (race_start_at - decision_time).total_seconds() / 60
    ideal_time = race_start_at - timedelta(minutes=target_minutes)
    latency = (decision_time - ideal_time).total_seconds()
    return actual_minutes, latency


def _persist_decision_run(
    store: SQLiteStore,
    *,
    race_id: str,
    raceday_key: str,
    race_start_at: datetime,
    decision_time: datetime,
    policy: ShadowPolicy,
    status: str,
    reason: str | None,
    fundamental_model_version: str | None = None,
    source_market_observed_at: str | None = None,
    fundamental: dict[str, float] | None = None,
    market: dict[str, float] | None = None,
    market_odds: dict[str, float] | None = None,
    combined: dict[str, float] | None = None,
    conflict: float | None = None,
    ticket_count: int = 0,
) -> None:
    actual_minutes, latency = _timing(
        race_start_at,
        decision_time,
        policy.target_minutes_to_start,
    )
    decision_run_id = _decision_run_id(
        race_id,
        "V",
        policy.model_version,
        policy.target_minutes_to_start,
    )
    store.insert_shadow_decision_run(
        {
            "decision_run_id": decision_run_id,
            "race_id": race_id,
            "provider_raceday_key": raceday_key,
            "product": "V",
            "created_at_utc": decision_time.isoformat(),
            "race_start_time_utc": race_start_at.isoformat(),
            "decision_status": status,
            "reason": reason,
            "shadow_model_version": policy.model_version,
            "fundamental_model_version": fundamental_model_version,
            "source_market_observed_at_utc": source_market_observed_at,
            "target_minutes_to_start": policy.target_minutes_to_start,
            "actual_minutes_to_start": actual_minutes,
            "execution_latency_seconds": latency,
            "field_size": (
                len(fundamental)
                if fundamental
                else len(market) if market else None
            ),
            "fundamental_probabilities_json": (
                None if fundamental is None else json.dumps(fundamental, sort_keys=True)
            ),
            "market_probabilities_json": (
                None if market is None else json.dumps(market, sort_keys=True)
            ),
            "combined_probabilities_json": (
                None if combined is None else json.dumps(combined, sort_keys=True)
            ),
            "model_market_conflict_score": conflict,
            "ticket_count": ticket_count,
        }
    )
    governance = load_governance(GOVERNANCE_PATH)
    store.upsert_decision_provenance(
        {
            "decision_run_id": decision_run_id,
            "market_odds_json": (
                None if market_odds is None else json.dumps(market_odds, sort_keys=True)
            ),
            "combination_policy_json": json.dumps(
                {
                    "fundamental_weight": policy.fundamental_weight,
                    "market_weight": policy.market_weight,
                    "material_conflict_threshold": policy.material_conflict_threshold,
                },
                sort_keys=True,
            ),
            "decision_policy_json": json.dumps(
                {
                    "minimum_edge": policy.minimum_edge,
                    "safety_margin": policy.safety_margin,
                    "single_win_stake_nok": policy.single_win_stake_nok,
                    "max_win_bets_per_race": policy.max_win_bets_per_race,
                },
                sort_keys=True,
            ),
            "code_sha": os.getenv("GITHUB_SHA"),
            "governance_hash": governance_hash(governance),
            "recorded_at_utc": decision_time.isoformat(),
        }
    )


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
    frozen_id = _decision_run_id(
        race_id,
        "V",
        rules.model_version,
        rules.target_minutes_to_start,
    )
    existing = store.get_shadow_decision_run(frozen_id)
    if existing is not None:
        return ShadowRunResult(
            race_id=race_id,
            created=0,
            status=str(existing["decision_status"]),
            reason=(
                None
                if existing.get("reason") is None
                else str(existing.get("reason"))
            ),
        )

    rows = store.latest_provider_market(race_id, "V")
    if not rows:
        _persist_decision_run(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            race_start_at=race_start_at,
            decision_time=current,
            policy=rules,
            status="NOT_EXECUTABLE",
            reason="NO_WIN_MARKET_SNAPSHOT",
        )
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
    market = normalize_market_odds(market_odds) if market_odds else None
    source_market_time = str(rows[0]["observed_at_utc"])

    fundamental_run = store.latest_fundamental_model_run(race_id, before=current)
    fundamental_model_version = (
        None
        if fundamental_run is None
        else str(fundamental_run.get("model_version") or "") or None
    )
    if fundamental_run is not None and not bool(fundamental_run["shadow_eligible"]):
        reason = str(
            fundamental_run.get("reason") or "FUNDAMENTAL_NOT_SHADOW_ELIGIBLE"
        )
        raw_probabilities = fundamental_run.get("probabilities_json")
        fundamental = (
            json.loads(str(raw_probabilities))
            if raw_probabilities
            else None
        )
        _persist_decision_run(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            race_start_at=race_start_at,
            decision_time=current,
            policy=rules,
            status="NOT_EXECUTABLE",
            reason=reason,
            fundamental_model_version=fundamental_model_version,
            source_market_observed_at=source_market_time,
            fundamental=fundamental,
            market=market,
            market_odds=market_odds,
        )
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
        _persist_decision_run(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            race_start_at=race_start_at,
            decision_time=current,
            policy=rules,
            status="NOT_EXECUTABLE",
            reason="NO_FUNDAMENTAL_PREDICTIONS",
            fundamental_model_version=fundamental_model_version,
            source_market_observed_at=source_market_time,
            market=market,
            market_odds=market_odds,
        )
        return _record_not_executable(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            decision_time=current,
            race_start_at=race_start_at,
            policy=rules,
            reason="NO_FUNDAMENTAL_PREDICTIONS",
        )

    gate = evaluate_win_eligibility(
        decision_time=current,
        race_start_time=race_start_at,
        market_observed_at=datetime.fromisoformat(source_market_time),
        fundamental_shadow_eligible=True,
        fundamental_selections=set(fundamental),
        market_selections=set(market_odds),
    )
    if not gate.allowed:
        reason = gate.reasons[0]
        _persist_decision_run(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            race_start_at=race_start_at,
            decision_time=current,
            policy=rules,
            status="NOT_EXECUTABLE",
            reason=reason,
            fundamental_model_version=fundamental_model_version,
            source_market_observed_at=source_market_time,
            fundamental=fundamental,
            market=market,
            market_odds=market_odds,
        )
        return _record_not_executable(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            decision_time=current,
            race_start_at=race_start_at,
            policy=rules,
            reason=reason,
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
        _persist_decision_run(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            race_start_at=race_start_at,
            decision_time=current,
            policy=rules,
            status="PASS",
            reason="NO_VALUE_BET",
            fundamental_model_version=fundamental_model_version,
            source_market_observed_at=source_market_time,
            fundamental=evaluated.fundamental_probabilities,
            market=evaluated.market_probabilities,
            market_odds=market_odds,
            combined=evaluated.combined_probabilities,
            conflict=evaluated.model_market_conflict_score,
        )
        return ShadowRunResult(
            race_id=race_id,
            created=0,
            status="PASS",
            reason="NO_VALUE_BET",
        )

    actual_minutes, latency = _timing(
        race_start_at,
        current,
        rules.target_minutes_to_start,
    )
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
            "source_snapshot_time_utc": source_market_time,
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

    _persist_decision_run(
        store,
        race_id=race_id,
        raceday_key=provider_raceday_key,
        race_start_at=race_start_at,
        decision_time=current,
        policy=rules,
        status="SHADOW_BET",
        reason=None,
        fundamental_model_version=fundamental_model_version,
        source_market_observed_at=source_market_time,
        fundamental=evaluated.fundamental_probabilities,
        market=evaluated.market_probabilities,
        combined=evaluated.combined_probabilities,
        conflict=evaluated.model_market_conflict_score,
        ticket_count=created,
    )
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
