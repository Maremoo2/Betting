"""Fail-closed cloud source handoff: synthetic fixtures are not live acceptance."""
import hashlib
import json
import zipfile

import pytest

from hbi.cloud_run001_archive import audit_release

DAY = "2026-11-12"
RUN = "20261112T062004681934Z"


def fixture(tmp_path, *, manifest=None, entries=None):
    archive = tmp_path / f"rikstoto-{DAY}-{RUN}.zip"
    sidecar = tmp_path / (archive.name + ".sha256")
    doc = manifest if manifest is not None else {
        "date_oslo": DAY, "run_id": RUN, "status": "CAPTURED_UNVERIFIED",
        "meetings": [{"meeting_id": "S1_NR_2026-11-12"}],
    }
    members = entries if entries is not None else {
        f"{DAY}/{RUN}/manifest.json": json.dumps(doc).encode(),
        f"{DAY}/{RUN}/meetings/S1_NR_2026-11-12/full_program.pdf": b"%PDF-1.4 fixture",
    }
    with zipfile.ZipFile(archive, "w") as zf:
        for key, body in members.items():
            zf.writestr(key, body)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, sidecar


def test_source_zip_readback_remains_research_only(tmp_path):
    report = audit_release(*fixture(tmp_path))
    assert report["status"] == "SOURCE_BYTES_VERIFIED_RESEARCH_ONLY"
    assert report["original_program_pdf_files"] == 1
    assert report["collector_status"] == "CAPTURED_UNVERIFIED"
    assert report["source_bytes_readback_verified"] is True
    for gate in ("live_win_verified", "independent_t4_attested",
                 "permanent_horse_identity_attested", "primary_pit_qualified",
                 "bet_authorized", "complete_race_coverage_verified"):
        assert report[gate] is False


def test_archive_bytes_tamper_fail_closed(tmp_path):
    archive, sidecar = fixture(tmp_path)
    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        audit_release(archive, sidecar)


def test_wrong_sidecar_rejected(tmp_path):
    archive, sidecar = fixture(tmp_path)
    sidecar.write_text("0" * 64 + "  different.zip\n")
    with pytest.raises(ValueError, match="CHECKSUM_FORMAT_INVALID"):
        audit_release(archive, sidecar)


def test_mismatched_manifest_identity_rejected(tmp_path):
    archive, sidecar = fixture(tmp_path, manifest={
        "date_oslo": "2026-11-11", "run_id": RUN,
        "status": "CAPTURED_UNVERIFIED", "meetings": [],
    })
    with pytest.raises(ValueError, match="MANIFEST_IDENTITY_MISMATCH"):
        audit_release(archive, sidecar)


def test_path_traversal_rejected(tmp_path):
    archive, sidecar = fixture(tmp_path, entries={
        f"{DAY}/{RUN}/manifest.json": json.dumps({
            "date_oslo": DAY, "run_id": RUN, "meetings": [], "status": "CAPTURED_UNVERIFIED",
        }).encode(),
        f"{DAY}/{RUN}/../escape.pdf": b"unsafe",
    })
    with pytest.raises(ValueError, match="UNSAFE_MEMBER"):
        audit_release(archive, sidecar)


def test_no_program_pdf_never_claims_verified_coverage(tmp_path):
    archive, sidecar = fixture(tmp_path, entries={
        f"{DAY}/{RUN}/manifest.json": json.dumps({
            "date_oslo": DAY, "run_id": RUN,
            "status": "CAPTURED_UNVERIFIED", "meetings": [],
        }).encode(),
    })
    result = audit_release(archive, sidecar)
    assert result["original_program_pdf_files"] == 0
    assert result["complete_race_coverage_verified"] is False
    assert result["bet_authorized"] is False


def test_missing_source_fails_closed(tmp_path):
    archive, sidecar = fixture(tmp_path)
    archive.unlink()
    with pytest.raises(ValueError, match="FILE_UNSAFE_OR_MISSING"):
        audit_release(archive, sidecar)
