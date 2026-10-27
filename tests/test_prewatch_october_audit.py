"""No-live-writes / fail-closed regression tests for October funnel reconciliation."""
from __future__ import annotations

import csv
from copy import deepcopy
from datetime import date

import pytest

from hbi.prewatch_october_audit import (
    REQUIRED_COLUMNS,
    _market_evidence,
    _preflight_evidence,
    audit_october,
    read_exported_tabs,
)


def _race(when: str, track: str, number: int, score: str, status: str,
          mispricing: str = "16", liquidity: str = "3") -> dict[str, str]:
    return {
        "race_id": f"{when}|{track}|{number}",
        "race_date": when,
        "screening_status_formula": status,
        "total_formula": score,
        "A_WATCH_gate_formula": "NO",
        "data_25": "20",
        "shape_20": str(
            int(score) - 30 - int(mispricing) - int(liquidity)
        ) if score.isdecimal() else "16",
        "mispricing_30": mispricing,
        "liquidity_15": liquidity,
        "today_fit_10": "10",
        "source_backed_hypothesis": "Visible performance is not priced",
        "uncertainty_and_missing": "Standalone WIN pool and scratches not verified",
        "liquidity_source_and_proxy": "V75 is not WIN; standalone unknown",
        "candidate_horse_no_name": "#3 Example",
    }


@pytest.fixture()
def tabs() -> dict[str, list[dict[str, str]]]:
    r1 = _race("2026-10-27", "Bjerke", 7, "69", "SCREENED_BELOW_THRESHOLD")
    r2 = _race("2026-10-27", "Jägersro", 8, "65", "SCREENED_BELOW_THRESHOLD",
               "18", "3")
    r3 = _race("2026-10-27", "Bjerke", 8, "", "PARTIAL", "", "")
    r4 = _race("2026-10-15", "Solvalla", 4, "#REF!", "#REF!", "", "")
    r5 = _race("2026-10-13", "Romme", 1, "61", "SCREENED_BELOW_THRESHOLD")
    before = {
        "race_id": r1["race_id"],
        "observed_at_utc": "2026-10-27T16:30:00Z",
        "scheduled_start_oslo": "2026-10-27T18:00:00+01:00",
        "win_market_scope": "V75_TOTAL_NOT_WIN",
        "win_pool_amount": "300000",
        "win_pool_asof": "2026-10-27T16:28:00Z",
        "operational_gate": "PARTIAL_UNRESOLVED",
    }
    after = {**before, "observed_at_utc": "2026-10-27T17:01:00Z"}
    market = {
        "race_id": r1["race_id"],
        "snapshot_id": "win_test",
        "market_type": "WIN",
        "observed_at": "2026-10-27T16:30:00Z",
        "scheduled_start_at": "2026-10-27T18:00:00+01:00",
        "is_prestart": "YES",
        "full_field_same_timestamp": "YES",
    }
    return {
        "PreWatchFunnel": [r1, r2, r3, r4, r5],
        "PreWatchPreflight": [before, before.copy(), after],
        "MarketSnapshots": [market, market.copy()],
        "FrozenDecisions": [{
            "race_id": r1["race_id"], "decision_id": "frozen_1",
            "status": "NOT_EVALUABLE", "hard_gates_pass": "NO",
        }],
        "ProbabilitySnapshots": [],
        "RunLog": [
            {"run_id": "run_A", "run_time_iso": "2026-10-27T19:00:00+01:00",
             "identified_races": "99"},
            {"run_id": "run_A", "run_time_iso": "2026-10-27T19:05:00+01:00",
             "identified_races": "99"},
        ],
    }


