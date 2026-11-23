"""004B6 TEST_ONLY negative mutations; positive authentic proof is in Action."""
from copy import deepcopy

import pytest

from hbi.prewatch004b6_candidate_audit import CANDIDATES, audit


def fixture():
    base = {
        "schema": "M7B2B_GATE_REPORT_V1", "model_eligible": False,
        "cutoff_observations": [],
    }
    for i in range(51):
        positive = i < 18
        ae = i < 9
        obs = CANDIDATES[i] if ae else f"TEST_ONLY_{i}"
        base["cutoff_observations"].append({
            "observation_id": obs, "cutoff_minutes": 4,
            "decision_cutoff_at": "2026-10-20T12:00:00+00:00",
            "historical_result_chain_pit_decision": (
                "PIT_VERIFIED" if positive else "PIT_UNPROVEN"
            ),
            "A_E_research": ae, "model_eligible": False,
            "exclusion_reasons": [
                "HISTORICAL_HORSE_IDENTITY_NOT_APPROVED",
                "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "PIT_NOT_APPROVED"
            ],
            "pdf_pit_decision": {"pit_decision": "PIT_VERIFIED"},
            "pdf_contract": {
                "model_eligible": False, "origin": "ORIGINAL_ARCHIVED_BYTES",
                "purpose": "AS_OBSERVED_INPUT_EVIDENCE",
                "source_snapshot_at": "2026-10-20T08:00:00+00:00",
                "first_observed_at": "2026-10-20T08:00:00+00:00",
                "source_version": {
                    "url": "https://official.example/original", "sha256": "a" * 64,
                    "archive_sha256": "b" * 64, "member": "real-file",
                    "observed_at": "2026-10-20T08:00:00+00:00",
                },
            },
        })
    return base


def test_exact_scope_and_no_promotions():
    report = audit(fixture())
    assert report["T_minus_4_legacy_scoped_source_pit"] == 18
    assert report["T_minus_4_A_E_research_candidates"] == 9
    assert len(report["candidate_audits"]) == 9
    assert report["genuine_new_target_historical_PIT_admissions"] == 0
    assert report["bet_authorized"] is False
    assert audit(fixture()) == report


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "evidence", "false_AE", "published_revision",
    "future_clock", "promoted", "wrong_origin", "missing_original",
    "unreviewed", "wrong_count",
])
def test_reject_bad_or_fabricated_candidate(mutation):
    value = fixture()
    candidate = value["cutoff_observations"][0]
    if mutation == "missing":
        candidate["observation_id"] = "DIFFERENT"
    elif mutation == "duplicate":
        value["cutoff_observations"][9]["observation_id"] = CANDIDATES[0]
    elif mutation == "evidence":
        candidate["historical_result_chain_pit_decision"] = "PIT_UNPROVEN"
    elif mutation == "false_AE":
        candidate["A_E_research"] = False
    elif mutation == "published_revision":
        candidate["pdf_pit_decision"]["pit_decision"] = "PIT_UNPROVEN"
    elif mutation == "future_clock":
        candidate["pdf_contract"]["source_version"]["observed_at"] = "2026-10-20T13:00:00+00:00"
    elif mutation == "promoted":
        candidate["model_eligible"] = True
    elif mutation == "wrong_origin":
        candidate["pdf_contract"]["origin"] = "RECONSTRUCTED"
    elif mutation == "missing_original":
        candidate["pdf_contract"]["source_version"]["sha256"] = ""
    elif mutation == "unreviewed":
        candidate["exclusion_reasons"] = ["NO_PROBLEMS"]
    elif mutation == "wrong_count":
        value["cutoff_observations"].pop()
    with pytest.raises(ValueError):
        audit(value)
