"""Deterministic tests for prospective, isolated CORE-003 pilot metrics."""

import json
from datetime import datetime, timedelta

import pytest
from test_core_prefetch import (
    NOW,
    RID,
    CollectorStub,
    add_race,
    fundamental,
    make_db,
    market,
)
from test_core_prefetch_worker import StoreStub

from hbi.core_shadow_pilot import SCHEMA, run_pilot


def _pilot(c, *, collector=None, now=NOW, execute=True, clock=None, **kwargs):
    return run_pilot(
        store=StoreStub(c), collector=collector or CollectorStub(c),
        now=now, clock=clock or (lambda: now), execute=execute, discover=False, **kwargs,
    )


def test_real_source_stub_improves_roster_history_and_win_market():
    c = make_db()
    report = _pilot(c)
    assert report["schema_version"] == SCHEMA
    assert report["authority"] == "SHADOW_RESEARCH_ONLY_NO_MODEL_NO_BET"
    assert report["mode"] == "FETCH_SOURCES"
    assert report["races_in_fixed_cohort"] == [RID]
    assert report["before"]["races_full_sources"] == 0
    assert report["after"]["races_full_sources"] == 1
    assert report["delta"]["races_full_history"] == 1
    assert report["delta"]["races_full_win_market"] == 1
    assert report["delta"]["active_horses_with_verified_history"] == 3
    assert report["tasks_attempted"] == 2
    assert report["provider_event_statuses"] == {"FETCHED_NOT_PROVEN_COMPLETE": 2}
    assert report["bet_count"] == report["model_invocations"] == 0
    assert report["prospective_t4_success_proven"] is False


def test_preview_has_no_discovery_no_provider_calls_no_mutation():
    c = make_db()
    class FailCollector:
        def discover(self, *_):
            raise AssertionError("discovery forbidden in preview")
    report = _pilot(c, collector=FailCollector(), execute=False)
    assert report["mode"] == "PREVIEW_NO_PROVIDER_CALLS"
    assert report["provider_events"] == []
    assert report["before"] == report["after"]
    assert report["tasks_selected"] == 2


def test_persisted_complete_sources_have_no_fictitious_new_gains():
    c = make_db()
    fundamental(c)
    market(c)
    report = _pilot(c)
    assert report["tasks_attempted"] == 0
    assert all(value == 0 for value in report["delta"].values())
    assert report["before"]["races_full_sources"] == 1


def test_partial_market_never_reported_complete():
    c = make_db()
    fundamental(c)
    market(c, include=(1, 2))
    report = _pilot(c, execute=False)
    assert report["before"]["races_full_history"] == 1
    assert report["before"]["races_full_win_market"] == 0
    assert report["before"]["races_full_sources"] == 0


def test_future_history_and_odds_cannot_count_toward_readiness():
    c = make_db()
    fundamental(c, now=NOW + timedelta(minutes=5))
    market(c, now=NOW + timedelta(minutes=5))
    report = _pilot(c, execute=False)
    assert report["before"]["races_full_history"] == 0
    assert report["before"]["races_full_win_market"] == 0


def test_t4_cutoff_rejects_late_source_records_even_after_fetch():
    c = make_db()
    # Runner cohort arrives beyond the race's frozen T-4 cutoff.
    cutoff = NOW + timedelta(minutes=4)
    fundamental(c, now=cutoff + timedelta(seconds=5))
    market(c, now=cutoff + timedelta(seconds=5))
    report = _pilot(c, now=NOW + timedelta(minutes=3), execute=False)
    assert report["before"]["races_full_sources"] == 0
    assert report["race_readiness_before"][0]["t4_cutoff_utc"] == cutoff.isoformat()


def test_crossing_t4_does_not_falsely_increase_readiness():
    c = make_db()
    report = _pilot(c, clock=lambda: NOW + timedelta(minutes=5))
    assert report["tasks_attempted"] == 2
    assert report["provider_event_statuses"] == {"TOO_LATE_TO_PREFETCH": 2}
    assert report["delta"]["races_full_sources"] == 0


def test_duplicate_race_reference_only_counted_once():
    c = make_db()
    add_race(c, rid="RIKSTOTO:T2_NR_2026-10-30:1", track="Testbane", no=1)
    report = _pilot(c, execute=False)
    assert report["before"]["races_checked"] == 1


def test_excluded_non_trot_and_past_race():
    c = make_db()
    c.execute("UPDATE races SET discipline='gallop'")
    assert _pilot(c, execute=False)["before"]["races_checked"] == 0
    c.execute("UPDATE races SET discipline='trot',start_time_utc=?",
              ((NOW - timedelta(minutes=1)).isoformat(),))
    assert _pilot(c, execute=False)["before"]["races_checked"] == 0


@pytest.mark.parametrize("bad", [0, 13, -1, 1.4, True])
def test_invalid_max_tasks_rejected(bad):
    with pytest.raises(ValueError, match="max_tasks"):
        _pilot(make_db(), max_tasks=bad)


def test_naive_now_rejected():
    with pytest.raises(ValueError, match="timezone"):
        _pilot(make_db(), now=datetime(2026, 10, 30, 12, 0))


def test_empty_plan_still_measures_known_race():
    c = make_db()
    fundamental(c)
    market(c)
    result = _pilot(c, execute=False)
    assert result["before"]["races_checked"] == 1
    assert result["tasks_attempted"] == 0
    assert result["races_in_fixed_cohort"] == [RID]


