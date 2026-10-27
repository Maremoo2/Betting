"""DATA-004F: original-PDF glyph hints for a *blind* 390-cell review.

Read-only research. These literal snippets are NOT adjudicated semantic gold.
They must never populate the accepted holdout or train/promote any parser.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from hbi.data004_diagnostic import FIELDS
from hbi.data004_row_geometry import verify_original_row_geometry

DATE_RACE = re.compile(r"(?P<date>\d{2}\.\d{2}\.\d{2})-(?P<race>\d{1,2})")
DISTANCE_TIME = re.compile(
    r"(?P<distance>\d{3,4})(?:\s+(?P<time>\d{1,2},\d{1,2}[a-z]{0,3}|[a-z]{1,3}))?\Z",
    re.IGNORECASE,
)
PLACEMENT = re.compile(r"(?:\d{1,2}|d|k|-)\Z", re.IGNORECASE)
SHOE_CODE = re.compile(r"[c¢]{2}\Z")
WAGON_CODE = re.compile(r"(?:Va|Am)(?=\s|\Z)")
GALLOP_CODE = re.compile(
    r"(?:\d{1,2},\d{1,2}a?g|ug|dg|g)\Z", re.IGNORECASE
)


def _historical_row_glyph_spans(
    page: Any, token_box: list[float]
) -> list[dict[str, Any]]:
    """Select only raw PDF glyphs aligned with the locked history row."""
    output = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                literal = "".join(char["c"] for char in chars)
                if literal and abs(float(span["bbox"][1]) - token_box[1]) <= 2.8:
                    output.append({
                        "text": literal, "bbox": span["bbox"], "chars": chars,
                    })
    return sorted(output, key=lambda item: item["bbox"][0])


def _glyph_bbox(
    span: dict[str, Any], start: int, end: int
) -> list[float]:
    chars = span["chars"][start:end]
    if not chars or len(chars) != end - start:
        raise ValueError("Historical source-token glyphs are missing")
    return [
        round(float(min(char["bbox"][0] for char in chars)), 3),
        round(float(min(char["bbox"][1] for char in chars)), 3),
        round(float(max(char["bbox"][2] for char in chars)), 3),
        round(float(max(char["bbox"][3] for char in chars)), 3),
    ]


def source_field_hints(page: Any, original_row: dict[str, Any]) -> dict[str, Any]:
    """Locate printed tokens only, abstaining on absent/foreign/derived fields.

    Positive gallop/DQ glyphs may be offered as unreviewed source hints;
    *absence never implies False*. All outputs remain unverified.
    """
    spans = _historical_row_glyph_spans(
        page, original_row["date_race_token_bbox_pdf_points"]
    )
    token = original_row["historical_date_race_token"]
    candidates = [
        (span, match)
        for span in spans
        for match in DATE_RACE.finditer(span["text"])
        if match.group(0) == token
    ]
    if len(candidates) != 1:
        raise ValueError("Historical date/race token is not uniquely printed")
    date_span, date_match = candidates[0]
    fields: dict[str, dict[str, Any]] = {
        field: {
            "field": field,
            "hint_status": "VISUAL_REVIEW_REQUIRED",
            "printed_token": "",
            "printed_bbox_pdf_points": None,
            "hint_only_not_gold": True,
            "reason": "No unambiguous printed source token located",
        }
        for field in FIELDS
    }

    def offer(field: str, span: dict[str, Any], start: int, end: int) -> None:
        literal = span["text"][start:end]
        if literal and not fields[field]["printed_token"]:
            fields[field] = {
                "field": field,
                "hint_status": "PRINTED_TOKEN_HINT_UNREVIEWED",
                "printed_token": literal,
                "printed_bbox_pdf_points": _glyph_bbox(span, start, end),
                "hint_only_not_gold": True,
                "reason": (
                    "Source glyphs on the frozen physical PDF history row; "
                    "field interpretation not visually verified"
                ),
            }

    offer("date", date_span, date_match.start("date"), date_match.end("date"))
    offer(
        "race_number", date_span,
        date_match.start("race"), date_match.end("race"),
    )

    # Read *historical* track, not the target meeting's (potentially composite)
    # track. For foreign PDFs where track/date share another layout, abstain.
    prefix = date_span["text"][:date_match.start()].strip()
    if (1 <= len(prefix) <= 3 and prefix.isalpha()
            and 44 <= date_span["bbox"][0] <= 65):
        start = date_span["text"].find(prefix)
        offer("track", date_span, start, start + len(prefix))
    elif 55 <= date_span["bbox"][0] <= 69:
        preceding = [
            span for span in spans
            if 45 <= span["bbox"][0] <= 55
            and span["bbox"][2] <= date_span["bbox"][0]
        ]
        if (len(preceding) == 1
                and 1 <= len(preceding[0]["text"].strip()) <= 3
                and preceding[0]["text"].strip().isalpha()):
            span = preceding[0]
            offer("track", span, 0, len(span["text"].strip()))

    drivers = [
        span for span in spans
        if 20 <= span["bbox"][0] <= 30
        and span["bbox"][2] < 49
        and not DATE_RACE.search(span["text"])
    ]
    if len(drivers) == 1 and 2 <= len(drivers[0]["text"].strip()) <= 30:
        span = drivers[0]
        offer("driver", span, 0, len(span["text"].rstrip()))

    placings = [
        span for span in spans
        if 98 <= span["bbox"][0] <= 105
        and PLACEMENT.fullmatch(span["text"].strip())
    ]
    if len(placings) == 1:
        span = placings[0]
        offer("placing", span, 0, len(span["text"].strip()))
        if span["text"].strip().casefold() == "d":
            offer("dq", span, 0, len(span["text"].strip()))

    # Keep a strict, track-specific layout for original distance/time columns.
    # Foreign elapsed times, prize values and result notes are not kilometre
    # times and must not be silently assigned to that field.
    distances = [
        (span, DISTANCE_TIME.fullmatch(span["text"].strip()))
        for span in spans if 111 <= span["bbox"][0] <= 119
    ]
    distances = [(span, match) for span, match in distances if match]
    if len(distances) == 1:
        span, match = distances[0]
        offer("distance", span, match.start("distance"), match.end("distance"))
        time = match.group("time")
        if time:
            if re.fullmatch(r"\d{1,2},\d{1,2}a?", time, re.IGNORECASE):
                offer("km_time", span, match.start("time"), match.end("time"))
            if GALLOP_CODE.fullmatch(time):
                offer("gallop", span, match.start("time"), match.end("time"))

    shoes = [
        span for span in spans
        if 173 <= span["bbox"][0] <= 179
        and SHOE_CODE.fullmatch(span["text"].strip())
    ]
    if len(shoes) == 1:
        span = shoes[0]
        offer("shoes", span, 0, len(span["text"].strip()))

    wagons = [
        (span, WAGON_CODE.match(span["text"]))
        for span in spans if 185 <= span["bbox"][0] <= 194
    ]
    wagons = [(span, match) for span, match in wagons if match]
    if len(wagons) == 1:
        span, match = wagons[0]
        offer("wagon", span, match.start(), match.end())

    return {
        "sample_id": original_row["sample_id"],
        "horse": original_row["horse"],
        "meeting": original_row["meeting"],
        "source_pdf_page": original_row["source_pdf_page"],
        "source_pdf_sha256": original_row["source_pdf_sha256"],
        "historical_marker": token,
        "evidence": [fields[field] for field in FIELDS],
        "independent_gold_fields_accepted": 0,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
    }


def build_original_pdf_review_hints(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    locators: dict[str, Any],
    source_root: Path,
) -> dict[str, Any]:
    """Reverify all 24 real PDF bytes and 30 physical horse/history rows first."""
    from fitz import open as open_pdf

    geometry = verify_original_row_geometry(
        manifest, evidence, locators, source_root
    )
    if (geometry.get("status") != "SOURCE_GEOMETRY_MATCHED_GOLD_PENDING"
            or geometry.get("original_pdf_byte_matches") != 24
            or geometry.get("source_rows_with_unique_physical_header_and_history") != 30
            or geometry.get("holdout_verified") is not False):
        raise ValueError("Unverified original-PDF source geometry")
    frozen = {item["sample_id"]: item for item in manifest["selected"]}
    rows = []
    root = source_root.resolve(strict=True)
    for original in geometry["rows"]:
        source = frozen[original["sample_id"]]
        path = (root / source["expected_pdf_path"]).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Source PDF path escaped original archive")
        with open_pdf(path) as pdf:
            rows.append(source_field_hints(
                pdf[original["source_pdf_page"] - 1], original,
            ))
    if len(rows) != 30 or len({row["sample_id"] for row in rows}) != 30:
        raise ValueError("Frozen 30 historical source rows are incomplete")
    if any(len(row["evidence"]) != len(FIELDS) for row in rows):
        raise ValueError("Missing one of the 13 source field review prompts")
    counts = Counter(
        item["field"] for row in rows for item in row["evidence"]
        if item["hint_status"] == "PRINTED_TOKEN_HINT_UNREVIEWED"
    )
    return {
        "schema_version": "DATA004F_ORIGINAL_PDF_REVIEW_HINTS_V1",
        "status": "ORIGINAL_PDF_GLYPH_HINTS_GOLD_PENDING",
        "locked_rows": 30,
        "field_assessments": 30 * len(FIELDS),
        "literal_hints_by_field": dict(counts),
        "literal_hints_total": sum(counts.values()),
        "independent_source_gold_accepted": 0,
        "holdout_verified": False,
        "production_parser_approved": False,
        "bet_gates_changed": False,
        "rows": rows,
        "limitations": [
            "Automated glyph hints do not constitute independent visual gold.",
            "All 390 cells still need original-PDF reviewer attestation and adjudication.",
            "No negative gallop/disqualification assertions are manufactured.",
            "No old/candidate parser output, training data or racing model was read.",
        ],
    }



REVIEW_NAV_COLUMNS = (
    "sample_id", "horse", "meeting", "source_pdf_sha256",
    "source_pdf_page", "field", "hint_status",
    "printed_token_hint_unreviewed", "printed_bbox_pdf_points",
    "source_reading_accepted_gold",
)


def write_navigation_csv(report: dict[str, Any], destination: Path) -> None:
    """Off-repo 390-cell source-only CSV, with NO review or gold promotion."""
    if (report.get("schema_version") != "DATA004F_ORIGINAL_PDF_REVIEW_HINTS_V1"
            or report.get("locked_rows") != 30
            or report.get("field_assessments") != 390
            or report.get("independent_source_gold_accepted") != 0
            or report.get("holdout_verified") is not False):
        raise ValueError("Unverified/altered source hint report")
    with destination.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_NAV_COLUMNS)
        writer.writeheader()
        for row in report["rows"]:
            for evidence in row["evidence"]:
                box = evidence["printed_bbox_pdf_points"]
                writer.writerow({
                    "sample_id": row["sample_id"],
                    "horse": row["horse"],
                    "meeting": row["meeting"],
                    "source_pdf_sha256": row["source_pdf_sha256"],
                    "source_pdf_page": row["source_pdf_page"],
                    "field": evidence["field"],
                    "hint_status": evidence["hint_status"],
                    "printed_token_hint_unreviewed": evidence["printed_token"],
                    "printed_bbox_pdf_points": (
                        ",".join(str(v) for v in box) if box else ""
                    ),
                    "source_reading_accepted_gold": "NO",
                })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--locators", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--navigation-csv-output", type=Path)
    args = parser.parse_args()
    manifest, evidence, locators = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (args.manifest, args.source_evidence, args.locators)
    ]
    result = build_original_pdf_review_hints(
        manifest, evidence, locators, args.source_root
    )
    # Private/off-repository source snippets. Never replace an existing file.
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    with args.output.open("x", encoding="utf-8") as output:
        output.write(payload)
    if args.navigation_csv_output is not None:
        write_navigation_csv(result, args.navigation_csv_output)
    print(json.dumps(
        {key: value for key, value in result.items() if key != "rows"},
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
