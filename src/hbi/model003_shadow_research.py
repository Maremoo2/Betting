"""MODEL-003 market-free, strictly qualified Challenger V3 feature research.

No model fitting, weights, price comparisons or betting authority. Missing
historical identity, PIT or full-field evidence blocks feature promotion.
"""
from __future__ import annotations

from datetime import date
from typing import Any

FEATURES = (
    "recent_clean_time_mean", "days_since_last_start",
    "recent_gallop_fraction", "official_class_index", "opponent_strength",
)


def candidate_features(
    *, target_date: str, horse_id: str | None,
    identity_status: str, starts: list[dict[str, Any]],
) -> dict[str, Any]:
    target = date.fromisoformat(target_date)
    reasons = []
    if identity_status != "VERIFIED_ID" or not horse_id:
        reasons.append("PERMANENT_ID_NOT_VERIFIED")
    if len(starts) != 5:
        reasons.append("COMPLETE_FIVE_REQUIRED")
    dates = []
    for row in starts:
        try:
            when = date.fromisoformat(row["performance_date"])
        except (KeyError, ValueError, TypeError):
            reasons.append("HISTORY_DATE_MISSING")
            continue
        if when >= target:
            reasons.append("HISTORICAL_LOOKAHEAD")
        dates.append(when)
        if row.get("horse_id") != horse_id:
            reasons.append("HISTORICAL_ID_MISMATCH")
        if row.get("pit_evidence_status") != "PIT_CERTIFIED":
            reasons.append("HISTORICAL_PIT_NOT_CERTIFIED")
        if not row.get("result_source_sha256"):
            reasons.append("HISTORY_SOURCE_HASH_MISSING")
        if not row.get("official_race_id"):
            reasons.append("HISTORIC_RACE_ID_MISSING")
    if len(set(dates)) != len(dates):
        reasons.append("DUPLICATE_PERFORMANCE_DATE")
    if dates != sorted(dates):
        reasons.append("NOT_CHRONOLOGICAL")
    if reasons:
        return {
            "schema": "MODEL003_FEATURE_GATE_V1", "horse_id": horse_id,
            "status": "NOT_TESTABLE", "reasons": sorted(set(reasons)),
            "features": {}, "model_version": "CHALLENGER_V3_SHADOW_UNFITTED",
            "bet_authority": False,
        }
    clean = [
        float(r["km_seconds"]) for r in starts
        if r.get("km_seconds") is not None and not r.get("gallop")
    ]
    values = {
        "recent_clean_time_mean": sum(clean) / len(clean) if clean else None,
        "days_since_last_start": (target - dates[-1]).days,
        "recent_gallop_fraction": sum(r.get("gallop") is True for r in starts) / 5,
        "official_class_index": None, "opponent_strength": None,
    }
    missing = []
    for key in ("official_class_index", "opponent_strength"):
        if any(r.get(key) is None for r in starts):
            missing.append(key)
        else:
            values[key] = sum(float(r[key]) for r in starts) / 5
    return {
        "schema": "MODEL003_FEATURE_GATE_V1", "horse_id": horse_id,
        "status": (
            "MARKET_FREE_RESEARCH_CANDIDATE"
            if not missing else "PARTIAL_RESEARCH_FEATURES"
        ),
        "reasons": ["UNAVAILABLE_" + k.upper() for k in missing],
        "features": values, "model_version": "CHALLENGER_V3_SHADOW_UNFITTED",
        "bet_authority": False,
    }
