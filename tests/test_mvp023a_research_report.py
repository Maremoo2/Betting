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
    feat_row = {"race_id": RID, "date": "2020-01-04", "country": "NO", "active_runners": 2,
                "fundamental_training_eligible": False}
    features = {
        "schema": "MVP023A_HISTORICAL_FEATURE_AUDIT_V1",
        "source_dataset_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "bet_authority": False, "training_performed": False,
        "by_race": [feat_row], "feature_audit_sha256": digest([feat_row]),
        "training_ready_races": 0, "lockbox_2025_opened": False,
        "physical_races": 1,
        "features": {"driver": {
            "eligible_runners": 0, "eligible_races": 0,
            "denominator_active_runners": 2, "qualified_runner_coverage_rate": 0,
            "status_counts": {"RETROSPECTIVE_ONLY": 2},
            "by_year": {"2020": {"RETROSPECTIVE_ONLY": 2}},
            "by_country": {"NO": {"RETROSPECTIVE_ONLY": 2}},
            "main_blocker": "SOURCE_OBSERVED_AT_OR_AFTER_EVENT",
            "leakage_risk": "RETROSPECTIVE_SOURCE_OR_TIME_UNVERIFIED",
            "identity_requirement": "INDEPENDENT_HORSE_IDENTITY_AT_PREDICTION_TIME",
            "source_time_field": "source_observed_at",
        }},
        "by_country": {"NO": {"races": 1, "active_runners": 2}},
        "by_year": {"2020": {"races": 1, "active_runners": 2}},
    }
    dataset = {
        "schema": "MVP023A_RESEARCH_DATASET_PARTITION_V1",
        "source_m5_dataset_sha256": "a" * 64,
        "source_m5_manifest_sha256": "b" * 64,
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
    assert output["features"]["driver"]["by_year"]["2020"] == {"RETROSPECTIVE_ONLY": 2}
    assert output["features"]["driver"]["main_blocker"] == "SOURCE_OBSERVED_AT_OR_AFTER_EVENT"
    assert output["features"]["driver"]["qualified_races"] == 0
    assert output["features"]["driver"]["time_integrity"] == "NOT_PIT_CERTIFIED"
    assert output["benter"]["fit_readiness"] == "NOT_READY"
    assert output["benter"]["fundamental_dataset_ready"] is False
    assert output["benter"]["pre_race_market_ready"] is False
    assert output["benter"]["same_race_alignment_structure_only"] is False
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
    extra = [
        {"race_id": f"RIKSTOTO:BJ_NR_2019-01-04:{n}",
         "date": "2019-01-04", "country": "NO",
         "active_runners": 2, "fundamental_training_eligible": False}
        for n in range(1, 17)
    ]
    inputs["features"]["by_race"].extend(extra)
    inputs["features"]["feature_audit_sha256"] = digest(inputs["features"]["by_race"])
    inputs["features"]["physical_races"] = 17
    inputs["features"]["by_year"]["2019"] = {"races": 16, "active_runners": 32}
    inputs["features"]["by_country"]["NO"] = {"races": 17, "active_runners": 34}
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


def test_fake_feature_country_or_year_denominator_rejected():
    inputs = sample()
    inputs["features"]["by_country"]["NO"]["races"] = 5
    with pytest.raises(ValueError, match="FEATURE_BY_COUNTRY_DENOMINATOR_CONFLICT"):
        evaluate(inputs)
    inputs = sample()
    inputs["features"]["by_year"]["2020"]["active_runners"] = 5
    with pytest.raises(ValueError, match="FEATURE_BY_YEAR_DENOMINATOR_CONFLICT"):
        evaluate(inputs)


def test_cross_pr_m5_sha_conflict_fails_closed():
    inputs = sample()
    inputs["features"]["source_dataset_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="M5_FEATURE_PARTITION_ORIGINAL_PROVENANCE_CONFLICT"):
        evaluate(inputs)
    inputs = sample()
    inputs["dataset"]["source_m5_manifest_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="M5_FEATURE_PARTITION_ORIGINAL_PROVENANCE_CONFLICT"):
        evaluate(inputs)


def test_cross_pr_same_valid_m5_source_but_disjoint_race_ids_fails():
    inputs = sample()
    ids = ["RIKSTOTO:BJ_NR_2024-02-01:1"]
    inputs["dataset"]["partitions"]["DEVELOPMENT_2015_2022"].update({
        "race_ids": ids, "count": 1, "sha256": digest(ids),
    })
    with pytest.raises(ValueError, match="M5_FEATURE_PARTITION_RACE_COHORT_CONFLICT"):
        evaluate(inputs)


def test_integration_2025_result_cannot_be_indirectly_hidden_by_report():
    inputs = sample()
    row = inputs["coverage"]["by_race"][0]
    row["race_id"] = "RIKSTOTO:BJ_NR_2025-01-04:1"
    row["year"] = 2025
    row["categories"]["RESULT_VERIFIED"] = True
    row["official_result_sha256"] = "a" * 64
    inputs["coverage"]["data_sha256"] = digest(inputs["coverage"]["by_race"])
    inputs["coverage"]["by_year"] = {
        "2025": inputs["coverage"]["by_year"].pop("2020")
    }
    with pytest.raises(ValueError, match="2025_LOCKBOX_RESULT_INDIRECTLY_EXPOSED"):
        evaluate(inputs)


def test_integration_2025_benter_or_dataset_cannot_be_laundered():
    inputs = sample()
    inputs["benter"]["per_race"] = [{
        "race_id": "RIKSTOTO:BJ_NR_2025-01-04:1",
        "readiness": "NOT_READY",
    }]
    with pytest.raises(ValueError, match="2025_LOCKBOX_BENTER_EVALUATION_INDIRECTLY_EXPOSED"):
        evaluate(inputs)
    inputs = sample()
    ids = ["RIKSTOTO:BJ_NR_2025-01-04:1"]
    inputs["dataset"]["partitions"] = {
        "DEVELOPMENT_2015_2022": {
            "race_ids": ids, "count": 1, "sha256": digest(ids),
        }
    }
    with pytest.raises(ValueError, match="2025_LOCKBOX_PARTITION_INDIRECTLY_EXPOSED"):
        evaluate(inputs)
