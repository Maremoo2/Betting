"""Byte-exact DATA-004 original archive replay using disposable mock ZIPs.

These fixtures are deliberately synthetic; they are NOT original gold labels.
The Actions E2E must separately inspect the seven real original archives.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from hbi.data004_archive_replay import audit_archives

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs(tmp_path):
    manifest = copy.deepcopy(json.loads(
        (ROOT / "research/data004-holdout-prereg-v1.json").read_text(encoding="utf-8")
    ))
    evidence = copy.deepcopy(json.loads(
        (ROOT / "research/data004-holdout-source-pdf-evidence-v1.json").read_text(
            encoding="utf-8")
    ))
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.write(buf)
    original = buf.getvalue()
    original_sha = hashlib.sha256(original).hexdigest()
    by_meeting = {x["meeting"]: x["expected_pdf_path"] for x in manifest["selected"]}
    archives = {}
    for program in evidence["programs"]:
        program["pdf_sha256"] = original_sha
        program["pages"] = 1
    for artifact_id in sorted({p["artifact_id"] for p in evidence["programs"]}):
        archive = tmp_path / f"{artifact_id}.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for program in evidence["programs"]:
                if program["artifact_id"] == artifact_id:
                    z.writestr(by_meeting[program["meeting"]], original)
        archives[artifact_id] = archive
    return manifest, evidence, archives, tmp_path, by_meeting


def test_exact_synthetic_archive_replay_reports_zero_gold(inputs):
    manifest, evidence, archives, temp, _ = inputs
    csv_path = temp / "blank-review.csv"
    report = audit_archives(manifest, evidence, archives, blank_ledger_output=csv_path)
    assert report["status"] == "ORIGINAL_24_PDFS_BYTE_VERIFIED_GOLD_PENDING"
    assert report["archive_count"] == 7
    assert report["verified_original_pdf_programs"] == 24
    assert report["locked_sample_rows"] == 30
    assert report["original_holdout_cells"] == 390
    assert len(report["archive_zip_sha256_by_artifact_id"]) == 7
    assert len(report["verified_original_pdfs"]) == 24
    assert all(len(p["original_pdf_sha256"]) == 64 for p in report["verified_original_pdfs"])
    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 390
    assert {r["gold_status"] for r in rows} == {"PENDING_VISUAL_REVIEW"}
    assert all(not r["gold_value"] for r in rows)
    assert not report["source_row_identity_independently_accepted"]
    assert not report["gold_fields_independently_verified"]
    assert not report["holdout_validated"]
    assert not report["pit_certified"]
    assert not report["model_training_or_bet_authority"]
    with pytest.raises(FileExistsError):
        audit_archives(manifest, evidence, archives, blank_ledger_output=csv_path)


@pytest.mark.parametrize("fault", [
    "archive_missing",
    "archive_extra",
    "missing_pdf",
    "wrong_bytes",
    "wrong_page_count",
    "duplicate_zip_member",
    "path_outside_root",
    "inconsistent_meeting_path",
    "wrong_source_evidence_sha",
])
def test_incomplete_or_tampered_original_archive_never_passes(inputs, fault):
    manifest, evidence, archives, temp, paths = inputs
    first = evidence["programs"][0]
    artifact_id = first["artifact_id"]
    original = archives[artifact_id]
    if fault == "archive_missing":
        archives.pop(artifact_id)
    elif fault == "archive_extra":
        archives[999999] = original
    elif fault in {"missing_pdf", "wrong_bytes", "duplicate_zip_member"}:
        replacement = temp / "mutated.zip"
        with zipfile.ZipFile(original) as z, zipfile.ZipFile(replacement, "w") as out:
            for name in z.namelist():
                if fault == "missing_pdf" and name == paths[first["meeting"]]:
                    continue
                value = z.read(name)
                if fault == "wrong_bytes" and name == paths[first["meeting"]]:
                    value += b"modified-after-capture"
                out.writestr(name, value)
            if fault == "duplicate_zip_member":
                # Two same-named entries are ambiguous, never pick one.
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    out.writestr(paths[first["meeting"]], b"different fake PDF")
        archives[artifact_id] = replacement
    elif fault == "wrong_page_count":
        first["pages"] += 1
    elif fault == "path_outside_root":
        for row in manifest["selected"]:
            if row["meeting"] == first["meeting"]:
                row["expected_pdf_path"] = "../fake/full_program.pdf"
    elif fault == "inconsistent_meeting_path":
        # Select an actually duplicated locked meeting, not whichever
        # first program appears in the archive evidence index.
        counts = {m: sum(r["meeting"] == m for r in manifest["selected"])
                  for m in paths}
        meeting = next(m for m, count in counts.items() if count > 1)
        rows = [r for r in manifest["selected"] if r["meeting"] == meeting]
        assert len(rows) > 1
        rows[1]["expected_pdf_path"] = "different/full_program.pdf"
    elif fault == "wrong_source_evidence_sha":
        first["pdf_sha256"] = "0" * 64
    with pytest.raises((ValueError, FileNotFoundError)):
        audit_archives(manifest, evidence, archives)


def test_zip_with_unrelated_non_source_files_cannot_satisfy_missing_original(inputs):
    manifest, evidence, archives, temp, paths = inputs
    first = evidence["programs"][0]
    artifact_id = first["artifact_id"]
    changed = temp / "extra.zip"
    with zipfile.ZipFile(archives[artifact_id]) as source, zipfile.ZipFile(changed, "w") as out:
        for name in source.namelist():
            if name != paths[first["meeting"]]:
                out.writestr(name, source.read(name))
        out.writestr("unrelated/updated_full_program.pdf", b"%PDF-unrelated")
    archives[artifact_id] = changed
    with pytest.raises(ValueError, match="Original PDF absent"):
        audit_archives(manifest, evidence, archives)


def test_unreviewed_navigation_output_cannot_run_without_source_locator_index(inputs):
    manifest, evidence, archives, root, _ = inputs
    destination = root / "forbidden-review-hints.json"
    with pytest.raises(ValueError, match="needs frozen original locator"):
        audit_archives(
            manifest, evidence, archives, review_hints_output=destination,
        )
    assert not destination.exists()


def test_unverified_or_changed_locator_index_does_not_generate_gold_hints(inputs):
    manifest, evidence, archives, root, _ = inputs
    target = root / "no-fabricated-gold.csv"
    with pytest.raises(ValueError):
        audit_archives(
            manifest, evidence, archives,
            source_locators={"schema_version": "FAKE_MAPPED_GOLD",
                             "rows": [], "holdout_verified": True},
            navigation_csv_output=target,
        )
    assert not target.exists()
