import hashlib

import pytest

from hbi.hq_acceptance import pinned_zip


def test_pinned_archive_replay_rejects_changed_bytes(tmp_path):
    original = tmp_path / "123.zip"
    body = b"fixture bytes"
    original.write_bytes(body)
    pin = hashlib.sha256(body).hexdigest()
    assert pinned_zip(tmp_path, "123", pin) == original
    assert pinned_zip(tmp_path, "123", pin) == original
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA mismatch"):
        pinned_zip(tmp_path, "123", pin)


def test_archive_id_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError, match="artifact ID"):
        pinned_zip(tmp_path, "../123", "0" * 64)

def test_daily_inventory_uses_oslo_day_and_sorts(monkeypatch):
    from datetime import date

    from hbi import hq_daily_operations as daily

    rows = [
        {"id": 3, "created_at": "2026-11-13T23:00:00Z"},
        {"id": 2, "created_at": "2026-11-13T21:00:00Z"},
        {"id": 1, "created_at": "2026-11-12T23:00:00Z"},
        {"id": 0, "created_at": "2026-11-12T22:59:59Z"},
    ]
    monkeypatch.setattr(daily, "pages", lambda _: [{"workflow_runs": rows}])
    assert [r["id"] for r in daily.day_runs(date(2026, 11, 13))] == [1, 2]


def test_daily_inventory_preserves_cancelled_run_originals(monkeypatch, tmp_path):
    from datetime import date
    from zipfile import ZipFile

    from hbi import hq_daily_operations as daily

    runs = [
        {"id": 10, "status": "completed", "conclusion": "cancelled"},
        {"id": 11, "status": "completed", "conclusion": "success"},
    ]
    listings = {}
    for run in runs:
        rid = run["id"]
        artifacts = []
        for number, (name, member) in enumerate((
            (f"core003-pilot-report-{rid}", "core003-pilot-report.json"),
            (f"bet-mvp-shadow-{rid}", "cohort-index.json"),
            (f"collector-handoff-{rid}", "collector-handoff.json"),
            (f"pit003a-collector-evidence-{rid}", "manifest.json"),
            ("core003-pilot-state", "core003-pilot.sqlite"),
        ), 1):
            artifact_id = rid * 10 + number
            archive = tmp_path / f"{artifact_id}.zip"
            with ZipFile(archive, "w") as output:
                output.writestr(member, b"isolated inventory fixture")
            artifacts.append({
                "name": name, "id": artifact_id, "expired": False,
                "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
            })
        listings[rid] = [{"artifacts": artifacts}]
    monkeypatch.setattr(daily, "day_runs", lambda _: runs)
    monkeypatch.setattr(daily, "pages", lambda url: listings[int(url.split("/")[5])])
    config = daily.inventory(date(2026, 11, 13), tmp_path)
    assert config["state_artifact"] == "115"
    assert config["args"][config["args"].index("--prior-cohort") + 1] == "102.zip"
    assert {"run_id": 10, "reason": "cancelled"} in config["gaps"]


def test_daily_result_capture_includes_started_race_without_model(monkeypatch, tmp_path):
    import json

    from hbi import hq_acceptance as acceptance
    race_id = "RIKSTOTO:S2_NR_2026-11-13:2"
    future_id = "RIKSTOTO:S2_NR_2026-11-13:3"
    seen = []
    day = {"races": [
        {"race_id": race_id, "start": "2020-11-13T18:00:00Z", "analysis": None,
         "active": 4, "official": None},
        {"race_id": future_id, "start": "2099-11-13T18:00:00Z", "analysis": None,
         "active": 4, "official": None},
    ]}

    def render(command, **_):
        destination = acceptance.Path(command[-1])
        destination.mkdir(exist_ok=True)
        (destination / "betting-hq.json").write_text(json.dumps(day))

    def capture(folder, rid, client):
        seen.append(rid)
        (folder / "example").write_bytes(b"isolated result fixture")

    monkeypatch.setattr(acceptance.subprocess, "run", render)
    monkeypatch.setattr(acceptance, "capture_result", capture)
    monkeypatch.setattr(acceptance, "official_observation", lambda *args: None)
    out, stage, archive = [tmp_path / name for name in ("out", "stage", "archive")]
    out.mkdir()
    stage.mkdir()
    summary = acceptance.render_daily(
        ["--report-at", "2026-11-13T18:00:00Z"], archive, stage, out, {"runs": [], "gaps": []},
    )
    assert seen == [race_id]
    assert summary["results"][0]["status"] == "LINKED"
    assert summary["model_freezes"] == summary["scored"] == 0

