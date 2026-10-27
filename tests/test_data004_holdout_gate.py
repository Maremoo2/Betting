"""DATA-004: source-index checks never masquerade as independent gold labels."""
import copy
import json
from pathlib import Path

import pytest

from hbi.data004_holdout_gate import audit_source_evidence

ROOT = Path(__file__).parents[1]


@pytest.fixture()
def inputs():
    manifest = json.loads(
        (ROOT / "research/data004-holdout-prereg-v1.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (ROOT / "research/data004-holdout-source-pdf-evidence-v1.json").read_text(
            encoding="utf-8"
        )
    )
    return manifest, evidence


def test_real_frozen_references_are_consistent_but_gold_is_blocked(inputs):
    result = audit_source_evidence(*inputs)
    assert result["selected_rows"] == 30
    assert result["distinct_pdf_programs"] == 24
    assert result["source_archives"] == 7
    assert result["strata"] == {"PARSED": 10, "PARTIAL": 10, "UNPARSEABLE": 10}
    assert result["status"] == "SOURCE_PDF_BYTES_REFERENCED_GOLD_PENDING"
    assert result["row_identity_independently_accepted"] is False
    assert result["holdout_verified"] is False
    assert result["production_parser_approved"] is False


@pytest.mark.parametrize("fault", [
    "missing_meeting",
    "duplicate_meeting",
    "invalid_sha",
    "unopened_pdf",
    "missing_archive",
    "bad_strata",
    "fake_gold",
    "fake_identity",
    "fake_acceptance",
    "duplicate_sample",
])
def test_fail_closed_for_source_or_holdout_claims(inputs, fault):
    manifest, evidence = copy.deepcopy(inputs)
    if fault == "missing_meeting":
        evidence["programs"].pop()
    elif fault == "duplicate_meeting":
        evidence["programs"][0]["meeting"] = evidence["programs"][1]["meeting"]
    elif fault == "invalid_sha":
        evidence["programs"][0]["pdf_sha256"] = "not-a-digest"
    elif fault == "unopened_pdf":
        evidence["programs"][0]["pdf_opened_with_fitz"] = False
    elif fault == "missing_archive":
        artifact = evidence["programs"][0]["artifact_id"]
        for item in evidence["programs"]:
            if item["artifact_id"] == artifact:
                item["artifact_id"] = evidence["programs"][-1]["artifact_id"]
    elif fault == "bad_strata":
        manifest["selected"][0]["original_parser_status"] = "UNPARSEABLE"
    elif fault == "fake_gold":
        evidence["independent_gold_fields_verified"] = True
    elif fault == "fake_identity":
        evidence["historical_row_identity_verified"] = True
    elif fault == "fake_acceptance":
        evidence["holdout_model_acceptance"] = "ACCEPTED"
    elif fault == "duplicate_sample":
        manifest["selected"][0]["sample_id"] = manifest["selected"][1]["sample_id"]
    with pytest.raises(ValueError):
        audit_source_evidence(manifest, evidence)
