"""Bounded real-source reviews; every intentional mutation is TEST_ONLY."""
import copy
import json
from pathlib import Path

import pytest

from hbi.history_source_verification import (
    atg_review,
    bind_verified,
    checked_source,
    run,
    sources,
)
from hbi.pdf_validation import sha

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return run(ROOT)


@pytest.fixture(scope="module")
def register():
    return json.loads((ROOT / "docs/M7B1A_TRACK_REGISTER.json").read_text())


@pytest.fixture(scope="module")
def raw():
    return sources(ROOT / "tests/fixtures/m7b1a-official-sources-v1.zip")


@pytest.fixture(scope="module")
def eire():
    rows = json.loads((ROOT / "tests/fixtures/m7a1-ground-truth-v1.json").read_text())["rows"]
    row = next(r for r in rows if r["observation_id"] == "M7A1-017")
    cases = json.loads((ROOT / "docs/M7B1A_REVIEW_CLAIMS.json").read_text())["se_cases"]
    case = next(c for c in cases if c["observation_id"] == row["observation_id"])
    identity = {"horse_id": 791286, "pedigree": ["walner", "vivaciousallie"]}
    return row, case, identity


def test_real_all_ninety_and_seventeen_official_chains(report):
    assert report["rows"] == report["printed_codes_correct"] == 90
    assert report["track_status_counts"] == {"VERIFIED": 17, "CANDIDATE_ONLY": 43,
        "AMBIGUOUS": 30, "UNRESOLVED": 0, "CONFLICTING_EVIDENCE": 0}
    assert report["official_starts_reviewed"] == 17 and report["official_countries"] == {"NO": 7, "SE": 10}
    assert report["adapter_incorrect_values"] == report["pdf_official_conflicts"] == 0
    assert report["adapter_missing_official_values"] == 12
    assert report["code_family_verification_counts"] == {"VERIFIED_SCOPED": 7, "PARTIALLY_DOCUMENTED": 4}
    assert report["pit_verified"] == report["model_eligible"] == 0
    assert all(r["allowed_use"] == "RESEARCH_ONLY" and not r["model_eligible"] for r in report["observations"])
    assert len(report["attempts_without_link"]) == 2


def test_real_ambiguous_code_never_globally_promoted(report, register):
    b = [r for r in report["observations"] if r["printed_code"] == "B"]
    assert any(r["status"] == "VERIFIED" for r in b)
    assert any(r["status"] == "AMBIGUOUS" for r in b)
    assert register["codes"]["B"]["status"] == "AMBIGUOUS"
    assert register["codes"]["L"]["status"] == "AMBIGUOUS"
    assert all(r["status"] != "VERIFIED" for r in report["observations"] if r["observation_id"].startswith("M7B1"))


def test_real_high_risk_results_preserve_layers(report):
    records = {r["observation_id"]: r for r in report["observations"]}
    custer = records["M7A1-003"]["review"]
    assert custer["values"]["disqualification_flag"] is True
    assert custer["values"]["gallop_flag"] is True
    assert custer["values"]["placing"] == "UNKNOWN"
    assert records["M7A1-006"]["review"]["values"]["placing"] == "UNPLACED"
    assert records["M7A1-006"]["review"]["values"]["disqualification_flag"] == "NOT_REPORTED"
    eire = records["M7A1-017"]
    assert eire["review"]["raw_official_result"]["kmTime"] == {"code": "frd8"}
    assert eire["review"]["values"]["km_time"] == "NOT_REPORTED"
    assert eire["review"]["values"]["placing"] == "UNKNOWN"  # finishOrder43 is not numeric placing
    assert records["M7A1-054"]["review"]["values"]["start_method"] == "VOLT"
    # Official VOLT is separate, never backfilled into original PDF UNKNOWN.
    truth = json.loads((ROOT / "tests/fixtures/m7a1-ground-truth-v1.json").read_text())
    assert next(r for r in truth["rows"] if r["observation_id"] == "M7A1-054")["start_method"] == "UNKNOWN"


@pytest.mark.parametrize("mutation", ["country", "date", "race", "horse", "pedigree", "code", "provenance"])
def test_test_only_official_conflicts_rejected(eire, raw, mutation):
    row, case, identity = copy.deepcopy(eire)
    meta, body = copy.deepcopy(raw[case["source_member"]])
    p = json.loads(body)
    race = p["races"][0]
    horse = next(s for s in race["starts"] if s["horse"]["id"] == 791286)
    if mutation == "country":
        case["country"] = "NO"
    elif mutation == "date":
        race["date"] = "2020-01-01"
    elif mutation == "race":
        race["number"] = 1
    elif mutation == "horse":
        horse["horse"]["id"] = 999
    elif mutation == "pedigree":
        horse["horse"]["pedigree"]["mother"]["name"] = "TEST_ONLY_WRONG"
    elif mutation == "code":
        row["historical_track"] = "B"
    else:
        meta.pop("url")
    body = json.dumps(p).encode()
    meta.update(sha256=sha(body), bytes=len(body))  # Reach semantic checks, not merely hash failure.
    with pytest.raises(ValueError):
        atg_review(row, case, (meta, body), identity)


@pytest.mark.parametrize("mutation", ["no_review", "candidate_claim", "missing_provenance", "alias", "country"])
def test_test_only_candidate_cannot_promote_without_bound_source(eire, raw, register, mutation):
    row, case, identity = copy.deepcopy(eire)
    review = atg_review(row, case, copy.deepcopy(raw[case["source_member"]]), identity)
    register = copy.deepcopy(register)
    if mutation == "no_review":
        review = None
    elif mutation == "candidate_claim":
        review = {"status": "VERIFIED", "source": review["source"], "identity_proof": identity}
    elif mutation == "missing_provenance":
        review["source"].pop("sha256")
    elif mutation == "alias":
        # Cannot recycle a real source proof to certify an invented historical alias.
        row["historical_track"] = "TEST_ONLY_ALIAS"
        register["codes"]["TEST_ONLY_ALIAS"] = register["codes"]["Ax"]
    else:
        register["codes"]["Ax"]["candidates"][0]["country"] = "NO"
    with pytest.raises(ValueError):
        bind_verified(row, review, register)


def test_test_only_source_digest_and_aware_observation_required(raw):
    source = copy.deepcopy(raw["atg-eire-20260719.json"])
    source[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        checked_source(source)
    source = copy.deepcopy(raw["atg-eire-20260719.json"])
    source[0]["observed_at"] = "2026-10-23T00:00:00"
    with pytest.raises(ValueError):
        checked_source(source)


def test_real_unknown_code_families_are_not_numeric_or_model_ready():
    book = json.loads((ROOT / "docs/M7B1A_RESULT_CODEBOOK.json").read_text())
    unknown = [f for f in book["families"] if f["verification_status"] == "PARTIALLY_DOCUMENTED"]
    assert {f["family"] for f in unknown} == {"frd8a", "ug", "kubug", "vändg"}
    assert all(f["normalization_permission"] == "UNKNOWN_CODE" for f in unknown)
    assert all(f["occurrence_count"] > 0 for f in book["families"])
    assert book["model_eligible"] is False and book["allowed_use"] == "RESEARCH_ONLY"
