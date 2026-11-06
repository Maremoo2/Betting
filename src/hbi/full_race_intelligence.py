"""Full-field race intelligence math; read-only and never a betting adapter.

Consumes immutable prestart runner predictions and source-labelled market observations.
This module neither estimates fundamental probabilities nor changes Champion/V3.3.12.
Incomplete fields cannot be promoted to BET, WATCH or PASS.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

SCHEMA = "FULL_RACE_INTELLIGENCE_SHADOW_V1"
FEATURES_UNMODELED = (
    "recent_5_starts", "recent_10_starts", "career_race_by_race",
    "race_times_margins", "surface_distance_start_method",
    "post_position_effect", "driver_and_trainer_changes",
    "gallop_disqualification_events", "recent_form_trend",
    "days_since_prior_start", "opponent_prior_strength",
    "direct_head_to_head", "opponent_later_results_asof",
    "class_adjusted_form", "verified_pace_sectionals",
)


def _prob(value: Any) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value) if 0 < value < 1 else None


def _odds(value: Any) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value) if value > 1 else None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.utcoffset() is not None else None


def _safe_round_stakes(
    odds: list[float], budget: float, quantum: float,
) -> list[float]:
    """Largest-remainder monetary simulation; not a provider's staking policy."""
    if (not odds or not math.isfinite(budget) or not math.isfinite(quantum)
            or budget <= 0 or quantum <= 0):
        raise ValueError("DUTCH_SIMULATION_INPUT_INVALID")
    units = round(budget / quantum)
    if not math.isclose(units * quantum, budget, abs_tol=1e-7, rel_tol=0):
        raise ValueError("DUTCH_BUDGET_NOT_MULTIPLE_OF_SIMULATION_UNIT")
    weights = [1.0 / o for o in odds]
    total = math.fsum(weights)
    exact = [units * w / total for w in weights]
    floors = [math.floor(v) for v in exact]
    remainder = units - sum(floors)
    order = sorted(range(len(floors)), key=lambda i: (-(exact[i]-floors[i]), i))
    for i in order[:remainder]:
        floors[i] += 1
    return [round(x * quantum, 10) for x in floors]


def _dutch_simulation(
    label: str,
    selected: list[dict],
    complete_active: list[dict],
    *,
    budget: float,
    quantum: float,
) -> dict:
    """Exact full-field outcome table and expectation from fundamental p(win).

    A valid arithmetic hypothetical does NOT imply market/PIT authority.
    """
    keyset = [str(r["selection_id"]) for r in selected]
    if len(keyset) < 2 or len(set(keyset)) != len(keyset):
        return {"name": label, "status": "NOT_CALCULABLE", "reason": "SET_NOT_TWO_UNIQUE_RUNNERS"}
    if any(_prob(r["p_win"]) is None for r in complete_active):
        return {"name": label, "status": "NOT_CALCULABLE", "reason": "NO_FULL_FIELD_FUNDAMENTAL_P_WIN"}
    selected_odds = [_odds(r.get("win_odds_raw")) for r in selected]
    if any(x is None for x in selected_odds):
        return {"name": label, "status": "NOT_CALCULABLE",
                "reason": "SET_HAS_UNQUOTED_OR_INVALID_WIN_ODDS",
                "unquoted": [str(r["selection_id"]) for r in selected
                             if _odds(r.get("win_odds_raw")) is None]}
    prices = [float(x) for x in selected_odds if x is not None]
    stakes = _safe_round_stakes(prices, budget, quantum)
    by_sel = dict(zip(keyset, zip(stakes, prices), strict=True))
    returns = {
        str(row["selection_id"]): (
            round(by_sel[str(row["selection_id"])][0] * by_sel[str(row["selection_id"])][1], 10)
            if str(row["selection_id"]) in by_sel else 0.0
        ) for row in complete_active
    }
    outcome_table = [
        {"selection_id": str(r["selection_id"]),
         "horse_name": r.get("horse_name"),
         "probability": r["p_win"],
         "net_if_wins": round(returns[str(r["selection_id"])] - budget, 10)}
        for r in complete_active
    ]
    gross_expected = math.fsum(
        row["probability"] * returns[row["selection_id"]]
        for row in outcome_table
    )
    hit = math.fsum(r["p_win"] for r in selected)
    ev_cash = gross_expected - budget
    # +5%/-5% scenario: original p is held fixed, no future odds substituted.
    sensitivity = {}
    for pct in (-0.05, 0.05):
        shifted = [max(1.000001, p * (1+pct)) for p in prices]
        moved_stakes = _safe_round_stakes(shifted, budget, quantum)
        moved_gross = math.fsum(
            r["p_win"] * moved_stakes[i] * shifted[i]
            for i, r in enumerate(selected)
        )
        sensitivity[f"{pct:+.0%}"] = round((moved_gross - budget) / budget, 10)
    return {
        "name": label, "status": "ARITHMETIC_RESEARCH_ONLY",
        "bet_authority": False, "stake_budget_nok_hypothetical": budget,
        "stake_rounding_quantum_simulation_not_provider": quantum,
        "actual_provider_minimum_and_rounding": "UNVERIFIED",
        "stakes": [
            {"selection_id": k, "horse_name": r.get("horse_name"),
             "odds_decimal": p, "stake_nok_hypothetical": s}
            for k, r, p, s in zip(keyset, selected, prices, stakes, strict=True)
        ],
        "net_if_each_active_horse_wins_nok": outcome_table,
        "probability_any_selected_wins": hit,
        "probability_total_loss": max(0., 1. - hit),
        "ev_nok_hypothetical": ev_cash,
        "ev_roi_hypothetical": ev_cash / budget,
        "odds_sensitivity_roi": sensitivity,
        "decision": "NOT_EXECUTABLE",
        "blockers": ["NO_BET_AUTHORITY", "UNVERIFIED_PROVIDER_STAKE_RULES"],
    }