def test_join_deduplicates_repeated_runs_and_preflight_evidence(tabs):
    report = audit_october(tabs)
    assert report["unique_frozen_funnel_races"] == 5
    assert report["runlog_rows_not_unique_race_count"] == 2
    assert report["runlog_distinct_ids"] == 1
    assert report["funnel_terminal_status_counts"] == {
        "FORMULA_ERROR": 1, "PARTIAL": 1, "SCREENED_BELOW_THRESHOLD": 3
    }
    assert report["scored_component_counts"] == {
        "liquidity_component_below_8": 3,
        "mispricing_component_below_18": 2,
        "near_65_to_69": 2,
        "scored_below_threshold": 3,
        "scored_total_below_70": 3,
    }
    assert report["quality_anomalies"]["FORMULA_ERROR_EXCLUDED_FROM_SCORED"] == 1
    assert not report["canonical_snapshots_mutated"]
    assert report["BET_BLOCKED"]


def test_near_threshold_does_not_imply_edge_or_measure_market_liquidity(tabs):
    report = audit_october(tabs)
    near = report["near_threshold_65_69"]
    assert len(near) == 2
    assert near[0]["frozen_total_score_display"] == "69"
    assert near[0]["win_pool_evidence_class"] == "UNKNOWN_OR_PROXY_NOT_MEASURED"
    assert near[0]["prestart_preflight_observations"] == 2
    assert near[0]["poststart_preflight_observations_excluded"] == 1
    assert near[0]["probability_rows_exact_join"] == 0
    assert near[0]["frozen_decision_rows_exact_join"] == 1
    assert near[0]["diagnostic_blockers"].count("FROZEN_DECISION_NOT_EVALUABLE") == 1
    assert not near[0]["live_BET_eligible_by_this_audit"]
    assert not near[0]["independent_probability_approved_by_this_audit"]


def test_a_declared_full_field_win_snapshot_is_not_verified_for_bet(tabs):
    item = audit_october(tabs)["near_threshold_65_69"][0]
    assert item["WIN_snapshot_groups"] == 1
    assert item["prestart_full_field_WIN_self_declared_groups"] == 1
    assert item["WIN_snapshot_independently_validated_for_BET"] is False


def test_genuine_poststart_snapshot_is_rejected_from_prestart_count(tabs):
    item = deepcopy(tabs["MarketSnapshots"][0])
    item["observed_at"] = "2026-10-27T17:02:00Z"
    tabs["MarketSnapshots"] = [item]
    result = _market_evidence(tabs["MarketSnapshots"])
    assert result["WIN_snapshot_groups_stale_or_poststart"] == 1
    assert result["prestart_full_field_WIN_self_declared_groups"] == 0


def test_unknown_timestamp_and_historical_win_pool_are_not_current(tabs):
    race_id = tabs["PreWatchFunnel"][0]["race_id"]
    pref = {**tabs["PreWatchPreflight"][0],
            "observed_at_utc": "2026-10-27T16:30:00Z",
            "win_market_scope": "CURRENT_STANDALONE_WIN",
            "win_pool_asof": "2026-10-01T15:00:00Z"}
    evidence, blockers = _preflight_evidence(race_id, [pref])
    assert evidence["win_pool_evidence_class"] == "UNKNOWN_OR_PROXY_NOT_MEASURED"
    assert "CURRENT_STANDALONE_WIN_POOL_NOT_ESTABLISHED" in blockers
    pref["observed_at_utc"] = "clock_unknown"
    evidence, blockers = _preflight_evidence(race_id, [pref])
    assert evidence["prestart_preflight_observations"] == 0
    assert "PREFLIGHT_INVALID_OR_MISSING_TIMESTAMP" in blockers


def test_report_does_not_rewrite_original_rows(tabs):
    preserved = deepcopy(tabs)
    report = audit_october(tabs)
    assert tabs == preserved
    assert report["frozen_thresholds_unchanged"] == {
        "A_WATCH": 70, "mispricing": 18, "liquidity": 8
    }


def test_invalid_and_duplicate_primary_race_identity_fail_closed(tabs):
    tabs["PreWatchFunnel"].append(deepcopy(tabs["PreWatchFunnel"][0]))
    with pytest.raises(ValueError, match="Repeated primary frozen race key"):
        audit_october(tabs)
    tabs["PreWatchFunnel"].pop()
    tabs["PreWatchFunnel"][0]["race_id"] = "unknown|Bjerke|7"
    with pytest.raises(ValueError, match="Invalid primary race"):
        audit_october(tabs)


