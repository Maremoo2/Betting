"""DATA-004 dual review checks on synthetic PDFs; no holdout values supplied."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from hbi.data004_dual_review_audit import audit_dual_review
from hbi.data004_original_pdf_audit import verify_original_pdfs, write_blank_gold_ledger

ROOT = Path(__file__).parents[1]


@pytest.fixture
def review_sources(tmp_path):
    manifest = json.loads(
        (ROOT / "research/data004-holdout-prereg-v1.json").read_text(encoding="utf-8"))
    evidence = json.loads(
        (ROOT / "research/data004-holdout-source-pdf-evidence-v1.json").read_text(
            encoding="utf-8"))
    manifest, evidence = copy.deepcopy(manifest), copy.deepcopy(evidence)
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    io_out = io.BytesIO()
    writer.write(io_out)
    source = io_out.getvalue()
    digest = hashlib.sha256(source).hexdigest()
    paths = {r["meeting"]: r["expected_pdf_path"] for r in manifest["selected"]}
    for program in evidence["programs"]:
        program["pdf_sha256"] = digest
        program["pages"] = 1
        path = tmp_path / paths[program["meeting"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
    verified = verify_original_pdfs(manifest, evidence, tmp_path)
    first = tmp_path / "review-a.csv"
    second = tmp_path / "review-b.csv"
    write_blank_gold_ledger(manifest, verified, first)
    write_blank_gold_ledger(manifest, verified, second)
    return manifest, evidence, tmp_path, first, second, paths


def run(item):
    manifest, evidence, root, a, b, _paths = item
    return audit_dual_review(manifest, evidence, root, a, b)


def edit(path, callback):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        cols = reader.fieldnames
        rows = list(reader)
    callback(rows)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def populate(rows, reviewer="reviewer-a", count=None):
    subset = rows if count is None else rows[:count]
    for row in subset:
        row.update({
            "gold_status": "GOLD_VALUE_RECORDED", "gold_value": "synthetic literal",
            "independent_reviewer": reviewer,
            "source_pdf_page": "1", "visual_row_locator": "Synthetic page row",
        })


def test_blank_double_review_keeps_all_gold_blocked(review_sources):
    result = run(review_sources)
    assert result["status"] == "REVIEW_SUBMISSIONS_INCOMPLETE"
    assert result["source_root_verified_original_pdf_count"] == 24
    assert result["locked_cell_denominator"] == 390
    assert result["pending_cells"] == 390
    assert result["both_submitted_cells"] == 0
    assert result["holdout_validated"] is False
    assert result["betting_authority"] is False


def test_one_dual_reviewed_cell_keeps_remaining_389_pending(review_sources):
    *_, a, b, _ = review_sources
    edit(a, lambda rows: populate(rows, "reviewer-a", count=1))
    edit(b, lambda rows: populate(rows, "reviewer-b", count=1))
    result = run(review_sources)
    assert result["matching_submissions_needing_human_authentication"] == 1
    assert result["pending_cells"] == 389
    assert result["gold_fields_semantically_verified"] is False


def test_complete_matching_transcripts_never_self_approve_gold(review_sources):
    *_, a, b, _ = review_sources
    edit(a, lambda rows: populate(rows, "reviewer-a"))
    edit(b, lambda rows: populate(rows, "reviewer-b"))
    result = run(review_sources)
    assert result["status"] == "STRUCTURAL_CONSENSUS_REQUIRES_HUMAN_SOURCE_SIGNOFF"
    assert result["both_submitted_cells"] == 390
    assert result["matching_submissions_needing_human_authentication"] == 390
    assert result["pending_cells"] == result["disputed_cells"] == 0
    assert not result["source_row_identity_independently_accepted"]
    assert not result["reviewer_identity_independence_authenticated"]
    assert not result["gold_fields_semantically_verified"]
    assert not result["holdout_validated"]
    assert not result["pit_or_model_admission_approved"]


@pytest.mark.parametrize("status", ["GOLD_UNAVAILABLE", "GOLD_AMBIGUOUS"])
def test_independent_uncertain_or_unavailable_gold_does_not_invent_false(review_sources, status):
    a, b = review_sources[3:5]
    def fill_one(rows, reviewer):
        populate(rows, reviewer, count=1)
        rows[0]["gold_status"] = status
        rows[0]["gold_value"] = ""
        rows[0]["visual_row_locator"] = "Original page inspected; unreadable or absent"
    edit(a, lambda rows: fill_one(rows, "reviewer-a"))
    edit(b, lambda rows: fill_one(rows, "reviewer-b"))
    result = run(review_sources)
    assert result["status"] == "REVIEW_SUBMISSIONS_INCOMPLETE"
    assert result["matching_submissions_needing_human_authentication"] == 1
    assert result["pending_cells"] == 389
    assert result["gold_fields_semantically_verified"] is False
    assert result["holdout_validated"] is False


def test_two_reviewers_disagree_when_one_claims_unavailable(review_sources):
    a, b = review_sources[3:5]
    edit(a, lambda rows: populate(rows, "reviewer-a"))
    def change(rows):
        populate(rows, "reviewer-b")
        rows[0]["gold_status"] = "GOLD_UNAVAILABLE"
        rows[0]["gold_value"] = ""
    edit(b, change)
    result = run(review_sources)
    assert result["status"] == "REVIEW_DISAGREEMENTS_NEED_ADJUDICATION"
    assert result["disputed_cells"] == 1
    assert result["disputes"][0]["status_one"] == "GOLD_VALUE_RECORDED"
    assert result["disputes"][0]["status_two"] == "GOLD_UNAVAILABLE"
    assert not result["holdout_validated"]


def test_same_value_on_different_horse_history_row_needs_human_adjudication(review_sources):
    a, b = review_sources[3:5]
    edit(a, lambda rows: populate(rows, "reviewer-a"))
    def different_source_horse_row(rows):
        populate(rows, "reviewer-b")
        rows[0]["visual_row_locator"] = "Synthetic page row - OTHER HORSE"
    edit(b, different_source_horse_row)
    result = run(review_sources)
    assert result["status"] == "REVIEW_DISAGREEMENTS_NEED_ADJUDICATION"
    assert result["both_submitted_cells"] == 390
    assert result["disputed_cells"] == 1
    assert result["matching_submissions_needing_human_authentication"] == 389
    assert result["disputes"][0]["reason"] == "INDEPENDENT_SOURCE_ROW_LOCATOR_MISMATCH"
    assert result["disputes"][0]["value_equal"] is True
    assert result["disputes"][0]["page_equal"] is True
    assert result["disputes"][0]["row_locator_equal"] is False
    assert result["holdout_validated"] is False


def test_same_normalized_literal_locator_does_not_invent_gold(review_sources):
    a, b = review_sources[3:5]
    edit(a, lambda rows: populate(rows, "reviewer-a"))
    def same_row_with_whitespace(rows):
        populate(rows, "reviewer-b")
        rows[0]["visual_row_locator"] = "  Synthetic page row  "
    edit(b, same_row_with_whitespace)
    result = run(review_sources)
    assert result["status"] == "STRUCTURAL_CONSENSUS_REQUIRES_HUMAN_SOURCE_SIGNOFF"
    assert result["matching_submissions_needing_human_authentication"] == 390
    assert result["source_row_identity_independently_accepted"] is False
    assert result["gold_fields_semantically_verified"] is False


def test_one_conflicting_value_stays_disputed(review_sources):
    *_, a, b, _ = review_sources
    edit(a, lambda rows: populate(rows, "reviewer-a"))
    def change(rows):
        populate(rows, "reviewer-b")
        rows[0]["gold_value"] = "different synthetic text"
    edit(b, change)
    report = run(review_sources)
    assert report["status"] == "REVIEW_DISAGREEMENTS_NEED_ADJUDICATION"
    assert report["disputed_cells"] == 1
    assert report["matching_submissions_needing_human_authentication"] == 389
    assert report["disputes"][0]["value_equal"] is False
    assert report["holdout_validated"] is False


def test_different_page_requires_explicit_adjudication(review_sources):
    a, b = review_sources[3:5]
    # Synthetic PDF source is one page only; a real two-page source needed
    # for a valid but conflicting page. Testing page out-of-range is stricter.
    edit(a, lambda rows: populate(rows, "reviewer-a", count=1))
    def change(rows):
        populate(rows, "reviewer-b", count=1)
        rows[0]["source_pdf_page"] = "2"
    edit(b, change)
    with pytest.raises(ValueError, match="page outside verified PDF"):
        run(review_sources)


@pytest.mark.parametrize("fault", [
    "fake_reviewer", "missing_page", "missing_locator", "invalid_gold_empty",
    "unknown_status", "pending_with_value", "duplicate_cell", "bad_sha", "wrong_meeting",
])
def test_broken_source_or_review_field_blocks(review_sources, fault):
    a = review_sources[3]
    def mutate(rows):
        populate(rows, "reviewer-a", count=1)
        row = rows[0]
        if fault == "fake_reviewer":
            row["independent_reviewer"] = ""
        elif fault == "missing_page":
            row["source_pdf_page"] = ""
        elif fault == "missing_locator":
            row["visual_row_locator"] = ""
        elif fault == "invalid_gold_empty":
            row["gold_value"] = ""
        elif fault == "unknown_status":
            row["gold_status"] = "VERIFIED_AUTOMATICALLY"
        elif fault == "pending_with_value":
            row["gold_status"] = "PENDING_VISUAL_REVIEW"
        elif fault == "duplicate_cell":
            rows[1]["sample_id"] = row["sample_id"]
            rows[1]["field"] = row["field"]
        elif fault == "bad_sha":
            row["source_pdf_sha256"] = "a" * 64
        elif fault == "wrong_meeting":
            row["meeting"] = "CHANGED_TRACK"
    edit(a, mutate)
    with pytest.raises(ValueError):
        run(review_sources)


def test_same_file_cannot_pretend_to_be_two_reviewers(review_sources):
    manifest, evidence, root, a, _b, _paths = review_sources
    with pytest.raises(ValueError, match="Two distinct"):
        audit_dual_review(manifest, evidence, root, a, a)


def test_same_typed_reviewer_name_does_not_count_as_independent(review_sources):
    *_, a, b, _ = review_sources
    edit(a, lambda rows: populate(rows, "ONE REVIEWER", count=1))
    edit(b, lambda rows: populate(rows, "one reviewer", count=1))
    with pytest.raises(ValueError, match="Same reviewer identity"):
        run(review_sources)


def test_wrong_original_pdf_byte_hash_fails_before_review_comparison(review_sources):
    manifest, evidence, root, a, b, paths = review_sources
    pdf = root / next(iter(paths.values()))
    pdf.write_bytes(pdf.read_bytes() + b"\nchanged source")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        audit_dual_review(manifest, evidence, root, a, b)
