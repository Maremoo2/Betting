"""Frozen real-source research gates; intentional mutations are TEST_ONLY."""
import copy
import json
from itertools import pairwise
from pathlib import Path

import pytest

from hbi.history_quality import evaluate, refine_pdf, run
from hbi.history_semantic_benchmark import run as semantic_run
from hbi.history_source_verification import run as source_run
from hbi.pdf_semantic_validation import read_sources

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return run(ROOT)


@pytest.fixture(scope="module")
def cases():
    rows = json.loads((ROOT / "tests/fixtures/m7a1-ground-truth-v1.json").read_text())["rows"]
    semantics = semantic_run(ROOT, None, archived=True, include_holdout=False)["known"]["observations"]
    contexts = source_run(ROOT)["observations"]
    return {r["observation_id"]: (r, s["semantic"], c) for r, s, c in zip(rows, semantics, contexts, strict=False)}


@pytest.fixture(scope="module")
def originals():
    return read_sources(ROOT / "tests/fixtures/m7a-pdf-validation.zip")


def document(name):
    return json.loads((ROOT / "docs" / name).read_text())


def assess(case, originals, policy=None):
    row, sem, context = case
    return evaluate(row, sem, context, document("M7B1B_TRACK_REGISTER.json"), originals,
        policy or document("M7B1B_EXCLUSION_POLICY.json"))


def test_real_twelve_gaps_individually_classified(report):
    assert len(report["gaps"]) == 12
    assert report["gap_classification_counts"] == {"CORRECTED_AND_VERIFIED": 5,
        "DOCUMENTED_NOT_REPRESENTED_IN_PDF": 6, "INTENTIONALLY_EXCLUDED_UNKNOWN_COMPOSITION": 1}
    fixed = {(g["observation_id"], g["field"]) for g in report["gaps"] if g["classification"] == "CORRECTED_AND_VERIFIED"}
    assert fixed == {(oid, "disqualification_flag") for oid in ("M7A1-003", "M7A1-017", "M7A1-038", "M7A1-052", "M7A1-053")}
    assert sum(len(r["changes"]) for r in report["observations"]) == 5
    for r in report["observations"]:
        assert r["raw_history_line"] and r["raw_codes"] and r["official_control"]
        assert r["after"]["gates"]["D"] == r["after"]["gates"]["E"] == "NOT_APPROVED"
        assert not r["model_eligible"] and r["allowed_use"] == "RESEARCH_ONLY"


def test_real_all_seventy_three_reviewed_with_positive_or_exclusion(report):
    pending = [r for r in report["observations"] if r["original_venue_status"] != "VERIFIED"]
    assert len(pending) == report["previously_unverified_reviewed"] == 73
    assert all(r["venue_review"]["status"] and r["candidates"] for r in pending)
    assert all(r["after"]["gates"]["C"] == "PASS" or "PHYSICAL_RACE_VENUE_UNVERIFIED" in r["after"]["exclusion_reasons"] for r in pending)
    assert report["summary"]["before"]["venue_status"] == {"VERIFIED": 17, "AMBIGUOUS": 30, "CANDIDATE_ONLY": 43}
    assert report["summary"]["after"]["gate_counts"]["A"] == {"PASS": 90}
    assert report["summary"]["after"]["gate_counts"]["B"] == {"PASS": 53, "EXPLICIT_UNKNOWN": 37}
    assert report["summary"]["after"]["venue_status"] == {"VERIFIED": 51, "CANDIDATE_ONLY": 25, "AMBIGUOUS": 14}
    assert report["gate_D_approved"] == report["gate_E_approved"] == report["model_eligible"] == 0


def test_real_same_code_two_countries_is_observation_bound(report):
    b = [r for r in report["observations"] if r["printed_track"] == "B" and r["after"]["gates"]["C"] == "PASS"]
    assert {r["historical_country"] for r in b} == {"NO", "SE"}
    assert document("M7B1B_TRACK_REGISTER.json")["codes"]["B"]["status"] == "AMBIGUOUS"
    # Corrects the two earlier misrouted lookups without changing old reports.
    for oid in ("M7A1-007", "M7A1-009"):
        r = next(r for r in report["observations"] if r["observation_id"] == oid)
        assert r["historical_venue"]["name"] == "Bjerke Travbane"


def test_real_no_volt_or_unknown_compound_backfill(report):
    pure = next(r for r in report["observations"] if r["observation_id"] == "M7A1-054")
    assert pure["after_fields"]["start_method"]["value"] == "UNKNOWN"
    for row in report["observations"]:
        if row["raw_codes"]["km_time"] in ("frd8a", "ug", "kubug", "vändg", "5g", "4g", "8g", "br"):
            assert row["after_fields"]["km_time"]["status"] == "UNKNOWN_CODE"
            assert row["after_fields"]["km_time"]["value"] == "UNKNOWN"
    assert all(r["after_fields"]["start_method"]["value"] != "VOLT" for r in report["observations"])


