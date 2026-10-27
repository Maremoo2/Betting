"""DATA-004E negative controls use synthetic reviewer assertions, never gold."""
import copy
import json
from pathlib import Path

import pytest

from hbi.data004_diagnostic import FIELDS
from hbi.data004_double_review import compare_independent_reviews

ROOT = Path(__file__).parents[1]


@pytest.fixture()
def sources():
    def load(path):
        return json.loads((ROOT / path).read_text(encoding="utf-8"))

    m = load("research/data004-holdout-prereg-v1.json")
    e = load("research/data004-holdout-source-pdf-evidence-v1.json")
    l = load("research/data004c-holdout-source-locators-v1.json")
    by_id = {row["sample_id"]: row for row in l["records"]}
    blank = []
    for item in m["selected"]:
        loc = by_id[item["sample_id"]]
        for field in FIELDS:
            blank.append({
                "sample_id": item["sample_id"],
                "horse": loc["horse"],
                "meeting": loc["meeting"],
                "field": field,
                "source_pdf_sha256": loc["source_pdf_sha256"],
                "source_pdf_page": str(loc["pdf_page"]),
                "visual_row_locator": "",
                "row_identity_visual": "",
                "reviewer_id": "",
                "gold_status": "PENDING_VISUAL_REVIEW",
                "gold_value": "",
                "evidence_code": "",
                "review_note": "",
            })
    assert len(blank) == 390
    return m, e, l, blank


def _synthetic_filled(rows, reviewer):
    result = copy.deepcopy(rows)
    for row in result:
        row.update({
            "visual_row_locator": "10,20,140,35",
            "row_identity_visual": "CONFIRMED",
            "reviewer_id": reviewer,
            "gold_status": "VERIFIED",
            "gold_value": "SYNTHETIC_TEST_ONLY",
            "evidence_code": "PRINTED_CELL",
        })
    return result


def test_two_blank_reviews_never_create_gold(sources):
    m, e, l, rows = sources
    result = compare_independent_reviews(m, e, l, rows, copy.deepcopy(rows))
    assert len(result["pending_pairs"]) == 390
    assert not result["double_read_fully_clear"]
    assert not result["holdout_verified"]


def test_even_matching_separate_reviewers_cannot_approve_gold(sources):
    m, e, l, rows = sources
    a, b = _synthetic_filled(rows, "reviewer_a"), _synthetic_filled(rows, "reviewer_b")
    result = compare_independent_reviews(m, e, l, a, b)
    assert result["double_read_fully_clear"]
    assert result["identical_source_values_by_status"]["VERIFIED"] == 390
    assert not result["source_pdf_semantics_independently_verified_by_this_code"]
    assert not result["reviewer_independence_externally_verified"]
    assert not result["holdout_verified"]
    assert not result["production_parser_approved"]


def test_same_reviewer_cannot_be_counted_as_independent(sources):
    m, e, l, rows = sources
    a, b = _synthetic_filled(rows, "Reviewer A"), _synthetic_filled(rows, "reviewer a")
    result = compare_independent_reviews(m, e, l, a, b)
    assert len(result["reviewer_identity_collisions"]) == 390
    assert not result["double_read_fully_clear"]


def test_disagreement_reported_without_silent_normalization(sources):
    m, e, l, rows = sources
    a, b = _synthetic_filled(rows, "reviewer_a"), _synthetic_filled(rows, "reviewer_b")
    b[0]["gold_value"] += " "
    result = compare_independent_reviews(m, e, l, a, b)
    assert len(result["disagreements"]) == 1
    assert result["disagreements"][0]["sample_id"] == a[0]["sample_id"]
    assert not result["double_read_fully_clear"]


@pytest.mark.parametrize("fault", ["missing", "duplicate", "tampered_hash", "parser_leak"])
def test_invalid_source_or_field_schema_is_rejected(sources, fault):
    m, e, l, rows = sources
    a, b = _synthetic_filled(rows, "reviewer_a"), _synthetic_filled(rows, "reviewer_b")
    if fault == "missing":
        b.pop()
    elif fault == "duplicate":
        b[-1] = copy.deepcopy(b[0])
    elif fault == "tampered_hash":
        b[0]["source_pdf_sha256"] = "0" * 64
    elif fault == "parser_leak":
        b[0]["parser_prediction"] = "TEST"
    with pytest.raises(ValueError):
        compare_independent_reviews(m, e, l, a, b)
