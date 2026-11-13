"""The research gate must reject late inputs before invoking the model."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_model_admission_evidence import NOW, RACE, SOURCE, START
from test_model_admission_evidence import cohort as cohort_fixture

from hbi import admission_originals, cloud_run003_model
from hbi.shadow import ShadowPolicy

cohort = cohort_fixture

CUTOFF = START - timedelta(minutes=ShadowPolicy().target_minutes_to_start)


@pytest.mark.parametrize(("role", "delta", "reason"), [
    ("scratch", -1, None),
    ("scratch", 0, "INDEPENDENT_SCRATCH_AT_OR_AFTER_T4"),
    ("scratch", 1, "INDEPENDENT_SCRATCH_AT_OR_AFTER_T4"),
    ("registry", 1, "REGISTRY_ORIGINAL_AT_OR_AFTER_T4"),
    ("history", 1, "ATG_HISTORY_ORIGINAL_AT_OR_AFTER_T4"),
    ("model", -1, None),
    ("model", 0, "MODEL_COMPUTATION_AT_OR_AFTER_T4"),
    ("model", 1, "MODEL_COMPUTATION_AT_OR_AFTER_T4"),
])
def test_cutoff_boundaries(cohort, monkeypatch, role, delta, reason):
    store, proofs, scratch = cohort
    stamp = CUTOFF + timedelta(seconds=delta)
    pins = admission_originals._REVIEWED_RECEIPTS
    if role == "scratch":
        scratch = replace(scratch, observed_at=stamp)
        pins |= {("INDEPENDENT_SCRATCH", scratch.original_uri, scratch.original_sha256, stamp)}
    elif role == "registry":
        proofs = (replace(proofs[0], observed_at=stamp), proofs[1])
    elif role == "history":
        proofs = (replace(proofs[0], history_completed_at=stamp), proofs[1])
    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", pins)
    if reason:
        monkeypatch.setattr(cloud_run003_model, "run_and_persist_fundamental",
                            lambda *a, **kw: pytest.fail("model invoked after rejection"))
    result = cloud_run003_model.assess_and_run(
        store, SOURCE, now=stamp, identity_evidence=proofs, scratch_evidence=(scratch,),
    )
    record = result["records"][0]
    if reason:
        assert reason in record["reasons"]
        assert result["p_win_computed"] == 0
        assert store.fetch_table("predictions") == []
        assert any(item["reason"] == reason and item["cutoff_utc"] == CUTOFF.isoformat()
                   for item in record["timing_rejections"])
    else:
        assert result["p_win_computed"] == 1
        assert len(store.fetch_table("predictions")) == 2


@pytest.mark.parametrize(("fault", "reason"), [
    ("unknown_start", "CANONICAL_START_CLOCK_INVALID"),
    ("naive_start", "CANONICAL_START_CLOCK_INVALID"),
    ("conflict", "FUNDAMENTAL_RACE_START_CONFLICT"),
    ("missing_stamp", "FUNDAMENTAL_SNAPSHOT_CLOCK_INVALID"),
    ("incomplete", "FULL_FIELD_FUNDAMENTAL_COHORT_MISSING"),
])
def test_invalid_timing_and_field_never_invoke_model(cohort, monkeypatch, fault, reason):
    store, proofs, scratch = cohort
    with store.connect() as db:
        if fault in {"unknown_start", "naive_start"}:
            value = "" if fault == "unknown_start" else "2026-11-12T12:05:00"
            db.execute("UPDATE races SET start_time_utc=? WHERE race_id=?", (value, RACE))
        elif fault == "conflict":
            row = db.execute("SELECT payload_json FROM provider_payloads WHERE payload_id='test-only'").fetchone()
            payload = json.loads(row[0])
            payload["race_start_utc"] = (START + timedelta(minutes=1)).isoformat()
            db.execute("UPDATE provider_payloads SET payload_json=? WHERE payload_id='test-only'",
                       (json.dumps(payload),))
        elif fault == "missing_stamp":
            db.execute("UPDATE runner_fundamental_snapshots SET observed_at_utc='' WHERE snapshot_id='1'")
        else:
            db.execute("DELETE FROM runner_fundamental_snapshots WHERE snapshot_id='1'")
    monkeypatch.setattr(cloud_run003_model, "run_and_persist_fundamental",
                        lambda *a, **kw: pytest.fail("model invoked after rejection"))
    result = cloud_run003_model.assess_and_run(
        store, SOURCE, now=NOW, identity_evidence=proofs, scratch_evidence=(scratch,),
    )
    assert reason in result["records"][0]["reasons"]
    assert result["p_win_computed"] == 0
    assert store.fetch_table("predictions") == []
