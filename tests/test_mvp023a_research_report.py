"""TEST_ONLY combined report status fixtures; not authentic racing records."""
from __future__ import annotations

import json

import pytest

from hbi.mvp023a_research_report import build_consolidated_report, main
from hbi.research_lab import digest

RID = "RIKSTOTO:BJ_NR_2020-01-04:1"
SHAS = {k: k[0] * 64 for k in ("coverage", "features", "dataset", "benter")}


def sample():
    race = {
        "race_id": RID, "year": 2020,
        "categories": {"SOURCE_ARCHIVED": True, "RESULT_VERIFIED": True,
                       "PIT_MODEL_ELIGIBLE": False}, "bet_authority": False,
    }
    coverage = {
        "schema": "MVP023A_HISTORICAL_COVERAGE_V1",
        "research_only": True, "bet_authority": False,
        "training_performed": False, "historical_not_prospective": True,
        "by_race": [race], "data_sha256": digest([race]),
        "counts": {"physical_races": 1},
        "by_year": {"2020": {
            "physical_races": 1, "coverage_denominator": 1,
            "SOURCE_ARCHIVED": 1, "RESULT_VERIFIED": 1,
            "MARKET_COMPLETE": 1, "PIT_MODEL_ELIGIBLE": 0,
        }},
        "by_country": {"NO": {"physical_races": 1}},
        "readiness": {
            "pit_model_eligible": 0,
            "lockbox_2025_accessed_for_tuning": False,
        },
    }
    feat_row = {"race_id": RID, "active_runners": 2,
                "fundamental_training_eligible": False}
    features = {
        "schema": "MVP023A_HISTORICAL_FEATURE_AUDIT_V1",
        "bet_authority": False, "training_performed": False,
        "by_race": [feat_row], "feature_audit_sha256": digest([feat_row]),
        "training_ready_races": 0, "lockbox_2025_opened": False,
        "physical_races": 1,
        "features": {"driver": {
            "eligible_runners": 0, "denominator_active_runners": 2,
            "status_counts": {"RETROSPECTIVE_ONLY": 2},
        }},
        "by_country": {"NO": {"races": 1, "active_runners": 2}},
        "by_year": {"2020": {"races": 1, "active_runners": 2}},
    }
    dataset = {
        "schema": "MVP023A_RESEARCH_DATASET_PARTITION_V1",
        "bet_authority": False, "training_performed": False,
        "model_training_eligible": 0, "benter_fit_eligible": 0,
        "2025_candidate_lockbox_opened": False,
        "label_separated_from_fundamentals": True,
        "readiness": "BLOCKED_SOURCE", "races": 1,
        "partitions": {"DEVELOPMENT_2015_2022": {
            "race_ids": [RID], "count": 1, "sha256": digest([RID]),
        }},
    }
    benter = {
        "schema": "MVP023A_BENTER_READINESS_V1",
        "bet_authority": False, "training_performed": False,
        "fit_readiness": "NOT_READY",
        "weight_estimation_performed": False,
        "2025_lockbox_used_for_tuning": False,
        "combination_fit_ready": False, "economic_ev_ready": False,
        "blocker_counts": {"IMMUTABLE_RAW_ORIGINAL_REPLAY_REQUIRED": 1},
    }
    return {"coverage": coverage, "features": features, "dataset": dataset,
            "benter": benter}


def evaluate(inputs):
    return build_consolidated_report(**inputs, input_sha256=SHAS)


def test_distinct_annual_denominators_and_unobserved_years():
    output = evaluate(sample())
    year = {r["year"]: r for r in output["years"]}
    assert len(year) == 12
    assert year[2015]["data_scope"] == "NOT_MEASURED_NO_ORIGINAL_ARCHIVE"
    assert year[2015]["discovered_physical"] is None
    assert year[2015]["official_result_verified"] is None
    assert year[2020]["discovered_physical"] == 1
    assert year[2020]["coverage_denominator"] == 1
    assert year[2020]["official_result_verified"] == 1
    assert year[2020]["m5_feature_audit_races_separate_cohort"] == 1
    assert year[2025]["data_scope"] == "CANDIDATE_2025_LOCKBOX_RESULTS_WITHHELD"
    assert year[2025]["official_result_verified"] is None
    assert output["features"]["driver"]["m5_active_runner_denominator"] == 2
    assert output["benter"]["fit_readiness"] == "NOT_READY"
    assert output["readiness"]["production_betting_ready"] is False
    assert output["2025_lockbox_opened"] is False
    assert output["training_performed"] is False
    assert output["bet_authority"] is False
    assert evaluate(sample())["report_sha256"] == output["report_sha256"]


