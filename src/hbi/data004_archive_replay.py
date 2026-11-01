"""DATA-004: immutable 7-archive original PDF replay for 30-row holdout.

No provider calls, source rewriting, parser-as-gold, PIT, model or BET.
Original HTTP capture bundles are source-only; archive presence is not a
proof that the PDF's historical result row or any gold field is correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .data004_original_pdf_audit import verify_original_pdfs, write_blank_gold_ledger
from .data004_source_review_assist import (
    build_original_pdf_review_hints,
    write_navigation_csv,
)

MAX_PDF_BYTES = 50 * 1024 * 1024


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_archives(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    archives: dict[int, Path],
    *,
    blank_ledger_output: Path | None = None,
    source_locators: dict[str, Any] | None = None,
    review_hints_output: Path | None = None,
    navigation_csv_output: Path | None = None,
) -> dict[str, Any]:
    """Re-read exact original PDFs INSIDE archive ZIPs and the frozen source gate.

    No extraction outside a disposable temp directory. Never trusts a path
    inside the ZIP for writing: only a locked manifest path is used.
    """
    if (review_hints_output is not None or navigation_csv_output is not None) and (
        source_locators is None
    ):
        raise ValueError("Source review output needs frozen original locator evidence")
    programs = evidence.get("programs")
    if not isinstance(programs, list):
        raise TypeError("Expected original source program evidence")
    required = {p["artifact_id"] for p in programs}
    if len(required) != 7 or set(archives) != required or any(
        type(i) is not int for i in archives
    ):
        raise ValueError("Expected exactly the seven locked original artifact IDs")
    if len(programs) != 24:
        raise ValueError("Expected exactly 24 original source programs")
    paths = {}
    for sample in manifest.get("selected", []):
        meeting, relative = sample.get("meeting"), sample.get("expected_pdf_path")
        if not isinstance(meeting, str) or not isinstance(relative, str):
            raise TypeError("Missing locked source path")
        if not relative.endswith("/full_program.pdf"):
            raise ValueError("Not the original full PDF")
        if relative.startswith("/") or "\\" in relative or ".." in PurePosixPath(relative).parts:
            raise ValueError("Unsafe original source path")
        previous = paths.setdefault(meeting, relative)
        if previous != relative:
            raise ValueError("Inconsistent locked meeting PDF path")
    if set(paths) != {p["meeting"] for p in programs}:
        raise ValueError("Locked source meeting denominator mismatch")
    hashes: dict[str, str] = {}
    received: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="data004-original-source-") as directory:
        root = Path(directory)
        for artifact_id in sorted(required):
            archive = archives[artifact_id]
            if not archive.is_file():
                raise FileNotFoundError(archive)
            hashes[str(artifact_id)] = digest(archive)
            with zipfile.ZipFile(archive) as source:
                members = source.namelist()
                if len(members) != len(set(members)):
                    raise ValueError(f"Duplicate ZIP member in {artifact_id}")
                for program in programs:
                    if program["artifact_id"] != artifact_id:
                        continue
                    meeting = program["meeting"]
                    relative = paths[meeting]
                    if relative not in members:
                        raise ValueError(f"Original PDF absent: {artifact_id}/{relative}")
                    info = source.getinfo(relative)
                    if info.is_dir() or info.flag_bits & 1 or not 0 < info.file_size <= MAX_PDF_BYTES:
                        raise ValueError(f"Original PDF size/encryption invalid: {meeting}")
                    pdf_bytes = source.read(info)  # ZIP CRC checked on extraction
                    checksum = hashlib.sha256(pdf_bytes).hexdigest()
                    if checksum != program["pdf_sha256"]:
                        raise ValueError(f"Original archived PDF bytes mismatch: {meeting}")
                    location = root / relative
                    location.parent.mkdir(parents=True, exist_ok=True)
                    location.write_bytes(pdf_bytes)
                    received.append({"meeting": meeting, "artifact_id": artifact_id,
                                     "original_pdf_sha256": checksum})
        report = verify_original_pdfs(manifest, evidence, root)
        if blank_ledger_output is not None:
            write_blank_gold_ledger(manifest, report, blank_ledger_output)
        review_hints = None
        if source_locators is not None:
            # Independent source geometry and literal glyphs remain UNREVIEWED.
            # Not used to prefill gold, nor accepted as PDF field truth.
            review_hints = build_original_pdf_review_hints(
                manifest, evidence, source_locators, root
            )
            if (review_hints["locked_rows"] != 30
                    or review_hints["field_assessments"] != 390
                    or review_hints["independent_source_gold_accepted"] != 0
                    or review_hints["holdout_verified"] is not False):
                raise ValueError("Unverified review hints attempted gold promotion")
            if review_hints_output is not None:
                with review_hints_output.open("x", encoding="utf-8") as stream:
                    json.dump(review_hints, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
            if navigation_csv_output is not None:
                write_navigation_csv(review_hints, navigation_csv_output)

    if report["verified_pdf_programs"] != 24 or len(received) != 24:
        raise ValueError("Incomplete locked 24-original-PDF physical replay")
    return {
        "schema": "DATA004_ORIGINAL_ACTION_ARCHIVE_REPLAY_V1",
        "status": "ORIGINAL_24_PDFS_BYTE_VERIFIED_GOLD_PENDING",
        "archive_count": len(hashes),
        "archive_zip_sha256_by_artifact_id": hashes,
        "verified_original_pdf_programs": report["verified_pdf_programs"],
        "locked_sample_rows": report["locked_sample_rows"],
        "original_holdout_cells": report["field_assessments_required"],
        "source_byte_checks_performed_in_this_run": True,
        "historical_source_row_geometry_found": (
            review_hints["locked_rows"] if review_hints else None
        ),
        "unreviewed_glyph_hints": (
            review_hints["literal_hints_total"] if review_hints else None
        ),
        "review_source_navigation_is_not_gold": True,
        "verified_original_pdfs": sorted(received, key=lambda x: x["meeting"]),
        "source_row_identity_independently_accepted": False,
        "gold_fields_independently_verified": False,
        "holdout_validated": False,
        "pit_certified": False,
        "parser_approved": False,
        "model_training_or_bet_authority": False,
        "limitations": [
            "Archive ID and PDF SHA-256/page-count are checked; no publisher publication time.",
            "Printed horse history row ownership still needs independent visual review.",
            "No field among 390 becomes independent gold from byte integrity alone.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-evidence", required=True, type=Path)
    parser.add_argument("--archive", action="append", required=True,
                        help="One original GitHub Actions artifact: ID=/path/original.zip")
    parser.add_argument("--blank-ledger-output", type=Path)
    parser.add_argument("--source-locators", type=Path)
    parser.add_argument("--review-hints-output", type=Path)
    parser.add_argument("--navigation-csv-output", type=Path)
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    archives = {}
    for spec in args.archive:
        if "=" not in spec:
            parser.error("Expected --archive ID=/path/original.zip")
        key, path = spec.split("=", 1)
        if not key.isdecimal() or int(key) in archives or not path:
            parser.error("Invalid or duplicate artifact ID")
        archives[int(key)] = Path(path)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    evidence = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    source_locators = (
        json.loads(args.source_locators.read_text(encoding="utf-8"))
        if args.source_locators is not None else None
    )
    report = audit_archives(
        manifest, evidence, archives,
        blank_ledger_output=args.blank_ledger_output,
        source_locators=source_locators,
        review_hints_output=args.review_hints_output,
        navigation_csv_output=args.navigation_csv_output,
    )
    if args.report_output is not None:
        if args.report_output.exists():
            parser.error("Refusing overwrite existing original replay report")
        args.report_output.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
