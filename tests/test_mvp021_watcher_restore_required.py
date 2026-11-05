"""Canonical watcher must never continue after missing/unverified previous state.

Source contract: scheduled watcher requires authenticated GitHub artifact; other
explicit bootstrap callers can still opt out. No canonical state or bets touched.
"""
from __future__ import annotations

import io
import json
import urllib.error
import zipfile

import pytest

from hbi import state_artifact


def _env(monkeypatch, tmp_path, *, required=True):
    monkeypatch.setenv("GITHUB_REPOSITORY", "Maremoo2/Betting")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("HBI_DB_PATH", str(tmp_path / "hbi.sqlite"))
    monkeypatch.delenv("HBI_RESTORE_RECEIPT_PATH", raising=False)
    if required:
        monkeypatch.setenv("HBI_RESTORE_REQUIRED", "1")
    else:
        monkeypatch.delenv("HBI_RESTORE_REQUIRED", raising=False)


def _inventory(monkeypatch, artifacts):
    def fake_urlopen(request, timeout):
        assert request.full_url.endswith("/actions/artifacts?name=hbi-state&per_page=100")
        return io.BytesIO(json.dumps({"artifacts": artifacts}).encode())

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", fake_urlopen)


@pytest.mark.parametrize("artifacts", [
    [],
    [{"id": 1, "expired": True, "created_at": "2026-11-05T10:00:00Z",
      "workflow_run": {"head_branch": "main"}}],
    [{"id": 2, "expired": False, "created_at": "2026-11-05T10:00:00Z",
      "workflow_run": {"head_branch": "different-branch"}}],
])
def test_required_watcher_refuses_missing_expired_or_wrong_branch_state(
    monkeypatch, tmp_path, artifacts, capsys,
):
    _env(monkeypatch, tmp_path)
    _inventory(monkeypatch, artifacts)
    with pytest.raises(SystemExit, match="STATE_RESTORE_REQUIRED_BUT_NO_VERIFIED_ARTIFACT"):
        state_artifact.main()
    assert not (tmp_path / "hbi.sqlite").exists()
    assert "STATE_RESTORE=EMPTY" not in capsys.readouterr().out


def test_required_watcher_http_403_fails_before_analyzing_or_creating_state(
    monkeypatch, tmp_path,
):
    _env(monkeypatch, tmp_path)

    def forbidden(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", {}, io.BytesIO(b""),
        )

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", forbidden)
    with pytest.raises(urllib.error.HTTPError) as raised:
        state_artifact.main()
    assert raised.value.code == 403
    assert not (tmp_path / "hbi.sqlite").exists()


def test_required_watcher_restores_prior_original_and_can_continue(
    monkeypatch, tmp_path, capsys,
):
    _env(monkeypatch, tmp_path)
    original_db = b"SQLite format 3\\x00prior-authenticated-state"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("data/hbi.sqlite", original_db)
    payload = buffer.getvalue()
    artifact = {
        "id": 43, "expired": False, "created_at": "2026-11-05T10:00:00Z",
        "archive_download_url": "https://api.github.com/repos/x/y/actions/artifacts/43/zip",
        "workflow_run": {"head_branch": "main"},
    }
    _inventory(monkeypatch, [artifact])

    class _FakeOpener:
        def open(self, request, timeout):
            assert request.full_url == artifact["archive_download_url"]
            return io.BytesIO(payload)

    monkeypatch.setattr(
        state_artifact.urllib.request, "build_opener",
        lambda *handlers: _FakeOpener(),
    )
    state_artifact.main()
    assert (tmp_path / "hbi.sqlite").read_bytes() == original_db
    assert "STATE_RESTORE=RESTORED" in capsys.readouterr().out


def test_explicit_noncanonical_bootstrap_remains_opt_in(monkeypatch, tmp_path, capsys):
    _env(monkeypatch, tmp_path, required=False)
    _inventory(monkeypatch, [])
    state_artifact.main()
    assert "STATE_RESTORE=EMPTY" in capsys.readouterr().out
    assert not (tmp_path / "hbi.sqlite").exists()