@pytest.mark.parametrize("mutation", ["no_official", "missing_identity", "serialized_promotion", "other_observation"])
def test_test_only_refinement_needs_positive_context(cases, originals, mutation):
    row, sem, context = copy.deepcopy(cases["M7A1-017"])
    if mutation == "no_official":
        context = None
    elif mutation == "missing_identity":
        context["review"].pop("identity_proof")
    elif mutation == "serialized_promotion":
        context = json.loads(json.dumps(context))  # VERIFIED text is not proof.
    else:
        row["observation_id"] = "TEST_ONLY_DIFFERENT_START"
    result = refine_pdf(row, sem, context, document("M7B1B_TRACK_REGISTER.json"), document("M7B1B_CODEBOOK.json"), True)
    assert result["fields"]["disqualification_flag"]["status"] == "UNKNOWN_CODE"
    evaluated = assess((row, result, context), originals)
    assert evaluated["gates"]["C"] != "PASS" and not evaluated["model_eligible"]


def test_test_only_official_controls_do_not_supply_parser_values(cases, originals):
    row, sem, context = copy.deepcopy(cases["M7A1-017"])
    context["review"]["values"]["disqualification_flag"] = False  # TEST_ONLY contradiction.
    refined = refine_pdf(row, sem, context, document("M7B1B_TRACK_REGISTER.json"), document("M7B1B_CODEBOOK.json"), True)
    assert refined["fields"]["disqualification_flag"]["value"] is True  # PDF d rule, not official False.
    evaluated = assess((row, refined, context), originals)
    assert evaluated["gates"]["B"] == "FAIL" and evaluated["gates"]["C"] != "PASS"
    assert "OFFICIAL_SOURCE_OR_VALUE_CONFLICT" in evaluated["exclusion_reasons"]


@pytest.mark.parametrize("day", ["2026-10-20", "2027-01-01"])
def test_test_only_same_day_and_future_keep_all_reasons(cases, originals, day):
    row, sem, context = copy.deepcopy(cases["M7A1-017"])
    row["historical_date"] = day
    row["source_evidence"].pop("bundle_sha256")
    context["review"].pop("identity_proof")
    evaluated = assess((row, sem, context), originals)
    assert {"FUTURE_SAME_DAY_OR_INVALID_HISTORY_DATE", "SOURCE_PROVENANCE_OR_LOCATION_CONFLICT",
        "UNKNOWN_RESULT_OR_TIME_CODE", "HISTORICAL_HORSE_IDENTITY_NOT_APPROVED", "PIT_NOT_APPROVED"}.issubset(evaluated["exclusion_reasons"])
    assert evaluated["gates"]["B"] == "FAIL" and evaluated["gates"]["C"] != "PASS"


def test_test_only_no_norwegian_rule_transfer_to_swedish_namespace(cases):
    row, sem, context = copy.deepcopy(cases["M7A1-003"])
    book = document("M7B1B_CODEBOOK.json")
    next(r for r in book["pdf_rules"] if r["id"] == "NO_DG_TIME_DQ")["country"] = "SE"
    with pytest.raises(ValueError, match="NAMESPACE"):
        refine_pdf(row, sem, context, document("M7B1B_TRACK_REGISTER.json"), book, True)


@pytest.mark.parametrize("field,value", [("placing", True), ("km_time", 68), ("km_time", float("nan")),
    ("start_method", "VOLT"), ("historical_date", "2027-01-01")])
def test_test_only_unsupported_core_value_is_not_verified(cases, originals, field, value):
    row, sem, context = copy.deepcopy(cases["M7A1-017"])
    sem["fields"][field].update(value=value, status="EXTRACTED")
    assert assess((row, sem, context), originals)["gates"]["B"] == "FAIL"


@pytest.mark.parametrize("mutation", ["model", "D", "E", "absence_of_evidence"])
def test_test_only_policy_cannot_admit_models_identity_or_pit(cases, originals, mutation):
    policy = document("M7B1B_EXCLUSION_POLICY.json")
    if mutation == "model":
        policy["model_eligible"] = True
    elif mutation == "absence_of_evidence":
        policy["positive_evidence_required"] = False
    else:
        policy["gates"][mutation]["status"] = "PASS"
    with pytest.raises(ValueError):
        assess(copy.deepcopy(cases["M7A1-017"]), originals, policy)


def test_test_only_input_admission_claim_does_not_bypass_policy(cases, originals):
    row, sem, context = copy.deepcopy(cases["M7A1-001"])
    sem.update(model_eligible=True, pit_status="VERIFIED")
    result = assess((row, sem, context), originals)
    assert not result["model_eligible"] and result["gates"]["E"] == "NOT_APPROVED"
    assert "UNAUTHORIZED_ADMISSION_CLAIM" in result["exclusion_reasons"]


def test_real_bias_denominators_and_excluded_start_ids(report):
    assert sum(v["observations"] for v in report["bias_groups"]["target_country"].values()) == 90
    assert report["bias_groups"]["dq_evidence"]["AFFIRMATIVE"]["quantitative_ABC"] == 0
    assert report["bias_groups"]["start_kind"]["QUALIFICATION"]["observations"] == 2
    assert report["reason_overlap_pairs"]
    for side in ("before", "after"):
        stages = report["summary"][side]["sequential_attrition"]
        for old, new in pairwise(stages):
            assert old["remaining"] - len(new["excluded_here"]) == new["remaining"]
