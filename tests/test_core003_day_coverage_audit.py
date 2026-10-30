"""CORE-003 whole-day denominator and hard blocker regression tests."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from test_pit_roster_verification import R, fixture_db

SOURCE = Path(__file__).resolve().parents[1] / "scripts/core003_day_coverage_audit.py"
SPEC = importlib.util.spec_from_file_location("core003_day_coverage_audit", SOURCE)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

ASOF = "2026-10-30T15:10:00+00:00"


def run(path, **kw):
    return audit.analyze(path, start_date=kw.get("start", "2026-10-30"),
                         end_date=kw.get("end", "2026-10-30"),
                         asof=kw.get("asof", ASOF))


def test_full_day_ledger_accounts_for_all_races_and_does_not_edit_db(tmp_path):
    p = fixture_db(tmp_path)
    before = audit.sha256(p)
    result = run(p)
    assert result["source_db_sha256"] == before == audit.sha256(p)
    assert result["source_db_unchanged"] is True
    assert result["summary"]["races_total"] == 1
    assert result["summary"]["raw_input_ready"] == 1
    assert result["summary"]["pit_certified"] == 0
    assert result["country_days"]["2026-10-30|SE"]["races_total"] == 1
    assert result["track_days"]["2026-10-30|SE|Synthetic"]["races_total"] == 1
    assert result["races"][0]["race_id"] == R
    assert result["races"][0]["terminal_status"] == "SOURCE_OBSERVED_UNATTESTED"
    assert result["betting_authority"] is False


def test_future_race_counted_but_not_claimed_as_failed_t4(tmp_path):
    p = fixture_db(tmp_path)
    result = run(p, asof="2026-10-30T14:40:00+00:00")
    assert result["summary"]["races_total"] == 1
    assert result["summary"]["races_t4_elapsed"] == 0
    assert result["summary"]["races_future_not_at_t4"] == 1
    assert result["summary"]["blocked"] == 0
    assert result["races"][0]["terminal_status"] == "FUTURE"


def test_blocked_country_day_is_not_filtered_out(tmp_path):
    p = fixture_db(tmp_path)
    with sqlite3.connect(p) as c:
        c.execute("UPDATE races SET country='FR' WHERE race_id=?", (R,))
        c.execute("DELETE FROM provider_payloads")
    result = run(p)
    assert result["summary"]["races_total"] == 1
    assert result["summary"]["raw_input_ready"] == 0
    assert result["country_days"]["2026-10-30|FR"]["blocked"] == 1
    assert result["races"][0]["blockers"]


def test_multiday_denominator_and_track_totals_match(tmp_path):
    p = fixture_db(tmp_path)
    with sqlite3.connect(p) as c:
        c.execute("INSERT INTO races SELECT 'R2','2026-10-29','NO','Bjerke',2,"
                  "'2026-10-29T15:00:00+00:00','trot'")
    report = run(p, start="2026-10-29")
    assert report["summary"]["races_total"] == 2
    assert report["summary"]["blocked"] == 1
    assert report["summary"]["raw_input_ready"] == 1
    assert sum(v["races_total"] for v in report["track_days"].values()) == 2


@pytest.mark.parametrize("first,last,asof", [
    ("2026-10-31", "2026-10-30", ASOF),
    ("2026-09-01", "2026-10-30", ASOF),
    ("2026-10-30", "2026-10-30", "2026-10-30T15:10:00"),
])
def test_invalid_date_window_and_naive_asof_rejected(tmp_path, first, last, asof):
    with pytest.raises(ValueError):
        run(fixture_db(tmp_path), start=first, end=last, asof=asof)


def test_empty_day_not_misreported_as_full_coverage(tmp_path):
    with pytest.raises(ValueError, match="NO_RACES_IN_EXPLICIT_COHORT"):
        run(fixture_db(tmp_path), start="2026-10-29", end="2026-10-29")


def test_duplicate_physical_race_rejected(tmp_path):
    p = fixture_db(tmp_path)
    with sqlite3.connect(p) as c:
        c.execute("INSERT INTO races SELECT * FROM races")
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE"):
        run(p)


def test_source_clock_conflict_is_visible_and_not_pit_certificate(tmp_path):
    p = fixture_db(tmp_path, source_start="2026-10-30T14:57:00+00:00")
    report = run(p)
    assert report["summary"]["clock_conflicts"] == 1
    assert report["summary"]["raw_input_ready"] == 0
    assert report["summary"]["pit_certified"] == 0
    assert report["races"][0]["clock_disagreement_seconds"] == 180


def test_cross_track_x1_race_is_retained_but_not_claimed_physical(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute(
            "INSERT INTO races VALUES (?,?,?,?,?,?,?)",
            ("RIKSTOTO:X1_NR_2026-10-30:1", "2026-10-30", None,
             "Jarlsberg/Romme", 1, "2026-10-30T15:00:00+00:00", "trot"),
        )
    r = run(path)
    assert r["summary"]["races_total"] == 2
    assert r["summary"]["single_track_candidates"] == 1
    assert r["summary"]["unresolved_composite_or_unlocated_refs"] == 1
    assert r["single_track_is_physical_race_proven"] is False
    assert r["unresolved_references_retained_in_denominator"] is True
    bad = next(x for x in r["races"] if x["race_id"].startswith("RIKSTOTO:X1_"))
    assert bad["race_identity_kind"] == "UNRESOLVED_COMPOSITE_OR_UNLOCATED"
    assert bad["terminal_status"] == "BLOCKED"
    assert sum(v["races_total"] for v in r["country_days"].values()) == 2


def test_composite_track_not_mislabeled_single_track_when_country_present():
    assert audit.identity_kind("RIKSTOTO:S3_NR_2026-10-30:4", "SE",
                               "Romme/Axevalla") == "UNRESOLVED_COMPOSITE_OR_UNLOCATED"
    assert audit.identity_kind("RIKSTOTO:S3_NR_2026-10-30:4", "SE",
                               "Romme") == "SINGLE_TRACK_CANDIDATE"
    assert audit.identity_kind("RIKSTOTO:X1_NR_2026-10-30:4", "SE",
                               "Romme") == "UNRESOLVED_COMPOSITE_OR_UNLOCATED"
