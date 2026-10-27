"""DATA-004C: blind, source-only original-PDF gold-review protocol.

The original PDF remains authoritative. The locked selection and source locators
are navigation aids, NEVER ground-truth transcriptions or model predictions.
This module intentionally cannot promote parser, model or BET readiness.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from hbi.data004_diagnostic import FIELDS
from hbi.data004_holdout_gate import audit_source_evidence
from hbi.data004_original_pdf_audit import verify_original_pdfs

REVIEW_COLUMNS = (
    "sample_id", "horse", "meeting", "field", "source_pdf_sha256",
    "source_pdf_page", "visual_row_locator", "row_identity_visual",
    "reviewer_id", "gold_status", "gold_value", "evidence_code",
    "review_note",
)
REVIEW_STATES = {
    "PENDING_VISUAL_REVIEW", "VERIFIED", "AMBIGUOUS", "UNAVAILABLE",
}
BBOX_PATTERN = re.compile(
    r"\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?),\s*"
    r"(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\s*\Z"
)


def validate_source_locators(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    locators: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Verify frozen identity JOIN, not the unreviewed PDF semantic fields."""
    audit_source_evidence(manifest, evidence)
    if locators.get("schema_version") != "DATA004C_SOURCE_LOCATOR_INDEX_V1":
        raise ValueError("Unexpected blind source-locator schema")
    if (locators.get("source_mapping_is_independent_gold") is not False
            or locators.get("visual_horse_row_identity_verified") is not False
            or locators.get("field_gold_verified") is not False
            or locators.get("holdout_verified") is not False):
        raise ValueError("Source locators cannot claim gold-field approval")
    records = locators.get("records")
    if not isinstance(records, list) or len(records) != 30:
        raise ValueError("Expected 30 source-only navigation records")
    locked = {row["sample_id"]: row for row in manifest["selected"]}
    programs = {item["meeting"]: item for item in evidence["programs"]}
    by_id: dict[str, dict[str, Any]] = {}
    names: set[str] = set()
    for record in records:
        sid = record.get("sample_id")
        if sid in by_id or sid not in locked:
            raise ValueError("Duplicate or unknown source sample ID")
        frozen = locked[sid]
        meeting = record.get("meeting")
        if meeting != frozen["meeting"]:
            raise ValueError(f"Source meeting differs from preregistration: {sid}")
        program = programs[meeting]
        if record.get("source_pdf_sha256") != program["pdf_sha256"]:
            raise ValueError(f"Wrong source PDF hash for {sid}")
        page = record.get("pdf_page")
        if type(page) is not int or not (1 <= page <= program["pages"]):
            raise ValueError(f"Unusable page locator for {sid}")
        horse = record.get("horse")
        if not isinstance(horse, str) or not horse.strip() or horse in names:
            raise ValueError(f"Missing or duplicate horse header for {sid}")
        try:
            date.fromisoformat(record["source_date"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError(f"Invalid historical date locator for {sid}") from exc
        if not isinstance(record.get("historical_race_token"), str):
            raise TypeError(f"Missing historical race locator for {sid}")
        if record.get("source_locator_origin") != (
            "EXISTING_TEXT_MAPPING_VISUAL_REVIEW_REQUIRED"
        ):
            raise ValueError(f"Source locator must not imply visual confirmation: {sid}")
        names.add(horse)
        by_id[sid] = record
    if set(by_id) != set(locked):
        raise ValueError("The 30 registered holdout identities changed")
    return by_id


def make_blank_review_ledger(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    locators: dict[str, Any],
    byte_audit: dict[str, Any],
    output: Path,
) -> None:
    """Generate 390 blind reviews; never copy archived parser field values."""
    by_id = validate_source_locators(manifest, evidence, locators)
    if (byte_audit.get("status") != "ORIGINAL_PDF_BYTES_VERIFIED_GOLD_PENDING"
            or byte_audit.get("verified_pdf_programs") != 24
            or byte_audit.get("original_source_bytes_verified") is not True
            or byte_audit.get("holdout_verified") is not False):
        raise ValueError("Source-byte verification is required before gold review")
    original_sha_by_meeting = {
        item["meeting"]: item["source_pdf_sha256"]
        for item in byte_audit.get("verified_programs", [])
    }
    if len(original_sha_by_meeting) != 24:
        raise ValueError("Incomplete original PDF byte audit")
    for loc in by_id.values():
        if original_sha_by_meeting.get(loc["meeting"]) != loc["source_pdf_sha256"]:
            raise ValueError("Original-PDF audit and frozen locator disagree")
    with output.open("x", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for frozen in manifest["selected"]:
            loc = by_id[frozen["sample_id"]]
            for field in FIELDS:
                writer.writerow({
                    "sample_id": frozen["sample_id"],
                    "horse": loc["horse"],
                    "meeting": loc["meeting"],
                    "field": field,
                    "source_pdf_sha256": loc["source_pdf_sha256"],
                    "source_pdf_page": loc["pdf_page"],
                    "visual_row_locator": "",
                    "row_identity_visual": "",
                    "reviewer_id": "",
                    "gold_status": "PENDING_VISUAL_REVIEW",
                    "gold_value": "",
                    "evidence_code": "",
                    "review_note": "",
                })


def _check_bbox(value: str) -> None:
    match = BBOX_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("Evidence requires an x0,y0,x1,y1 original-page locator")
    x0, y0, x1, y1 = map(float, match.groups())
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Source locator has invalid rectangle dimensions")


def audit_review_ledger(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    locators: dict[str, Any],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Validate review completeness and citations, NOT accuracy or independence."""
    by_id = validate_source_locators(manifest, evidence, locators)
    if len(rows) != 390:
        raise ValueError("Exactly 390 field review records are mandatory")
    frozen_by_id = {x["sample_id"]: x for x in manifest["selected"]}
    observed: set[tuple[str, str]] = set()
    states: Counter[str] = Counter()
    by_stratum: dict[str, Counter[str]] = {
        s: Counter() for s in ("PARSED", "PARTIAL", "UNPARSEABLE")
    }
    for row in rows:
        if set(row) != set(REVIEW_COLUMNS):
            raise ValueError("Invalid review schema or parser-derived value column")
        sample_id, field = row["sample_id"], row["field"]
        key = (sample_id, field)
        if sample_id not in by_id or field not in FIELDS or key in observed:
            raise ValueError(f"Unknown or duplicate assessment: {key!r}")
        observed.add(key)
        loc = by_id[sample_id]
        if (
            row["horse"] != loc["horse"]
            or row["meeting"] != loc["meeting"]
            or row["source_pdf_sha256"] != loc["source_pdf_sha256"]
            or row["source_pdf_page"] != str(loc["pdf_page"])
        ):
            raise ValueError(f"Source-page identity was altered: {key!r}")
        status = row["gold_status"]
        if status not in REVIEW_STATES:
            raise ValueError(f"Unsupported field evidence state: {key!r}")
        states[status] += 1
        by_stratum[frozen_by_id[sample_id]["original_parser_status"]][status] += 1
        if status == "PENDING_VISUAL_REVIEW":
            if any(row[k].strip() for k in (
                "visual_row_locator", "row_identity_visual", "reviewer_id",
                "gold_value", "evidence_code", "review_note",
            )):
                raise ValueError(f"Pending cell contains unverifiable data: {key!r}")
            continue
        if row["row_identity_visual"] != "CONFIRMED":
            raise ValueError(f"Visual horse/row ownership not attested: {key!r}")
        if not row["reviewer_id"].strip():
            raise ValueError(f"Missing independent reviewer declaration: {key!r}")
        _check_bbox(row["visual_row_locator"])
        code = row["evidence_code"]
        value = row["gold_value"]
        if status == "VERIFIED":
            if value == "" or code not in {"PRINTED_CELL", "EXPLICIT_NEGATIVE_MARK"}:
                raise ValueError(f"Verified field lacks a literal source value: {key!r}")
            if (field in {"gallop", "dq"} and value == "False"
                    and code != "EXPLICIT_NEGATIVE_MARK"):
                raise ValueError(
                    "Absence of a gallop/DQ marker is not a verified negative"
                )
        elif status == "AMBIGUOUS":
            if value != "" or code != "AMBIGUOUS_LAYOUT":
                raise ValueError(f"Ambiguous source cannot assert a value: {key!r}")
            if len(row["review_note"].strip()) < 8:
                raise ValueError("Ambiguity needs a concrete review explanation")
        elif status == "UNAVAILABLE":
            if value != "" or code not in {
                "NOT_PRINTED", "FOREIGN_FORMAT_UNRESOLVED",
            }:
                raise ValueError(f"Unavailable source cannot assert a value: {key!r}")
            if len(row["review_note"].strip()) < 8:
                raise ValueError("Unavailable evidence needs a reason")
    if len(observed) != 390:
        raise ValueError("At least one frozen sample/field pair is missing")

    fully_reviewed = sum(
        all(
            next(r["gold_status"] for r in rows if (
                r["sample_id"] == sid and r["field"] == field
            )) != "PENDING_VISUAL_REVIEW"
            for field in FIELDS
        )
        for sid in by_id
    )
    return {
        "schema_version": "DATA004C_BLIND_GOLD_REVIEW_AUDIT_V1",
        "status": (
            "REVIEW_ATTESTED_EXTERNAL_ACCEPTANCE_REQUIRED"
            if states["PENDING_VISUAL_REVIEW"] == 0
            else "HOLDOUT_GOLD_REVIEW_INCOMPLETE"
        ),
        "locked_samples": 30,
        "required_field_assessments": 390,
        "field_review_states": dict(states),
        "field_review_states_by_original_status": {
            k: dict(v) for k, v in by_stratum.items()
        },
        "fully_reviewed_samples": fully_reviewed,
        "source_identifiers_checked": True,
        "original_pdf_values_independently_verified_by_this_code": False,
        "reviewer_attestations_externally_verified": False,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
        "limitations": [
            "PDF page/horse locators are from an earlier text-mapping audit, not gold.",
            "Self-declared reviews and bounding-box strings need independent human audit.",
            "Gold cannot be scored against candidate parser or promoted by this utility.",
            "No source-unavailable cells are silently counted as correct negatives.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--locators", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--blank-output", type=Path)
    group.add_argument("--audit-review", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    evidence = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    locators = json.loads(args.locators.read_text(encoding="utf-8"))
    if args.blank_output:
        if args.source_root is None:
            parser.error("--blank-output requires --source-root")
        verified = verify_original_pdfs(manifest, evidence, args.source_root)
        make_blank_review_ledger(
            manifest, evidence, locators, verified, args.blank_output,
        )
        report = {
            "status": "BLIND_390_REVIEW_TASKS_CREATED_GOLD_PENDING",
            "review_output": str(args.blank_output),
            "holdout_verified": False,
        }
    else:
        if args.source_root is None:
            parser.error("--audit-review requires --source-root")
        verify_original_pdfs(manifest, evidence, args.source_root)
        with args.audit_review.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or set(reader.fieldnames) != set(REVIEW_COLUMNS):
                raise ValueError("Incorrect ledger header or parser value leak")
            report = audit_review_ledger(
                manifest, evidence, locators, list(reader),
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