def test_market_prefetch_expands_beyond_15_minute_scheduler_interval():
    c = make_db()
    c.execute("UPDATE races SET start_time_utc=?", ((NOW + timedelta(minutes=25)).isoformat(),))
    report = _pilot(c, execute=False)
    assert report['tasks_selected'] == 2
    assert report['task_reason_counts']['MISSING_OR_INCOMPLETE_WIN_MARKET'] == 1


def test_atg_source_diagnostic_reports_exact_runner_blocker():
    c = make_db()
    c.execute('''CREATE TABLE provider_payloads(
        provider TEXT, category TEXT, provider_raceday_key TEXT,
        race_number INTEGER, observed_at_utc TEXT, payload_json TEXT)''')
    c.execute('''INSERT INTO provider_payloads VALUES (?,?,?,?,?,?)''', (
        'atg', 'FULL_FIELD_ONLY_V1', RID, 1, NOW.isoformat(),
        json.dumps({'passed': False, 'matched_complete_runners': 2,
                    'active_runners': 3, 'reasons': ['INCOMPLETE_RUNNER_HISTORY_OR_IDENTITY'],
                    'runners': [{'selection_id': '2', 'horse_name': 'Horse 2',
                                 'schema_ok': False, 'reason': 'LIFETIME_BELOW_YEAR_TOTALS'}]}),
    ))
    report = _pilot(c, execute=False)
    d = report['race_readiness_before'][0]['atg_history_source_diagnostic']
    assert d['full_field_gate_passed'] is False
    assert d['matched_complete_runners'] == 2
    assert d['runner_issues'] == [{
        'selection_id': '2', 'horse_name': 'Horse 2',
        'reason': 'LIFETIME_BELOW_YEAR_TOTALS',
    }]


def test_atg_evidence_after_asof_is_not_leaked():
    c = make_db()
    c.execute('''CREATE TABLE provider_payloads(
        provider TEXT, category TEXT, provider_raceday_key TEXT,
        race_number INTEGER, observed_at_utc TEXT, payload_json TEXT)''')
    c.execute('INSERT INTO provider_payloads VALUES (?,?,?,?,?,?)', (
        'atg', 'FULL_FIELD_ONLY_V1', RID, 1,
        (NOW + timedelta(minutes=1)).isoformat(), json.dumps({'passed': True}),
    ))
    report = _pilot(c, execute=False)
    assert report['race_readiness_before'][0]['atg_history_source_diagnostic'] is None


def _add_atg_clock(c, observed, source_start):
    c.execute("""CREATE TABLE IF NOT EXISTS provider_payloads(
        provider TEXT, category TEXT, provider_raceday_key TEXT,
        race_number INTEGER, observed_at_utc TEXT, payload_json TEXT)""")
    c.execute("INSERT INTO provider_payloads VALUES (?,?,?,?,?,?)", (
        "atg", "FULL_FIELD_ONLY_V1", RID, 1, observed.isoformat(),
        json.dumps({
            "passed": True, "race_start_utc": source_start,
            "matched_complete_runners": 3, "active_runners": 3,
            "reasons": [], "runners": [],
        }),
    ))


def test_source_clock_earlier_than_canonical_blocks_late_market_from_ready():
    c = make_db()
    fundamental(c, now=NOW - timedelta(minutes=2))
    market(c, now=NOW)
    source_start = NOW + timedelta(minutes=3)
    _add_atg_clock(c, NOW - timedelta(minutes=2), source_start.isoformat())
    report = _pilot(c, execute=False)
    case = report["race_readiness_before"][0]
    assert case["source_clock_conservative_guard_applied"] is True
    assert case["start_clock_disagreement_seconds"] == 300
    assert case["t4_cutoff_utc"] == (NOW - timedelta(minutes=1)).isoformat()
    assert case["canonical_t4_cutoff_utc"] == (NOW + timedelta(minutes=4)).isoformat()
    assert case["history_complete_as_of_t4"] is True
    assert case["win_market_complete_as_of_t4"] is False
    assert case["all_inputs_complete_as_of_t4"] is False
    assert report["before"]["races_full_sources"] == 0
    assert report["before"]["races_with_earlier_source_clock"] == 1
    assert report["roster_pit_verified"] is False


def test_earliest_source_clock_wins_over_later_schedule_revision():
    c = make_db()
    fundamental(c, now=NOW - timedelta(minutes=2))
    market(c, now=NOW)
    first = NOW + timedelta(minutes=3)
    revised = NOW + timedelta(minutes=9)
    _add_atg_clock(c, NOW - timedelta(minutes=2), first.isoformat())
    _add_atg_clock(c, NOW - timedelta(minutes=1), revised.isoformat())
    report = _pilot(c, execute=False)
    case = report["race_readiness_before"][0]
    assert case["earliest_retained_source_start_utc"] == first.isoformat()
    assert case["atg_history_source_diagnostic"]["source_race_start_utc"] == revised.isoformat()
    assert case["all_inputs_complete_as_of_t4"] is False


def test_invalid_archived_source_clock_fails_closed():
    c = make_db()
    fundamental(c)
    market(c)
    _add_atg_clock(c, NOW, "not-an-ISO-clock")
    report = _pilot(c, execute=False)
    case = report["race_readiness_before"][0]
    assert case["atg_history_source_diagnostic"]["source_clock_invalid"] is True
    assert case["all_inputs_complete_as_of_t4"] is False
    assert report["before"]["races_full_sources"] == 0
    assert report["prospective_t4_success_proven"] is False
