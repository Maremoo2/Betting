"""TEST_ONLY Benter readiness contracts; no historical edge or fitted weights."""
from __future__ import annotations

import copy
import json

import pytest

from hbi.mvp023a_benter_readiness import inspect_benter_readiness, main

TRAIN = "RIKSTOTO:BJ_NR_2022-01-01:1"
RACE = "RIKSTOTO:BJ_NR_2023-02-01:1"


def _bundle():
    start = "2023-02-01T12:00:00+00:00"
    pre = "2023-02-01T11:54:00+00:00"
    source = {
        "sha256": "a" * 64,
        "observed_at_utc": pre,
        "published_at_utc": pre,
    }
    runners = [
        {
            "runner_id": str(n), "identity_verified": True,
            "prediction_at": pre,
            "model_probability": p, "market_probability": .5,
            "features": {"driver": {
                "value": f"Driver {n}",
                "event_at": "2023-01-25T10:00:00+00:00",
                "available_at": "2023-01-26T10:00:00+00:00",
                "source_sha256": "d" * 64,
            }},
        } for n, p in ((1, .6), (2, .4))
    ]
    race = {
        "race_id": RACE, "start_at": start,
        "active_runner_ids": ["1", "2"], "winner_id": "1",
        "result_complete": True, "identity_verified": True, "dead_heat": False,
        "market_snapshot_type": "PRE_RACE_VERIFIED",
        "market_available_at": pre,
        "model_training_race_ids": [TRAIN],
        "frozen_fundamental_prediction_sha256": "e" * 64,
        "runners": runners,
        "source_receipts": {
            "market": dict(source),
            "official_result": {"sha256": "b" * 64},
            "fundamental_freeze": dict(source, sha256="c" * 64),
        },
    }
    model = {
        "training_race_ids": [TRAIN],
        "model_original_sha256": "f" * 64,
        "training_dataset_sha256": "1" * 64,
        "frozen_prediction_bundle_sha256": "2" * 64,
        "uses_market_features": False,
    }
    plan = {
        "features": ["driver"],
        "test_period": [
            "2023-01-01T00:00:00+00:00",
            "2023-12-31T23:59:59+00:00",
        ],
    }
    return {
        "schema": "MVP023A_BENTER_READINESS_V1",
        "plan": plan, "races": [race],
        "fundamental_model": model, "combination_weights": None,
        "lockbox_exposure_approved": False,
    }


def test_valid_structural_fixture_does_not_claim_benter_fit():
    payload = _bundle()
    report = inspect_benter_readiness(payload)
    assert report["races_checked"] == 1
    assert report["same_race_alignment_structure_ready"] is True
    assert report["per_race"][0]["blockers"] == [
        "IMMUTABLE_RAW_ORIGINAL_REPLAY_REQUIRED"
    ]
    assert report["fit_readiness"] == "NOT_READY"
    assert report["blocker_counts"]["UNFITTED_ALPHA_BETA_NOT_ESTIMATED"] == 1
    assert report["fundamental_dataset_ready"] is False
    assert report["combination_fit_ready"] is False
    assert report["economic_ev_ready"] is False
    assert report["bet_authority"] is False
    assert report["weight_estimation_performed"] is False
    assert report["weight_estimation_performed"] is False
    assert "estimated_weights" not in report
    assert inspect_benter_readiness(copy.deepcopy(payload)) == report


def test_close_price_cannot_be_used_as_historical_pre_race_market():
    payload = _bundle()
    payload["races"][0]["market_snapshot_type"] = "TERMINAL_HISTORICAL"
    payload["races"][0]["market_available_at"] = "2023-02-01T12:10:00+00:00"
    reasons = inspect_benter_readiness(payload)["per_race"][0]["blockers"]
    assert "HISTORICAL_TERMINAL_MARKET_NOT_EXECUTABLE" in reasons
    assert "MARKET_PRICE_NOT_AVAILABLE_BY_T4" in reasons
    assert any("RESEARCH_LAB_PIT_OR_FIELD" in value for value in reasons)


def test_frozen_model_training_on_evaluation_race_is_blocked():
    payload = _bundle()
    payload["fundamental_model"]["training_race_ids"] = [TRAIN, RACE]
    with pytest.raises(ValueError, match="TRAINING_OUTSIDE_FROZEN_DEVELOPMENT_YEARS"):
        inspect_benter_readiness(payload)


def test_duplicated_race_and_incorrect_runner_field_are_blocked():
    payload = _bundle()
    payload["races"].append(copy.deepcopy(payload["races"][0]))
    with pytest.raises(ValueError, match="DUPLICATE_EVALUATION_RACE"):
        inspect_benter_readiness(payload)
    payload = _bundle()
    payload["races"][0]["active_runner_ids"].append("3")
    reasons = inspect_benter_readiness(payload)["per_race"][0]["blockers"]
    assert any("FULL_FIELD_ONLY" in value for value in reasons)


def test_missing_publication_time_or_original_sha_never_passes():
    payload = _bundle()
    payload["races"][0]["source_receipts"]["market"].pop("published_at_utc")
    payload["races"][0]["source_receipts"]["fundamental_freeze"]["sha256"] = "bad"
    reasons = inspect_benter_readiness(payload)["per_race"][0]["blockers"]
    assert "MARKET_SOURCE_PUBLICATION_TIME_NOT_PROVEN" in reasons
    assert "FUNDAMENTAL_FREEZE_ORIGINAL_SHA_NOT_ATTESTED" in reasons
    assert "IMMUTABLE_RAW_ORIGINAL_REPLAY_REQUIRED" in reasons


