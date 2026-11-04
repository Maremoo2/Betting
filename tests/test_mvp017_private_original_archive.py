"""MVP-017 private local original bytes: append-only, provenance, tamper, fail-closed."""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from hbi.mvp017_private_original_archive import store_original, verify_archive

EXPECTED_ORIGINAL_SHA = "ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0"


def _put(tmp_path: Path, *, data: bytes = b'{"source":"public"}\n', **overrides):
    src = tmp_path / "original.json"
    src.write_bytes(data)
    args = {
        "archive_root": tmp_path / "private",
        "source_file": src,
        "source_provider": "RIKSTOTO",
        "endpoint": "/api/racedays",
        "observed_at_utc": "2026-11-04T07:59:00+00:00",
        "source_run_id": 41796128435,
        "source_artifact_id": 13304793845,
        "approval_id": "MVP017_LOCAL_REPLAY_APPROVED",
        "physical_race_id": "RIKSTOTO:S1_NR_2026-11-03:8",
    }
    return store_original(**(args | overrides))


def test_append_only_roundtrip_and_distinct_origin_receipts(tmp_path):
    first = _put(tmp_path)
    root = tmp_path / "private"
    assert len(first["original_sha256"]) == 64
    assert first["bet_authority"] is False
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert verify_archive(root)["original_source_blobs"] == 1
    with pytest.raises(FileExistsError):
        _put(tmp_path)
    second = _put(tmp_path, source_artifact_id=13304793846)
    assert first["original_sha256"] == second["original_sha256"]
    assert first["receipt_sha256"] != second["receipt_sha256"]
    out = verify_archive(root)
    assert out["original_source_blobs"] == 1
    assert out["distinct_provenance_receipts"] == 2
    assert out["permanent_external_retention_configured"] is False
    assert out["pit_certified"] is False and out["bet_authority"] is False


def test_tampered_original_detected_without_any_repair(tmp_path):
    first = _put(tmp_path)
    root = tmp_path / "private"
    blob = root / "sha256" / first["original_sha256"][:2] / first["original_sha256"]
    blob.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ARCHIVE_ORIGINAL_BYTES_MISSING_OR_CHANGED"):
        verify_archive(root)
    with pytest.raises(ValueError, match="ARCHIVE_EXISTING_BLOB_CORRUPT"):
        _put(tmp_path)
    assert blob.read_bytes() == b"tampered"


def test_tampered_receipt_detected(tmp_path):
    _put(tmp_path)
    root = tmp_path / "private"
    receipt = next((root / "receipts").glob("*.json"))
    receipt.write_bytes(receipt.read_bytes() + b" ")
    with pytest.raises(ValueError, match="ARCHIVE_RECEIPT_SHA_MISMATCH"):
        verify_archive(root)


@pytest.mark.parametrize(("field", "bad_value", "reason"), [
    ("endpoint", "/api/racedays?token=abc", "ARCHIVE_ENDPOINT_WITH_POTENTIAL_SECRET"),
    ("endpoint", "https://example.org/private", "ARCHIVE_ENDPOINT_WITH_POTENTIAL_SECRET"),
    ("approval_id", "with spaces", "ARCHIVE_PROVIDER_OR_APPROVAL_INVALID"),
    ("observed_at_utc", "2026-11-04T10:59:00", "OBSERVATION_CLOCK_NAIVE"),
    ("source_run_id", 0, "ARCHIVE_RUN_ID_INVALID"),
    ("source_artifact_id", None, "ARCHIVE_ARTIFACT_ID_INVALID"),
    ("model_sha256", "0" * 63, "ARCHIVE_MODEL_SHA_INVALID"),
    ("original_decision", "PIT_CERTIFIED", "ARCHIVE_MUST_NOT_CLAIM_ADMISSION_OR_PIT"),
])
def test_unapproved_provenance_and_betting_gate_fail_closed(tmp_path, field, bad_value, reason):
    with pytest.raises(ValueError, match=reason):
        _put(tmp_path, **{field: bad_value})
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("raw", [
    b'{"access_token":"some-secret-value"}',
    b"Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    b'{"client_secret":"no-archive"}',
])
def test_sensitive_original_rejected_before_any_write(tmp_path, raw):
    with pytest.raises(ValueError, match="ARCHIVE_POSSIBLE_SENSITIVE_ORIGINAL"):
        _put(tmp_path, data=raw)
    assert not (tmp_path / "private").exists()


def test_source_symlink_and_archive_symlink_rejected(tmp_path):
    target = tmp_path / "real"
    target.write_bytes(b"public")
    source_link = tmp_path / "sym"
    source_link.symlink_to(target)
    with pytest.raises(ValueError, match="ARCHIVE_SOURCE_NOT_REGULAR"):
        _put(tmp_path, source_file=source_link)
    link_root = tmp_path / "private"
    link_root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="ARCHIVE_SYMLINK_FORBIDDEN"):
        _put(tmp_path)


def test_authentic_git_original_replayed_byte_exactly(tmp_path):
    env = os.environ.get("MVP017_PRIVATE_ARCHIVE_ORIGINAL_ROOT")
    if not env:
        pytest.skip("Authentic GitHub original supplied only in PR CI")
    original = Path(env) / "cohort-index.json"
    raw = original.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_ORIGINAL_SHA
    result = _put(tmp_path, source_file=original)
    assert result["original_sha256"] == EXPECTED_ORIGINAL_SHA
    assert verify_archive(tmp_path / "private")["distinct_provenance_receipts"] == 1
