"""P0 restore HTTP 403 evidence: no bootstrap, no trust-gate relaxation."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from hbi import state_artifact


def _denied(url, *, message, stage=403, headers=None):
    raw = json.dumps({"message": message}).encode()
    return urllib.error.HTTPError(
        url, stage, "Forbidden", headers or {}, io.BytesIO(raw),
    )


def _artifact():
    return {
        "id": 80, "created_at": "2026-11-06T13:10:00Z",
        "expired": False, "archive_download_url":
            "https://api.github.com/repos/Maremoo2/Betting/actions/artifacts/80/zip",
        "workflow_run": {"id": 42, "head_branch": "main", "head_sha": "a" * 40},
    }


def _restore(tmp_path):
    return state_artifact.restore_latest_state(
        repository="Maremoo2/Betting", token="dummy-private-token",
        target_path=tmp_path / "hbi.sqlite", branch="main",
    )


def test_inventory_403_installation_limit_fails_closed_and_classifies(monkeypatch, tmp_path, capsys):
    def fake_open(request, timeout):
        raise _denied(
            request.full_url, message="API rate limit exceeded for installation",
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1793980000"},
        )

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", fake_open)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _restore(tmp_path)
    assert exc.value.code == 403
    assert not (tmp_path / "hbi.sqlite").exists()
    lines = capsys.readouterr().err
    assert "EXTERNAL_ACCESS_FAILURE stage=ARTIFACT_INVENTORY" in lines
    assert "classification=INSTALLATION_RATE_LIMIT" in lines
    assert "rate_remaining=0" in lines
    assert "no_bootstrap=true" in lines
    assert "dummy-private-token" not in lines


def test_inventory_403_no_rate_message_not_misclassified(monkeypatch, tmp_path, capsys):
    def fake_open(request, timeout):
        raise _denied(request.full_url, message="Resource not accessible by integration")

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", fake_open)
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path)
    lines = capsys.readouterr().err
    assert "classification=HTTP_ACCESS_OR_SCOPE_UNVERIFIED" in lines
    assert "INSTALLATION_RATE_LIMIT" not in lines
    assert not (tmp_path / "hbi.sqlite").exists()


def test_zip_download_403_reports_zip_stage_and_preserves_state(monkeypatch, tmp_path, capsys):
    artifact = _artifact()
    def inventory(request, timeout):
        return io.BytesIO(json.dumps({"artifacts": [artifact]}).encode())
    class NoZip:
        def open(self, request, timeout):
            raise _denied(request.full_url, message="API rate limit exceeded for installation")

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", inventory)
    monkeypatch.setattr(state_artifact.urllib.request, "build_opener",
                        lambda *handlers: NoZip())
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path)
    assert "stage=ARTIFACT_ZIP" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()


def test_signed_storage_403_not_mislabeled_inventory(monkeypatch, tmp_path, capsys):
    artifact = _artifact()
    def inventory_or_storage(request, timeout):
        if "storage.example" in request.full_url:
            raise _denied(request.full_url, message="AccessDenied")
        return io.BytesIO(json.dumps({"artifacts": [artifact]}).encode())
    class RedirectZip:
        def open(self, request, timeout):
            raise _denied(
                request.full_url, message="Moved Temporarily", stage=302,
                headers={"Location": "https://storage.example/signed-zip"},
            )

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", inventory_or_storage)
    monkeypatch.setattr(state_artifact.urllib.request, "build_opener",
                        lambda *handlers: RedirectZip())
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path)
    assert "stage=ARTIFACT_SIGNED_STORAGE" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()


def test_branchless_original_not_admitted_to_main(monkeypatch, tmp_path):
    wrong = _artifact()
    wrong["workflow_run"].pop("head_branch")
    def inventory(request, timeout):
        return io.BytesIO(json.dumps({"artifacts": [wrong]}).encode())

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", inventory)
    assert _restore(tmp_path) is False
    assert not (tmp_path / "hbi.sqlite").exists()


def test_expired_and_different_branch_do_not_restore(monkeypatch, tmp_path):
    expired = _artifact()
    expired["expired"] = True
    different = _artifact()
    different["workflow_run"]["head_branch"] = "release"
    def inventory(request, timeout):
        return io.BytesIO(json.dumps({"artifacts": [expired, different]}).encode())

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", inventory)
    assert _restore(tmp_path) is False
    assert not (tmp_path / "hbi.sqlite").exists()


def test_http_429_installation_rate_limit_fails_closed(monkeypatch, tmp_path, capsys):
    def fake_open(request, timeout):
        raise _denied(request.full_url, message="secondary rate limit", stage=429)

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", fake_open)
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path)
    assert "classification=INSTALLATION_RATE_LIMIT" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()
