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
