"""Accelerated SYNTHETIC clock/journal tests; no live or PIT acceptance evidence."""
import importlib.util
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from hbi.prewatch_shadow_handoff import completion_health

spec = importlib.util.spec_from_file_location(
    "clock_reconciliation", Path(__file__).parents[1] / "scripts/release003_clock.py")
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)


def inputs():
    inventory = [{"race_id": "SYNTHETIC", "start_utc": "2026-11-22T10:10:00+00:00"}]
    plan = clock.make_plan("2026-11-22T10:00:00Z", "2026-11-22T11:10:00Z", "a" * 40,
                           inventory)
    receipts, runs, reports = [], [], {}
    for i, tick in enumerate(plan["ticks"], 1):
        when = clock.stamp(tick) + timedelta(seconds=20)
        receipts.append({"planned_at_utc": tick, "head": plan["pin"], "workflow_run_id": i,
                         "status": "DISPATCH_ACCEPTED_OBSERVATION_PENDING"})
        runs.append({"id": i, "head_sha": plan["pin"], "head_branch": plan["branch"],
                     "event": "workflow_dispatch", "display_title": "V3313 tick " + tick,
                     "created_at": (when - timedelta(seconds=18)).isoformat(),
                     "status": "completed", "conclusion": "success"})
        reports[i] = {"observed_at_utc": when.isoformat(), "inventory": ["SYNTHETIC"],
                      "races": [{"race_id": "SYNTHETIC", "terminal_status": "MODEL_BLOCKED",
                                 "blockers": ["SYNTHETIC_MISSING_ID"]}],
                      "counts": {"prospective_predictions": 0},
                      "evidence_mode": "SYNTHETIC_UNIT_TEST_ONLY", "bet_authority": False,
                      "production_activated": False, "champion_changed": False}
    return plan, inventory, receipts, runs, reports


def test_complete_clock_is_not_whole_day_or_pit_acceptance():
    args = inputs()
    result = clock.reconcile_clock(*args, observed_at=args[0]["end"])
    assert result["clock_reconciliation_complete"]
    assert result["status"] == "TECHNICALLY_COMPLETE"
    assert not result["full_day_accepted"] and not result["pit_certified"]


def test_closed_jobs_do_not_end_the_frozen_observation_window_early():
    args = inputs()
    when = (clock.stamp(args[0]["end"]) - timedelta(minutes=1)).isoformat()
    result = clock.reconcile_clock(*args, observed_at=when)
    assert result["status"] == "WAIT_LIVE" and not result["clock_reconciliation_complete"]


def test_missing_ticks_alert_even_when_surviving_day_reports_are_complete():
    plan, inventory, receipts, runs, reports = inputs()
    runs = [run for run in runs if run["id"] not in (3, 4)]
    surviving = [reports[run["id"]] for run in runs]
    assert not completion_health(surviving)["alert_required"]
    result = clock.reconcile_clock(plan, inventory, receipts, runs, reports,
                                   observed_at=plan["end"])
    assert result["alert_required"]
    assert result["known_failed_ticks"] == 2
    assert result["status"] == "BLOCKED_INTEGRATION"


@pytest.mark.parametrize("fault,status", [
    ("no_run", "NO_WORKFLOW_RUN"),
    ("failed_run", "RUN_FAILED"),
    ("no_report", "ACCEPTANCE_ARTIFACT_MISSING"),
    ("empty_report", "ACCEPTANCE_ARTIFACT_INVALID"),
    ("duplicate", "DUPLICATE_RUNS"),
])
def test_green_controller_or_post_ack_is_not_enough(fault, status):
    plan, inventory, receipts, runs, reports = inputs()
    if fault == "no_run":
        runs.pop(0)
    elif fault == "failed_run":
        runs[0]["conclusion"] = "failure"
    elif fault == "no_report":
        reports.pop(1)
    elif fault == "empty_report":
        reports[1]["inventory"] = []
    else:
        duplicate = dict(runs[0], id=99)
        runs.append(duplicate)
    result = clock.reconcile_clock(plan, inventory, receipts, runs, reports,
                                   observed_at=plan["end"])
    assert result["observations"][0]["status"] == status
    assert result["status"] == "BLOCKED_INTEGRATION"


def test_missing_final_controller_receipt_is_explicit_source_gap():
    plan, inventory, receipts, runs, reports = inputs()
    result = clock.reconcile_clock(plan, inventory, receipts[1:], runs, reports,
                                   observed_at=plan["end"])
    assert result["status"] == "BLOCKED_SOURCE"


def test_wrong_head_is_quarantined_and_cannot_cover_a_tick():
    plan, inventory, receipts, runs, reports = inputs()
    runs[0]["head_sha"] = "b" * 40
    result = clock.reconcile_clock(plan, inventory, receipts, runs, reports,
                                   observed_at=plan["end"])
    assert result["quarantined_runs"]
    assert result["observations"][0]["status"] == "NO_WORKFLOW_RUN"


def test_forged_receipt_or_revised_frozen_plan_is_rejected():
    args = inputs()
    revised = deepcopy(args[0])
    revised["ticks"].pop()
    with pytest.raises(ValueError, match="FROZEN_ACCEPTANCE_PLAN_CONFLICT"):
        clock.reconcile_clock(revised, *args[1:], observed_at=args[0]["end"])
    args[2][0]["head"] = "b" * 40
    with pytest.raises(ValueError, match="RECEIPT_CLOCK_OR_HEAD_CONFLICT"):
        clock.reconcile_clock(*args, observed_at=args[0]["end"])
