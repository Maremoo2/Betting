from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from .contender_gate import Contender, Pricing, Quote, review_contenders
from .decision import DecisionPolicy
from .domain import Decision
from .eligibility import evaluate_win_eligibility
from .engine import CombinationPolicy, evaluate_race
from .probability import normalize_market_odds
from .provider_capability import full_field_gate
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
    combined: dict[str, float] | None = None,
    conflict: float | None = None,
    ticket_count: int = 0,
) -> None:
    actual_minutes, latency = _timing(
        race_start_at,
        decision_time,
        policy.target_minutes_to_start,
    )
    store.insert_shadow_decision_run(
        {
            "decision_run_id": _decision_run_id(
                race_id,
                "V",
                policy.model_version,
                policy.target_minutes_to_start,
            ),
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

    gate_reason = full_field_gate(
        store, race_id, store.latest_runner_fundamentals(race_id, before=current), current,
    )
    if gate_reason:
        _persist_decision_run(
            store, race_id=race_id, raceday_key=provider_raceday_key,
            race_start_at=race_start_at, decision_time=current, policy=rules,
            status="NOT_EXECUTABLE", reason=gate_reason,
        )
        return ShadowRunResult(race_id, 0, "NOT_EXECUTABLE", gate_reason)

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
    if race_id.startswith("RIKSTOTO:"):
        cohort = store.latest_runner_fundamentals(race_id, before=current)
        feature_time = max((r["feature_as_of_utc"] for r in cohort
                            if not r.get("scratched")), default=None)
        if fundamental_run is None or fundamental_run["feature_as_of_utc"] != feature_time:
            reason = "FULL_FIELD_ONLY_MODEL_COHORT_MISMATCH"
            _persist_decision_run(
                store, race_id=race_id, raceday_key=provider_raceday_key,
                race_start_at=race_start_at, decision_time=current, policy=rules,
                status="NOT_EXECUTABLE", reason=reason,
            )
            return ShadowRunResult(race_id, 0, "NOT_EXECUTABLE", reason)
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
    if race_id.startswith("RIKSTOTO:") and fundamental_run is not None:
        # Use exactly the gated model cohort, never per-runner predictions from mixed runs.
        fundamental = json.loads(str(fundamental_run["probabilities_json"]))
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

    try:
        market_observed_at = datetime.fromisoformat(source_market_time)
    except ValueError:
        market_observed_at = None

    eligibility = evaluate_win_eligibility(
        decision_time=current,
        race_start_time=race_start_at,
        market_observed_at=market_observed_at,
        fundamental_shadow_eligible=(
            fundamental_run is None or bool(fundamental_run["shadow_eligible"])
        ),
        fundamental_selections=set(fundamental),
        market_selections=set(market_odds),
    )
    if not eligibility.allowed:
        reason = "|".join(eligibility.reasons)
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
    contender_report = review_contenders(
        contenders=[Contender(selection, winner_odds=odds)
                    for selection, odds in market_odds.items()],
        pricing={selection: Pricing(
            p_win=a.probability, fair_odds=a.fair_odds,
            minimum_odds=max(a.minimum_price, (1 + rules.minimum_edge) / a.probability),
            decision=a.decision.value, priced_at=current,
        ) for selection, a in evaluated.assessments.items()},
        latest_quotes={str(row["selection_key"]): Quote(
            float(row["odds_decimal"]), datetime.fromisoformat(str(row["observed_at_utc"])),
        ) for row in rows if str(row["selection_key"]) in market_odds},
        decision_time=current, race_start=race_start_at,
    )
    store.insert_provider_payload(
        payload_id=f"contender:{frozen_id}", provider="hbi",
        category="CONTENDER_GATE_V2_1", provider_raceday_key=provider_raceday_key,
        observed_at=current, source_uri=f"hbi:shadow:{frozen_id}", product="V",
        payload={"race_id": race_id, "decision_run_id": frozen_id,
                 **contender_report.to_dict()},
    )
    if not contender_report.allowed:
        reason = "|".join(contender_report.errors)
        _persist_decision_run(
            store, race_id=race_id, raceday_key=provider_raceday_key,
            race_start_at=race_start_at, decision_time=current, policy=rules,
            status="NOT_EXECUTABLE", reason=reason,
        )
        return ShadowRunResult(race_id, 0, "NOT_EXECUTABLE", reason)
    executable_selections = {
        row["selection"] for row in contender_report.runners
        if row["pricing"] and row["pricing"]["decision"] == Decision.BET
    }
    candidates = [
        (selection, assessment)
        for selection, assessment in evaluated.assessments.items()
        if selection in executable_selections
    ]
    candidates.sort(key=lambda item: item[1].expected_value, reverse=True)
    candidates = candidates[: rules.max_win_bets_per_race]

    if not candidates:
        status = "WATCH" if contender_report.winner_status == "WATCH" else "PASS"
        reason = "CONTENDERS_AWAIT_PRICE_OR_REVIEW" if status == "WATCH" else "NO_VALUE_BET"
        _persist_decision_run(
            store,
            race_id=race_id,
            raceday_key=provider_raceday_key,
            race_start_at=race_start_at,
            decision_time=current,
            policy=rules,
            status=status,
            reason=reason,
            fundamental_model_version=fundamental_model_version,
            source_market_observed_at=source_market_time,
            fundamental=evaluated.fundamental_probabilities,
            market=evaluated.market_probabilities,
            combined=evaluated.combined_probabilities,
            conflict=evaluated.model_market_conflict_score,
        )
        return ShadowRunResult(
            race_id=race_id,
            created=0,
            status=status,
            reason=reason,
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