def test_missing_prediction_t4_and_market_overlap_are_blocked():
    payload = _bundle()
    payload["races"][0]["runners"][0]["prediction_at"] = "2023-02-01T11:58:00+00:00"
    payload["races"][0]["runners"][0]["market_probability"] = .6
    reasons = inspect_benter_readiness(payload)["per_race"][0]["blockers"]
    assert "FUNDAMENTAL_PREDICTION_AFTER_T4" in reasons
    assert any("Invalid full-field distribution: market_probability" in value for value in reasons)


def test_market_or_outcome_input_to_fundamental_prohibited():
    for name in ["closing_odds", "result", "market_probability"]:
        payload = _bundle()
        payload["plan"]["features"] = ["driver", name]
        if name == "market_probability":
            # Market probabilities may be an OUTPUT benchmark only, never a
            # fundamental feature selected in the training plan.
            assert name not in payload["plan"]["features"][:1]
        with pytest.raises(ValueError, match="MARKET_OR_OUTCOME_LEAKAGE"):
            inspect_benter_readiness(payload)
    payload = _bundle()
    payload["fundamental_model"]["uses_market_features"] = True
    with pytest.raises(ValueError, match="FUNDAMENTAL_MODEL_NOT_MARKET_INDEPENDENT"):
        inspect_benter_readiness(payload)


def test_unapproved_2025_evaluation_never_reads_or_scores_race():
    payload = _bundle()
    payload["races"][0]["race_id"] = "RIKSTOTO:BJ_NR_2025-02-01:1"
    with pytest.raises(ValueError, match="CANDIDATE_2025_LOCKBOX_NOT_AUTHORIZED"):
        inspect_benter_readiness(payload)


def test_unproven_weights_add_blocker_not_estimated_fit():
    payload = _bundle()
    payload["combination_weights"] = {"fundamental_weight": .5, "market_weight": .5}
    report = inspect_benter_readiness(payload)
    assert report["blocker_counts"]["COMBINATION_WEIGHTS_NOT_PROVEN_INDEPENDENTLY_FITTED"] == 1
    assert report["weight_estimation_performed"] is False
    assert report["fit_readiness"] == "NOT_READY"


def test_write_once_read_only_cli(tmp_path):
    payload = _bundle()
    source = tmp_path / "bundle.json"
    target = tmp_path / "audit.json"
    source.write_text(json.dumps(payload))
    before = source.read_bytes()
    assert main(["--bundle", str(source), "--output", str(target)]) == 0
    assert source.read_bytes() == before
    assert json.loads(target.read_text())["bet_authority"] is False
    with pytest.raises(FileExistsError):
        main(["--bundle", str(source), "--output", str(target)])


def test_p1e_fundamental_model_calibration_must_exclude_evaluation_races():
    payload = _bundle()
    payload["fundamental_model"]["calibration_race_ids"] = [RACE]
    with pytest.raises(ValueError, match="FUNDAMENTAL_MODEL_CALIBRATED_ON_EVALUATION_RACES"):
        inspect_benter_readiness(payload)
    payload["fundamental_model"]["calibration_race_ids"] = [
        "RIKSTOTO:BJ_NR_2025-03-01:1"
    ]
    with pytest.raises(ValueError, match="CANDIDATE_2025_LOCKBOX_CALIBRATION_NOT_AUTHORIZED"):
        inspect_benter_readiness(payload)


def test_p1e_benter_weight_fit_cannot_reuse_eval_or_lockbox():
    payload = _bundle()
    payload["combination_weights"] = {
        "fundamental_weight": 0.6, "market_weight": 0.4,
        "fit_race_ids": [RACE],
    }
    with pytest.raises(ValueError, match="COMBINATION_FIT_TUNED_ON_EVALUATION_RACES"):
        inspect_benter_readiness(payload)
    payload["combination_weights"]["fit_race_ids"] = [
        "RIKSTOTO:BJ_NR_2025-03-01:1"
    ]
    with pytest.raises(ValueError, match="CANDIDATE_2025_LOCKBOX_COMBINATION_FIT_NOT_AUTHORIZED"):
        inspect_benter_readiness(payload)
    payload["combination_weights"]["fit_race_ids"] = [
        "RIKSTOTO:BJ_NR_2023-01-20:1"
    ]
    result = inspect_benter_readiness(payload)
    assert result["fit_readiness"] == "NOT_READY"
    assert result["combination_fit_ready"] is False
    assert result["blocker_counts"]["COMBINATION_WEIGHTS_NOT_PROVEN_INDEPENDENTLY_FITTED"] == 1


def test_p1e_fitted_weights_without_published_fit_cohort_stay_blocked():
    payload = _bundle()
    payload["combination_weights"] = {
        "fundamental_weight": .6, "market_weight": .4,
    }
    result = inspect_benter_readiness(payload)
    assert result["blocker_counts"]["COMBINATION_FIT_COHORT_NOT_ATTESTED"] == 1
    assert result["economic_ev_ready"] is False
