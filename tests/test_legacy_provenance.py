"""Frozen replay: original market snapshot proves old-provenance discrepancy."""
import hashlib
import json
import sqlite3

from hbi.decision import DecisionPolicy
from hbi.engine import CombinationPolicy, evaluate_race
from hbi.legacy_provenance import classify_legacy_replay

SOURCE_TIME = "2026-10-09T17:48:00+00:00"
FUND = {"1": 0.55, "2": 0.45}
ORIGINAL_ODDS = {"1": 2.6, "2": 3.4}
LATE_ODDS = {"1": 8.0, "2": 1.5}
COMBO = {
    "fundamental_weight": 1.0, "market_weight": 1.0,
    "material_conflict_threshold": 20.0,
}
POLICY = {"minimum_edge": 0.05, "safety_margin": 0.05}


def _db(tmp_path, *, provenance_odds, include_original=True):
    path = tmp_path / "history.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE shadow_decision_runs (
                decision_run_id TEXT PRIMARY KEY,
                race_id TEXT, product TEXT,
                source_market_observed_at_utc TEXT,
                fundamental_probabilities_json TEXT,
                combined_probabilities_json TEXT,
                model_market_conflict_score REAL
            );
            CREATE TABLE decision_provenance (
                decision_run_id TEXT PRIMARY KEY,
                market_odds_json TEXT,
                combination_policy_json TEXT,
                decision_policy_json TEXT,
                recorded_at_utc TEXT
            );
            CREATE TABLE provider_market_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                race_id TEXT, product TEXT, selection_key TEXT,
                observed_at_utc TEXT, odds_decimal REAL
            );
        """)
        result = evaluate_race(
            fundamental_probabilities=FUND,
            market_decimal_odds=ORIGINAL_ODDS,
            executable_prices=ORIGINAL_ODDS,
            combination_policy=CombinationPolicy(**COMBO),
            decision_policy=DecisionPolicy(**POLICY),
        )
        conn.execute(
            "INSERT INTO shadow_decision_runs VALUES (?,?,?,?,?,?,?)",
            ("frozen-one", "TEST:race:1", "V", SOURCE_TIME,
             json.dumps(FUND), json.dumps(result.combined_probabilities),
             result.model_market_conflict_score),
        )
        conn.execute(
            "INSERT INTO decision_provenance VALUES (?,?,?,?,?)",
            ("frozen-one", json.dumps(provenance_odds), json.dumps(COMBO),
             json.dumps(POLICY), "2026-10-09T17:57:30+00:00"),
        )
        if include_original:
            for selection, price in ORIGINAL_ODDS.items():
                conn.execute(
                    "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?,?)",
                    (f"original-{selection}", "TEST:race:1", "V",
                     selection, SOURCE_TIME, price),
                )
    return path


def _checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_later_market_in_provenance_can_be_reconstructed_without_mutation(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    before = _checksum(path)
    report = classify_legacy_replay(path)
    assert _checksum(path) == before
    assert report["status"] == "DIAGNOSTIC_ONLY_NOT_PRODUCTION_CLEARANCE"
    assert report["total_decisions"] == 1
    assert report["provenance_eligible_checked"] == 1
    assert report["legacy_source_reconstructed"] == 1
    assert report["unreconciled"] == 0
    assert report["saved_provenance_replay_pass"] == 0
    assert report["exceptions"][0]["classification"] == (
        "LEGACY_LATE_PROVENANCE_SOURCE_RECONSTRUCTED"
    )
    assert report["existing_integrity_audit_overridden"] is False


def test_matching_provenance_has_no_exception(tmp_path):
    path = _db(tmp_path, provenance_odds=ORIGINAL_ODDS)
    report = classify_legacy_replay(path)
    assert report["saved_provenance_replay_pass"] == 1
    assert report["legacy_source_reconstructed"] == 0
    assert report["exceptions"] == []


def test_missing_original_snapshot_cannot_be_claimed_reconstructed(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS, include_original=False)
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1
    assert report["exceptions"][0]["classification"] == "UNRECONCILED"
    assert report["exceptions"][0]["source_field_complete"] is False


def test_incomplete_original_field_cannot_be_claimed_reconstructed(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM provider_market_snapshots WHERE selection_key='2'")
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1


def test_source_timestamp_does_not_fallback_to_newer_market(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS, include_original=False)
    with sqlite3.connect(path) as conn:
        for key, odds in ORIGINAL_ODDS.items():
            conn.execute(
                "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?,?)",
                (f"later-{key}", "TEST:race:1", "V", key,
                 "2026-10-09T17:49:00+00:00", odds),
            )
    report = classify_legacy_replay(path)
    assert report["unreconciled"] == 1
    assert report["legacy_source_reconstructed"] == 0


def test_unpriced_inactive_original_source_reconstructed(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?,?)",
            ("unpriced-3", "TEST:race:1", "V", "3", SOURCE_TIME, -0.02),
        )
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 1
    assert report["unreconciled"] == 0
    assert report["exceptions"][0]["excluded_unpriced_nonactive_selections"] == ["3"]


def test_extra_priced_selection_cannot_be_excluded(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?,?)",
            ("priced-3", "TEST:race:1", "V", "3", SOURCE_TIME, 8.0),
        )
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1


def test_unknown_market_marker_cannot_be_excluded(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO provider_market_snapshots VALUES (?,?,?,?,?,?)",
            ("unknown-3", "TEST:race:1", "V", "3", SOURCE_TIME, -0.01),
        )
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1


def test_invalid_active_quote_cannot_be_suppressed(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE provider_market_snapshots SET odds_decimal=-0.02 WHERE selection_key='2'"
        )
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1


def test_evidence_manifest_hashes_are_deterministic_and_source_is_unchanged(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    original_sha256 = _checksum(path)
    first = classify_legacy_replay(path)
    second = classify_legacy_replay(path)
    assert first["source_database_sha256"] == original_sha256
    assert second["source_database_sha256"] == original_sha256
    assert first["source_database_unchanged"] is True
    assert _checksum(path) == original_sha256
    for field in ("frozen_inputs_sha256", "exact_source_market_sha256",
                  "attached_provenance_sha256"):
        assert first["exceptions"][0][field] == second["exceptions"][0][field]
        assert len(first["exceptions"][0][field]) == 64
    assert first["exceptions"][0]["provenance_timestamp_strictly_later"] is True
    assert first["exceptions"][0]["original_source_replays_frozen"] is True


def test_same_instant_provenance_is_not_mislabeled_late(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE decision_provenance SET recorded_at_utc=?", (SOURCE_TIME,)
        )
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1
    item = report["exceptions"][0]
    assert item["classification"] == "UNRECONCILED"
    assert item["original_source_replays_frozen"] is True
    assert item["provenance_timestamp_strictly_later"] is False


def test_naive_provenance_time_cannot_prove_late_attachment(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE decision_provenance SET recorded_at_utc=?",
            ("2026-10-09T17:57:30",),
        )
    report = classify_legacy_replay(path)
    assert report["legacy_source_reconstructed"] == 0
    assert report["unreconciled"] == 1
    assert report["exceptions"][0]["provenance_timestamp_strictly_later"] is False


def test_missing_exact_source_does_not_emit_fake_market_hash(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS, include_original=False)
    report = classify_legacy_replay(path)
    assert report["unreconciled"] == 1
    assert report["exceptions"][0]["exact_source_market_sha256"] is None
    assert report["exceptions"][0]["original_source_replays_frozen"] is False


def test_unparseable_policy_does_not_crash_forensic_hashing(tmp_path):
    path = _db(tmp_path, provenance_odds=LATE_ODDS)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE decision_provenance SET combination_policy_json=?",
            ("{bad-json",),
        )
    report = classify_legacy_replay(path)
    assert report["unreconciled"] == 1
    assert report["legacy_source_reconstructed"] == 0
    assert len(report["exceptions"][0]["attached_provenance_sha256"]) == 64
