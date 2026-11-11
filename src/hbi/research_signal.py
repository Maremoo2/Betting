"""Immutable, non-executable WIN BET research signals – RELEASE-005.

These rows never enter shadow_tickets and have no conversion/settlement API.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .horse_identity import AttestedHorseIdentity, identity_fields

SIGNAL_SCHEMA = "RELEASE005_WIN_RESEARCH_SIGNAL_V1"


def _probabilities(value: object) -> dict[str, float]:
    if not isinstance(value, dict) or len(value) < 2:
        raise ValueError("RESEARCH_SIGNAL_INCOMPLETE_PROBABILITIES")
    try:
        result = {str(k): float(v) for k, v in value.items()}
    except (TypeError, ValueError) as exc:
        raise ValueError("RESEARCH_SIGNAL_INCOMPLETE_PROBABILITIES") from exc
    if not all(math.isfinite(p) and 0 < p <= 1 for p in result.values()):
        raise ValueError("RESEARCH_SIGNAL_INCOMPLETE_PROBABILITIES")
    if abs(sum(result.values()) - 1.0) > 1e-6:
        raise ValueError("RESEARCH_SIGNAL_INCOMPLETE_PROBABILITIES")
    return result


def record_win_research_signal(
    store: Any,
    *,
    race_id: str,
    decision_run_id: str,
    selection_id: str,
    model_version: str,
    fundamental_model_version: str | None,
    fundamental: dict[str, float],
    market: dict[str, float],
    combined: dict[str, float],
    assessment: Any,
    minimum_edge: float,
    calculated_at: datetime,
    source_market_time: str | None,
    source_receipts: dict[str, dict[str, Any]] | None,
    rejected_candidates: list[dict[str, Any]],
    contender_payload_id: str,
    identity_attestations: tuple[AttestedHorseIdentity, ...] = (),
) -> datetime:
    """Save a complete winner candidate, verify immutable SQLite readback.

    Return the *postcommit* wall-clock witness. Failure is fail-closed and
    never creates/settles a SHADOW_BET ticket.
    """
    if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
        raise ValueError("RESEARCH_SIGNAL_CLOCK_MISSING")
    frozen_fund = _probabilities(fundamental)
    frozen_market = _probabilities(market)
    frozen_combined = _probabilities(combined)
    keys = set(frozen_combined)
    if (
        set(frozen_fund) != keys or set(frozen_market) != keys
        or not isinstance(selection_id, str) or selection_id not in keys
        or not race_id or not model_version or not decision_run_id
    ):
        raise ValueError("RESEARCH_SIGNAL_FIELD_OR_IDENTITY_MISMATCH")
    try:
        p = float(assessment.probability)
        price = float(assessment.available_price)
        fair = float(assessment.fair_odds)
        ev = float(assessment.expected_value)
        base_minimum = float(assessment.minimum_price)
        if not math.isfinite(p) or p <= 0:
            raise ValueError("RESEARCH_SIGNAL_PROBABILITY_INVALID")
        minimum = max(base_minimum, (1 + minimum_edge) / p)
    except (TypeError, AttributeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError("RESEARCH_SIGNAL_ODDS_OR_PROBABILITY_INVALID") from exc
    if not (
        math.isfinite(p) and 0 < p <= 1
        and math.isclose(p, frozen_combined[selection_id], abs_tol=1e-9)
        and math.isfinite(price) and price > 1
        and math.isfinite(fair) and fair >= 1
        and math.isclose(fair, 1 / p, abs_tol=1e-7)
        and math.isfinite(ev) and math.isclose(ev, p * price - 1, abs_tol=1e-7)
        and math.isfinite(minimum) and minimum >= 1
    ):
        raise ValueError("RESEARCH_SIGNAL_ODDS_OR_PROBABILITY_INVALID")

    sources = source_receipts if isinstance(source_receipts, dict) else {}
    win = sources.get("WIN") or {}
    signal_id = hashlib.sha256(
        f"{SIGNAL_SCHEMA}|{decision_run_id}|{selection_id}".encode()
    ).hexdigest()
    record = {
        "signal_id": signal_id,
        "decision_run_id": decision_run_id,
        "race_id": race_id,
        "selection_id": selection_id,
        **identity_fields(race_id, selection_id, identity_attestations),
        "horse_id_scope": "RACE_LOCAL_SELECTION_NOT_PERMANENT_HORSE_ID",
        "shadow_model_name": "HBI_WIN_SHADOW",
        "shadow_model_version": model_version,
        "fundamental_model_version": fundamental_model_version,
        "fundamental_probabilities_json": json.dumps(frozen_fund, sort_keys=True),
        "market_probabilities_json": json.dumps(frozen_market, sort_keys=True),
        "combined_probabilities_json": json.dumps(frozen_combined, sort_keys=True),
        "observed_win_odds": price,
        "p_win": p,
        "fair_odds": fair,
        "expected_value": ev,
        "minimum_acceptable_odds": minimum,
        "signal_calculated_at_utc": calculated_at.isoformat(),
        "record_requested_at_utc": datetime.now(UTC).isoformat(),
        "source_observed_at_utc": source_market_time,
        "source_uri": win.get("source_uri"),
        "source_body_sha256": win.get("body_sha256"),
        "source_receipts_json": json.dumps(sources, sort_keys=True),
        "rejected_candidates_json": json.dumps(rejected_candidates, sort_keys=True),
        "contender_payload_id": contender_payload_id,
    }
    try:
        store.insert_shadow_research_signal(record)
        readback = store.get_shadow_research_signal(signal_id)
    except sqlite3.Error as exc:
        # The protected shadow caller already converts this failure to NOT_EXECUTABLE.
        raise RuntimeError("RESEARCH_SIGNAL_SQLITE_FAILURE") from exc
    verified = datetime.now(UTC)
    if readback is None or any(
        readback.get(k) != v for k, v in record.items()
        if k != "record_requested_at_utc"
    ):
        raise RuntimeError("RESEARCH_SIGNAL_READBACK_MISMATCH")
    if (
        readback.get("status") != "SIGNAL_RECORDED"
        or readback.get("t4_attested") != 0
        or readback.get("pit_certified") != 0
        or readback.get("shadow_ticket_created") != 0
        or readback.get("research_only") != 1
    ):
        raise RuntimeError("RESEARCH_SIGNAL_IS_NOT_RESEARCH_ONLY")
    return verified