def test_premature_benter_fit_is_rejected_not_advertised():
    inputs = sample()
    inputs["benter"]["combination_fit_ready"] = True
    with pytest.raises(ValueError, match="BENTER_PREMATURE_FIT_OR_EV_CLAIM"):
        evaluate(inputs)


def test_internal_coverage_and_feature_sha_tampering_rejected():
    inputs = sample()
    inputs["coverage"]["by_race"][0]["race_id"] = "tampered"
    with pytest.raises(ValueError, match="COVERAGE_ORIGINAL_BASIS_OR_PIT_CLAIM_INVALID"):
        evaluate(inputs)
    inputs = sample()
    inputs["features"]["by_race"][0]["active_runners"] = 123
    with pytest.raises(ValueError, match="HISTORICAL_FEATURE_ORIGINAL_BASIS_INVALID"):
        evaluate(inputs)


def test_dataset_partition_sha_and_lockbox_authority_rejected():
    inputs = sample()
    inputs["dataset"]["partitions"]["DEVELOPMENT_2015_2022"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="DATASET_PARTITION_OR_LOCKBOX_CONTRACT_INVALID"):
        evaluate(inputs)
    inputs = sample()
    inputs["dataset"]["2025_candidate_lockbox_opened"] = True
    with pytest.raises(ValueError, match="DATASET_PARTITION_OR_LOCKBOX_CONTRACT_INVALID"):
        evaluate(inputs)


def test_race_denominator_not_silently_mixed_with_m5():
    inputs = sample()
    inputs["features"]["physical_races"] = 17
    output = evaluate(inputs)
    assert output["coverage_original_physical_races"] == 1
    assert output["m5_feature_audit_races_separate_cohort"] == 17
    assert output["years"][5]["coverage_denominator"] == 1  # 2020
    assert output["years"][5]["m5_feature_audit_races_separate_cohort"] == 1
    assert "M5_DIAGNOSTIC_COHORT_NOT_JOINED_TO_COVERAGE" == (
        output["features"]["driver"]["scope"]
    )


def test_cli_reads_four_reports_without_overwriting_sources(tmp_path):
    docs = sample()
    paths = {}
    for key, doc in docs.items():
        p = tmp_path / (key + ".json")
        p.write_text(json.dumps(doc), encoding="utf-8")
        paths[key] = p
    output = tmp_path / "out" / "research-report.json"
    args = []
    for key, path in paths.items():
        args.extend(["--" + key, str(path)])
    args.extend(["--output", str(output)])
    assert main(args) == 0
    report = json.loads(output.read_text())
    assert report["research_only"] is True
    assert report["raw_source_scope"] == "SELECTED_LOCAL_ARCHIVES_ONLY"
    assert report["coverage_original_physical_races"] == 1
    assert report["input_report_sha256"]["coverage"] != SHAS["coverage"]
    assert report["input_report_sha256"]["dataset"] != SHAS["dataset"]
    with pytest.raises(FileExistsError):
        main(args)


def test_fake_green_market_pit_in_coverage_rejected():
    inputs = sample()
    inputs["coverage"]["readiness"]["pit_model_eligible"] = 1
    with pytest.raises(ValueError, match="COVERAGE_ORIGINAL_BASIS_OR_PIT_CLAIM_INVALID"):
        evaluate(inputs)


def test_fake_year_coverage_denominator_cannot_be_reported():
    inputs = sample()
    inputs["coverage"]["by_year"]["2020"]["physical_races"] = 5
    with pytest.raises(ValueError, match="COVERAGE_YEAR_DENOMINATOR_MISMATCH"):
        evaluate(inputs)
    inputs = sample()
    inputs["coverage"]["by_year"] = {}
    with pytest.raises(ValueError, match="COVERAGE_YEAR_DENOMINATOR_MISSING_OR_INVENTED"):
        evaluate(inputs)
