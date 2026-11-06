"""TEST_ONLY adversarial source-admission/replay tests. Real 2022 replay runs in CI."""
import hashlib
import json

import pytest

from hbi.mvp023b_archive_admission import admit_month
from test_mvp023a_historical_coverage import fixture

from scripts.mvp023b_real_month_m5_replay import replay

MONTH = "2020-01"


def _admitted(tmp_path):
    source = tmp_path / "genuine-shaped-fixture"
    fixture(source)
    admission = admit_month(source, MONTH)
    receipt = tmp_path / "month-admission.json"
    receipt.write_text(json.dumps(admission), encoding="utf-8")
    return source, receipt


def test_replay_refuses_2025_without_opening_source(tmp_path):
    source, receipt = _admitted(tmp_path)
    lockbox = source / "result-days/2025-06-01.json"
    lockbox.write_bytes(b"SECRET_INVALID_JSON_DO_NOT_OPEN")
    with pytest.raises(ValueError, match="2025_LOCKBOX"):
        replay(source, receipt, "2025-06", tmp_path / "forbidden")
    assert lockbox.read_bytes() == b"SECRET_INVALID_JSON_DO_NOT_OPEN"
    assert not (tmp_path / "forbidden").exists()


def test_replay_detects_original_member_byte_mutation(tmp_path):
    source, receipt = _admitted(tmp_path)
    manifest = json.loads(receipt.read_text())
    target_name = manifest["read_only_native_files_sha256"][0]["path"]
    target = source / target_name
    target.write_bytes(target.read_bytes() + b"extra")
    with pytest.raises(ValueError, match="HISTORICAL_ORIGINAL_BYTES_SHA_CONFLICT"):
        replay(source, receipt, MONTH, tmp_path / "out")


def test_replay_detects_manifest_hash_or_denominator_forgery(tmp_path):
    source, receipt = _admitted(tmp_path)
    doc = json.loads(receipt.read_text())
    doc["source_manifest_sha256"] = "f" * 64
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="RECEIPT_MANIFEST_SHA"):
        replay(source, receipt, MONTH, tmp_path / "bad-sha")
    doc["source_manifest_sha256"] = admit_month(source, MONTH)["source_manifest_sha256"]
    doc["source_file_count"] += 1
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="SOURCE_DENOMINATOR_CONFLICT"):
        replay(source, receipt, MONTH, tmp_path / "bad-count")


def test_replay_rejects_symlinks_traversal_or_duplicate_paths(tmp_path):
    source, receipt = _admitted(tmp_path)
    doc = json.loads(receipt.read_text())
    first = doc["read_only_native_files_sha256"][0]
    doc["read_only_native_files_sha256"].append(first)
    from rikstoto_crawler.transport import digest

    doc["source_file_count"] += 1
    doc["source_manifest_sha256"] = digest(doc["read_only_native_files_sha256"])
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="UNSAFE_OR_DUPLICATE_ORIGINAL"):
        replay(source, receipt, MONTH, tmp_path / "dup")
    doc = admit_month(source, MONTH)
    name = doc["read_only_native_files_sha256"][0]["path"]
    existing = source / name
    existing.unlink()
    existing.symlink_to(source / "market-days/2020-01-04.json")
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="SYMLINKED_ORIGINAL"):
        replay(source, receipt, MONTH, tmp_path / "symlink")


def test_replay_rejects_2026_or_unauthenticated_admission(tmp_path):
    source, receipt = _admitted(tmp_path)
    with pytest.raises(ValueError, match="NONHISTORIC_MONTH"):
        replay(source, receipt, "2026-10", tmp_path / "no-2026")
    doc = json.loads(receipt.read_text())
    doc["bet_authority"] = True
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="HISTORICAL_MONTH_SOURCE_ADMISSION_REQUIRED"):
        replay(source, receipt, MONTH, tmp_path / "no-bets")
