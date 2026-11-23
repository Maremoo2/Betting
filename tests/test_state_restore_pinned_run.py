"""Run-scoped state handoff: no latest-state fallback, overwrite or bootstrap."""
import hashlib
import io
import json

import pytest
from test_release004_restore import _meta, _valid_db, _zip

from hbi import state_artifact as state


def feed(monkeypatch, body, *, status="completed", conclusion="success", duplicate=False,
         missing=False, digest=True):
    item = _meta(body)
    item["name"] = "hbi-state"
    if not digest:
        item.pop("digest")
    calls = []

    def fetch(url, token):
        calls.append(url)
        if url.endswith("/actions/runs/99"):
            return {"id": 99, "status": status, "conclusion": conclusion,
                    "head_branch": "main", "head_sha": "a" * 40}
        assert url.endswith("/actions/runs/99/artifacts?per_page=100")
        return {"artifacts": [] if missing else [item, item] if duplicate else [item]}

    class Download:
        def open(self, request, timeout):
            return io.BytesIO(body)

    monkeypatch.setattr(state, "_inventory_json", fetch)
    monkeypatch.setattr(state.urllib.request, "build_opener", lambda *args: Download())
    return calls


def restore(tmp_path, **kwargs):
    return state.restore_latest_state(repository="Maremoo2/Betting", token="test",
                                      target_path=tmp_path / "hbi.sqlite", branch="main",
                                      source_run_id=99, required=True, validate_sqlite=True,
                                      **kwargs)


def test_two_independent_restores_same_bytes_and_receipt(tmp_path, monkeypatch):
    raw = _valid_db(tmp_path)
    body = _zip(raw)
    calls = feed(monkeypatch, body)
    for _ in range(2):
        assert restore(tmp_path, expected_zip_sha256=hashlib.sha256(body).hexdigest(),
                       expected_database_sha256=hashlib.sha256(raw).hexdigest(),
                       receipt_path=tmp_path / "receipt.json", audit_workflow_run_id=123,
                       audit_code_sha="b" * 40)
        assert (tmp_path / "hbi.sqlite").read_bytes() == raw
        receipt = json.loads((tmp_path / "receipt.json").read_bytes())
        assert receipt["selection_rule"] == "EXACT_SUCCESSFUL_SOURCE_RUN"
    assert len(calls) == 4


@pytest.mark.parametrize("options,reason", [
    ({"status": "in_progress", "conclusion": None}, "SOURCE_RUN_NOT_SUCCESSFUL"),
    ({"conclusion": "failure"}, "SOURCE_RUN_NOT_SUCCESSFUL"),
    ({"missing": True}, "REQUIRED_BUT_NO_VERIFIED_ARTIFACT"),
    ({"duplicate": True}, "SOURCE_ARTIFACT_NOT_UNIQUE"),
    ({"digest": False}, "ARTIFACT_DIGEST_REQUIRED"),
])
def test_invalid_producer_never_falls_back_or_changes_state(tmp_path, monkeypatch, options, reason):
    body = _zip(_valid_db(tmp_path))
    previous = b"previous state remains untouched"
    (tmp_path / "hbi.sqlite").write_bytes(previous)
    feed(monkeypatch, body, **options)
    with pytest.raises((ValueError, RuntimeError), match=reason):
        restore(tmp_path)
    assert (tmp_path / "hbi.sqlite").read_bytes() == previous


@pytest.mark.parametrize("key", ["expected_zip_sha256", "expected_database_sha256"])
def test_wrong_expected_hash_preserves_previous_state(tmp_path, monkeypatch, key):
    body = _zip(_valid_db(tmp_path))
    feed(monkeypatch, body)
    (tmp_path / "hbi.sqlite").write_bytes(b"previous")
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        restore(tmp_path, **{key: "0" * 64})
    assert (tmp_path / "hbi.sqlite").read_bytes() == b"previous"


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_busy_target_never_replaced(tmp_path, monkeypatch, suffix):
    feed(monkeypatch, _zip(_valid_db(tmp_path)))
    (tmp_path / "hbi.sqlite").write_bytes(b"previous")
    (tmp_path / ("hbi.sqlite" + suffix)).write_bytes(b"busy")
    with pytest.raises(ValueError, match="TARGET_BUSY"):
        restore(tmp_path)
    assert (tmp_path / "hbi.sqlite").read_bytes() == b"previous"


def test_restore_failure_is_durable_observable_and_not_overwritten(tmp_path):
    target = tmp_path / "state-status/failure.json"
    report = state.write_restore_failure_status(target, reason="SHA_MISMATCH", run_id="123",
                                                declared_race_ids=("RIKSTOTO:TEST:1",))
    assert report["alert_required"] is True
    assert report["declared_races"][0]["terminal_status"] == "SYSTEM_BLOCKED"
    assert report["declaration_is_live_discovery"] is False
    assert report["restored"] is False
    assert report["bootstrap_allowed"] is False
    assert json.loads(target.read_bytes()) == report
    with pytest.raises(FileExistsError):
        state.write_restore_failure_status(target, reason="other", run_id="123")


@pytest.mark.parametrize("writer_status,writer_result,accepted", [
    ("completed", "success", True), ("in_progress", None, False),
    ("completed", "failure", False),
])
def test_only_github_completed_writer_can_handoff_while_readonly_sidecar_runs(
        tmp_path, monkeypatch, writer_status, writer_result, accepted):
    raw = _valid_db(tmp_path)
    body = _zip(raw)
    feed(monkeypatch, body)
    original = state._inventory_json

    def api(url, token):
        if url.endswith("/jobs?per_page=100"):
            return {"jobs": [{"name": "source-pilot", "status": writer_status,
                              "conclusion": writer_result}]}
        result = original(url, token)
        if url.endswith("/actions/runs/99"):
            result.update(status="in_progress", conclusion=None)
        return result

    monkeypatch.setattr(state, "_inventory_json", api)
    kwargs = {"source_job_name": "source-pilot", "audit_code_sha": "a" * 40}
    if accepted:
        assert restore(tmp_path, **kwargs)
        assert (tmp_path / "hbi.sqlite").read_bytes() == raw
    else:
        with pytest.raises(ValueError, match="WRITER_JOB_NOT_SUCCESSFUL"):
            restore(tmp_path, **kwargs)
        assert not (tmp_path / "hbi.sqlite").exists()