def test_offline_daily_replay_uses_pinned_result_and_no_provider_calls(monkeypatch, tmp_path):
    import json
    from pathlib import Path

    from hbi import hq_acceptance as acceptance
    rid = "RIKSTOTO:S2_NR_2026-11-13:1"
    result_bytes = b"saved result fixture"
    version = acceptance.digest(json.dumps(
        {"fixture": acceptance.digest(result_bytes)}, sort_keys=True,
    ).encode())
    archive, stage, output = [tmp_path / label for label in ("archive", "stage", "output")]
    stage.mkdir()
    target = archive / "results" / version
    target.mkdir(parents=True)
    (target / "fixture").write_bytes(result_bytes)
    race = {"race_id": rid, "start": "2026-11-13T18:00:00+00:00",
            "analysis": None, "active": 4, "official": None}

    def render(command, **_):
        destination = Path(command[-1])
        destination.mkdir(exist_ok=True)
        (destination / "betting-hq.json").write_text(json.dumps({"races": [race]}))

    def unexpected(*_):
        pytest.fail("Offline replay must not fetch a live result")

    monkeypatch.setattr(acceptance.subprocess, "run", render)
    monkeypatch.setattr(acceptance, "capture_result", unexpected)
    monkeypatch.setattr(acceptance, "official_observation", lambda *args: None)
    config = {"runs": [], "gaps": [], "result_versions": {rid: version}}
    args = ["--report-at", "2026-11-13T18:01:00+00:00"]
    summary = acceptance.render_daily(args, archive, stage, output, config)
    assert summary["results"] == [{"race_id": rid, "status": "LINKED", "result_version_sha256": version}]
    (target / "fixture").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Archived result version SHA mismatch"):
        acceptance.render_daily(args, archive, stage, output, config)

def test_live_result_falls_back_to_verified_archive_only_for_unavailable_source(monkeypatch, tmp_path):
    import json

    from hbi import hq_acceptance as acceptance

    rid = "RIKSTOTO:S2_NR_2026-11-13:1"
    race = {"race_id": rid, "start": "2026-11-12T18:00:00+00:00", "analysis": None,
            "active": 4, "official": None}
    observation = {"receipts": {"complete": {"observed_at_utc": "2026-11-12T18:30:00+00:00"}}}
    files = {"fixture": b"saved result fixture"}
    version = acceptance.result_version(files)
    archive = tmp_path / "archive"
    target = archive / "results" / version
    target.mkdir(parents=True)
    (target / "fixture").write_bytes(files["fixture"])
    acceptance.remember_result(archive, rid, version, observation)

    def render(command, **_):
        destination = acceptance.Path(command[-1])
        destination.mkdir(exist_ok=True)
        (destination / "betting-hq.json").write_text(json.dumps({"races": [race]}))

    def capture(*_):
        raise capture.error

    monkeypatch.setattr(acceptance.subprocess, "run", render)
    monkeypatch.setattr(acceptance, "capture_result", capture)
    monkeypatch.setattr(acceptance, "official_observation", lambda *args: observation)
    for index, error, status in (
        (1, acceptance.OfficialResultUnavailable("Source incomplete"), "LINKED"),
        (2, ValueError("Source race ID mismatch"), "BLOCKED"),
    ):
        capture.error = error
        stage, output = [tmp_path / f"{label}-{index}" for label in ("stage", "output")]
        stage.mkdir()
        args = ["--report-at", "2026-11-13T18:01:00+00:00"]
        summary = acceptance.render_daily(args, archive, stage, output, {"runs": [], "gaps": []})
        assert summary["results"][0]["status"] == status
        if status == "LINKED":
            assert summary["results"][0]["result_version_sha256"] == version
            assert summary["results"][0]["retrieval"] == "ARCHIVED_AFTER_SOURCE_UNAVAILABLE"
