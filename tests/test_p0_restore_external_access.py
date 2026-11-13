"""P0 external GitHub 403 and immutable state-restore fail-closed regression."""
from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pytest

from hbi import state_artifact


def _artifact(archive: bytes, *, branch="main", digest=None, expired=False):
    return {
        "id": 42, "created_at": "2026-11-06T10:00:00Z", "expired": expired,
        "digest": digest, "archive_download_url":
            "https://api.github.com/repos/Maremoo2/Betting/actions/artifacts/42/zip",
        "workflow_run": {"id": 99, "head_branch": branch, "head_sha": "b" * 40},
    }


def _zip(body: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data/hbi.sqlite", body)
    return buf.getvalue()


def _fake_inventory(monkeypatch, artifacts):
    def urlopen(request, timeout):
        assert request.full_url.endswith("/actions/artifacts?name=hbi-state&per_page=100")
        return io.BytesIO(json.dumps({"artifacts": artifacts}).encode())
    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", urlopen)


def _restore(tmp_path, **kwargs):
    return state_artifact.restore_latest_state(
        repository="Maremoo2/Betting", token="dummy",
        target_path=tmp_path / "hbi.sqlite", artifact_name="hbi-state",
        branch="main", **kwargs,
    )


def test_installation_rate_limit_on_inventory_classified_without_fallback(
    monkeypatch, tmp_path, capsys,
):
    seen = []
    def denied(request, timeout):
        seen.append(request.full_url)
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", {"X-RateLimit-Remaining": "0"},
            io.BytesIO(b'{"message":"API rate limit exceeded for installation"}'),
        )
    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", denied)
    with pytest.raises(urllib.error.HTTPError) as raised:
        _restore(tmp_path, required=True)
    assert raised.value.code == 403
    assert "classification=INSTALLATION_RATE_LIMIT" in capsys.readouterr().err
    assert len(seen) == 1
    assert not (tmp_path / "hbi.sqlite").exists()


def test_permission_403_not_falsely_called_rate_limit(monkeypatch, tmp_path, capsys):
    def denied(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", {},
            io.BytesIO(b'{"message":"Resource not accessible by integration"}'),
        )
    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", denied)
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path, required=True)
    assert "classification=HTTP_ACCESS_OR_SCOPE_UNVERIFIED" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()


def test_zip_download_403_distinguished_from_inventory(monkeypatch, tmp_path, capsys):
    body = _zip(b"SQLite format 3\\x00")
    _fake_inventory(monkeypatch, [_artifact(body, digest=None)])

    class ForbiddenOpener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 403, "Forbidden", {},
                io.BytesIO(b'{"message":"API rate limit exceeded for installation"}'),
            )

    monkeypatch.setattr(
        state_artifact.urllib.request, "build_opener", lambda *args: ForbiddenOpener(),
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        _restore(tmp_path, required=True)
    assert raised.value.code == 403
    assert "stage=ARTIFACT_ZIP" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()


def test_sha_mismatch_does_not_write_database(monkeypatch, tmp_path):
    body = _zip(b"previous real source")
    _fake_inventory(monkeypatch, [_artifact(body, digest="sha256:" + "a" * 64)])

    class Opener:
        def open(self, request, timeout):
            return io.BytesIO(body)

    monkeypatch.setattr(
        state_artifact.urllib.request, "build_opener", lambda *args: Opener(),
    )
    with pytest.raises(ValueError, match="STATE_RESTORE_ARTIFACT_ZIP_SHA_MISMATCH"):
        _restore(tmp_path, required=True)
    assert not (tmp_path / "hbi.sqlite").exists()


def test_valid_authenticated_archive_with_original_digest(monkeypatch, tmp_path):
    data = b"SQLite format 3\\x00authentic prior research state"
    body = _zip(data)
    _fake_inventory(monkeypatch, [
        _artifact(body, digest="sha256:" + hashlib.sha256(body).hexdigest()),
    ])

    class Opener:
        def open(self, request, timeout):
            assert request.full_url.endswith("/42/zip")
            return io.BytesIO(body)

    monkeypatch.setattr(
        state_artifact.urllib.request, "build_opener", lambda *args: Opener(),
    )
    assert _restore(tmp_path, required=True)
    assert (tmp_path / "hbi.sqlite").read_bytes() == data


@pytest.mark.parametrize("artifacts", [
    [], [_artifact(b"zip", expired=True)],
    [_artifact(b"zip", branch="unrelated")],
])
def test_required_core003_restore_refuses_missing_expired_or_other_branch(
    monkeypatch, tmp_path, artifacts,
):
    _fake_inventory(monkeypatch, artifacts)
    with pytest.raises(RuntimeError, match="STATE_RESTORE_REQUIRED_BUT_NO_VERIFIED_ARTIFACT"):
        _restore(tmp_path, required=True)
    assert not (tmp_path / "hbi.sqlite").exists()


def test_core003_workflow_skips_downstream_api_reads_on_restore_failure():
    path = Path(__file__).resolve().parents[1] / (
        ".github/workflows/core-003-shadow-pilot.yml"
    )
    source = path.read_text(encoding="utf-8")
    assert "id: restore" in source
    assert "required=True" in source
    assert "steps.restore.outcome == 'success'" in source
    source_job, outcome_job = source.split("\n  outcome-research:", 1)
    collector = source_job.split("- name: Recover authenticated Collector originals (read only)", 1)[1]
    assert "steps.restore.outcome == 'success'" in collector.splitlines()[1]
    assert "restore: ${{ steps.restore.outcome }}" in source_job
    outcome_gate = outcome_job.split("    steps:", 1)[0]
    assert "needs: source-pilot" in outcome_gate
    assert "needs.source-pilot.outputs.restore == 'success'" in outcome_gate
    assert "needs.source-pilot.outputs.execute == 'true'" in outcome_gate
    for heading in (
        "Recover current-run original evidence",
        "Recover prior original prospective models (read only)",
        "Recover cumulative DEV-011 originals for scorecard only (NO BET)",
    ):
        assert "- name: " + heading in outcome_job
        assert "- name: " + heading not in source_job
    assert 'cron: "*/5 7-21 * * *"' in source
    assert "bet_authority: true" not in source


def test_missing_head_branch_never_becomes_main_state(monkeypatch, tmp_path):
    artifact = _artifact(b"original", branch=None)
    _fake_inventory(monkeypatch, [artifact])
    with pytest.raises(RuntimeError, match="STATE_RESTORE_REQUIRED_BUT_NO_VERIFIED_ARTIFACT"):
        _restore(tmp_path, required=True)
    assert not (tmp_path / "hbi.sqlite").exists()


def test_http_429_rate_limit_preserved_and_fails_closed(monkeypatch, tmp_path, capsys):
    def denied(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many Requests", {"X-RateLimit-Remaining": "0"},
            io.BytesIO(b'{"message":"secondary rate limit"}'),
        )
    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", denied)
    with pytest.raises(urllib.error.HTTPError) as err:
        _restore(tmp_path, required=True)
    assert err.value.code == 429
    assert "classification=INSTALLATION_RATE_LIMIT" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()
