"""Frozen V3.3 decision support; no database writes or wager execution."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from math import isclose, isfinite, prod

from . import ACTIVE_STANDARD

# Freeze before outcomes. Robustness means passing ALL four sensitivity corners.
# Borderline means passing ANY corner but not all, including the core threshold.
POLICY = {
    "version": ACTIVE_STANDARD,
    "delta": 0.05, "ratio_pos": 1.25, "ratio_neg": 0.75,
    "sensitivity_delta": [0.04, 0.06],
    "sensitivity_ratio_pos": [1.20, 1.30],
    "sensitivity_ratio_neg": [0.70, 0.80],
    "max_age_seconds": 120, "max_pool_skew_seconds": 60,
    "late_window_seconds": 300, "unit_nok": 25,
    "full_field_review_gate": "FFQ-1", "all_runner_cut_reasons": True,
    "explicit_multi_race_budget": True,
}
POLICY_HASH = sha256(json.dumps(POLICY, sort_keys=True).encode()).hexdigest()

# Screening categories are independent of price and public support.
REVIEW_STATUSES = {"QUALIFIED", "CASE_PASS", "DATA_MISSING"}
REVIEW_FACTORS = {
    "FORM", "CLASS", "DRAW", "RACE_SHAPE", "DRIVER_TRAINER",
    "DISTANCE", "GALLOP_RISK", "EQUIPMENT", "DATA_QUALITY", "OTHER",
}


def validate_field_review(case, *, product):
    """Fail closed if any runner has only a bare flag or generic unexplained PASS."""
    if type(case.get("qualified")) is not bool:
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:qualified")
    reason = case.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 18:
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:specific_reason")
    review = case.get("field_review")
    if not isinstance(review, dict):
        raise TypeError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:missing_audit")
    status = review.get("status")
    if status not in REVIEW_STATUSES:
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:status")
    if case["qualified"] != (status == "QUALIFIED"):
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:qualification_conflict")
    factors = review.get("checked_factors")
    if (not isinstance(factors, list) or len(factors) < 2
            or len(set(map(str, factors))) != len(factors)
            or any(not isinstance(factor, str) or factor not in REVIEW_FACTORS
                   for factor in factors)):
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:checked_factors")
    refs = review.get("source_refs")
    if (not isinstance(refs, list) or not refs
            or any(not isinstance(ref, str) or len(ref.strip()) < 8 for ref in refs)):
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:source_refs")
    if review.get("market_free") is not True:
        raise ValueError(f"FULL_FIELD_REVIEW_REQUIRED:{product}:market_free")
    return deepcopy(review)


def ranked_win_candidates(rows):
    """Compare every independent WIN case; rank conditional lower-bound EV, not winners."""
    candidates = [
        {"selection": key, "decision": row["WIN"]["decision"],
         "conservative_ev": row["WIN"]["p_low"] * row["WIN"]["available_odds"] - 1,
         "minimum_price": row["WIN"]["minimum_price"],
         "available_odds": row["WIN"]["available_odds"]}
        for key, row in rows.items() if row["WIN"]["decision"] != "CASE_PASS"
    ]
    return sorted(candidates, key=lambda item: (-item["conservative_ev"], item["selection"]))


def number(value, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("finite numeric input required")
    if value < low or (high is not None and value > high):
        raise ValueError("numeric input out of range")
    return float(value)


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return result


def normalize(values, field, *, odds=False):
    if set(values) != set(field):
        raise ValueError("FULL_FIELD_ONLY: market field mismatch")
    raw = {key: number(value) for key, value in values.items()}
    if odds:
        if any(value <= 1 for value in raw.values()):
            raise ValueError("decimal odds must exceed 1")
        raw = {key: 1 / value for key, value in raw.items()}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("empty market mass")
    return {key: value / total for key, value in raw.items()}


def distribution(values, field, *, place_count=None):
    if set(values) != set(field):
        raise ValueError("FULL_FIELD_ONLY: probability field mismatch")
    result = {}
    for key, row in values.items():
        lo, mid, hi = (number(row[name], 0, 1) for name in ("p_low", "p_mid", "p_high"))
        if not 0 < lo <= mid <= hi <= 1:
            raise ValueError("ordered nonzero probability bounds required")
        result[key] = {"p_low": lo, "p_mid": mid, "p_high": hi}
    target = place_count or 1
    if not isclose(sum(row["p_mid"] for row in result.values()), target, abs_tol=1e-6):
        raise ValueError("incoherent full-field midpoint mass")
    if sum(row["p_low"] for row in result.values()) > target + 1e-6:
        raise ValueError("incoherent lower probability mass")
    if sum(row["p_high"] for row in result.values()) < target - 1e-6:
        raise ValueError("incoherent upper probability mass")
    return result


def divergence(p_col, p_win):
    delta, ratio = p_col - p_win, p_col / p_win
    positive = delta >= POLICY["delta"] - 1e-12 and ratio >= POLICY["ratio_pos"] - 1e-12
    negative = delta <= -POLICY["delta"] + 1e-12 and ratio <= POLICY["ratio_neg"] + 1e-12
    corners = [
        delta >= d - 1e-12 and ratio >= r - 1e-12
        for d in POLICY["sensitivity_delta"] for r in POLICY["sensitivity_ratio_pos"]
    ] + [
        delta <= -d + 1e-12 and ratio <= r + 1e-12
        for d in POLICY["sensitivity_delta"] for r in POLICY["sensitivity_ratio_neg"]
    ]
    robust = all(corners[:4]) or all(corners[4:])
    return {"pCOL": p_col, "pWIN": p_win, "delta": delta, "ratio": ratio,
            "signal": "STRONG_POS" if positive else "STRONG_NEG" if negative else "NEUTRAL",
            "ROBUST_CORE": robust, "BORDERLINE": any(corners) and not robust}


def fresh(observed, now, start):
    age = (now - timestamp(observed)).total_seconds()
    return (0 <= age <= POLICY["max_age_seconds"]
            and 0 < (start - now).total_seconds() <= POLICY["late_window_seconds"])


def single(bounds, odds, *, case_qualified, minimum_price, price_fresh):
    minimum = number(minimum_price, 1)
    if minimum <= 1 or minimum < 1 / bounds["p_low"]:
        raise ValueError("minimum price must cover conservative fair odds")
    # Strictly positive conservative EV, even when minimum is exactly fair.
    decision = ("CASE_PASS" if not case_qualified else "WATCH" if not price_fresh
                else "BET" if odds >= minimum and odds * bounds["p_low"] > 1
                else "PRICE_PASS")
    return {**bounds, "fair_odds": 1 / bounds["p_mid"], "minimum_price": minimum,
            "decision": decision, "re_entry_price": minimum if case_qualified else None,
            "strict_positive_low_ev": True, "available_odds": odds,
            "stake": None, "execution": "SHADOW_ONLY"}


def evaluate(data):
    """Supplied pre-race estimates only; never infer intervals or PLACE from HBI scores."""
    field = data["active_field"]
    if (not field or any(not isinstance(k, str) or not k for k in field)
            or len(set(field)) != len(field)):
        raise ValueError("unique nonempty active field required")
    now, start = timestamp(data["decision_time"]), timestamp(data["race_start"])
    if now >= start:
        raise ValueError("RACE_ALREADY_STARTED")
    identity = data["identity_matches"]
    if set(identity) != set(field) or any(
        row.get("status") != "EXACT" or number(row["confidence"], 0, 1) != 1
        for row in identity.values()
    ):
        raise ValueError("FULL_FIELD_ONLY: exact identity evidence required")
    if any(not row.get("provider_id") for row in identity.values()) or len({
        row["provider_id"] for row in identity.values()
    }) != len(field):
        raise ValueError("unique provider identities required")
    model = data["fundamental"]
    if model.get("market_free") is not True or not model.get("model_version"):
        raise ValueError("market-free probability provenance required")
    if not timestamp(model["observed_at"]) <= timestamp(model["priced_at"]) <= now:
        raise ValueError("invalid fundamental PIT")
    bounds = distribution(model["probabilities"], field)
    win = data["decision_snapshot"]["WIN"]
    if win.get("race_id") != data["race_id"]:
        raise ValueError("WIN race mismatch")
    win_time = timestamp(win["observed_at"])
    if win_time > now or not win.get("snapshot_id"):
        raise ValueError("invalid decision snapshot")
    pwin = normalize(win["odds"], field, odds=True)
    pools, panel, unavailable = {}, {key: {} for key in field}, {}
    for name, pool in data["decision_snapshot"].get("collective", {}).items():
        try:
            if pool.get("product") != name:
                raise ValueError("canonical product identifier required")
            if pool.get("race_id") != data["race_id"] or not fresh(
                win["observed_at"], now, start
            ):
                raise ValueError("race mismatch or stale WIN")
            if not pool.get("snapshot_id") or not fresh(pool["observed_at"], now, start):
                raise ValueError("stale/future pool")
            if abs((timestamp(pool["observed_at"]) - win_time).total_seconds()) > POLICY[
                "max_pool_skew_seconds"
            ]:
                raise ValueError("noncontemporaneous pool")
            normalized = normalize(pool["shares"], field)
        except (ValueError, KeyError, TypeError) as exc:
            unavailable[name] = str(exc)
            continue
        pools[name] = normalized
        for key in field:
            panel[key][name] = divergence(normalized[key], pwin[key])
    if set(data["cases"]) != set(field):
        raise ValueError("FULL_FIELD_ONLY: explicit cases required")
    rows = {}
    place = data.get("place")
    place_bounds = None
    if place is not None:
        count = place["paid_places"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count < len(field):
            raise ValueError("invalid paid places")
        if not place.get("model_version") or place.get("market_free") is not True:
            raise ValueError("separate market-free PLACE model provenance required")
        if not timestamp(place["observed_at"]) <= timestamp(place["priced_at"]) <= now:
            raise ValueError("invalid PLACE PIT")
        place_bounds = distribution(place["probabilities"], field, place_count=count)
        if set(place["cases"]) != set(field):
            raise ValueError("FULL_FIELD_ONLY: explicit PLACE cases required")
        if place["snapshot"].get("race_id") != data["race_id"]:
            raise ValueError("PLACE race mismatch")
        normalize(place["snapshot"]["odds"], field, odds=True)
        if not place["snapshot"].get("snapshot_id"):
            raise ValueError("PLACE snapshot identity required")
    for key in field:
        case = data["cases"][key]
        field_review = validate_field_review(case, product="WIN")
        signals = [row["signal"] for row in panel[key].values()]
        pos, neg = signals.count("STRONG_POS"), signals.count("STRONG_NEG")
        consensus = ("CONFLICT" if pos and neg else "POSITIVE" if pos >= 2
                     else "NEGATIVE" if neg >= 2 else "INSUFFICIENT")
        winner = single(bounds[key], number(win["odds"][key], 1),
                        case_qualified=case["qualified"], minimum_price=case["minimum_price"],
                        price_fresh=fresh(win["observed_at"], now, start))
        required_place = case["qualified"] or pos > 0
        place_result = {"decision": "BLOCKED" if required_place else "NOT_REQUESTED",
                        "reason": "SEPARATE_P_PLACE_REQUIRED", "stake": None}
        if place_bounds is not None:
            pc = place["cases"][key]
            place_field_review = validate_field_review(pc, product="PLACE")
            place_result = single(
                place_bounds[key], number(place["snapshot"]["odds"][key], 1),
                case_qualified=pc["qualified"], minimum_price=pc["minimum_price"],
                price_fresh=fresh(place["snapshot"]["observed_at"], now, start))
        rows[key] = {"WIN": winner, "PLACE": place_result, "market_evidence": panel[key],
                     "expression": "WIN+PLACE" if winner["decision"] == "BET"
                     and place_result["decision"] == "BET" else "WIN"
                     if winner["decision"] == "BET" else "PLACE"
                     if place_result["decision"] == "BET" else "PASS",
                     "DUAL_POOL_STRONG": pos >= 2, "COL_CONSENSUS": consensus,
                     "case_reason": case["reason"], "field_review": field_review,
                     "place_field_review": place_field_review if place_bounds is not None else None,
                     "place_required": required_place,
                     "market_conflict_explanation": case.get("market_conflict_explanation"),
                     "conflict_review_required": case["qualified"] and neg > 0
                     and not case.get("market_conflict_explanation", "").strip()}
    # Optional blend is explicitly specified and recorded, never a decision input.
    combined = None
    if "shadow_weights" in data:
        weights = data["shadow_weights"]
        if weights != data["batch"].get("shadow_weights"):
            raise ValueError("shadow weights must be preregistered before the batch")
        if set(weights) != {"fundamental", "WIN", "collective"}:
            raise ValueError("explicit three-source shadow weights required")
        weights = {key: number(value, 0, 1) for key, value in weights.items()}
        if not isclose(sum(weights.values()), 1) or not pools:
            raise ValueError("shadow blend requires normalized weights and collective evidence")
        combined = {key: weights["fundamental"] * bounds[key]["p_mid"]
                    + weights["WIN"] * pwin[key]
                    + weights["collective"] * sum(p[key] for p in pools.values()) / len(pools)
                    for key in field}
    quality_incomplete = any(
        row["field_review"]["status"] == "DATA_MISSING"
        or (row["place_field_review"] is not None
            and row["place_field_review"]["status"] == "DATA_MISSING")
        for row in rows.values()
    )
    full_field_quality = {
        "gate_version": POLICY["full_field_review_gate"],
        "active_runners": len(field), "screened_runners": len(rows),
        "place_screened_runners": len(rows) if place_bounds is not None else 0,
        "blocked_by_missing_data": quality_incomplete,
    }
    report = {"standard": ACTIVE_STANDARD, "policy_hash": POLICY_HASH,
              "race_id": data["race_id"], "active_field": list(field),
              "decision_time": now.isoformat(), "race_start": start.isoformat(),
              "decision_snapshot": deepcopy(data["decision_snapshot"]),
              "closing_snapshot": None, "fundamental_provenance": deepcopy(model),
              "place_input": deepcopy(place), "runners": rows,
              "full_field_quality": full_field_quality,
              "ranked_qualified_WIN": ranked_win_candidates(rows),
              "unavailable_pools": unavailable, "shadow_combined": combined,
              "shadow_weights": deepcopy(data.get("shadow_weights")),
              "hbi_evidence": deepcopy(data.get("hbi_evidence", [])),
              "allowed": not quality_incomplete and not any(
                  r["place_required"] and r["PLACE"]["decision"] == "BLOCKED"
                  or r["conflict_review_required"] for r in rows.values()),
              "execution": "SHADOW_ONLY", "champion_changed": False,
              "batch": deepcopy(data["batch"])}
    batch = report["batch"]
    if (batch.get("mode") != "PROSPECTIVE_BLIND" or not batch.get("batch_id")
            or batch.get("policy_hash") != POLICY_HASH
            or timestamp(batch["registered_at"]) > now):
        raise ValueError("preregistered prospective/blind batch required")
    report["decision_id"] = sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    return report


def verify_report(report):
    basis = deepcopy(report)
    recorded_id = basis.pop("decision_id")
    basis["closing_snapshot"] = None
    if sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest() != recorded_id:
        raise ValueError("frozen decision integrity mismatch")
    if report["policy_hash"] != POLICY_HASH or report["standard"] != ACTIVE_STANDARD:
        raise ValueError("policy mismatch")


def allocate_stake(single_decision):
    """Independent fixed paper unit; no discretionary 2u or real-money route."""
    return {"unit_nok": 25, "units": 1 if single_decision["decision"] == "BET" else 0,
            "stake_nok": 25 if single_decision["decision"] == "BET" else 0,
            "execution": "SHADOW_ONLY"}


def reassess(report, snapshot, decision_time):
    """Append-only opportunity revision. CASE_PASS stays closed; original is untouched."""
    verify_report(report)
    now, start = timestamp(decision_time), timestamp(report["race_start"])
    if now < timestamp(report["decision_time"]) or now >= start:
        raise ValueError("invalid re-entry time")
    normalize(snapshot["odds"], report["active_field"], odds=True)
    if not snapshot.get("snapshot_id"):
        raise ValueError("snapshot identity required")
    rows = {}
    for key, row in report["runners"].items():
        original = row["WIN"]
        rows[key] = single(
            original, snapshot["odds"][key],
            case_qualified=original["decision"] != "CASE_PASS",
            minimum_price=original["minimum_price"],
            price_fresh=fresh(snapshot["observed_at"], now, start))
    if snapshot.get("race_id") != report["race_id"]:
        raise ValueError("re-entry race mismatch")
    # Reprice all starters; do not inherit a prior price-based PASS as a permanent veto.
    updated_rows = {
        key: {"WIN": candidate} for key, candidate in rows.items()
    }
    original_ranks = [
        item["selection"] for item in report["ranked_qualified_WIN"]
    ]
    updated_ranking = ranked_win_candidates(updated_rows)
    new_ranks = [item["selection"] for item in updated_ranking]
    changes = {}
    for key in report["active_field"]:
        old = report["runners"][key]["WIN"]
        current = rows[key]
        old_price = old["available_odds"]
        new_price = current["available_odds"]
        old_qual = old["decision"] != "CASE_PASS"
        status_changed = old["decision"] != current["decision"]
        price_crossed = old_qual and (
            (old_price < old["minimum_price"] <= new_price)
            or (new_price < old["minimum_price"] <= old_price)
        )
        rank_changed = (old_qual and original_ranks.index(key) != new_ranks.index(key))
        if status_changed or price_crossed or rank_changed:
            changes[key] = {
                "previous_status": old["decision"], "current_status": current["decision"],
                "price_crossed": price_crossed, "rank_changed": rank_changed,
                "old_odds": old_price, "new_odds": new_price,
            }
    return {"parent_decision_id": report["decision_id"], "policy_hash": POLICY_HASH,
            "decision_time": decision_time, "decision_snapshot": deepcopy(snapshot),
            "WIN": rows, "reprice_coverage": {"active": len(report["active_field"]),
                                             "checked": len(rows)},
            "ranked_qualified_WIN": updated_ranking, "changes": changes,
            "allowed": report["allowed"], "execution": "SHADOW_ONLY"}


def attach_closing(report, snapshot):
    """Closing prices are research-only and cannot change decision snapshots."""
    verify_report(report)
    if timestamp(snapshot["observed_at"]) < timestamp(report["decision_time"]):
        raise ValueError("closing predates decision")
    if not snapshot.get("snapshot_id"):
        raise ValueError("closing snapshot identity required")
    normalize(snapshot["odds"], report["active_field"], odds=True)
    if snapshot.get("race_id") != report["race_id"]:
        raise ValueError("closing race mismatch")
    result = deepcopy(report)
    result["closing_snapshot"] = deepcopy(snapshot)
    return result


def review_coupon(report, selections, *, omissions, banker=None, banker_reason=None):
    """Separate layer after singles; conservative cut audit, never auto-build a coupon."""
    verify_report(report)
    if not report["allowed"]:
        raise ValueError("single-bet review incomplete")
    if not selections or len(set(selections)) != len(selections):
        raise ValueError("unique nonempty coupon selections required")
    if not set(selections) <= set(report["active_field"]):
        raise ValueError("unknown coupon selection")
    cuts, errors = {}, []
    if not isinstance(omissions, dict):
        raise TypeError("full-field omission audit required")
    omitted = set(report["active_field"]) - set(selections)
    if set(omissions) - omitted:
        errors.append("CUT_AUDIT_UNKNOWN_SELECTION")
    for key, row in report["runners"].items():
        if key in selections:
            continue
        # A budget-driven cut still needs a reason, even for longshots and CASE_PASS runners.
        reason = omissions.get(key)
        valid_reason = isinstance(reason, str) and len(reason.strip()) >= 16
        cuts[key] = {
            "required": True, "reason": reason.strip() if valid_reason else None,
            "win_status": row["WIN"]["decision"],
            "p_mid": row["WIN"]["p_mid"],
            "qualified_case": row["WIN"]["decision"] != "CASE_PASS",
        }
        if not valid_reason:
            errors.append(f"CUT_AUDIT_REQUIRED:{key}")
    if banker is not None and (
        selections != [banker] or not banker_reason or not banker_reason.strip()
    ):
        errors.append("BANKER_REQUIRES_SINGLE_SELECTION_AND_EXPLANATION")
    return {"race_id": report["race_id"], "decision_id": report["decision_id"],
            "allowed": not errors, "errors": errors, "cut_audit": cuts,
            "selections": list(selections), "banker": banker,
            "banker_reason": banker_reason,
            "full_field_pricing": {k: r["WIN"] for k, r in report["runners"].items()},
            "full_field_quality": deepcopy(report["full_field_quality"]),
            "runner_audit_count": len(cuts) + len(selections),
            "execution": "SHADOW_ONLY"}


def construct_multi_race(legs, unit_price, *, max_paper_cost_nok=None):
    if not legs or any(not leg["allowed"] for leg in legs):
        raise ValueError("all legs must pass singles/cut audit")
    if len({leg["race_id"] for leg in legs}) != len(legs):
        raise ValueError("multi-race legs must refer to different races")
    price = number(unit_price)
    if price <= 0:
        raise ValueError("positive coupon unit price required")
    if max_paper_cost_nok is None:
        raise ValueError("explicit multi-race budget required")
    budget = number(max_paper_cost_nok)
    if budget <= 0:
        raise ValueError("positive paper budget required")
    combinations = prod(len(leg["selections"]) for leg in legs)
    cost = combinations * price
    if cost > budget + 1e-9:
        raise ValueError("multi-race selections exceed explicit fixed budget")
    return {"legs": deepcopy(legs), "combinations": combinations,
            "paper_cost_nok": cost, "max_paper_cost_nok": budget,
            "budget_remaining_nok": budget - cost, "execution": "SHADOW_ONLY"}
