"""Real known regression set; explicit synthetic mutations are TEST_ONLY."""
import copy
import json
from pathlib import Path

import pytest

from hbi.history_semantic_benchmark import run
from hbi.history_semantics import normalize_prior

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def known():
    # No holdout read during development; CI replays pinned archived collector
    # records. The separate CLI evidence records actual external parser execution.
    return run(ROOT, None, archived=True, include_holdout=False)["known"]


def test_real_known_sixty_semantic_fields(known):
    assert known["rows"] == 60
    assert known["structural_assignment"] == {"CORRECT": 60}
    assert known["source_localization"] == {"CORRECT": 60}
    assert known["critical_findings"] == {}
    for metric in known["field_metrics"].values():
        assert metric["incorrect"] == metric["not_extracted"] == 0
    assert known["field_metrics"]["distance_m"]["correct"] == 60
    assert known["field_metrics"]["gallop_flag"]["correct"] == 14
    assert known["field_metrics"]["qualification_flag"]["correct"] == 2
    assert known["model_eligible"] == 0


def test_real_codes_qualification_and_track_collisions(known):
    rows = known["observations"]
    eire = next(r["semantic"] for r in rows if "frd8a" in r["raw_history_line"])
    assert eire["fields"]["km_time"]["status"] == "UNKNOWN_CODE"
    assert eire["fields"]["start_method"]["status"] == "UNKNOWN_CODE"
    for r in rows:
        semantic = r["semantic"]
        assert semantic["allowed_use"] == "RESEARCH_ONLY"
        assert semantic["model_eligible"] is False and semantic["pit_status"] == "UNVERIFIED"
        assert "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED" in semantic["exclusion_reasons"]
        if semantic["fields"]["historical_track"]["value"] in ("B", "F", "J", "S"):
            assert semantic["fields"]["track_identity"]["status"] == "AMBIGUOUS"
        if semantic["raw_codes"]["placing"] == "0":
            assert semantic["fields"]["placing"]["value"] == "UNPLACED"
            assert semantic["fields"]["disqualification_flag"]["value"] == "NOT_REPORTED"
        if semantic["result_status"] == "QUALIFICATION_APPROVED":
            assert semantic["fields"]["placing"]["value"] == "NOT_APPLICABLE"


def book():
    return json.loads((ROOT / "docs/M7B1_CODEBOOK.json").read_text())


@pytest.mark.parametrize("mutation", ["future", "same_day", "wrong_race", "wrong_date", "missing_date"])
def test_test_only_temporal_or_upstream_conflicts_rejected(known, mutation):
    prior = copy.deepcopy(known["observations"][0]["semantic"]["upstream"])
    target = "2026-10-20"
    if mutation == "future":
        prior["date"] = "2027-01-01"
    elif mutation == "same_day":
        prior["date"] = target
    elif mutation == "wrong_race":
        prior["race_number"] += 1
    elif mutation == "wrong_date":
        prior["date"] = "2020-01-01"
    else:
        prior.pop("date")
    result = normalize_prior(prior, target_date=target, provenance={}, codebook=book())
    assert not result["history_accepted"] and result["model_eligible"] is False
    assert result["fields"]["distance_m"]["status"] == "NOT_EXTRACTED"


@pytest.mark.parametrize("code", ["frd8a", "dg", "br", "zz", "5g"])
def test_test_only_unknown_codes_never_numeric(code):
    # These intentional mutation lines are software tests, not source evidence.
    prior = {"date": "2020-01-01", "race_number": 1,
        "raw_text": f"TEST_ONLY B 01.01.20-1|1 1 d 2140 {code} 999 10'"}
    result = normalize_prior(prior, target_date="2020-01-02", provenance={}, codebook=book())
    assert result["fields"]["km_time"]["value"] == "UNKNOWN"
    assert result["fields"]["km_time"]["status"] == "UNKNOWN_CODE"
    assert result["fields"]["placing"]["value"] == "UNKNOWN"
    assert result["fields"]["track_identity"]["status"] == "AMBIGUOUS"


def test_test_only_absence_a_does_not_prove_volt_and_market_not_time():
    prior = {"date": "2020-01-01", "race_number": 1,
        "raw_text": "TEST_ONLY U 01.01.20-1|1 1 2 2140 17,9 999 10'"}
    result = normalize_prior(prior, target_date="2020-01-02", provenance={}, codebook=book())
    assert result["fields"]["km_time"]["value"] == 77.9
    assert result["fields"]["start_method"]["status"] == "AMBIGUOUS"
    assert result["fields"]["gallop_flag"]["value"] == "NOT_REPORTED"
    prior["raw_text"] = "TEST_ONLY U 01.01.20-1|999 10' 2140 13,1a"
    assert not normalize_prior(prior, target_date="2020-01-02", provenance={}, codebook=book())["history_accepted"]
