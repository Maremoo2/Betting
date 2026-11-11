from __future__ import annotations

import hashlib
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_release002_t4_runtime import CUTOFF, RACE, _store, setup

from hbi import local_watcher as local
from hbi import watcher
from hbi.private_win_archive import archive_win, verify_win
from hbi.providers.rikstoto import OriginalBytesFetchResult
from hbi.shadow import ShadowPolicy
from hbi.watcher import WatcherAudit

START = datetime(2026, 11, 11, 16, tzinfo=UTC)


@pytest.fixture
def host(tmp_path, monkeypatch):
    class Clock(datetime):
        instant = START

        @classmethod
        def now(cls, tz=None):
            return cls.instant

    state = _store(tmp_path)
    journal = tmp_path / "journal"
    journal.mkdir()
    monkeypatch.setattr(local, "datetime", Clock)
    monkeypatch.setattr(local, "writer_lock", lambda _: nullcontext())
    monkeypatch.setattr(local, "clock_offset", lambda _: 0.02)
    return state, journal, Clock


def test_restart_claim_and_next_slot_report_interruption(host, monkeypatch):
    state, journal, clock = host
    calls = []
    monkeypatch.setattr(local, "run_watcher", lambda **kw: (
        calls.append(kw) or WatcherAudit(started_at_utc=START.isoformat(), status="OK")
    ))
    local.write_journal(local.journal_path(journal, START), {"status": "RUNNING"})
    assert local.run_tick(state.path, journal, "clock")["status"] == "ALREADY_CLAIMED"
    clock.instant += timedelta(minutes=10)
    tick = local.run_tick(state.path, journal, "clock")
    assert tick["status"] == "COMPLETE"
    assert [gap["status"] for gap in tick["recent_gaps"]] == ["RUNNING", "MISSING"]
    assert local.run_tick(state.path, journal, "clock")["status"] == "ALREADY_CLAIMED"
    assert calls == [{"db_path": str(state.path), "skip_frozen": True}]


def test_bad_clock_and_missing_state_fail_before_watcher(host, monkeypatch):
    state, journal, clock = host
    monkeypatch.setattr(local, "run_watcher", lambda **_: pytest.fail("watcher must not run"))

    def unsynced(_):
        raise RuntimeError("WATCHER_CLOCK_UNVERIFIED")

    monkeypatch.setattr(local, "clock_offset", unsynced)
    assert local.run_tick(state.path, journal, "clock")["error"] == "WATCHER_CLOCK_UNVERIFIED"
    clock.instant += timedelta(minutes=5)
    monkeypatch.setattr(local, "clock_offset", lambda _: 0.02)
    missing = state.path.with_name("missing.sqlite")
    assert local.run_tick(missing, journal, "clock")["status"] == "FAILED"
    assert not missing.exists()


@pytest.mark.parametrize("audit,expected", [
    (WatcherAudit(started_at_utc="", status="OK", fetch_failures=1), "SOURCE_FAILURE"),
    (WatcherAudit(started_at_utc="", status="OK", cutoff_rejections=[{}]), "INCOMPLETE_RACES"),
    (WatcherAudit(started_at_utc="", status="OK", t4_attempts=[{}]), "INCOMPLETE_RACES"),
])
def test_incomplete_ticks_remain_visible(host, monkeypatch, audit, expected):
    state, journal, _ = host
    monkeypatch.setattr(local, "run_watcher", lambda **_: audit)
    assert local.run_tick(state.path, journal, "clock")["status"] == expected


@pytest.mark.parametrize("output,error", [
    ("18:12:00, +00.600s", "WATCHER_CLOCK_OFFSET_EXCEEDED"),
    ("No response", "WATCHER_CLOCK_UNVERIFIED"),
])
def test_bad_clock_sample(output, error, monkeypatch):
    monkeypatch.setattr(local.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        a, 0, stdout=output,
    ))
    with pytest.raises(RuntimeError, match=error):
        local.clock_offset("time.windows.com")


@pytest.mark.skipif(sys.platform != "win32", reason="uses Windows OS file lock")
def test_real_windows_lock_is_released_after_process_kill(tmp_path):
    lock = tmp_path / "state.lock"
    command = [
        sys.executable, "-c",
        (
            "import time, sys; from pathlib import Path; from hbi.local_watcher import writer_lock\n"
            "with writer_lock(Path(sys.argv[1])):\n print('locked', flush=True); time.sleep(30)"
        ),
        str(lock),
    ]
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as child:
        try:
            assert child.stdout.readline().strip() == "locked"
            with pytest.raises(RuntimeError, match="WATCHER_WRITER_BUSY"), local.writer_lock(lock):
                pytest.fail("another process held the lock")
        finally:
            child.kill()
            child.wait(timeout=5)
    with local.writer_lock(lock):
        assert lock.exists()


def test_private_archive_exact_readback_retry_and_tamper(tmp_path):
    body = b'{"result":{"odds":[2,3]}}'
    digest = hashlib.sha256(body).hexdigest()
    source = OriginalBytesFetchResult(
        url="https://www.rikstoto.no/api/game/S1_NR_2026-11-11/betdistribution/winodds/1",
        payload={}, success=True, status_code=200, latency_ms=1, raw_body=body,
        response_body_sha256=digest, response_completed_at=START,
    )
    opts = {"race_id": "RIKSTOTO:S1_NR_2026-11-11:1", "approval_id": "TEST_ONLY"}
    receipt = archive_win(tmp_path, source, **opts)
    assert archive_win(tmp_path, source, **opts) == receipt
    assert verify_win(tmp_path, receipt)["pit_certified"] is False
    with pytest.raises(ValueError, match="WIN_ARCHIVE_SOURCE_UNVERIFIED"):
        archive_win(tmp_path, replace(source, url=source.url + "0"), **opts)
    (tmp_path / f"{digest}.body").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="WIN_ARCHIVE_HASH_MISMATCH"):
        verify_win(tmp_path, receipt)


def test_restart_skips_frozen_race_before_source_fetch(tmp_path, monkeypatch):
    state = _store(tmp_path)
    fake = setup(monkeypatch, state)
    assert watcher._reject_missed_t4(
        state, race=RACE, policy=ShadowPolicy(), observed_now=CUTOFF,
    )
    before = state.fetch_table("shadow_decision_runs")
    audit = watcher.run_watcher(db_path="IGNORED", now=CUTOFF, skip_frozen=True)
    assert audit.due_races == audit.frozen_races_skipped == 1
    assert fake.calls == ["discover", "due"]
    assert audit.t4_attempts == []
    assert state.fetch_table("shadow_decision_runs") == before


def test_incomplete_deployment_stops_before_clock_and_watcher(host, monkeypatch, tmp_path):
    state, journal, _ = host
    monkeypatch.setattr(local, "GOVERNANCE", tmp_path / "missing-governance.json")
    monkeypatch.setattr(local, "clock_offset", lambda _: pytest.fail("clock must not run"))
    monkeypatch.setattr(local, "run_watcher", lambda **_: pytest.fail("watcher must not run"))
    result = local.run_tick(state.path, journal, "clock")
    assert result["status"] == "FAILED"
    assert result["error_type"] == "FileNotFoundError"
    assert not state.fetch_table("shadow_decision_runs")
