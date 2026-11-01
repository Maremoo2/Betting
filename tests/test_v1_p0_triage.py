"""V1 P0 forensic tests use synthetic shadow tickets, never live payouts."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hbi.storage import SQLiteStore
from hbi.v1_p0_triage import (
    build_triage,
    classify_missing_replay_provenance,
    inspect_unsettled_outcomes,
)

SCHEMA = Path(__file__).parents[1] / "db" / "schema.sql"
T0 = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)
RACE = "TEST:P0:1"


def _store(tmp_path):
    db = tmp_path / "checkpointed-hbi.sqlite"
    store = SQLiteStore(db)
    store.initialize(SCHEMA)
    store.upsert_race({
        "race_id": RACE, "race_date": "2026-10-26", "country": "NO",
        "track": "Synthetic P0", "race_no": 1,
        "start_time_utc": T0.isoformat(),
        "discipline": "trot", "distance_m": 2100, "start_method": "auto",
        "race_class": None, "created_at_utc": (T0 - timedelta(hours=2)).isoformat(),
    })
    store.settle_outcome(
        race_id=RACE, winner_selection_id="1",
        settled_at=T0 + timedelta(hours=2),
    )
    return store, db


def _ticket(store, ticket_id="unsettled-1", status="SHADOW_BET", selection="2",
            product="V", selections=None):
    store.create_shadow_ticket({
        "ticket_id": ticket_id, "dedupe_key": ticket_id,
        "created_at_utc": (T0 - timedelta(minutes=4)).isoformat(),
        "decision_time_utc": (T0 - timedelta(minutes=4)).isoformat(),
        "race_id": RACE, "provider": "rikstoto",
        "provider_raceday_key": "BJ_NR_2026-10-26", "product": product,
        "decision": "BET", "status": status,
        "selections_json": selections if selections is not None
        else json.dumps([selection]),
        "stake_nok": 25.0, "number_of_rows": 1,
        "model_version": "SYNTHETIC_SHADOW_ONLY",
    })


def _filehash(db):
    return hashlib.sha256(db.read_bytes()).hexdigest()


def test_original_snapshot_stays_byte_identical_while_p0_remains_blocked(tmp_path):
    store, db = _store(tmp_path)
    _ticket(store)
    before = _filehash(db)
    triage = build_triage(db, now=T0 + timedelta(hours=48))
    assert triage["status"] == "DIAGNOSTIC_ONLY_P0_NOT_CLEARED"
    assert triage["source_database_sha256"] == before == _filehash(db)
    assert triage["source_database_unchanged"] is True
    assert triage["replay"]["original_v1_audit_overridden"] is False
    assert triage["replay"]["frozen_probabilities_or_policies_modified"] is False
    assert triage["settlement"]["overdue_unsettled_with_stored_outcome"] == 1
    assert triage["settlement"]["tickets"][0]["ticket_id"] == "unsettled-1"
    assert triage["settlement"]["tickets"][0]["stored_winner_matches_selection"] is False
    assert triage["settlement"]["tickets"][0]["settlement_or_refund_authorized"] is False
    assert triage["model_or_bet_authority"] is False
    assert not triage["prospective_pit_validated"]
    assert not triage["v1_system_audit_failure_overridden"]
    assert store.fetch_table("shadow_tickets")[0]["status"] == "SHADOW_BET"


def test_stored_winner_matching_ticket_never_grants_winner_payout(tmp_path):
    store, db = _store(tmp_path)
    _ticket(store, selection="1")
    report = inspect_unsettled_outcomes(db, now=T0 + timedelta(days=2))
    ticket = report["tickets"][0]
    assert ticket["stored_winner_matches_selection"] is True
    assert ticket["original_complete_result_attested_by_this_report"] is False
    assert ticket["original_dividend_attested_by_this_report"] is False
    assert ticket["settlement_or_refund_authorized"] is False


def test_recent_outcome_does_not_trigger_overdue(tmp_path):
    store, db = _store(tmp_path)
    _ticket(store)
    report = inspect_unsettled_outcomes(db, now=T0 + timedelta(hours=23))
    assert report["overdue_unsettled_with_stored_outcome"] == 0
    assert report["not_yet_due_with_stored_outcome"] == 1


@pytest.mark.parametrize("status", ["NOT_EXECUTABLE", "SETTLED"])
def test_non_executable_or_settled_ticket_cannot_be_flagged_for_autosettlement(
    tmp_path, status,
):
    store, db = _store(tmp_path)
    if status == "NOT_EXECUTABLE":
        _ticket(store, status=status)
    else:
        _ticket(store)
        store.settle_shadow_ticket(
            ticket_id="unsettled-1", settled_at=T0 + timedelta(hours=4),
            gross_return_nok=0, net_pnl_nok=-25,
            settlement_source_uri="fixture://synthetic",
            closing_price=None, clv=None, result={"won": False},
        )
    report = inspect_unsettled_outcomes(db, now=T0 + timedelta(days=2))
    assert report["overdue_unsettled_with_stored_outcome"] == 0


def test_unsupported_multi_selection_is_not_automatically_interpreted_as_win(tmp_path):
    store, db = _store(tmp_path)
    _ticket(store, selections='["1", "2"]', product="V")
    report = inspect_unsettled_outcomes(db, now=T0 + timedelta(days=2))
    assert report["tickets"][0]["selected_runner"] is None
    assert report["tickets"][0]["stored_winner_matches_selection"] is None


def test_missing_original_race_clock_fails_closed(tmp_path):
    store, db = _store(tmp_path)
    _ticket(store)
    with store.connect() as c:
        c.execute("UPDATE races SET start_time_utc='nonsense' WHERE race_id=?", (RACE,))
    report = inspect_unsettled_outcomes(db, now=T0 + timedelta(days=2))
    assert report["malformed_original_race_clock"] == 1
    assert report["overdue_unsettled_with_stored_outcome"] == 1
    assert not report["tickets"][0]["settlement_or_refund_authorized"]


@pytest.mark.parametrize("bad_grace", [-1.0, float("nan"), float("inf")])
def test_bad_or_faked_grace_window_is_rejected(tmp_path, bad_grace):
    _, db = _store(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        inspect_unsettled_outcomes(db, now=T0, grace_hours=bad_grace)


def test_naive_clock_is_rejected_and_stored_data_untouched(tmp_path):
    _, db = _store(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        inspect_unsettled_outcomes(db, now=datetime(2026, 10, 28, 18, 0))


def test_multiple_overdue_tickets_report_each_without_bookkeeping(tmp_path):
    store, db = _store(tmp_path)
    _ticket(store, ticket_id="t1", selection="1")
    _ticket(store, ticket_id="t2", selection="2")
    report = inspect_unsettled_outcomes(db, now=T0 + timedelta(days=2))
    assert report["overdue_unsettled_with_stored_outcome"] == 2
    assert [x["ticket_id"] for x in report["tickets"]] == ["t1", "t2"]
    assert all(x["settlement_or_refund_authorized"] is False for x in report["tickets"])



def test_477_style_skips_are_split_by_frozen_decision_status_not_silently_passed(
    tmp_path,
):
    store, db = _store(tmp_path)
    for decision_id, status, with_probabilities in (
        ("blocked-no-input", "NOT_EXECUTABLE", False),
        ("unpriced-source-missing", "PASS", True),
        ("watch-source-missing", "WATCH", True),
    ):
        store.insert_shadow_decision_run({
            "decision_run_id": decision_id,
            "race_id": RACE,
            "provider_raceday_key": "BJ_NR_2026-10-26",
            "product": "V",
            "created_at_utc": (T0 - timedelta(minutes=4)).isoformat(),
            "race_start_time_utc": T0.isoformat(),
            "decision_status": status,
            "reason": "SYNTHETIC",
            "shadow_model_version": "SYNTHETIC_REPLAY_ONLY",
            "target_minutes_to_start": 4.0,
            "fundamental_probabilities_json": (
                json.dumps({"1": 0.6, "2": 0.4}) if with_probabilities else None
            ),
            "combined_probabilities_json": (
                json.dumps({"1": 0.55, "2": 0.45}) if with_probabilities else None
            ),
        })
    result = classify_missing_replay_provenance(db)
    assert result["total_decisions_examined"] == 3
    assert result["incomplete_replay_evidence"] == 3
    assert result["eligible_with_original_saved_provenance"] == 0
    assert result["incomplete_evidence_for_priced_or_watched_decision"] == 2
    assert result["reason_by_frozen_status"] == {
        "NOT_EXECUTABLE:FROZEN_FUNDAMENTAL_OR_COMBINED_DISTRIBUTION_ABSENT": 1,
        "PASS:NO_FROZEN_MARKET_PROVENANCE": 1,
        "WATCH:NO_FROZEN_MARKET_PROVENANCE": 1,
    }
    assert result["missing_historical_evidence_inferred_as_pass"] is False
    before = _filehash(db)
    triage = build_triage(db, now=T0 + timedelta(days=2))
    assert triage["source_database_sha256"] == before == _filehash(db)
    assert triage["replay_coverage"]["incomplete_replay_evidence"] == 3
    assert triage["replay"]["incomplete_provenance_skipped"] == 3
    assert triage["replay_coverage"]["shadow_executable_status_granted"] is False

