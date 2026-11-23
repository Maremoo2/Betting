"""Synthetic HTTP failures; never evidence of an actual expired original."""
import io
import json
import urllib.error

import pytest

from hbi import state_artifact


@pytest.mark.parametrize("code", [404, 410])
def test_missing_selected_zip_is_identifiable_without_fallback_or_state_change(
    monkeypatch, tmp_path, capsys, code,
):
    target = tmp_path / "hbi.sqlite"
    original = b"SYNTHETIC_PRIOR_STATE_MUST_REMAIN_IDENTICAL"
    target.write_bytes(original)
    receipt = tmp_path / "restore-receipt.json"
    artifacts = [
        {"id": aid, "created_at": date, "expired": False,
         "archive_download_url": f"https://api.github.com/repos/TEST/TEST/actions/artifacts/{aid}/zip",
         "workflow_run": {"id": run, "head_branch": "main", "head_sha": "a" * 40}}
        for aid, run, date in [(79, 41, "2026-11-21T10:00:00Z"),
                              (80, 42, "2026-11-22T10:00:00Z")]
    ]
    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", lambda *a, **kw:
                        io.BytesIO(json.dumps({"artifacts": artifacts}).encode()))
    calls = []

    class MissingZip:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, code, "Missing", {},
                                         io.BytesIO(b'{"message":"Not Found"}'))

    monkeypatch.setattr(state_artifact.urllib.request, "build_opener", lambda *a: MissingZip())
    with pytest.raises(urllib.error.HTTPError) as raised:
        state_artifact.restore_latest_state(
            repository="TEST/TEST", token="TEST_ONLY_SECRET", target_path=target,
            branch="main", required=True, receipt_path=receipt,
            audit_workflow_run_id=123, audit_code_sha="b" * 40,
        )
    assert raised.value.code == code
    assert calls == [artifacts[1]["archive_download_url"]]
    assert target.read_bytes() == original and not receipt.exists()
    log = capsys.readouterr().err
    assert "artifact_id=80 source_workflow_run_id=42" in log
    assert f"stage=ARTIFACT_ZIP http={code}" in log
    assert "classification=ORIGINAL_NOT_FOUND_OR_INACCESSIBLE" in log
    assert "no_bootstrap=true" in log and "source_state=NOT_RESTORED" in log
    assert "TEST_ONLY_SECRET" not in log and "https://" not in log


def test_missing_inventory_is_not_a_successful_empty_bootstrap(monkeypatch, tmp_path, capsys):
    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Missing", {}, io.BytesIO(b'{}'))

    monkeypatch.setattr(state_artifact.urllib.request, "urlopen", missing)
    with pytest.raises(urllib.error.HTTPError):
        state_artifact.restore_latest_state(repository="TEST/TEST", token="TEST_ONLY_SECRET",
                                            target_path=tmp_path / "hbi.sqlite", required=True)
    log = capsys.readouterr().err
    assert "stage=ARTIFACT_INVENTORY http=404" in log
    assert "SOURCE_SELECTED" not in log
    assert not (tmp_path / "hbi.sqlite").exists()
