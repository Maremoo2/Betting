"""DATA-004: compare TWO independent original-PDF holdout-review ledgers.

This checks provenance structure, original source bytes and reviewer agreement.
Even two identical transcripts do NOT establish human independence, visual
correctness, gold acceptance, parser accuracy or model/BET permission.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .data004_diagnostic import FIELDS
from .data004_original_pdf_audit import LEDGER_COLUMNS, verify_original_pdfs

REVIEWED = {"GOLD_VALUE_RECORDED", "GOLD_UNAVAILABLE", "GOLD_AMBIGUOUS"}
PENDING = "PENDING_VISUAL_REVIEW"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_review(
    path: Path, expected: dict[tuple[str, str], dict[str, str]],
    pages: dict[str, int], *, side: str,
) -> tuple[dict[tuple[str, str], dict[str, str]], str | None, int]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(LEDGER_COLUMNS):
            raise ValueError(f"{side}: frozen review columns changed")
        rows = list(reader)
    if len(rows) != len(expected):
        raise ValueError(f"{side}: expected exactly {len(expected)} cells")
    seen: dict[tuple[str, str], dict[str, str]] = {}
    names: set[str] = set()
    completed = 0
    for row in rows:
        if None in row or any(not isinstance(x, str) for x in row.values()):
            raise ValueError(f"{side}: malformed or truncated CSV row")
        key = (row["sample_id"], row["field"])
        source = expected.get(key)
        if source is None or key in seen:
            raise ValueError(f"{side}: unknown or duplicate frozen cell {key}")
        for col in ("sample_id", "field", "meeting", "original_parser_status",
                    "source_pdf_sha256"):
            if row[col] != source[col]:
                raise ValueError(f"{side}: source identity changed for cell {key}")
        status = row["gold_status"]
        if status == PENDING:
            if any(row[k] for k in (
                "source_pdf_page", "visual_row_locator", "independent_reviewer",
                "gold_value",
            )):
                raise ValueError(f"{side}: pending cell has fabricated partial review {key}")
        elif status in REVIEWED:
            reviewer = row["independent_reviewer"].strip()
            locator = row["visual_row_locator"].strip()
            page_text = row["source_pdf_page"]
            if not reviewer or not locator or not page_text.isdecimal():
                raise ValueError(f"{side}: reviewed cell has no page/locator/reviewer {key}")
            page = int(page_text)
            if not 1 <= page <= pages[row["meeting"]]:
                raise ValueError(f"{side}: page outside verified PDF {key}")
            if status == "GOLD_VALUE_RECORDED":
                if not row["gold_value"].strip():
                    raise ValueError(f"{side}: empty recorded value {key}")
            elif row["gold_value"].strip():
                raise ValueError(f"{side}: unavailable/ambiguous must not invent value {key}")
            names.add(reviewer)
            completed += 1
        else:
            raise ValueError(f"{side}: unknown review status {status!r} at {key}")
        seen[key] = row
    if set(seen) != set(expected):
        raise ValueError(f"{side}: incomplete exact locked sample-field cohort")
    if len(names) > 1:
        raise ValueError(f"{side}: require one named independent reviewer per ledger")
    return seen, next(iter(names), None), completed


def audit_dual_review(
    manifest: dict[str, Any], evidence: dict[str, Any], source_root: Path,
    first_review: Path, second_review: Path,
) -> dict[str, Any]:
    """Revalidate 24 originals before comparing 390 locked semantic cells.

    This function checks structure and disagreement, never visual truth. Human
    review provenance/independence cannot be inferred from a typed username.
    """
    a, b = first_review.resolve(strict=True), second_review.resolve(strict=True)
    if not a.is_file() or not b.is_file() or a == b:
        raise ValueError("Two distinct existing original review CSV files required")
    report = verify_original_pdfs(manifest, evidence, source_root)
    if report["verified_pdf_programs"] != 24:
        raise ValueError("Original 24-PDF source gate not complete")
    by_meeting = {
        item["meeting"]: item for item in report["verified_programs"]
    }
    expected = {}
    for row in manifest["selected"]:
        for field in FIELDS:
            key = (row["sample_id"], field)
            if key in expected:
                raise ValueError("Duplicate preregistered field cell")
            expected[key] = {
                "sample_id": row["sample_id"], "field": field,
                "original_parser_status": row["original_parser_status"],
                "meeting": row["meeting"],
                "source_pdf_sha256": by_meeting[row["meeting"]]["source_pdf_sha256"],
            }
    if len(expected) != 390:
        raise ValueError("Expected exactly 30 x 13 locked original-PDF fields")
    pages = {k: v["pages"] for k, v in by_meeting.items()}
    first, first_person, first_count = _read_review(
        a, expected, pages, side="review_one")
    second, second_person, second_count = _read_review(
        b, expected, pages, side="review_two")
    # A label with the same signature is not independent reviewer evidence.
    if first_person and second_person and first_person.casefold() == second_person.casefold():
        raise ValueError("Same reviewer identity in both supposedly independent ledgers")
    aligned = 0
    unresolved = []
    pending = 0
    both_submitted = 0
    for sample_id, field in sorted(expected):
        left, right = first[(sample_id, field)], second[(sample_id, field)]
        ls, rs = left["gold_status"], right["gold_status"]
        if PENDING in (ls, rs):
            pending += 1
            continue
        both_submitted += 1
        if (ls == rs and left["gold_value"] == right["gold_value"]
                and left["source_pdf_page"] == right["source_pdf_page"]):
            aligned += 1
        else:
            unresolved.append({
                "sample_id": sample_id, "field": field,
                "reason": "INDEPENDENT_REVIEWS_DISAGREE",
                "status_one": ls, "status_two": rs,
                "value_equal": left["gold_value"] == right["gold_value"],
                "page_equal": left["source_pdf_page"] == right["source_pdf_page"],
            })
    result = {
        "schema": "DATA004_INDEPENDENT_DUAL_PDF_REVIEW_AUDIT_V1",
        "status": (
            "REVIEW_SUBMISSIONS_INCOMPLETE" if pending
            else "REVIEW_DISAGREEMENTS_NEED_ADJUDICATION" if unresolved
            else "STRUCTURAL_CONSENSUS_REQUIRES_HUMAN_SOURCE_SIGNOFF"
        ),
        "source_root_verified_original_pdf_count": report["verified_pdf_programs"],
        "source_original_bytes_verified": True,
        "locked_samples": len(manifest["selected"]),
        "locked_fields_per_sample": len(FIELDS),
        "locked_cell_denominator": len(expected),
        "review_one_sha256": _sha(a),
        "review_two_sha256": _sha(b),
        "review_one_submitted_cells": first_count,
        "review_two_submitted_cells": second_count,
        "both_submitted_cells": both_submitted,
        "matching_submissions_needing_human_authentication": aligned,
        "pending_cells": pending,
        "disputed_cells": len(unresolved),
        "disputes": unresolved,
        "reviewer_identity_independence_authenticated": False,
        "source_row_identity_independently_accepted": False,
        "gold_fields_semantically_verified": False,
        "holdout_validated": False,
        "parser_approved": False,
        "pit_or_model_admission_approved": False,
        "betting_authority": False,
        "limitations": [
            "Original SHA and page count are rechecked against actual 24 PDF bytes.",
            "Distinct usernames/files are not proof that reviewers are independent humans.",
            "No automatic optical or parser-derived value may serve as independent gold.",
            "Even matching transcriptions require independent source-row/field signoff.",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-evidence", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--review-one", required=True, type=Path)
    parser.add_argument("--review-two", required=True, type=Path)
    args = parser.parse_args()
    result = audit_dual_review(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.source_evidence.read_text(encoding="utf-8")),
        args.source_root, args.review_one, args.review_two,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "STRUCTURAL_CONSENSUS_REQUIRES_HUMAN_SOURCE_SIGNOFF":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
