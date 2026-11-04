"""V1 audit must pin original watcher artifact and restored SQLite SHA (no bets)."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime

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

    class _FakeOpener:
        def open(self, request, timeout):
            assert request.full_url.endswith("/zip")
            return io.BytesIO(archive)

    monkeypatch.setattr(
        state_artifact.urllib.request, "build_opener",
        lambda *handlers: _FakeOpener(),
    )


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
        audit_workflow_run_id=41899900123, audit_code_sha="c" * 40,
    )
    actual = json.loads(receipt_path.read_text())
    assert database.read_bytes() == raw
    assert actual["artifact_id"] == 42
    assert actual["source_workflow_run_id"] == 2
    assert actual["audit_workflow_run_id"] == 41899900123
    assert actual["audit_code_sha"] == "c" * 40
    restored = datetime.fromisoformat(actual["restored_at_utc"])
    assert restored.tzinfo is not None
    assert abs((datetime.now(UTC) - restored).total_seconds()) < 60
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
            audit_workflow_run_id=41899900123, audit_code_sha="c" * 40,
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
        audit_workflow_run_id=41899900123, audit_code_sha="c" * 40,
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


@pytest.mark.parametrize("bad_run,bad_sha", [
    (None, "a" * 40), (0, "a" * 40), (-1, "a" * 40),
    (True, "a" * 40), (1, None), (1, "f" * 39), (1, "not-a-sha"),
])
def test_missing_audit_identity_rejects_receipt_before_network(
    monkeypatch, tmp_path, bad_run, bad_sha,
):
    from hbi import state_artifact

    def no_network(*args, **kwargs):
        raise AssertionError("must fail before any source request")

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", no_network)
    target = tmp_path / "hbi.sqlite"
    receipt = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="AUDIT_RUN_AND_CODE_SHA"):
        restore_latest_state(
            repository="x/y", token="dummy", target_path=target,
            branch="main", receipt_path=receipt,
            audit_workflow_run_id=bad_run, audit_code_sha=bad_sha,
        )
    assert not target.exists()
    assert not receipt.exists()
