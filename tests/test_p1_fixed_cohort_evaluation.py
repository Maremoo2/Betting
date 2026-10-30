"""P1 preregistered denominator and three-way paired-scoring research gates."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
from test_prospective_eval_gate import row

SOURCE = Path(__file__).resolve().parents[1] / "scripts/p1_fixed_cohort_evaluation.py"
SPEC = importlib.util.spec_from_file_location("p1_fixed_cohort_evaluation", SOURCE)
assert SPEC and SPEC.loader
p1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p1)
PROTOCOL = b'{"protocol":"research-only-protocol-synthetic-test"}\n'


def manifest(ids=("T:1",)):
    return {
        "experiment_id": "P1_SYNTHETIC_NOT_REGISTERED",
        "protocol_registered_at_utc": "2026-10-29T00:00:00+00:00",
        "protocol_sha256": hashlib.sha256(PROTOCOL).hexdigest(),
        "declared_race_ids": list(ids),
    }


def evaluate(records, m=None):
    return p1.evaluate(m or manifest(), records, protocol_bytes=PROTOCOL)


def test_synthetic_valid_pair_is_only_exploratory():
    item = row()
    report = evaluate([item])
    assert report["status"] == "EXPLORATORY_CLAIMS_ONLY_UNATTESTED"
    assert report["declared_total"] == report["submitted_total"] == 1
    assert report["metrics"]["candidate"]["log_loss"] < report["metrics"]["market"]["log_loss"] + 1
    assert report["metrics"]["candidate"]["brier"] >= 0
    assert report["distinct_days"] == 1
    assert report["at_least_30_consecutive_days"] is False
    assert "EXTERNAL_PIT_PROOF_AND_PREREG_TIMESTAMP_UNVERIFIED" in report["blockers"]
    assert report["p1_validated"] is False
    assert report["model_promotion_authority"] is False
    assert report["betting_authority"] is False
    assert evaluate([item])["records_sha256"] == report["records_sha256"]


def test_real_research_gate_blocks_false_attestation_not_just_scores():
    item = row()
    item["roster_pit_certified"] = False
    out = evaluate([item])
    assert out["metrics"] is None
    assert out["status"] == "BLOCKED_UNVERIFIED_PIT_OR_TIME"
    assert "UNATTESTED_ROSTER_PIT_CERTIFIED" in out["blockers"]


def test_one_missing_race_cannot_be_hidden_in_happy_subset():
    out = evaluate([row()], manifest(("T:1", "T:2")))
    assert out["metrics"] is None
    assert out["status"] == "BLOCKED_COHORT_INTEGRITY"
    assert out["missing_races"] == ["T:2"]
    assert out["declared_total"] == 2


def test_unpreregistered_extra_race_cannot_inflate_sample():
    item = row()
    extra = row()
    extra["race_id"] = "T:2"
    out = evaluate([item, extra])
    assert out["metrics"] is None
    assert out["status"] == "BLOCKED_COHORT_INTEGRITY"
    assert out["unexpected_races"] == ["T:2"]


def test_duplicate_race_is_rejected():
    with pytest.raises(ValueError, match="Duplicate physical"):
        evaluate([row(), row()])


def test_duplicate_declared_physical_race_is_rejected():
    with pytest.raises(ValueError, match="Duplicate race"):
        evaluate([row()], manifest(("T:1", "T:1")))


def test_edited_protocol_bytes_rejected_before_scoring():
    with pytest.raises(ValueError, match="Protocol bytes differ"):
        p1.evaluate(manifest(), [row()], protocol_bytes=b'changed')


def test_forged_postrace_preregistration_rejected():
    m = manifest()
    m["protocol_registered_at_utc"] = "2026-11-02T00:00:00+00:00"
    report = evaluate([row()], m)
    assert report["metrics"] is None
    assert "PROTOCOL_REGISTERED_AFTER_RACE_START" in report["blockers"]


def test_wrong_winner_and_future_snapshot_never_produce_metrics():
    item = row()
    item["market_snapshot_at_utc"] = "2026-10-31T15:00:30+00:00"
    item["winner_selection_id"] = "9"
    report = evaluate([item])
    assert report["metrics"] is None
    assert "MARKET_FUTURE_LEAKAGE" in report["blockers"]


def test_empty_actual_records_not_reclassified_as_success():
    out = evaluate([])
    assert out["metrics"] is None
    assert out["missing_races"] == ["T:1"]
    assert out["p1_validated"] is False


def test_full_denominator_but_one_blocked_race_suppresses_all_metrics():
    x = row()
    y = row()
    y["race_id"] = "T:2"
    y["roster_pit_certified"] = False
    out = evaluate([x, y], manifest(("T:1", "T:2")))
    assert out["metrics"] is None
    assert out["status"] == "BLOCKED_UNVERIFIED_PIT_OR_TIME"


def test_different_selected_sets_are_not_paired():
    item = row()
    item["candidate_probabilities"] = {"1": .6, "3": .4}
    out = evaluate([item])
    assert "NONPAIRED_SELECTION_SETS" in out["blockers"]
    assert out["metrics"] is None


def test_protocol_registered_after_race_prereg_but_before_start_is_rejected():
    m = manifest()
    # A protocol committed on October 30 cannot truthfully claim it had
    # preregistered its race record on October 29, even if the race has not run.
    m["protocol_registered_at_utc"] = "2026-10-30T10:00:00+00:00"
    out = evaluate([row()], m)
    assert out["status"] == "BLOCKED_COHORT_INTEGRITY"
    assert "RACE_PREREG_PRECEDES_PROTOCOL" in out["blockers"]
    assert out["metrics"] is None


def test_protocol_registered_after_freeze_but_before_race_is_rejected():
    m = manifest()
    m["protocol_registered_at_utc"] = "2026-10-31T14:55:00+00:00"
    out = evaluate([row()], m)
    assert "RACE_FREEZE_PRECEDES_PROTOCOL" in out["blockers"]
    assert out["metrics"] is None
    assert out["p1_validated"] is False


def test_equal_declared_prereg_and_manifest_registration_is_not_a_false_error():
    item = row()
    m = manifest()
    m["protocol_registered_at_utc"] = item["preregistered_at_utc"]
    out = evaluate([item], m)
    assert "RACE_PREREG_PRECEDES_PROTOCOL" not in out["blockers"]
    assert out["status"] == "EXPLORATORY_CLAIMS_ONLY_UNATTESTED"


def test_naive_declared_prereg_in_manifest_contract_fails_closed():
    item = row()
    item["preregistered_at_utc"] = "2026-10-29T12:00:00"
    out = evaluate([item])
    assert out["metrics"] is None
    assert "INVALID_DECLARED_RACE_TIME" in out["blockers"]
