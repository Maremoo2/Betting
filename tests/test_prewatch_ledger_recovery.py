"""BET-001B3 tests are local/deterministic and never touch Sheets."""
from copy import deepcopy

import pytest

from hbi.prewatch_ledger_recovery import diagnose_row, dry_run_future_formulas, row_formula


def _row(**changes):
    r = {"race_id": "2026-10-20|Bjerke|1", "screening_status_formula": "SCREENED_BELOW_THRESHOLD",
         "data_25": 20, "shape_20": 12, "mispricing_30": 15,
         "liquidity_15": 8, "today_fit_10": 5, "total_formula": 60,
         "screened_at_iso": "2026-10-20T14:00:00+02:00",
         "scheduled_start_iso": "2026-10-20T19:20:00+02:00"}
    r.update(changes)
    return r


def test_exact_ref_collision_is_process_failure():
    r = _row(total_formula="#REF!", screening_status_formula="#REF!")
    assert "FORMULA_REF_ERROR" in diagnose_row(r)["reason_codes"]


def test_complete_components_but_blank_total_is_process_failure():
    r = _row(total_formula="", screening_status_formula="PARTIAL")
    assert diagnose_row(r)["reason_codes"] == ["MISSING_TOTAL_WITH_ALL_DIMENSIONS"]


def test_partial_dimensions_remain_partial():
    assert diagnose_row(_row(data_25="", total_formula="", screening_status_formula="PARTIAL"))["diagnostic_status"] == "PARTIAL"


def test_source_missing_distinct_from_process_failure():
    assert diagnose_row(_row(missing_source_evidence=True))["diagnostic_status"] == "DATA_BLOCKED"


def test_frozen_below_threshold_is_not_upgraded():
    r = _row()
    old = deepcopy(r)
    assert diagnose_row(r)["diagnostic_status"] == "SCREENED_BELOW_THRESHOLD"
    assert r == old


@pytest.mark.parametrize("change,code", [
    ({"total_formula": 61}, "TOTAL_COMPONENT_MISMATCH"),
    ({"liquidity_15": 16}, "DIMENSION_OUT_OF_RANGE"),
    ({"screening_status_formula": "A_WATCH"}, "INCONSISTENT_AWATCH_STATUS"),
    ({"screened_at_iso": "2026-10-20T19:20:00+02:00"}, "POSTSTART_NOT_PRESTART"),
    ({"screened_at_iso": "2026-10-20T19:20:00"}, "INVALID_PRESTART_CLOCK"),
])
def test_invalid_rows_fail_closed(change, code):
    assert code in diagnose_row(_row(**change))["reason_codes"]


def test_blank_row_ignored_and_new_row_formula_is_scoped():
    assert diagnose_row({})["diagnostic_status"] == "SKIP_EMPTY_ROW"
    assert row_formula(26).startswith('=IF($A26')
    assert "ARRAYFORMULA" not in row_formula(26)


def test_dry_run_is_prospective_and_preserves_history():
    data = [{"_sheet_row": 25, **_row()}, {"_sheet_row": 26}]
    frozen = deepcopy(data)
    result = dry_run_future_formulas(data, last_historical_row=25,
                                     first_future_row=26, last_future_row=27)
    assert result["status"] == "DRY_RUN_ONLY"
    assert len(result["proposed_formulas"]) == 2
    assert data == frozen and result["production_written"] is False


def test_future_nonempty_row_blocks():
    result = dry_run_future_formulas([{"_sheet_row": 26, "total_formula": 1}],
                      last_historical_row=25, first_future_row=26, last_future_row=26)
    assert result["status"] == "BLOCKED"


def test_historical_rewrite_forbidden():
    with pytest.raises(ValueError, match="PROSPECTIVE_ONLY"):
        dry_run_future_formulas([], last_historical_row=25, first_future_row=25,
                                last_future_row=30)
