"""V1 audit must pin original watcher artifact and restored SQLite SHA (no bets)."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from hbi.state_artifact import restore_latest_state


def _archive(body: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("data/hbi.sqlite", body)
    return stream.getvalue()


def _responses(monkeypatch, artifacts: list[dict], archive: bytes):
    from hbi import state_artifact

    def fake_urlopen(request, timeout):
        url = request.full_url
        if "/actions/artifacts?" in url:
            return io.BytesIO(json.dumps({"artifacts": artifacts}).encode())
        if url.endswith("/zip"):
            return io.BytesIO(archive)
        raise AssertionError(f"Unexpected network read: {url}")

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", fake_urlopen)


def test_exact_restore_receipt_pins_actual_selected_original(monkeypatch, tmp_path):
    raw = b"immutable-sqlite-original-bytes"
    archive = _archive(raw)
    oldest = {
        "id": 41, "created_at": "2026-11-04T18:00:00Z",
        "expired": False,
        "archive_download_url": "https://api.github.com/repos/x/y/actions/artifacts/41/zip",
        "workflow_run": {"id": 1, "head_branch": "main", "head_sha": "a" * 40},
    }
    newest = {
        "id": 42, "created_at": "2026-11-04T18:48:08Z",
        "expired": False,
        "archive_download_url": "https://api.github.com/repos/x/y/actions/artifacts/42/zip",
        "workflow_run": {"id": 2, "head_branch": "main", "head_sha": "b" * 40},
    }
    _responses(monkeypatch, [oldest, newest], archive)
    database = tmp_path / "data" / "hbi.sqlite"
    receipt_path = tmp_path / "metadata" / "restore.json"
    assert restore_latest_state(
        repository="x/y", token="dummy", target_path=database,
        branch="main", receipt_path=receipt_path,
    )
    actual = json.loads(receipt_path.read_text())
    assert database.read_bytes() == raw
    assert actual["artifact_id"] == 42
    assert actual["source_workflow_run_id"] == 2
    assert actual["source_head_branch"] == "main"
    assert actual["source_head_sha"] == "b" * 40
    assert actual["artifact_zip_sha256"] == hashlib.sha256(archive).hexdigest()
    assert actual["restored_database_sha256"] == hashlib.sha256(raw).hexdigest()
    assert actual["restored_database_size_bytes"] == len(raw)
    assert actual["historical_decisions_modified"] is False
    assert actual["bet_authority"] is False


def test_unsafe_missing_artifact_metadata_refuses_receipt(monkeypatch, tmp_path):
    archive = _archive(b"sqlite")
    artifact = {
        "id": 11, "created_at": "2026-11-04T18:00:00Z", "expired": False,
        "archive_download_url": "https://api.github.com/repos/x/y/actions/artifacts/11/zip",
        "workflow_run": {"head_branch": "main", "head_sha": "a" * 40},
    }
    _responses(monkeypatch, [artifact], archive)
    db = tmp_path / "hbi.sqlite"
    receipt = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="NOT_ATTESTED"):
        restore_latest_state(
            repository="x/y", token="dummy", target_path=db,
            branch="main", receipt_path=receipt,
        )
    assert not db.exists()
    assert not receipt.exists()


def test_wrong_branch_or_empty_inventory_has_no_receipt(monkeypatch, tmp_path):
    artifact = {
        "id": 11, "created_at": "2026-11-04T18:00:00Z", "expired": False,
        "archive_download_url": "https://api.github.com/repos/x/y/actions/artifacts/11/zip",
        "workflow_run": {"id": 2, "head_branch": "dev", "head_sha": "b" * 40},
    }
    _responses(monkeypatch, [artifact], _archive(b"x"))
    receipt = tmp_path / "receipt.json"
    assert restore_latest_state(
        repository="x/y", token="dummy", target_path=tmp_path / "hbi.sqlite",
        branch="main", receipt_path=receipt,
    ) is False
    assert not receipt.exists()


def test_no_receipt_option_keeps_legacy_restore_contract(monkeypatch, tmp_path):
    archive = _archive(b"original-sqlite")
    artifact = {
        "id": 11, "created_at": "2026-11-04T18:00:00Z", "expired": False,
        "archive_download_url": "https://api.github.com/repos/x/y/actions/artifacts/11/zip",
        "workflow_run": {},
    }
    _responses(monkeypatch, [artifact], archive)
    db = tmp_path / "hbi.sqlite"
    assert restore_latest_state(
        repository="x/y", token="dummy", target_path=db, receipt_path=None
    )
    assert db.read_bytes() == b"original-sqlite"
