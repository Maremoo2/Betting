"""DATA-004C: no semantic gold labels are embedded in tests or the repository."""
import copy
import csv
import json
from pathlib import Path

import pytest

from hbi.data004_gold_review import (
    REVIEW_COLUMNS,
    audit_review_ledger,
    make_blank_review_ledger,
    validate_source_locators,
)

ROOT = Path(__file__).parents[1]


@pytest.fixture()
def references(tmp_path):
    def read(path):
        return json.loads((ROOT / path).read_text(encoding="utf-8"))

    manifest = read("research/data004-holdout-prereg-v1.json")
    evidence = read("research/data004-holdout-source-pdf-evidence-v1.json")
    locators = read("research/data004c-holdout-source-locators-v1.json")
    synthetic_byte_report = {
        # Test-only metadata. Production CLI must reopen original PDF bytes.
        "status": "ORIGINAL_PDF_BYTES_VERIFIED_GOLD_PENDING",
        "verified_pdf_programs": 24,
        "original_source_bytes_verified": True,
        "holdout_verified": False,
        "verified_programs": [
            {"meeting": x["meeting"], "source_pdf_sha256": x["pdf_sha256"]}
            for x in evidence["programs"]
        ],
    }
    output = tmp_path / "blank.csv"
    make_blank_review_ledger(
        manifest, evidence, locators, synthetic_byte_report, output,
    )
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return manifest, evidence, locators, output, rows


def test_frozen_30_source_pages_are_navigation_only(references):
    m, e, l, _, rows = references
    assert len(validate_source_locators(m, e, l)) == 30
    assert len(rows) == 390
    assert len({(x["sample_id"], x["field"]) for x in rows}) == 390
    assert all(set(x) == set(REVIEW_COLUMNS) for x in rows)
    assert all(x["gold_status"] == "PENDING_VISUAL_REVIEW" for x in rows)
    assert all(x["gold_value"] == "" for x in rows)
    assert all(x["reviewer_id"] == "" for x in rows)
    assert all(x["visual_row_locator"] == "" for x in rows)
    assert not any(
        key.startswith(("parser_", "parsed_"))
        for row in rows for key in row
    )
    report = audit_review_ledger(m, e, l, rows)
    assert report["status"] == "HOLDOUT_GOLD_REVIEW_INCOMPLETE"
    assert report["fully_reviewed_samples"] == 0
    assert report["holdout_verified"] is False


def _synthetic_attested(rows):
    """Fabricated values test validation only. Never export as actual gold."""
    result = copy.deepcopy(rows)
    for item in result:
        item.update({
            "visual_row_locator": "10,20,140,34",
            "row_identity_visual": "CONFIRMED",
            "reviewer_id": "synthetic_test_reviewer",
            "gold_status": "VERIFIED",
            "gold_value": "TEST_ONLY_PLACEHOLDER",
            "evidence_code": "PRINTED_CELL",
            "review_note": "",
        })
    return result


def test_structurally_complete_attestations_are_still_not_accepted_gold(references):
    m, e, l, output, rows = references
    report = audit_review_ledger(m, e, l, _synthetic_attested(rows))
    assert report["status"] == "REVIEW_ATTESTED_EXTERNAL_ACCEPTANCE_REQUIRED"
    assert report["fully_reviewed_samples"] == 30
    assert report["field_review_states"]["VERIFIED"] == 390
    assert report["reviewer_attestations_externally_verified"] is False
    assert report["holdout_verified"] is False
    assert report["production_parser_approved"] is False
    with pytest.raises(FileExistsError):
        make_blank_review_ledger(
            m, e, l, {
                "status": "ORIGINAL_PDF_BYTES_VERIFIED_GOLD_PENDING",
                "verified_pdf_programs": 24,
                "original_source_bytes_verified": True,
                "holdout_verified": False,
                "verified_programs": [
                    {"meeting": p["meeting"], "source_pdf_sha256": p["pdf_sha256"]}
                    for p in e["programs"]
                ],
            }, output,
        )


