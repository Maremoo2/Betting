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
