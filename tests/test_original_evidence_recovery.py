"""Synthetic security unit tests; never substitutes for the original ZIP."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from hbi.original_evidence_recovery import (
    PILOT_MEMBER,
    _read_exact_member,
    read_pilot,
    validate_pilot_manifest,
)

MANIFEST = Path(__file__).resolve().parents[1] / "docs/original_evidence_manifest.json"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _zip(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in members:
            archive.writestr(name, content)
    return stream.getvalue()


def _verify(raw, content=b"synthetic test"):
    return _read_exact_member(raw, zip_sha=_sha(raw),
                              member_sha=_sha(content), member_name=PILOT_MEMBER)


def test_manifest_pins_and_missing_original(tmp_path):
    manifest = _manifest()
    validate_pilot_manifest(manifest)
    with pytest.raises(ValueError, match="ORIGINAL_EVIDENCE_UNAVAILABLE"):
        read_pilot(manifest, tmp_path / "absent.zip")


@pytest.mark.parametrize("key,value", [
    ("artifact_id", 7), ("run_id", 7), ("repository", "other/repo"),
    ("artifact_name", "other"), ("zip_sha256", "a" * 64),
    ("member_sha256", "b" * 64), ("member_name", "../cohort-index.json"),
    ("zip_size_bytes", 576),
])
def test_manifest_substitution(key, value):
    manifest = _manifest()
    manifest["entries"][0][key] = value
    with pytest.raises(ValueError, match="EVIDENCE_(IDENTITY|PIN)_MISMATCH"):
        validate_pilot_manifest(manifest)


def test_exact_read_primitive_and_tampered_zip():
    raw = _zip([(PILOT_MEMBER, b"synthetic test")])
    assert _verify(raw) == b"synthetic test"
    with pytest.raises(ValueError, match="ZIP_HASH_MISMATCH"):
        _read_exact_member(raw + b"x", zip_sha=_sha(raw),
                           member_sha=_sha(b"synthetic test"), member_name=PILOT_MEMBER)


def test_changed_internal_file_even_with_matching_zip_hash():
    with pytest.raises(ValueError, match="MEMBER_HASH_MISMATCH"):
        _verify(_zip([(PILOT_MEMBER, b"changed")]))


@pytest.mark.parametrize("name", ["../cohort-index.json", "/cohort-index.json",
                                 "sub/cohort-index.json", "other.json"])
def test_unexpected_path(name):
    with pytest.raises(ValueError, match="ZIP_MEMBER_INVALID"):
        _verify(_zip([(name, b"synthetic test")]))


def test_multiple_members():
    raw = _zip([(PILOT_MEMBER, b"synthetic test"), ("other", b"x")])
    with pytest.raises(ValueError, match="ZIP_MEMBER_COUNT"):
        _verify(raw)


def test_symlink_member():
    info = zipfile.ZipInfo(PILOT_MEMBER)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="ZIP_MEMBER_INVALID"):
        _verify(_zip([(info, b"synthetic test")]))


def test_wrong_size_never_admitted(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not original")
    with pytest.raises(ValueError, match="ZIP_SIZE_MISMATCH"):
        read_pilot(_manifest(), path)
