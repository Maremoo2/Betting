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

def test_daily_result_capture_includes_started_race_without_model(monkeypatch, tmp_path):
    import json

    from hbi import hq_acceptance as acceptance
    from hbi import hq_daily_report

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
    monkeypatch.setattr(hq_daily_report, "official_observation", lambda *args: None)
    out, stage, archive = [tmp_path / name for name in ("out", "stage", "archive")]
    out.mkdir()
    stage.mkdir()
    summary = acceptance.render_daily(
        ["--report-at", "2026-11-13T18:00:00Z"], archive, stage, out, {"runs": [], "gaps": []},
    )
    assert seen == [race_id]
    assert summary["results"][0]["status"] == "LINKED"
    assert summary["model_freezes"] == summary["scored"] == 0