def analyze_race(
    race: dict[str, Any], *,
    decision_time_utc: str,
    simulation_budget_nok: float = 100.,
    simulation_rounding_quantum_nok: float = 0.01,
) -> dict[str, Any]:
    """Analyze every active runner without altering externally supplied p(win).

    Caller must supply exact physical race_id, authentic SHA source receipts,
    and already-frozen p(win), if actually available. Never backfit a model.
    """
    if not isinstance(race, dict) or not isinstance(race.get("runners"), list):
        raise ValueError("RACE_AND_RUNNERS_REQUIRED")
    rid = race.get("physical_race_id")
    if not isinstance(rid, str) or not rid.startswith("RIKSTOTO:"):
        raise ValueError("PHYSICAL_RACE_ID_REQUIRED")
    clock = _time(decision_time_utc)
    start = _time(race.get("start_utc"))
    if clock is None or start is None:
        raise ValueError("SOURCE_AWARE_DECISION_AND_START_REQUIRED")
    prospective = clock < start
    rows = []
    for original in race["runners"]:
        if (not isinstance(original, dict)
                or type(original.get("scratched")) is not bool
                or not isinstance(original.get("selection_id"), str)
                or not original["selection_id"].isdecimal()
                or original["selection_id"].startswith("0")):
            raise ValueError("RUNNER_OR_IDENTITY_SCHEMA_INVALID")
        n = original["selection_id"]
        p = _prob(original.get("p_win_frozen"))
        odds = _odds(original.get("win_odds_raw"))
        rows.append({
            "selection_id": n,
            "horse_name": original.get("horse_name"),
            "scratched": original["scratched"],
            "rikstoto_registration": original.get("rikstoto_registration"),
            "atg_horse_id": original.get("atg_horse_id"),
            "identity_attested": original.get("identity_attested") is True,
            "history_source_sha256": original.get("history_source_sha256"),
            "historical_factors": {
                "lifetime_starts": original.get("lifetime_starts"),
                "lifetime_wins": original.get("lifetime_wins"),
                **{name: "MISSING" for name in FEATURES_UNMODELED},
            },
            "p_win": p, "fair_odds": 1/p if p is not None else None,
            "win_odds_raw": odds,
            "win_price_source_sha256": original.get("win_price_source_sha256"),
            "win_observed_at_utc": original.get("win_observed_at_utc"),
            "win_provider_updated_raw": original.get("win_provider_updated_raw"),
            "market_implied_p_unnormalized": 1/odds if odds else None,
            "research_ev_roi_arithmetic": p*odds-1 if p and odds else None,
            "collective_share_not_p_win": original.get("collective_share"),
            "minimum_frozen_bet_odds": original.get("minimum_frozen_bet_odds"),
            "data_quality": original.get("data_quality", "UNVERIFIED"),
            "model_status": "FROZEN_RESEARCH" if p is not None else "NOT_ASSESSED",
            "decision": "NOT_APPLICABLE" if original["scratched"] else "NOT_EXECUTABLE",
            "blockers": list(original.get("blockers") or []),
        })
    ids = [r["selection_id"] for r in rows]
    if len(ids) != len(set(ids)) or len(rows) < 2:
        raise ValueError("DUPLICATE_OR_EMPTY_PHYSICAL_FIELD")
    active = [r for r in rows if not r["scratched"]]
    if len(active) < 2:
        raise ValueError("INSUFFICIENT_ACTIVE_FIELD")
    probs = [r["p_win"] for r in active]
    model_full = (all(p is not None for p in probs)
                  and math.isclose(math.fsum(probs), 1., abs_tol=1e-9, rel_tol=0))
    if not model_full:
        for r in active:
            if "NO_COMPLETE_FROZEN_FULL_FIELD_P_WIN" not in r["blockers"]:
                r["blockers"].append("NO_COMPLETE_FROZEN_FULL_FIELD_P_WIN")
        # No partial model probability can be marketed as a full-field estimate.
        for r in active:
            r["p_win"] = r["fair_odds"] = r["research_ev_roi_arithmetic"] = None
            r["model_status"] = "NOT_ASSESSED"
    market_full = (len(active) == sum(r["win_odds_raw"] is not None for r in active)
                   and race.get("full_field_win_verified") is True)
    if not prospective:
        for r in active:
            r["blockers"].append("RACE_ALREADY_STARTED_AT_ANALYSIS_TIME")
    if not market_full:
        for r in active:
            r["blockers"].append("FULL_FIELD_WIN_MARKET_UNVERIFIED")
    if race.get("pit_certified") is not True:
        for r in active:
            r["blockers"].append("PIT_NOT_CERTIFIED")
    if any(not r["identity_attested"] for r in active):
        for r in active:
            r["blockers"].append("INDEPENDENT_IDENTITY_NOT_ATTESTED")
    for r in active:
        if r["win_odds_raw"] is not None and _time(r["win_observed_at_utc"]) is None:
            r["blockers"].append("WIN_SOURCE_CLOCK_NOT_VERIFIED_PER_RUNNER")
        t = _time(r["win_observed_at_utc"])
        if t is not None and t > clock:
            r["blockers"].append("WIN_SOURCE_AFTER_ANALYSIS_CUTOFF")
            r["win_odds_raw"] = None
            r["market_implied_p_unnormalized"] = None
            r["research_ev_roi_arithmetic"] = None

    full_price = [r for r in active if r["win_odds_raw"] is not None]
    priced_leader = (min(full_price, key=lambda r:(r["win_odds_raw"], r["selection_id"]))
                     if full_price else None)
    actual_win_favourite = priced_leader if market_full else None
    shares = [r for r in active if _prob(r["collective_share_not_p_win"]) is not None]
    share_favourite = (max(shares, key=lambda r:r["collective_share_not_p_win"])
                       if len(shares) == len(active) else None)
    candidates = []
    if model_full:
        exclusions = (actual_win_favourite or share_favourite or priced_leader)
        if exclusions:
            challengers = sorted(
                (r for r in active if r["selection_id"] != exclusions["selection_id"]),
                key=lambda r: (-r["p_win"], r["selection_id"]),
            )
            for size in (2, 3, 4):
                if len(challengers) >= size:
                    candidates.append(_dutch_simulation(
                        f"TOP_{size}_CHALLENGERS_BY_FROZEN_P",
                        challengers[:size], active, budget=simulation_budget_nok,
                        quantum=simulation_rounding_quantum_nok,
                    ))
            candidates.append(_dutch_simulation(
                "ALL_EXCEPT_REFERENCE_FAVOURITE", challengers, active,
                budget=simulation_budget_nok, quantum=simulation_rounding_quantum_nok,
            ))
        positive = sorted(
            (r for r in active if r["research_ev_roi_arithmetic"] is not None
             and r["research_ev_roi_arithmetic"] > 0),
            key=lambda r: (-r["research_ev_roi_arithmetic"], r["selection_id"]),
        )[:4]
        if len(positive) >= 2:
            candidates.append(_dutch_simulation(
                "TOP_UP_TO_FOUR_RESEARCH_POSITIVE_EV",
                positive, active, budget=simulation_budget_nok,
                quantum=simulation_rounding_quantum_nok,
            ))
    single = [
        r for r in active if r["research_ev_roi_arithmetic"] is not None
    ] if model_full else []
    best = max(single, key=lambda r:r["research_ev_roi_arithmetic"]) if single else None
    working_dutches = [c for c in candidates if c["status"] == "ARITHMETIC_RESEARCH_ONLY"]
    best_dutch = max(working_dutches, key=lambda x:x["ev_roi_hypothetical"]) if working_dutches else None
    def compact(row: dict | None) -> dict | None:
        return ({k: row.get(k) for k in ("selection_id", "horse_name", "p_win",
                                        "win_odds_raw", "research_ev_roi_arithmetic")}
                if row else None)
    return {
        "schema": SCHEMA, "physical_race_id": rid, "round_name":race.get("round_name"),
        "leg": race.get("leg"), "start_utc": start.isoformat(),
        "analysis_cutoff_utc":clock.isoformat(),
        "cutoff_before_start": prospective, "bet_authority": False,
        "frozen_model_version": race.get("model_version"),
        "frozen_model_run_id": race.get("model_run_id"),
        "source_original_sha256": race.get("source_original_sha256"),
        "source_model_sha256": race.get("source_model_sha256"),
        "model_calibration": "UNVALIDATED_SHADOW_V1_1",
        "active_count": len(active), "total_count": len(rows),
        "full_field_model_valid": model_full,
        "p_win_sum": math.fsum(probs) if model_full else None,
        "win_full_field_verified": market_full,
        "win_quote_count":len(full_price),
        "win_favourite": compact(actual_win_favourite),
        "win_quoted_leader_provisional": (
            compact(priced_leader) if not market_full else None),
        "collective_favourite_separate": {
            **(compact(share_favourite) or {}),
            "share":share_favourite["collective_share_not_p_win"],
        } if share_favourite else None,
        "anti_favourite": {
            "reference": ("WIN_CERTIFIED" if actual_win_favourite else
                          "COLLECTIVE_SEPARATE" if share_favourite else
                          "QUOTED_WIN_LEADER_UNVERIFIED" if priced_leader else "UNAVAILABLE"),
            "reference_horse": compact(actual_win_favourite or share_favourite or priced_leader),
            "p_favourite_loses": (
                1-(actual_win_favourite or share_favourite or priced_leader)["p_win"]
                if model_full and (actual_win_favourite or share_favourite or priced_leader)
                else None),
            "can_confirm_overpriced_favourite": False,
            "reason": "NO_COMPLETE_CALIBRATED_PIT_AND_WIN_MARKET",
        },
        "best_single_win_research_only":compact(best),
        "dutching_scenarios": candidates,
        "best_dutch_research_only": (
            {"name":best_dutch["name"],"hypothetical_ev_roi":best_dutch["ev_roi_hypothetical"]}
            if best_dutch else None),
        "runners": rows, "decision":"NOT_EXECUTABLE",
        "hardgate_blockers": sorted(set(
            (["RACE_ALREADY_STARTED_AT_ANALYSIS_TIME"] if not prospective else [])
            + (["NO_COMPLETE_FROZEN_FULL_FIELD_P_WIN"] if not model_full else [])
            + (["FULL_FIELD_WIN_MARKET_UNVERIFIED"] if not market_full else [])
            + (["PIT_NOT_CERTIFIED"] if race.get("pit_certified") is not True else [])
            + (["INDEPENDENT_IDENTITY_NOT_ATTESTED"]
               if any(not r["identity_attested"] for r in active) else [])
            + ["BET_AUTHORITY_FALSE", "PROVIDER_MINIMUM_STAKE_UNVERIFIED"]
        )),
        "no_bet": True, "v85_system_ev": "NOT_ESTABLISHED",
        "no_autobet": True,
    }
