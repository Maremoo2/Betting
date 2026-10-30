"""Tests for restored-state E2E: no audit waiver or file mutation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p0_archive_readonly_e2e.py"
SPEC = importlib.util.spec_from_file_location("p0_archive_readonly_e2e", SCRIPT)
assert SPEC and SPEC.loader
e2e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e2e)

SOURCE = "2026-10-09T17:48:00+00:00"
LATER = "2026-10-09T17:57:00+00:00"
ORIGINAL = {"1": 2.5, "2": 4.0}
ATTACHED = {"1": 3.2, "2": 2.4}
RACE = "TEST:RACE:1"


def fixture_db(tmp_path: Path) -> Path:
    path = tmp_path / "read-only.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE shadow_decision_runs (
                decision_run_id TEXT PRIMARY KEY,
                race_id TEXT, product TEXT,
                source_market_observed_at_utc TEXT,
                market_probabilities_json TEXT,
                fundamental_probabilities_json TEXT
            );
            CREATE TABLE decision_provenance (
                decision_run_id TEXT PRIMARY KEY, market_odds_json TEXT,
                recorded_at_utc TEXT
            );
            CREATE TABLE provider_market_snapshots (
                race_id TEXT, product TEXT, observed_at_utc TEXT,
                selection_key TEXT, odds_decimal REAL
            );
            CREATE TABLE shadow_tickets (
                ticket_id TEXT PRIMARY KEY,race_id TEXT,
                provider_raceday_key TEXT,status TEXT,selections_json TEXT,
                stake_nok REAL,settled_at_utc TEXT,net_pnl_nok REAL
            );
            CREATE TABLE outcomes (race_id TEXT, winner_selection_id TEXT);
            CREATE TABLE provider_payloads (
                provider_raceday_key TEXT, category TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO shadow_decision_runs VALUES (?,?,?,?,?,?)",
            ("decision1", RACE, "V", SOURCE,
             json.dumps(e2e.normalize(ORIGINAL)),
             json.dumps({"1": 0.5, "2": 0.5})),
        )
        conn.execute(
            "INSERT INTO decision_provenance VALUES (?,?,?)",
            ("decision1", json.dumps(ATTACHED), LATER),
        )
        for when, prices in ((SOURCE, ORIGINAL), (LATER, ATTACHED)):
            for key, price in prices.items():
                conn.execute(
                    "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?)",
                    (RACE, "V", when, key, price),
                )
        conn.execute(
            "INSERT INTO shadow_tickets VALUES (?,?,?,?,?,?,?,?)",
            ("ticket1", RACE, "TEST_KEY", "SHADOW_BET", '["2"]', 25, None, None),
        )
        conn.execute("INSERT INTO outcomes VALUES (?,?)", (RACE, "1"))
    return path


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verified_historical_case_is_not_p0_clearance(tmp_path):
    path = fixture_db(tmp_path)
    before = file_sha(path)
    result = e2e.inspect(path)
    assert file_sha(path) == before
    assert result["source_database_sha256"] == before
    assert result["source_database_unchanged"] is True
    assert result["p0_status"] == "BLOCKED"
    assert result["market_replay_mismatches"] == 1
    assert result["original_source_and_late_provenance_confirmed"] == 1
    assert result["unreconciled_market_replays"] == 0
    assert result["exceptions"][0]["classification"] == (
        "EXACT_SOURCE_AND_LATE_ATTACHMENT_CORROBORATED"
    )
    assert result["open_shadow_tickets"][0]["archived_official_result_payloads"] == 0
    assert result["open_shadow_tickets"][0]["recorded_pnl"] is None
    assert result["real_money_authority"] is False
    assert result["model_promotion_authority"] is False
    assert e2e.inspect(path)["report_sha256"] == result["report_sha256"]


def test_unpriced_extra_original_is_accepted_as_nonactive_only(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?)",
            (RACE, "V", SOURCE, "3", -0.02),
        )
    result = e2e.inspect(path)
    assert result["original_source_and_late_provenance_confirmed"] == 1
    assert result["exceptions"][0]["excluded_inactive_unpriced_keys"] == ["3"]


@pytest.mark.parametrize("price", [2.1, -0.01, 0.0, float("nan")])
def test_unexpected_offfield_price_blocks_reconstruction(tmp_path, price):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?)",
            (RACE, "V", SOURCE, "3", price),
        )
    result = e2e.inspect(path)
    assert result["market_replay_mismatches"] == 1
    assert result["unreconciled_market_replays"] == 1


def test_incomplete_active_original_never_reconstructed(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "DELETE FROM provider_market_snapshots WHERE observed_at_utc=? "
            "AND selection_key='2'", (SOURCE,),
        )
    assert e2e.inspect(path)["unreconciled_market_replays"] == 1


@pytest.mark.parametrize("time", [SOURCE, "2026-10-09T17:57:00", "not-a-time"])
def test_provenance_without_proven_later_timestamp_blocks(tmp_path, time):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE decision_provenance SET recorded_at_utc=?", (time,))
    result = e2e.inspect(path)
    assert result["exceptions"][0]["provenance_recorded_strictly_later"] is False
    assert result["unreconciled_market_replays"] == 1


def test_missing_later_cohort_rejects_corrupt_provenance_explanation(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM provider_market_snapshots WHERE observed_at_utc=?", (LATER,))
    result = e2e.inspect(path)
    assert result["exceptions"][0]["later_attached_cohort_at_utc"] is None
    assert result["unreconciled_market_replays"] == 1


def test_malformed_market_odds_is_skipped_not_manufactured_pass(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE decision_provenance SET market_odds_json=?", ("broken",))
    result = e2e.inspect(path)
    assert result["checked_market_replays"] == 0
    assert result["skipped_decisions"] == 1
    assert result["market_replay_mismatches"] == 0
    assert result["p0_status"] == "BLOCKED"


def test_audit_reference_warns_when_raceday_state_differs(tmp_path):
    path = fixture_db(tmp_path)
    audit = tmp_path / "external-audit.json"
    audit.write_text(
        json.dumps({
            "runtime_replay_parity": {
                "checked_decisions": 1,
                "skipped_decisions": 1,
                "status": "FAIL",
                "mismatches": [{"decision_run_id": "decision1"}],
            },
        }),
        encoding="utf-8",
    )
    report = e2e.inspect(path, audit)
    assert report["audit_reference"]["audit_mismatch_ids_match_state"] is True
    assert report["audit_reference"]["exact_same_decision_denominator"] is False
    assert report["p0_status"] == "BLOCKED"


def test_extra_official_payload_not_claimed_valid_settlement(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO provider_payloads VALUES (?,?)",
            ("TEST_KEY", "OFFICIAL_COMPLETE_RESULTS"),
        )
    report = e2e.inspect(path)
    assert report["open_shadow_tickets"][0]["archived_official_result_payloads"] == 1
    assert report["open_shadow_tickets"][0]["settlement_authority"] is False
    assert report["p0_status"] == "BLOCKED"
