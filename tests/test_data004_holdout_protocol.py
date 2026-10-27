"""Pre-registered DATA-004 holdout is only a candidate list, not labeled proof."""
import json
from collections import Counter
from pathlib import Path

MANIFEST = Path(__file__).parents[1] / "research" / "data004-holdout-prereg-v1.json"


def test_holdout_candidate_manifest_is_disjoint_and_unlabeled_by_contract():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = payload["selected"]
    assert payload["schema_version"] == "DATA004_HOLDOUT_PREREG_V1"
    assert payload["status"] == "PREREGISTERED_LABELS_PENDING"
    assert payload["parent_data002_rows"] == 180
    assert payload["excluded_data003b_gold_rows"] == 60
    assert payload["eligible_remaining_rows"] == 120
    assert len(rows) == payload["selected_rows"] == 30
    assert len({r["sample_id"] for r in rows}) == 30
    assert Counter(r["original_parser_status"] for r in rows) == {
        "PARSED": 10, "PARTIAL": 10, "UNPARSEABLE": 10,
    }
    assert len({r["meeting"] for r in rows}) >= 15
    assert payload["independent_pdf_labels_verified"] is False
    assert payload["holdout_status_gate"] == "BLOCKED_PENDING_INDEPENDENT_PDF_FASIT"
    assert payload["original_pdf_bytes_sha256_verified"] is False
    for row in rows:
        assert row["independent_gold_transcribed"] is False
        assert row["original_horse_header_verified"] is False
        assert row["original_pdf_sha256"] is None
        assert row["expected_pdf_path_verified"] is False
        assert row["source_id"].endswith("structured_program.json")
        assert row["expected_pdf_path"].endswith("full_program.pdf")
        assert "horse" not in row and "gold_value" not in row


def test_holdout_pdf_byte_evidence_is_complete_but_not_gold_truth():
    source = (
        Path(__file__).parents[1]
        / "research"
        / "data004-holdout-source-pdf-evidence-v1.json"
    )
    proof = json.loads(source.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    programs = proof["programs"]
    indexed = {entry["meeting"]: entry for entry in programs}
    assert len(programs) == proof["distinct_pdf_programs"] == 24
    assert proof["source_archives"] == 7
    assert proof["pre_registered_samples"] == 30
    assert proof["source_pdf_byte_access_verified"] is True
    assert proof["historical_row_identity_verified"] is False
    assert proof["independent_gold_fields_verified"] is False
    assert {row["meeting"] for row in manifest["selected"]} == set(indexed)
    assert all(
        len(entry["pdf_sha256"]) == 64
        and entry["pages"] >= 1
        and entry["archive_entry_found"] is True
        and entry["pdf_opened_with_fitz"] is True
        for entry in programs
    )
    assert proof["holdout_model_acceptance"] == (
        "BLOCKED_PENDING_ROW_IDENTITY_AND_GOLD_TRANSCRIPTION"
    )
