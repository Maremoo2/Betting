"""Source byte audit uses disposable synthetic PDFs, not holdout gold labels."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from hbi.data004_original_pdf_audit import (
    verify_original_pdfs,
    write_blank_gold_ledger,
)

ROOT = Path(__file__).parents[1]


@pytest.fixture()
def source_fixture(tmp_path):
    manifest = json.loads(
        (ROOT / "research/data004-holdout-prereg-v1.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (
            ROOT / "research/data004-holdout-source-pdf-evidence-v1.json"
        ).read_text(encoding="utf-8")
    )
    manifest, evidence = copy.deepcopy(manifest), copy.deepcopy(evidence)
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    buffer = io.BytesIO()
    writer.write(buffer)
    fake_bytes = buffer.getvalue()
    fake_sha = hashlib.sha256(fake_bytes).hexdigest()

    by_meeting = {row["meeting"]: row["expected_pdf_path"] for row in manifest["selected"]}
    for program in evidence["programs"]:
        program["pdf_sha256"] = fake_sha
        program["pages"] = 1
        path = tmp_path / by_meeting[program["meeting"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fake_bytes)
    return manifest, evidence, tmp_path, by_meeting


def test_synthetic_bytes_verify_but_never_approve_holdout(source_fixture, tmp_path):
    manifest, evidence, root, _ = source_fixture
    result = verify_original_pdfs(manifest, evidence, root)
    assert result["verified_pdf_programs"] == 24
    assert result["locked_sample_rows"] == 30
    assert result["field_assessments_required"] == 390
    assert result["holdout_verified"] is False
    assert result["independent_field_gold_verified"] is False
    target = tmp_path / "review-only.csv"
    write_blank_gold_ledger(manifest, result, target)
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 390
    assert len({(x["sample_id"], x["field"]) for x in rows}) == 390
    assert {row["gold_status"] for row in rows} == {"PENDING_VISUAL_REVIEW"}
    assert all(row["gold_value"] == "" and row["visual_row_locator"] == "" for row in rows)
    with pytest.raises(FileExistsError):
        write_blank_gold_ledger(manifest, result, target)


@pytest.mark.parametrize("fault", [
    "missing_pdf", "wrong_bytes", "wrong_pages", "conflicting_path", "path_escape",
])
def test_rejects_unverified_or_inconsistent_original_sources(source_fixture, fault):
    manifest, evidence, root, paths = source_fixture
    first_meeting = evidence["programs"][0]["meeting"]
    path = root / paths[first_meeting]
    if fault == "missing_pdf":
        path.unlink()
    elif fault == "wrong_bytes":
        path.write_bytes(b"not the original PDF")
    elif fault == "wrong_pages":
        evidence["programs"][0]["pages"] += 1
    elif fault == "conflicting_path":
        matching = [r for r in manifest["selected"] if r["meeting"] == first_meeting]
        if len(matching) < 2:
            matching = [r for r in manifest["selected"] if r["meeting"] ==
                        next(k for k, v in paths.items() if sum(
                            x["meeting"] == k for x in manifest["selected"]
                        ) > 1)]
        matching[-1]["expected_pdf_path"] = (
            matching[-1]["expected_pdf_path"].replace("full_program.pdf", "other.pdf")
        )
    elif fault == "path_escape":
        manifest["selected"][0]["expected_pdf_path"] = "../full_program.pdf"
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_original_pdfs(manifest, evidence, root)
