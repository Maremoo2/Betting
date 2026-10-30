"""BET-001B3: prospective-only PreWatchFunnel ledger QA and dry-run migration.

Pure local functions. Never writes Google Sheets, recomputes frozen decisions,
changes V3.3.12 gates, or authorizes a betting action.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

DIMENSIONS = ("data_25", "shape_20", "mispricing_30", "liquidity_15", "today_fit_10")
BOUNDS = (25, 20, 30, 15, 10)


def _score(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _stamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value)
        return result if result.utcoffset() is not None else None
    except ValueError:
        return None


def row_formula(sheet_row: int) -> str:
    """One future-row U formula; no spill into archived U25/other cells."""
    if type(sheet_row) is not int or not 2 <= sheet_row <= 1500:
        raise ValueError("INVALID_ROW")
    return (
        f'=IF($A{sheet_row}="","",IF(COUNT(P{sheet_row}:T{sheet_row})=5,'
        f'SUM(P{sheet_row}:T{sheet_row}),""))'
    )


def diagnose_row(row: dict[str, Any]) -> dict[str, Any]:
    """Sidecar classification only; original values are never mutated."""
    original = deepcopy(row)
    relevant = ("race_id", "total_formula", "screening_status_formula", *DIMENSIONS)
    if not any(str(row.get(k, "")).strip() for k in relevant):
        outcome, reasons = "SKIP_EMPTY_ROW", []
    elif not str(row.get("race_id", "")).strip():
        outcome, reasons = "PROCESS_FAILURE", ["MISSING_RACE_ID"]
    else:
        reasons = []
        original_status = str(row.get("screening_status_formula", "")).strip()
        total_raw = str(row.get("total_formula", "")).strip()
        scores = [_score(row.get(k)) for k in DIMENSIONS]
        present = all(v is not None for v in scores)
        if "#REF!" in total_raw or "#REF!" in original_status:
            reasons.append("FORMULA_REF_ERROR")
        if present and total_raw == "":
            reasons.append("MISSING_TOTAL_WITH_ALL_DIMENSIONS")
        recorded = _score(total_raw)
        if present and recorded is not None:
            if any(v < 0 or v > maximum for v, maximum in zip(scores, BOUNDS, strict=True)):
                reasons.append("DIMENSION_OUT_OF_RANGE")
            if sum(scores, Decimal(0)) != recorded:
                reasons.append("TOTAL_COMPONENT_MISMATCH")
        if original_status == "SCREENED_BELOW_THRESHOLD" and (recorded is None or recorded >= 70):
            reasons.append("INCONSISTENT_SCREENED_STATUS")
        if original_status == "A_WATCH" and (recorded is None or recorded < 70):
            reasons.append("INCONSISTENT_AWATCH_STATUS")
        screened = _stamp(row.get("screened_at_iso"))
        start = _stamp(row.get("scheduled_start_iso"))
        if row.get("screened_at_iso") and row.get("scheduled_start_iso"):
            if screened is None or start is None:
                reasons.append("INVALID_PRESTART_CLOCK")
            elif screened >= start:
                reasons.append("POSTSTART_NOT_PRESTART")
        if reasons:
            outcome = "DATA_BLOCKED" if reasons == ["POSTSTART_NOT_PRESTART"] else "PROCESS_FAILURE"
        elif row.get("missing_source_evidence") is True:
            outcome = "DATA_BLOCKED"
        elif not present or recorded is None:
            outcome = "PARTIAL"
        else:
            outcome = original_status if original_status in {
                "A_WATCH", "SCREENED_BELOW_THRESHOLD", "BLOCKED_GATE"
            } else "PARTIAL"
    assert row == original
    return {"race_id": row.get("race_id"), "diagnostic_status": outcome,
            "reason_codes": reasons, "historical_data_changed": False,
            "bet_authorized": False}


def dry_run_future_formulas(rows: list[dict[str, Any]], *,
                            last_historical_row: int, first_future_row: int,
                            last_future_row: int) -> dict[str, Any]:
    """Never supplies a plan for a nonempty cell or any historical row."""
    if (any(type(x) is not int for x in (
            last_historical_row, first_future_row, last_future_row))
            or not 2 <= last_historical_row < first_future_row
            <= last_future_row <= 1500):
        raise ValueError("PROSPECTIVE_ONLY_ROW_BOUNDS")
    frozen = deepcopy(rows)
    by_index: dict[int, dict[str, Any]] = {}
    reasons = []
    for row in rows:
        index = row.get("_sheet_row")
        if type(index) is not int or index in by_index:
            reasons.append("DUPLICATE_OR_INVALID_SHEET_ROW")
        else:
            by_index[index] = row
    for index in range(first_future_row, last_future_row + 1):
        existing = by_index.get(index, {})
        if any(str(v).strip() for key, v in existing.items() if key != "_sheet_row"):
            reasons.append(f"TARGET_ROW_NOT_EMPTY:{index}")
    plan = [] if reasons else [
        {"cell": f"PreWatchFunnel!U{n}", "formula": row_formula(n)}
        for n in range(first_future_row, last_future_row + 1)
    ]
    assert rows == frozen
    return {"status": "BLOCKED" if reasons else "DRY_RUN_ONLY",
            "reasons": sorted(set(reasons)), "proposed_formulas": plan,
            "historical_rows_preserved": True, "production_written": False,
            "rollback": "Discard this plan; no mutations were performed"}