def test_below_threshold_status_with_70_is_flagged_not_promoted(tabs):
    tabs["PreWatchFunnel"][0]["total_formula"] = "70"
    report = audit_october(tabs)
    assert report["quality_anomalies"]["CONTRADICTORY_BELOW_THRESHOLD_TOTAL"] == 1
    assert len(report["near_threshold_65_69"]) == 1
    assert report["actual_WATCH_BET_not_authorized_by_report"]


def test_missing_days_are_unobserved_not_absent(tabs):
    report = audit_october(tabs, start=date(2026, 10, 12),
                           end=date(2026, 10, 27))
    assert "2026-10-12" in report["days_without_funnel_rows_not_proven_no_races"]
    assert "2026-10-13" not in report["days_without_funnel_rows_not_proven_no_races"]


def test_export_reader_validates_headers_empty_rows_and_checksums(tmp_path, tabs):
    for name, fields in REQUIRED_COLUMNS.items():
        with (tmp_path / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow({k: "" for k in fields})
            for row in tabs[name]:
                writer.writerow({k: row.get(k, "") for k in fields})
    parsed, hashes = read_exported_tabs(tmp_path)
    assert len(parsed["PreWatchFunnel"]) == 5
    assert len(parsed["PreWatchPreflight"]) == 3
    assert len(parsed["RunLog"]) == 2
    assert len(hashes) == len(REQUIRED_COLUMNS)
    report = audit_october(parsed, file_hashes=hashes)
    assert report["unique_frozen_funnel_races"] == 5
    assert len(report["file_sha256_by_sheet"]) == len(REQUIRED_COLUMNS)


def test_export_reader_missing_sheet_and_extra_cells_fail_closed(tmp_path, tabs):
    with pytest.raises(ValueError, match="Missing required read-only export"):
        read_exported_tabs(tmp_path)
    for name, fields in REQUIRED_COLUMNS.items():
        with (tmp_path / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in tabs[name]:
                writer.writerow({k: row.get(k, "") for k in fields})
    with (tmp_path / "PreWatchFunnel.csv").open("a", encoding="utf-8") as f:
        f.write("extra,unexpected,columns,not,covered,by,header," + ",".join(
            "unexpected" for _ in range(40)) + "\n")
    with pytest.raises(ValueError, match="Extra unnamed CSV cells"):
        read_exported_tabs(tmp_path)


def test_report_flags_arithmetic_and_false_A_WATCH_gate_without_repricing(tabs):
    row = tabs["PreWatchFunnel"][0]
    original = deepcopy(row)
    row["total_formula"] = "68"
    row["A_WATCH_gate_formula"] = "YES"
    report = audit_october(tabs)
    flags = report["quality_anomalies"]
    assert flags["TOTAL_COMPONENT_ARITHMETIC_MISMATCH_READONLY"] == 1
    assert flags["A_WATCH_GATE_CONTRADICTS_RECORDED_SCORE"] == 1
    assert flags["REPORTED_A_WATCH_REQUIRES_INDEPENDENT_VERIFICATION"] == 1
    assert original["total_formula"] == "69"
    assert row["total_formula"] == "68"  # audit cannot rewrite source


def test_canonical_race_date_disagreement_is_not_fuzzy_joined(tabs):
    tabs["PreWatchFunnel"][0]["race_date"] = "2026-10-26"
    with pytest.raises(ValueError, match="race_date and race_id disagree"):
        audit_october(tabs)


def test_component_out_of_bounds_is_flagged_not_interpreted_as_edge(tabs):
    tabs["PreWatchFunnel"][0]["mispricing_30"] = "40"
    report = audit_october(tabs)
    assert report["quality_anomalies"]["COMPONENT_OUTSIDE_FROZEN_RUBRIC_RANGE"] == 1
    assert report["BET_BLOCKED"]
