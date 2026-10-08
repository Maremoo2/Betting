import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from hbi.operations_report import build_operations_report
from hbi.storage import SQLiteStore

NOW = datetime(2026, 10, 2, 10, tzinfo=UTC)


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        build_operations_report(path, date(2026, 10, 1), date(2026, 10, 7), now=NOW)
    assert not path.exists()


def test_read_only_report_has_unknown_future_and_country_coverage(tmp_path):
    path = tmp_path / "state.sqlite"
    store = SQLiteStore(path)
    store.initialize(Path(__file__).parents[1] / "db/schema.sql")
    with store.connect() as c:
        c.execute("INSERT INTO races (race_id,race_date,country,track,race_no,start_time_utc,"
                  "discipline,created_at_utc) VALUES (?,?,?,?,?,?,?,?)",
                  ("r", "2026-10-01", "SE", "Test", 1, "2026-10-01T10:00:00+00:00",
                   "trot", "2026-10-01T08:00:00+00:00"))
        c.execute("INSERT INTO shadow_decision_runs (decision_run_id,race_id,created_at_utc,"
                  "race_start_time_utc,decision_status,shadow_model_version,product) "
                  "VALUES (?,?,?,?,?,?,?)",
                  ("d", "r", "2026-10-01T09:56:00+00:00", "2026-10-01T10:00:00+00:00",
                   "PASS", "test", "V"))
    # Later success cannot replace the failed evidence that existed at decision time.
    for stamp, passed in (("2026-10-01T09:55:00+00:00", False),
                          ("2026-10-01T09:57:00+00:00", True)):
        store.insert_provider_payload(
            payload_id=stamp, provider="atg", category="FULL_FIELD_ONLY_V1",
            provider_raceday_key="r", observed_at=datetime.fromisoformat(stamp),
            source_uri="test", payload={"passed": passed, "runners": [],
                                        "reasons": [] if passed else ["INCOMPLETE_FIELD"]})
    before = path.read_bytes()
    report = build_operations_report(path, date(2026, 10, 1), date(2026, 10, 7), now=NOW)
    assert path.read_bytes() == before
    assert len(report["daily"]) == 28
    assert not report["period_elapsed"]
    assert report["races"][0]["coverage"] == "REJECTED"
    se = report["daily"][0]
    assert se["t4_within_60_seconds"] == 1
    assert se["rejections"] == {"INCOMPLETE_FIELD": 1}
    assert report["daily"][1]["observation_status"] == "NO_EVIDENCE"
    assert report["daily"][-1]["observation_status"] == "FUTURE"
    json.dumps(report, allow_nan=False)


def test_missing_decision_and_exact_24h_backlog_remain_visible(tmp_path):
    path = tmp_path / "state.sqlite"
    store = SQLiteStore(path)
    store.initialize(Path(__file__).parents[1] / "db/schema.sql")
    with store.connect() as c:
        c.execute("INSERT INTO races (race_id,race_date,country,track,race_no,start_time_utc,"
                  "discipline,created_at_utc) VALUES (?,?,?,?,?,?,?,?)",
                  ("r", "2026-10-01", "FR", "Test", 1, "2026-10-01T10:00:00+00:00",
                   "trot", "2026-10-01T08:00:00+00:00"))
        c.execute("INSERT INTO shadow_tickets (ticket_id,dedupe_key,created_at_utc,"
                  "decision_time_utc,race_id,provider,product,decision,status,selections_json) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  ("t", "key", "2026-10-01T09:56:00+00:00", "2026-10-01T09:56:00+00:00",
                   "r", "rikstoto", "V", "BET", "SHADOW_BET", '["5"]'))
    report = build_operations_report(path, date(2026, 10, 1), date(2026, 10, 7), now=NOW)
    fr = next(r for r in report["daily"] if r["country"] == "FR")
    assert fr["missing_decision_after_start"] == 1
    assert fr["coverage"] == {"UNKNOWN": 1}
    assert fr["overdue_tickets"] == 1
    assert report["open_settlement_backlog_all_dates"][0]["age_hours"] == 24
    assert not report["open_settlement_backlog_all_dates"][0]["outcome_present"]
