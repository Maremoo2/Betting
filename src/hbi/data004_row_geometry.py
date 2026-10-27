"""DATA-004D: real-PDF source row geometry, with no gold/value inference.

A positive result proves only that a single horse header and a specific dated
history race token occupy the same bounded horse section on the frozen page.
It DOES NOT certify the 13 historical fields or any parser improvement.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from hbi.data004_gold_review import validate_source_locators
from hbi.data004_original_pdf_audit import verify_original_pdfs

RACE_SUFFIX = re.compile(r"-(\d{1,2})\Z")


def _normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.upper())
    return "".join(
        char for char in normalized
        if char.isalnum() and not unicodedata.combining(char)
    )


def _history_marker(source_date: str, race_token: str) -> str:
    try:
        day = date.fromisoformat(source_date)
    except ValueError as exc:
        raise ValueError("Invalid original-history source date") from exc
    suffix = RACE_SUFFIX.search(race_token)
    if suffix is None:
        raise ValueError("No explicit historical race number in frozen locator")
    return f"{day:%d.%m.%y}-{int(suffix.group(1))}"


def _rect(rect: tuple[float, float, float, float]) -> list[float]:
    return [round(float(item), 3) for item in rect]


def identify_original_row(page: Any, *, horse: str, source_date: str,
                          race_token: str) -> dict[str, Any]:
    """Find original printed row physically; fail closed on ambiguous sections.

    This is a document-layout locator. Font and left margin restrictions are
    deliberately conservative, based on observed Collector program layouts.
    Other PDF styles should abstain rather than force a match.
    """
    spans = [
        span for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ]
    headings = [
        span for span in spans
        if span["size"] >= 10.5 and span["bbox"][0] <= 31
        and len(span["text"].strip()) > 3
    ]
    normalized = _normalized_name(horse)
    headers = [span for span in headings
               if normalized and normalized in _normalized_name(span["text"])]
    if len(headers) != 1:
        raise ValueError(f"Expected exactly one physical horse header: {horse}")
    header = headers[0]
    start = float(header["bbox"][1])
    later = [float(span["bbox"][1]) for span in headings
             if float(span["bbox"][1]) > start + 2]
    end = min(later, default=float(page.rect.height))
    if end <= start + 12:
        raise ValueError("Horse section has no usable vertical extent")
    token = _history_marker(source_date, race_token)
    occurrences = [
        span for span in spans
        if start + 10 <= span["bbox"][1] < end
        and token in span["text"]
    ]
    if len(occurrences) != 1:
        raise ValueError(
            f"Historical date/race token must be unique inside horse section: {token}"
        )
    found = occurrences[0]
    return {
        "status": "GEOMETRY_UNIQUE_HEADER_AND_HISTORY_TOKEN",
        "horse_header_bbox_pdf_points": _rect(header["bbox"]),
        "physical_section_bbox_pdf_points": _rect(
            (0, max(start, 0), page.rect.width, min(end, page.rect.height))
        ),
        "date_race_token_bbox_pdf_points": _rect(found["bbox"]),
        "historical_date_race_token": token,
        "independent_visual_field_gold": False,
    }


def verify_original_row_geometry(
    manifest: dict[str, Any], evidence: dict[str, Any],
    locators: dict[str, Any], source_root: Path,
) -> dict[str, Any]:
    """Rehash all 24 originals, then check 30 printed section/token positions."""
    by_id = validate_source_locators(manifest, evidence, locators)
    byte_audit = verify_original_pdfs(manifest, evidence, source_root)
    from fitz import open as open_pdf  # PyMuPDF, dev-only original-layout evidence

    frozen = {row["sample_id"]: row for row in manifest["selected"]}
    rows: list[dict[str, Any]] = []
    for sample_id, locator in by_id.items():
        orig = frozen[sample_id]
        pdf_path = (source_root / orig["expected_pdf_path"]).resolve(strict=True)
        with open_pdf(pdf_path) as pdf:
            page = pdf[locator["pdf_page"] - 1]
            identified = identify_original_row(
                page,
                horse=locator["horse"],
                source_date=locator["source_date"],
                race_token=locator["historical_race_token"],
            )
        rows.append({
            "sample_id": sample_id,
            "meeting": locator["meeting"],
            "horse": locator["horse"],
            "source_pdf_sha256": locator["source_pdf_sha256"],
            "source_pdf_page": locator["pdf_page"],
            **identified,
        })
    positions = {x["sample_id"]: i for i, x in enumerate(manifest["selected"])}
    rows.sort(key=lambda item: positions[item["sample_id"]])
    return {
        "schema_version": "DATA004D_SOURCE_ROW_GEOMETRY_V1",
        "status": "SOURCE_GEOMETRY_MATCHED_GOLD_PENDING",
        "original_pdf_byte_matches": byte_audit["verified_pdf_programs"],
        "source_rows_with_unique_physical_header_and_history": len(rows),
        "locked_holdout_samples": len(by_id),
        "field_gold_independently_accepted": False,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
        "rows": rows,
        "limitations": [
            "Existing text-derived page/date/race locators were used to find printed positions.",
            "Font size and section boundaries are geometric evidence, not an independent visual reading.",
            "No parser outputs or 13-field labels were used or validated.",
            "Independent visual source-column review and external adjudication are still required.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--locators", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inputs = [json.loads(path.read_text(encoding="utf-8")) for path in (
        args.manifest, args.source_evidence, args.locators
    )]
    report = verify_original_row_geometry(*inputs, args.source_root)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
