"""Fail-closed DATA-004 source-availability audit; not a holdout-gold validator.

Validates *metadata consistency*, never PDF semantics, independent transcription,
parser accuracy, race predictions, or permission to bet.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
STRATA = {"PARSED": 10, "PARTIAL": 10, "UNPARSEABLE": 10}


def audit_source_evidence(
    manifest: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """Reject malformed/stale source metadata, without claiming PDF verification."""
    if manifest.get("schema_version") != "DATA004_HOLDOUT_PREREG_V1":
        raise ValueError("Unexpected frozen holdout manifest schema")
    if manifest.get("status") != "PREREGISTERED_LABELS_PENDING":
        raise ValueError("Frozen holdout status unexpectedly changed")
    rows = manifest.get("selected")
    if not isinstance(rows, list) or len(rows) != 30:
        raise ValueError("Expected exactly 30 locked holdout entries")
    ids = [row["sample_id"] for row in rows]
    if len(set(ids)) != 30 or manifest.get("selected_rows") != 30:
        raise ValueError("Missing or duplicate locked sample ID")
    if Counter(row["original_parser_status"] for row in rows) != STRATA:
        raise ValueError("10/10/10 locked stratification changed")
    if manifest.get("strata_quotas") != STRATA:
        raise ValueError("Frozen strata quotas changed")
    if (manifest.get("independent_pdf_labels_verified") is not False
            or manifest.get("holdout_status_gate")
            != "BLOCKED_PENDING_INDEPENDENT_PDF_FASIT"):
        raise ValueError("Frozen preregistration cannot certify holdout labels")
    if any(row.get("independent_gold_transcribed") is not False for row in rows):
        raise ValueError("Frozen candidate manifest unexpectedly includes gold")

    if evidence.get("schema_version") != "DATA004_HOLDOUT_PDF_SOURCE_EVIDENCE_V1":
        raise ValueError("Unexpected PDF-source evidence schema")
    if evidence.get("candidate_manifest") != "research/data004-holdout-prereg-v1.json":
        raise ValueError("Source evidence refers to another manifest")
    if (evidence.get("pre_registered_samples") != 30
            or evidence.get("distinct_pdf_programs") != 24
            or evidence.get("source_archives") != 7):
        raise ValueError("Source evidence denominator changed")
    programs = evidence.get("programs")
    if not isinstance(programs, list) or len(programs) != 24:
        raise ValueError("Expected 24 source-program references")
    meetings = [row["meeting"] for row in rows]
    pdf_by_meeting: dict[str, dict[str, Any]] = {}
    artifact_ids: set[int] = set()
    for item in programs:
        meeting = item.get("meeting")
        if not isinstance(meeting, str) or meeting in pdf_by_meeting:
            raise ValueError("Duplicate or invalid source meeting")
        if not SHA256.fullmatch(str(item.get("pdf_sha256", ""))):
            raise ValueError(f"Missing/invalid original PDF checksum: {meeting}")
        if type(item.get("pages")) is not int or item["pages"] < 1:
            raise ValueError(f"Invalid PDF page count: {meeting}")
        if type(item.get("artifact_id")) is not int:
            raise ValueError(f"Missing original action artifact ID: {meeting}")
        if (item.get("archive_entry_found") is not True
                or item.get("pdf_opened_with_fitz") is not True):
            raise ValueError(f"PDF access was not recorded: {meeting}")
        artifact_ids.add(item["artifact_id"])
        pdf_by_meeting[meeting] = item
    if set(meetings) != set(pdf_by_meeting):
        raise ValueError("Original PDF sources do not match locked meetings")
    if len(artifact_ids) != 7:
        raise ValueError("Seven distinct original action archives not represented")
    if evidence.get("source_pdf_byte_access_verified") is not True:
        raise ValueError("Original PDF byte access not recorded")

    # Neither a metadata record nor a Python test proves row identity or 13
    # visually checked fields. Do not accept an edited boolean as evidence.
    if (evidence.get("historical_row_identity_verified") is not False
            or evidence.get("independent_gold_fields_verified") is not False):
        raise ValueError("Field/row acceptance requires a separate original-PDF audit")
    if evidence.get("holdout_model_acceptance") != (
        "BLOCKED_PENDING_ROW_IDENTITY_AND_GOLD_TRANSCRIPTION"
    ):
        raise ValueError("Holdout acceptance must remain blocked")
    return {
        "schema_version": "DATA004_HOLDOUT_SOURCE_GATE_V1",
        "status": "SOURCE_PDF_BYTES_REFERENCED_GOLD_PENDING",
        "selected_rows": len(rows),
        "strata": dict(Counter(r["original_parser_status"] for r in rows)),
        "distinct_pdf_programs": len(pdf_by_meeting),
        "source_archives": len(artifact_ids),
        "row_identity_independently_accepted": False,
        "field_gold_independently_accepted": False,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
        "limitations": (
            "Stored SHA-256 strings are checked for format, not independently "
            "recomputed from original PDF bytes. This gate cannot verify "
            "original-page row identity or any of the 390 semantic gold cells."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    args = parser.parse_args()
    report = audit_source_evidence(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.source_evidence.read_text(encoding="utf-8")),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
