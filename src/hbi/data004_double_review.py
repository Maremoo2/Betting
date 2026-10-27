"""DATA-004E: independent double-read adjudication diagnostics, never gold approval.

Only compares two *separately prepared* DATA-004C review CSVs; it does not
extract, interpret or certify original PDF field values. No production writes.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from hbi.data004_gold_review import REVIEW_COLUMNS, audit_review_ledger


def compare_independent_reviews(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    locators: dict[str, Any],
    first: list[dict[str, str]],
    second: list[dict[str, str]],
) -> dict[str, Any]:
    """Require complete schema/identities and report disagreements, fail closed."""
    a = audit_review_ledger(manifest, evidence, locators, first)
    b = audit_review_ledger(manifest, evidence, locators, second)
    def indexed(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
        return {(r["sample_id"], r["field"]): r for r in rows}

    a_by, b_by = indexed(first), indexed(second)
    if a_by.keys() != b_by.keys():
        raise ValueError("Independent reviews do not cover identical locked field pairs")

    agreement = Counter()
    differences: list[dict[str, str]] = []
    pending = []
    reviewer_collisions = []
    for sample_id, field in sorted(a_by):
        left, right = a_by[(sample_id, field)], b_by[(sample_id, field)]
        key = {"sample_id": sample_id, "field": field}
        if (left["gold_status"] == "PENDING_VISUAL_REVIEW"
                or right["gold_status"] == "PENDING_VISUAL_REVIEW"):
            pending.append(key)
            continue
        if left["reviewer_id"].strip().casefold() == right["reviewer_id"].strip().casefold():
            reviewer_collisions.append(key)
            continue
        # Compare source values literally: no silent whitespace or semantic
        # normalization. Source box differences are recorded, not treated as
        # proof of agreement or disagreement about the field itself.
        if (left["gold_status"], left["gold_value"], left["evidence_code"]) == (
            right["gold_status"], right["gold_value"], right["evidence_code"]
        ):
            agreement[left["gold_status"]] += 1
        else:
            differences.append({
                **key,
                "review_a_status": left["gold_status"],
                "review_b_status": right["gold_status"],
                "review_a_value": left["gold_value"],
                "review_b_value": right["gold_value"],
                "review_a_evidence_code": left["evidence_code"],
                "review_b_evidence_code": right["evidence_code"],
            })
    return {
        "schema_version": "DATA004E_DOUBLE_READ_AUDIT_V1",
        "status": "EXTERNAL_ORIGINAL_PDF_ADJUDICATION_REQUIRED",
        "locked_field_pairs": 390,
        "identical_source_values_by_status": dict(agreement),
        "pending_pairs": pending,
        "reviewer_identity_collisions": reviewer_collisions,
        "disagreements": differences,
        "first_review_status": a["status"],
        "second_review_status": b["status"],
        "double_read_fully_clear": (
            not pending and not reviewer_collisions and not differences
        ),
        "source_pdf_semantics_independently_verified_by_this_code": False,
        "reviewer_independence_externally_verified": False,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
        "limitations": [
            "Two matching CSV assertions do not prove either reviewer consulted original PDFs.",
            "Matching values may share systematic mistakes; manual source adjudication is mandatory.",
            "Original PDF page/field bounding boxes require independent physical review.",
            "No parser candidate comparison or automatic gold promotion is performed.",
        ],
    }


def _read_review(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or tuple(reader.fieldnames) != REVIEW_COLUMNS:
            raise ValueError("Review CSV must use the exact frozen blind-review schema")
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--locators", type=Path, required=True)
    parser.add_argument("--review-a", type=Path, required=True)
    parser.add_argument("--review-b", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    from hbi.data004_original_pdf_audit import verify_original_pdfs

    manifest, evidence, locators = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (args.manifest, args.source_evidence, args.locators)
    ]
    verify_original_pdfs(manifest, evidence, args.source_root)
    report = compare_independent_reviews(
        manifest, evidence, locators,
        _read_review(args.review_a), _read_review(args.review_b),
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    print(serialized)


if __name__ == "__main__":
    main()
