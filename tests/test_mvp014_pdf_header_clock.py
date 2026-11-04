"""MVP-014 P0: genuine 4 Nov physical PDF headers vs immutable /starts field."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest
import fitz

from hbi.collector_handoff import pdf_field


ORIGINAL_SHA256 = {
    "F1_NR_2026-11-04": {
        "full_program.pdf": "b5b7f5999fed5241cef3c16b27cf31161c010822474b5417d97710e15f828496",
        "starts.raw.json": "3ad6930eaf0f6add093e6fb201076ba6c5a5c948eb49af087db6ca9b897bbd3b",
    },
    "S1_NR_2026-11-04": {
        "full_program.pdf": "f562baa4102b0c6655ffe1829e65369d8b48dc75de87fada3d03a5ab0b0b0210",
        "starts.raw.json": "1e4a6abf7b3212c896b4c8c6129d9f546804c93baf3fa53e7088cf25d7765d50",
    },
    "S2_NR_2026-11-04": {
        "full_program.pdf": "897c6c636d7c70c2ed106b3d8365061378e0e3d85dc41453c7ee2b2fbe463a01",
        "starts.raw.json": "b3da4823aafaaf2386dc89be37421fae1ca2242517298aff71d54b8f9a6fb420",
    },
    "S3_NR_2026-11-04": {
        "full_program.pdf": "ddbe3bf9fe96dd04492509c184de9ae6491e9660f4f2772d2b8f07645eb74ba2",
        "starts.raw.json": "fe1cde9c8642d8f526eb95c69c524c7b24243ba6669540f9126197e5ff4ea386",
    },
    "F2_NR_2026-11-04": {
        "full_program.pdf": "28e2091b68d551ffc65aac7c03ccefc1a973c2066bcad5436a0d01a5cb740510",
        "starts.raw.json": "30f4db225d2fe04d169cb1e715f5dd4c388bdeeaf4b79ecfab869c00d3dfca04",
    },
}


def _real_root() -> Path:
    path = os.environ.get("MVP014_NOV04_COLLECTOR_ORIGINAL_ROOT")
    if not path:
        pytest.skip("Requires original 4 Nov Collector GitHub artifact")
    root = Path(path)
    manifests = list(root.rglob("manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_bytes())
    assert manifest["date_oslo"] == "2026-11-04"
    return manifests[0].parent


def _original(root: Path, meeting: str) -> tuple[bytes, dict]:
    folder = root / "meetings" / meeting
    for filename, expected in ORIGINAL_SHA256[meeting].items():
        raw = (folder / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
    starts = json.loads((folder / "starts.raw.json").read_bytes())
    assert starts["success"] is True
    return (folder / "full_program.pdf").read_bytes(), starts["result"]


def _runners(starts: dict, number: str) -> dict:
    return {
        str(row["startNumber"]): {
            "name": row["horseName"], "scratched": row["isScratched"],
        }
        for row in starts[number]
    }


@pytest.mark.parametrize(
    "meeting,number,clock,extra_numeral",
    [
        ("F1_NR_2026-11-04", "4", "2026-11-04T14:05:00+00:00", "0"),
        ("S1_NR_2026-11-04", "2", "2026-11-04T11:45:00+00:00", "62"),
        ("S1_NR_2026-11-04", "5", "2026-11-04T13:00:00+00:00", "59"),
    ],
)
def test_real_pdf_header_excludes_post_clock_first_runner_numbers(
    meeting, number, clock, extra_numeral,
):
    root = _real_root()
    raw, starts = _original(root, meeting)
    runner_field = _runners(starts, number)
    # Reproduce the old bug's triggering extraction: stray numeric values
    # in first 14 PDF text lines were formerly misread as race header labels.
    with fitz.open(stream=raw, filetype="pdf") as pdf:
        headers = [p.get_text().splitlines()[:14] for p in pdf]
    assert any(
        number in lines and any(l.strip() == extra_numeral for l in lines)
        and any(re.search(r"START\s+KL", l, re.IGNORECASE) for l in lines)
        for lines in headers
    )
    assert pdf_field(raw, int(number), runner_field, "2026-11-04") == clock


def test_real_nov04_all_35_physical_races_have_one_safely_bounded_pdf_header():
    root = _real_root()
    n = 0
    for meeting in ORIGINAL_SHA256:
        raw, starts = _original(root, meeting)
        for number in starts:
            field = _runners(starts, number)
            outcome = pdf_field(raw, int(number), field, "2026-11-04")
            assert outcome.startswith("2026-11-04T")
            n += 1
    assert n == 35


def test_real_pdf_never_accepts_wrong_runner_or_wrong_physical_race():
    root = _real_root()
    raw, starts = _original(root, "S1_NR_2026-11-04")
    field = _runners(starts, "2")
    field["1"] = {**field["1"], "name": "THIS_IS_NOT_AN_ORIGINAL_RUNNER"}
    with pytest.raises(ValueError, match="COLLECTOR_PDF_FIELD_MISMATCH"):
        pdf_field(raw, 2, field, "2026-11-04")
    with pytest.raises(ValueError, match="COLLECTOR_PDF_PHYSICAL_RACE_AMBIGUOUS"):
        pdf_field(raw, 99, field, "2026-11-04")


def test_real_jagersro_nine_tmp_identities_still_not_pit():
    root = _real_root()
    raw, starts = _original(root, "S3_NR_2026-11-04")
    field = _runners(starts, "5")
    assert len(field) == 9
    assert pdf_field(raw, 5, field, "2026-11-04") == "2026-11-04T19:30:00+00:00"
    assert all(
        row["horseRegistrationNumber"].startswith("TMP-")
        for row in starts["5"]
    )
    assert all(not row["isScratched"] for row in starts["5"])
