"""PR187 owner review: late SQLite commits must not enter prospective scoring.

Synthetic fixtures only. The four scoring tests intentionally expose the
missing downstream T-4 receipt gate; they must pass before merge approval.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from hbi.observatory import materialize_race_evaluations
from hbi.storage import SQLiteStore
from hbi.t4_evidence import classify_t4_receipt

RACE_ID = "r-pr187-late-commit"
RACE_START = "2026-11-11T14:00:00+00:00"
CUTOFF = "2026-11-11T13:56:00+00:00"
FROZEN_CREATED = "2026-11-11T13:55:55+00:00"
ACTUAL_COMMIT_READBACK = "2026-11-11T13:56:05+00:00"
MODEL = "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL"
ROOT = Path(__file__).parents[1]


def _real_schema_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(ROOT / "db" / "schema.sql")
    store.upsert_race({
        "race_id": RACE_ID, "race_date": "2026-11-11",
        "country": "NO", "track": "Synthetic",
        "race_no": 1, "start_time_utc": RACE_START,
        "discipline": "trot", "distance_m": 2100,
        "start_method": "auto", "race_class": None,
        "created_at_utc": "2026-11-11T09:00:00+00:00",
    })
    return store


def _late_receipt(row: dict[str, object]) -> dict[str, object]:
    sources = {
        name: {
            "source_uri": f"https://www.rikstoto.no/api/{name.lower()}",
            "response_completed_at_utc": "2026-11-11T13:55:40+00:00",
            "body_sha256": "a" * 64,
        }
        for name in ("WIN", "STARTS", "SCRATCHED")
    }
    return classify_t4_receipt(
        race_id=RACE_ID,
        race_start_utc=RACE_START,
        target_minutes=4.0,
        model_version=MODEL,
        decision_row=row,
        sources=sources,
        model_finished_at_utc="2026-11-11T13:55:50+00:00",
        decision_calculated_at_utc="2026-11-11T13:55:57+00:00",
        persist_started_at_utc="2026-11-11T13:55:58+00:00",
        persist_confirmed_at_utc=ACTUAL_COMMIT_READBACK,
    )


def _frozen_row(store: SQLiteStore, status: str) -> dict[str, object]:
    signal = status in {"PASS", "WATCH", "T4_PENDING_ATTESTATION"}
    store.insert_shadow_decision_run({
        "decision_run_id": f"late-{status}",
        "race_id": RACE_ID,
        "provider_raceday_key": "MO_NR_2026-11-11",
        "product": "V",
        "created_at_utc": FROZEN_CREATED,
        "race_start_time_utc": RACE_START,
        "decision_status": status,
        "reason": "SHADOW_BET_SIGNAL_PENDING_END_TO_END_PROOF"
        if status == "T4_PENDING_ATTESTATION" else None,
        "shadow_model_version": MODEL,
        "fundamental_model_version": "FUNDAMENTAL_CHAMPION_V1_1",
        "source_market_observed_at_utc": "2026-11-11T13:55:40+00:00",
        "target_minutes_to_start": 4.0,
        "actual_minutes_to_start": 245 / 60,
        "execution_latency_seconds": -5.0,
        "field_size": 2 if signal else None,
        "fundamental_probabilities_json":
            json.dumps({"1": 0.7, "2": 0.3}) if signal else None,
        "market_probabilities_json":
            json.dumps({"1": 0.4, "2": 0.6}) if signal else None,
        "combined_probabilities_json":
            json.dumps({"1": 0.55, "2": 0.45}) if signal else None,
        "ticket_count": 0,
    })
    return next(
        row for row in store.fetch_table("shadow_decision_runs")
        if row["decision_run_id"] == f"late-{status}"
    )


@pytest.mark.parametrize("status", [
    "PASS", "WATCH", "NOT_EXECUTABLE", "T4_PENDING_ATTESTATION",
])
def test_late_commit_rejected_by_t4_receipt_for_every_status(tmp_path, status):
    store = _real_schema_store(tmp_path)
    row = _frozen_row(store, status)
    receipt = _late_receipt(row)
    assert receipt["cutoff_utc"] == CUTOFF
    assert receipt["decision_persisted_before_t4"] is False
    assert "PERSIST_CONFIRMED_AT_OR_AFTER_T4" in receipt["reasons"]
    assert receipt["shadow_executable"] is False
    assert receipt["pit_certified"] is False
    assert store.get_shadow_decision_run(f"late-{status}") == row
    assert store.fetch_table("shadow_tickets") == []


@pytest.mark.parametrize("status", [
    "PASS", "WATCH", "NOT_EXECUTABLE", "T4_PENDING_ATTESTATION",
])
def test_late_or_unattested_row_not_scored_as_prospective(
    tmp_path, status,
):
    """RED acceptance: downstream scorer must use post-commit, not created_at."""
    store = _real_schema_store(tmp_path)
    row = _frozen_row(store, status)
    receipt = _late_receipt(row)
    assert receipt["decision_persisted_before_t4"] is False
    # This is the same metadata channel the watcher uses after commit.
    with store.connect() as db:
        db.execute(
            "INSERT INTO system_run_manifests "
            "(run_id,run_type,started_at_utc,finished_at_utc,status,metadata_json) "
            "VALUES (?,?,?,?,?,?)",
            (
                f"owner-review-{status}", "WATCHER",
                "2026-11-11T13:55:00+00:00",
                "2026-11-11T13:56:06+00:00",
                "OK", json.dumps({"t4_attempts": [receipt]}),
            ),
        )
    store.settle_outcome(
        race_id=RACE_ID,
        winner_selection_id="1",
        settled_at=datetime(2026, 11, 11, 14, 30, tzinfo=UTC),
    )
    scored = materialize_race_evaluations(
        store, date(2026, 11, 11),
        created_at=datetime(2026, 11, 11, 15, tzinfo=UTC),
    )
    # No prospective evaluation from a late/unattested decision row.
    assert scored == 0
    assert store.fetch_table("race_research_evaluations") == []