@pytest.mark.parametrize("fault", [
    "missing_pair", "duplicate_pair", "parser_leak", "tampered_source",
    "wrong_page", "unattested_identity", "missing_reviewer",
    "unlocated_row", "negative_by_absence", "ambiguous_with_value",
    "ambiguous_without_reason", "unavailable_with_value",
    "pending_with_value", "unknown_status", "unknown_sample",
])
def test_broken_gold_ledger_fails_closed(references, fault):
    m, e, l, _, original = references
    rows = _synthetic_attested(original)
    row = rows[0]
    if fault == "missing_pair":
        rows.pop()
    elif fault == "duplicate_pair":
        rows[-1]["sample_id"] = row["sample_id"]
        rows[-1]["field"] = row["field"]
    elif fault == "parser_leak":
        row["parser_value"] = "LEAKED"
    elif fault == "tampered_source":
        row["source_pdf_sha256"] = "0" * 64
    elif fault == "wrong_page":
        row["source_pdf_page"] = "999"
    elif fault == "unattested_identity":
        row["row_identity_visual"] = ""
    elif fault == "missing_reviewer":
        row["reviewer_id"] = ""
    elif fault == "unlocated_row":
        row["visual_row_locator"] = "not a physical bbox"
    elif fault == "negative_by_absence":
        row = next(item for item in rows if item["field"] == "gallop")
        row["gold_value"] = "False"
    elif fault == "ambiguous_with_value":
        row["gold_status"] = "AMBIGUOUS"
        row["evidence_code"] = "AMBIGUOUS_LAYOUT"
    elif fault == "ambiguous_without_reason":
        row.update({"gold_status": "AMBIGUOUS", "gold_value": "",
                    "evidence_code": "AMBIGUOUS_LAYOUT"})
    elif fault == "unavailable_with_value":
        row.update({"gold_status": "UNAVAILABLE",
                    "evidence_code": "NOT_PRINTED"})
    elif fault == "pending_with_value":
        row["gold_status"] = "PENDING_VISUAL_REVIEW"
    elif fault == "unknown_status":
        row["gold_status"] = "GUESSED"
    elif fault == "unknown_sample":
        row["sample_id"] = "999"
    with pytest.raises(ValueError):
        audit_review_ledger(m, e, l, rows)


@pytest.mark.parametrize("fault", [
    "missing_locator", "fake_gold", "wrong_hash", "bad_page",
    "bad_horse", "foreign_sample",
])
def test_locator_manifest_is_not_automatically_promotable(references, fault):
    m, e, l, _, _ = references
    l = copy.deepcopy(l)
    item = l["records"][0]
    if fault == "missing_locator":
        l["records"].pop()
    elif fault == "fake_gold":
        l["field_gold_verified"] = True
    elif fault == "wrong_hash":
        item["source_pdf_sha256"] = "0" * 64
    elif fault == "bad_page":
        item["pdf_page"] = 10000
    elif fault == "bad_horse":
        item["horse"] = ""
    elif fault == "foreign_sample":
        item["sample_id"] = "999"
    with pytest.raises(ValueError):
        validate_source_locators(m, e, l)


def test_ambiguous_and_unavailable_are_not_silent_correct_negatives(references):
    m, e, l, _, rows = references
    rows = _synthetic_attested(rows)
    rows[0].update({
        "gold_status": "AMBIGUOUS", "gold_value": "",
        "evidence_code": "AMBIGUOUS_LAYOUT",
        "review_note": "Source columns are overlapping",
    })
    rows[1].update({
        "gold_status": "UNAVAILABLE", "gold_value": "",
        "evidence_code": "NOT_PRINTED",
        "review_note": "Not represented in original PDF",
    })
    report = audit_review_ledger(m, e, l, rows)
    assert report["field_review_states"]["AMBIGUOUS"] == 1
    assert report["field_review_states"]["UNAVAILABLE"] == 1
    assert report["field_review_states"]["VERIFIED"] == 388
    assert report["holdout_verified"] is False
