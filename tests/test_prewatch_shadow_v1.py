from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from betting.v33 import POLICY_HASH, evaluate
from hbi.prewatch_shadow_v1 import (
    append, fit, negative_col, power, read_ledger, report, score, validate_decision,
    validate_model,
)

ROOT = Path(__file__).parents[1]


def _entry():
    original = json.loads((ROOT / "examples/betting-v33.json").read_text())
    original["decision_time"] = "2026-10-10T12:56:00+00:00"
    original["race_start"] = "2026-10-10T13:00:00+00:00"
    original["fundamental"]["observed_at"] = "2026-10-10T12:50:00+00:00"
    original["fundamental"]["priced_at"] = "2026-10-10T12:55:00+00:00"
    for market in [original["decision_snapshot"]["WIN"],
                   *original["decision_snapshot"]["collective"].values(),
                   original["place"]["snapshot"]]:
        market["observed_at"] = "2026-10-10T12:55:50+00:00"
    original["place"]["observed_at"] = "2026-10-10T12:50:00+00:00"
    original["place"]["priced_at"] = "2026-10-10T12:55:00+00:00"
    original["batch"] = {
        "mode": "PROSPECTIVE_BLIND", "batch_id": "test-1",
        "policy_hash": POLICY_HASH, "registered_at": "2026-10-09T00:00:00+00:00",
    }
    frozen = evaluate(original)
    return {
        "race_id": "race", "product": "V4", "v3_report": frozen,
        "recorded_at": "2026-10-10T12:56:01+00:00",
        "evidence": {
            "WIN": {
                "source_uri": "rikstoto://win", "captured_at": "2026-10-10T12:55:55+00:00"
            },
            "COL": {
                "source_uri": "rikstoto://col", "captured_at": "2026-10-10T12:55:55+00:00"
            },
        },
    }


def test_record_v3_provenance_full_field_and_outcome(tmp_path):
    entry = _entry()
    decision = validate_decision(entry)
    assert decision["pit_eligible"]
    assert decision["v3_policy_hash"] == POLICY_HASH
    assert abs(sum(decision["p_win"].values()) - 1) < 1e-12
    ledger = tmp_path / "ledger.jsonl"
    key = decision["race_id"] + "|" + decision["product"]
    append(ledger, "decision", key, decision)
    append(ledger, "decision", key, decision)  # idempotent
    assert len(read_ledger(ledger)) == 1
    append(ledger, "outcome", key, {
        "winner": "1", "race_id": "race", "product": "V4",
        "result_at": "2026-10-10T14:00:00+00:00",
        "scheduled_start": "2026-10-10T13:00:00+00:00",
        "official_win_dividend": 3.5, "official_source_uri": "rikstoto://result",
    })
    summary = report(ledger)
    assert summary["models"]["win_raw"]["n_unique_races"] == 1
    assert summary["n_decisions"] == 1


def test_late_provider_evidence_excluded():
    entry = _entry()
    entry["evidence"]["WIN"]["captured_at"] = "2026-10-10T13:10:00+00:00"
    decision = validate_decision(entry)
    assert not decision["pit_eligible"]
    assert "WIN_NOT_AVAILABLE_AT_DECISION" in decision["flags"]


def test_missing_collective_source_is_not_accepted():
    entry = _entry()
    del entry["evidence"]["COL"]["source_uri"]
    assert "COL_MISSING_SOURCE_CAPTURE" in validate_decision(entry)["flags"]


def test_mutation_rejected(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    append(ledger, "decision", "race|V4", {"a": 1})
    with pytest.raises(ValueError, match="overwritten"):
        append(ledger, "decision", "race|V4", {"a": 2})
    ledger.write_text(ledger.read_text().replace('"a":1', '"a":9'))
    with pytest.raises(ValueError, match="checksum"):
        read_ledger(ledger)


def test_negative_col_and_calibration_are_full_field():
    win = {"1": 0.6, "2": 0.3, "3": 0.1}
    col = {"1": 0.4, "2": 0.4, "3": 0.2}
    adjusted = negative_col(win, col, 0.5)
    assert adjusted["1"] < win["1"]
    assert adjusted["2"] > win["2"]
    assert abs(sum(adjusted.values()) - 1) < 1e-12
    assert abs(sum(power(win, 1.1).values()) - 1) < 1e-12
    assert score(adjusted, "2")["log_loss"] > 0


def test_fitted_weights_locked_and_not_reused_on_development():
    template = validate_decision(_entry())
    records = []
    for i in range(12):
        dt = (datetime(2026, 10, 10, tzinfo=timezone.utc)
              + timedelta(days=i)).isoformat()
        row = {
            "race_id": f"race-{i}", "pit_eligible": True, "decision_at": dt,
            "scheduled_start": dt, "outcome_at": (
                datetime(2026, 10, 10, tzinfo=timezone.utc)
                + timedelta(days=i, hours=2)).isoformat(),
            "winner": "1" if i % 2 else "2",
            "p_win": template["p_win"], "p_col": template["p_col"],
        }
        records.append(row)
    model = fit(records, "2026-11-10T00:00:00+00:00", minimum=8)
    validate_model(model)
    assert model["train_n"] == 8 and model["validation_n"] == 4
    tampered = deepcopy(model)
    tampered["negative_col_penalty"] = 9
    with pytest.raises(ValueError, match="changed"):
        validate_model(tampered)
    with pytest.raises(ValueError, match="insufficient"):
        fit(records[:3], "2026-11-10T00:00:00+00:00", minimum=8)
