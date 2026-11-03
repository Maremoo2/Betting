"""DEV-012: strict multi-page physical PDF roster verification.

The opt-in original replay reads the immutable 3 Nov Vincennes Collector
artifact. Ordinary tests use purpose-built PDF pages and never assert PIT.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import fitz
import pytest

from hbi.collector_handoff import pdf_field


def _pdf(*pages: list[str]) -> bytes:
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page()
        for i, line in enumerate(lines):
            page.insert_text((40, 50 + 18 * i), line)
    raw = doc.tobytes()
    doc.close()
    return raw


def _runners(*names: str) -> dict:
    return {str(i): {"name": name} for i, name in enumerate(names, 1)}


def test_multpage_original_race_matches_only_its_continuation():
    body = _pdf(
        ["6", "START KL. 16:50", "1 FIRST HORSE, Driver", "2 SECOND HORSE, Driver"],
        ["3 THIRD HORSE, Driver", "13", "4 FOURTH HORSE, Driver"],
        ["7", "START KL. 17:25", "1 DIFFERENT HORSE, Driver"],
    )
    assert pdf_field(
        body, 6, _runners("First Horse", "Second Horse", "Third Horse", "Fourth Horse"),
        "2026-11-03",
    ) == datetime(2026, 11, 3, 15, 50, tzinfo=UTC).isoformat()


def test_missing_continuation_runner_still_fails_closed():
    body = _pdf(
        ["6", "START KL. 16:50", "1 FIRST HORSE, Driver"],
        ["2 A DIFFERENT HORSE, Driver"],
    )
    with pytest.raises(ValueError, match="COLLECTOR_PDF_FIELD_MISMATCH"):
        pdf_field(body, 6, _runners("First Horse", "Second Horse"), "2026-11-03")


def test_next_physical_race_is_never_used_to_complete_previous_field():
    body = _pdf(
        ["6", "START KL. 16:50", "1 FIRST HORSE, Driver"],
        ["7", "START KL. 17:25", "2 SECOND HORSE, Driver"],
    )
    with pytest.raises(ValueError, match="COLLECTOR_PDF_FIELD_MISMATCH"):
        pdf_field(body, 6, _runners("First Horse", "Second Horse"), "2026-11-03")


def test_duplicate_race_heading_remains_ambiguous():
    body = _pdf(
        ["6", "START KL. 16:50", "1 FIRST HORSE, Driver"],
        ["Lopp 6", "START KL. 16:50", "2 SECOND HORSE, Driver"],
    )
    with pytest.raises(ValueError, match="COLLECTOR_PDF_PHYSICAL_RACE_AMBIGUOUS"):
        pdf_field(body, 6, _runners("First Horse", "Second Horse"), "2026-11-03")


def test_unverifiable_physical_clock_remains_blocked():
    body = _pdf(
        ["6", "1 FIRST HORSE, Driver"],
        ["2 SECOND HORSE, Driver"],
    )
    with pytest.raises(ValueError, match="COLLECTOR_PDF_RACE_CLOCK_UNVERIFIED"):
        pdf_field(body, 6, _runners("First Horse", "Second Horse"), "2026-11-03")


def test_authentic_vincennes_original_fields_and_source_hashes():
    """Opt-in: HBI_DEV012_AUTHENTIC_ARCHIVE is an extracted Collector artifact.

    GitHub source run 41663427015, artifact pit003a-collector-evidence-41663427015.
    This verifies PDF + starts bytes, not independent provider identity or PIT.
    """
    root = os.environ.get("HBI_DEV012_AUTHENTIC_ARCHIVE")
    if not root:
        pytest.skip("opt-in original Collector archive not supplied")
    base = Path(root)
    meeting = list(base.rglob("meetings/F1_NR_2026-11-03/full_program.pdf"))
    starts = list(base.rglob("meetings/F1_NR_2026-11-03/starts.raw.json"))
    assert len(meeting) == len(starts) == 1
    raw_pdf = meeting[0].read_bytes()
    raw_starts = starts[0].read_bytes()
    assert hashlib.sha256(raw_pdf).hexdigest() == (
        "e565e0f797a74c7c82f7bf9e302d7b6a33a6433cea2334d5e093904f5447fb57"
    )
    assert hashlib.sha256(raw_starts).hexdigest() == (
        "a4e4330ae9fc9279619333ecf55604c042021227a0bec0d3d69fd512b33eeea0"
    )
    source = json.loads(raw_starts)
    assert source["success"] is True
    for number, hh, mm, size in [(6, 15, 50, 14), (7, 16, 25, 13), (8, 17, 0, 16)]:
        field = source["result"][str(number)]
        assert len(field) == size
        runners = {
            str(row["startNumber"]): {"name": row["horseName"]}
            for row in field
        }
        assert len(runners) == size
        assert pdf_field(raw_pdf, number, runners, "2026-11-03") == (
            datetime(2026, 11, 3, hh, mm, tzinfo=UTC).isoformat()
        )
