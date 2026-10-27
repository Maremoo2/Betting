"""DATA-004 original PDF byte verification and EMPTY gold-review ledger.

Read-only source audit. It cannot establish independently transcribed field
truth or authorize production parser/model/wagering changes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from hbi.data004_diagnostic import FIELDS
from hbi.data004_holdout_gate import audit_source_evidence

LEDGER_COLUMNS = (
    "sample_id", "original_parser_status", "meeting", "field",
    "source_pdf_sha256", "source_pdf_page", "visual_row_locator",
    "independent_reviewer", "gold_status", "gold_value",
)


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def verify_original_pdfs(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Verify actual 24 source files, not just the claimed checksum format.

    `root` is a local directory containing the archived `output/daily/...`
    tree. Never download, guess, repair, or substitute missing files.
    """
    audit_source_evidence(manifest, evidence)
    from pypdf import PdfReader  # optional research-only dependency

    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Source root must be a directory")
    programs = {item["meeting"]: item for item in evidence["programs"]}
    paths_by_meeting: dict[str, str] = {}
    for row in manifest["selected"]:
        meeting = row["meeting"]
        path = row["expected_pdf_path"]
        if not isinstance(path, str) or not path.endswith("/full_program.pdf"):
            raise ValueError(f"Invalid locked PDF path: {meeting}")
        previous = paths_by_meeting.setdefault(meeting, path)
        if previous != path:
            raise ValueError(f"One meeting maps to conflicting PDF paths: {meeting}")
    if set(paths_by_meeting) != set(programs):
        raise ValueError("PDF-to-meeting mapping is incomplete")

    verified: list[dict[str, Any]] = []
    for meeting, relative in sorted(paths_by_meeting.items()):
        candidate = root / relative
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"PDF path leaves original source root: {meeting}")
        if not resolved.is_file():
            raise ValueError(f"Original PDF missing: {meeting}")
        expected = programs[meeting]
        digest = _digest(resolved)
        if digest != expected["pdf_sha256"]:
            raise ValueError(f"Original PDF SHA-256 mismatch: {meeting}")
        try:
            with resolved.open("rb") as stream:
                page_count = len(PdfReader(stream, strict=False).pages)
        except Exception as exc:
            raise ValueError(f"Original PDF cannot be read: {meeting}") from exc
        if page_count != expected["pages"]:
            raise ValueError(f"Original PDF page-count mismatch: {meeting}")
        verified.append({
            "meeting": meeting,
            "source_pdf_sha256": digest,
            "pages": page_count,
            "original_action_artifact_id": expected["artifact_id"],
        })

    return {
        "schema_version": "DATA004_ORIGINAL_PDF_BYTE_AUDIT_V1",
        "status": "ORIGINAL_PDF_BYTES_VERIFIED_GOLD_PENDING",
        "verified_pdf_programs": len(verified),
        "locked_sample_rows": len(manifest["selected"]),
        "field_assessments_required": len(manifest["selected"]) * len(FIELDS),
        "original_source_bytes_verified": True,
        "historical_row_identity_independently_accepted": False,
        "independent_field_gold_verified": False,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
        "verified_programs": verified,
        "limitations": [
            "SHA-256 and page count validate original source bytes only.",
            "No original horse header, history-row ownership or x/y column reading is certified.",
            "All 390 field cells require independent visual source review.",
            "The blank gold ledger never contains parser predictions or inferred answers.",
        ],
    }


def write_blank_gold_ledger(
    manifest: dict[str, Any],
    verified_report: dict[str, Any],
    target: Path,
) -> None:
    """Emit unlabelled review task rows only after original-byte verification."""
    if (verified_report.get("status") != "ORIGINAL_PDF_BYTES_VERIFIED_GOLD_PENDING"
            or verified_report.get("verified_pdf_programs") != 24
            or verified_report.get("holdout_verified") is not False):
        raise ValueError("Original source-byte audit must pass first")
    digests = {
        program["meeting"]: program["source_pdf_sha256"]
        for program in verified_report["verified_programs"]
    }
    if len(digests) != 24:
        raise ValueError("Original PDF audit is not complete")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite an existing gold ledger: {target}")
    with target.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=LEDGER_COLUMNS)
        writer.writeheader()
        for row in manifest["selected"]:
            for field in FIELDS:
                writer.writerow({
                    "sample_id": row["sample_id"],
                    "original_parser_status": row["original_parser_status"],
                    "meeting": row["meeting"],
                    "field": field,
                    "source_pdf_sha256": digests[row["meeting"]],
                    "source_pdf_page": "",
                    "visual_row_locator": "",
                    "independent_reviewer": "",
                    "gold_status": "PENDING_VISUAL_REVIEW",
                    "gold_value": "",
                })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--blank-ledger-output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    evidence = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    report = verify_original_pdfs(manifest, evidence, args.source_root)
    if args.blank_ledger_output is not None:
        write_blank_gold_ledger(manifest, report, args.blank_ledger_output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
