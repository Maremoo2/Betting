"""RELEASE-004 isolated GitHub state-restore safety, no production source calls."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import urllib.error
import zipfile

import pytest

from hbi import state_artifact


def _valid_db(tmp_path, *, complete=True):
    path = tmp_path / "fixture.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE races (race_id TEXT PRIMARY KEY)")
        if complete:
            for name in (
                "provider_race_refs", "shadow_decision_runs",
                "shadow_tickets", "schema_migrations",
            ):
                db.execute(f"CREATE TABLE {name} (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO races VALUES ('original-race')")
    return path.read_bytes()


def _zip(raw):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("data/hbi.sqlite", raw)
    return stream.getvalue()


def _meta(body, digest=None):
    return {
        "id": 77, "expired": False, "created_at": "2026-11-11T10:00:00Z",
        "archive_download_url":
            "https://api.github.com/repos/Maremoo2/Betting/actions/artifacts/77/zip",
        "digest": "sha256:" + (digest or hashlib.sha256(body).hexdigest()),
        "workflow_run": {
            "id": 99, "head_branch": "main", "head_sha": "a" * 40,
        },
    }


def _feed(monkeypatch, archive, *, attempts=None, digest=None):
    calls = []
    item = _meta(archive, digest=digest)

    def inventory(request, timeout):
        calls.append(request.full_url)
        assert request.full_url.endswith(
            "/actions/artifacts?name=hbi-state&per_page=100"
        )
        if attempts:
            answer = attempts.pop(0)
            if answer is not None:
                raise answer
        return io.BytesIO(json.dumps({"artifacts": [item]}).encode())

    class Downloader:
        def open(self, request, timeout):
            calls.append("ZIP")
            assert request.full_url == item["archive_download_url"]
            return io.BytesIO(archive)

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", inventory)
    monkeypatch.setattr(
        state_artifact.urllib.request, "build_opener", lambda *a: Downloader(),
    )
    return calls


def _restore(tmp_path, **kwargs):
    return state_artifact.restore_latest_state(
        repository="Maremoo2/Betting", token="fake-token-not-logged",
        target_path=tmp_path / "hbi.sqlite",
        artifact_name="hbi-state", branch="main", required=True,
        validate_sqlite=True, **kwargs,
    )


def test_strict_valid_state_atomic_restore_and_sha(tmp_path, monkeypatch):
    raw = _valid_db(tmp_path)
    calls = _feed(monkeypatch, _zip(raw))
    assert _restore(tmp_path)
    assert (tmp_path / "hbi.sqlite").read_bytes() == raw
    assert len(calls) == 2  # exactly one inventory, one ZIP (no redirect in test)
    assert not list(tmp_path.glob(".hbi.sqlite.restore-*"))


def test_incomplete_state_never_replaces_verified_previous(tmp_path, monkeypatch):
    previous = b"preserve immutable previous state"
    dest = tmp_path / "hbi.sqlite"
    dest.write_bytes(previous)
    raw = _valid_db(tmp_path, complete=False)
    _feed(monkeypatch, _zip(raw))
    with pytest.raises(ValueError, match="REQUIRED_TABLES_MISSING"):
        _restore(tmp_path)
    assert dest.read_bytes() == previous
    assert not list(tmp_path.glob(".hbi.sqlite.restore-*"))


def test_invalid_zip_digest_never_replaces_previous(tmp_path, monkeypatch):
    dest = tmp_path / "hbi.sqlite"
    dest.write_bytes(b"verified existing")
    _feed(monkeypatch, _zip(_valid_db(tmp_path)), digest="0" * 64)
    with pytest.raises(ValueError, match="ARTIFACT_ZIP_SHA_MISMATCH"):
        _restore(tmp_path)
    assert dest.read_bytes() == b"verified existing"


def test_integrity_failure_with_non_sqlite_bytes_fails_closed(tmp_path, monkeypatch):
    _feed(monkeypatch, _zip(b"not a SQLite database"))
    with pytest.raises(ValueError, match="SQLITE_HEADER_INVALID"):
        _restore(tmp_path)
    assert not (tmp_path / "hbi.sqlite").exists()


def test_rename_error_preserves_previous_state(tmp_path, monkeypatch):
    dest = tmp_path / "hbi.sqlite"
    dest.write_bytes(b"unchanged")
    _feed(monkeypatch, _zip(_valid_db(tmp_path)))
    def broken_replace(*_args):
        raise OSError("synthetic crash immediately before atomic install")
    monkeypatch.setattr(state_artifact.os, "replace", broken_replace)
    with pytest.raises(OSError, match="synthetic crash"):
        _restore(tmp_path)
    assert dest.read_bytes() == b"unchanged"
    assert not list(tmp_path.glob(".hbi.sqlite.restore-*"))


def _denial(*, remaining="0", reset="130", message="API rate limit exceeded"):
    return urllib.error.HTTPError(
        "https://api.github.com/repos/Maremoo2/Betting/actions/artifacts",
        403, "Forbidden",
        {"X-RateLimit-Remaining": remaining, "X-RateLimit-Reset": reset},
        io.BytesIO(json.dumps({"message": message}).encode()),
    )


def test_short_reset_one_bounded_retry_no_bootstrap(tmp_path, monkeypatch):
    raw = _valid_db(tmp_path)
    calls = _feed(monkeypatch, _zip(raw), attempts=[_denial(), None])
    monkeypatch.setattr(state_artifact.time, "time", lambda: 100.0)
    waited = []
    monkeypatch.setattr(state_artifact.time, "sleep", waited.append)
    assert _restore(tmp_path)
    assert waited == [31.0]
    assert calls.count("ZIP") == 1
    assert len(calls) == 3  # 2 inventory attempts + 1 ZIP
    assert (tmp_path / "hbi.sqlite").read_bytes() == raw


@pytest.mark.parametrize("reset,remaining", [
    ("500", "0"),  # server reset too far away
    ("130", "17"),  # permissions issue: never retry an unverified 403
    ("not-a-time", "0"),
])
def test_403_no_safe_reset_fails_without_retry(
    tmp_path, monkeypatch, reset, remaining, capsys,
):
    calls = _feed(
        monkeypatch, _zip(_valid_db(tmp_path)),
        attempts=[_denial(remaining=remaining, reset=reset)],
    )
    monkeypatch.setattr(state_artifact.time, "time", lambda: 100.0)
    monkeypatch.setattr(
        state_artifact.time, "sleep",
        lambda _s: pytest.fail("must not sleep on unsafe reset"),
    )
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path)
    assert len(calls) == 1
    assert not (tmp_path / "hbi.sqlite").exists()
    assert "no_bootstrap=true" in capsys.readouterr().err


def test_second_403_stops_safely(tmp_path, monkeypatch, capsys):
    calls = _feed(
        monkeypatch, _zip(_valid_db(tmp_path)),
        attempts=[_denial(), _denial()],
    )
    monkeypatch.setattr(state_artifact.time, "time", lambda: 100.0)
    monkeypatch.setattr(state_artifact.time, "sleep", lambda _s: None)
    with pytest.raises(urllib.error.HTTPError):
        _restore(tmp_path)
    assert len(calls) == 2
    assert "no_bootstrap=true" in capsys.readouterr().err
    assert not (tmp_path / "hbi.sqlite").exists()


def test_missing_artifact_never_bootstraps_or_overwrites(tmp_path, monkeypatch):
    target = tmp_path / "hbi.sqlite"
    target.write_bytes(b"prior")
    def empty_inventory(request, timeout):
        return io.BytesIO(b'{"artifacts":[]}')
    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", empty_inventory)
    with pytest.raises(RuntimeError, match="NO_VERIFIED_ARTIFACT"):
        _restore(tmp_path)
    assert target.read_bytes() == b"prior"
