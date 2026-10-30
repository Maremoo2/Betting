"""CORE-004: safety and data provenance tests for an UNFITTED research candidate."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from hbi.core_multifactor_research import (
    ExperimentalCoefficients,
    _standardize,
    analyze_card,
    analyze_multifactor,
    main,
)
from hbi.race_core_review import historical_win_prior

RACE = "CORE004:TEST:1"
START = "2026-10-30T15:00:00+00:00"
CUTOFF = "2026-10-30T14:56:00+00:00"
T0 = "2026-10-30T14:50:00+00:00"


def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    create table races(race_id text,race_date text,country text,track text,race_no int,
      start_time_utc text,discipline text,distance_m int,start_method text,race_class text);
    create table runners(race_id text,selection_id text,horse_name text,post_position int,
      driver_or_jockey text,trainer text,scratched int);
    create table runner_fundamental_snapshots(race_id text,selection_id text,
      observed_at_utc text,feature_as_of_utc text,full_field_history_complete int,
      source_uri text,scratched int,history_total_starts int,history_total_wins int,
      history_total_seconds int,history_total_thirds int,history_total_earnings real,
      age int);
    create table provider_market_snapshots(race_id text,selection_key text,product text,
      observed_at_utc text,odds_decimal real);
    """)
    conn.execute("insert into races values (?,?,?,?,?,?,?,?,?,?)",
                 (RACE, "2026-10-30", "SE", "Synthetic", 1, START, "trot", 2140, "Auto", None))
    horses = [("1", "A", 12, 3, 4, 1, 1000.), ("2", "B", 24, 5, 4, 3, 2400.),
              ("3", "C", 8, 0, 2, 2, 400.)]
    for sid, name, starts, wins, seconds, thirds, earnings in horses:
        conn.execute("insert into runners values (?,?,?,?,?,?,?)",(RACE,sid,name,int(sid),"Driver","Trainer",0))
        conn.execute("insert into runner_fundamental_snapshots values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (RACE,sid,T0,T0,1,"atg:test",0,starts,wins,seconds,thirds,earnings,5))
        conn.execute("insert into provider_market_snapshots values (?,?,?,?,?)",
                     (RACE,sid,"V",T0,5.5))
    conn.commit()
    return conn


def report(conn=None, *, as_of=CUTOFF):
    conn = conn or db()
    return analyze_multifactor(conn, race_id=RACE, as_of=as_of)


def test_candidate_is_complete_and_marked_unfitted():
    r=report()
    assert r["status"] == "CANDIDATE_READY_UNCALIBRATED"
    assert r["authority"] == "RESEARCH_ONLY_NO_EV_NO_WATCH_NO_BET"
    assert r["bet_count"] == 0 and r["watch_count"] == 0
    assert not r["ev_calculated"] and not r["roster_point_in_time_attested"]
    assert len(r["runners"]) == 3
    assert sum(x["p_candidate"] for x in r["runners"]) == pytest.approx(1)
    assert sum(x["p_champion"] for x in r["runners"]) == pytest.approx(1)
    assert any(abs(x["candidate_minus_champion"]) > 1e-4 for x in r["runners"])


def test_champion_parity_exact():
    c=db()
    r=report(c)
    baseline,_=historical_win_prior([dict(x) for x in c.execute("select * from runner_fundamental_snapshots")])
    assert {x["selection_id"]:x["p_champion"] for x in r["runners"]} == baseline


def test_prices_are_not_used_in_any_probability():
    c=db()
    first=report(c)
    c.execute("update provider_market_snapshots set odds_decimal=9999")
    c.execute("insert into provider_market_snapshots values (?,?,?,?,?)",(RACE,"4","V",T0,2.0))
    assert first == report(c)


def test_do_not_use_future_snapshot_or_old_complete_cohort():
    c=db()
    c.execute("insert into runner_fundamental_snapshots select race_id,selection_id,?,?,?,?,?,history_total_starts,history_total_wins,history_total_seconds,history_total_thirds,history_total_earnings,age from runner_fundamental_snapshots where selection_id='1' limit 1",
              ("2026-10-30T14:55:00+00:00","2026-10-30T14:55:00+00:00",1,"atg:test",0))
    assert "FUNDAMENTAL_FIELD_MISMATCH" in report(c)["blocked_reasons"]
    assert report(c,as_of="2026-10-30T14:53:00+00:00")["status"] == "CANDIDATE_READY_UNCALIBRATED"


def test_future_only_blocks():
    c=db()
    c.execute("update runner_fundamental_snapshots set observed_at_utc='2026-10-30T15:00:01+00:00'")
    assert "NO_FUNDAMENTAL_COHORT_AS_OF" in report(c)["blocked_reasons"]


def test_timezone_offsets_cannot_hide_future_cohort():
    c=db()
    c.execute("update runner_fundamental_snapshots set observed_at_utc='2026-10-30T16:55:00+02:00' where selection_id='1'")
    assert "FUNDAMENTAL_FIELD_MISMATCH" in report(c)["blocked_reasons"]


def test_future_feature_time_blocks_even_if_observed_in_time():
    c=db()
    c.execute("update runner_fundamental_snapshots set feature_as_of_utc='2026-10-30T15:02:00+00:00' where selection_id='1'")
    assert "FEATURE_AS_OF_AFTER_CUTOFF" in report(c)["blocked_reasons"]


def test_invalid_source_timestamp_fails_closed():
    c=db()
    c.execute("update runner_fundamental_snapshots set observed_at_utc='unknown' where selection_id='1'")
    assert "INVALID_OBSERVATION_TIMESTAMP" in report(c)["blocked_reasons"]


def test_at_or_after_start_blocks():
    assert "NOT_BEFORE_RECORDED_START" in report(as_of=START)["blocked_reasons"]


@pytest.mark.parametrize("column,value,code", [
    ("history_total_seconds", None, "MISSING_OR_INVALID_MULTIFACTOR_INPUT"),
    ("history_total_thirds", -1, "MISSING_OR_INVALID_MULTIFACTOR_INPUT"),
    ("history_total_earnings", None, "MISSING_OR_INVALID_MULTIFACTOR_INPUT"),
    ("history_total_earnings", -7.0, "MISSING_OR_INVALID_MULTIFACTOR_INPUT"),
    ("history_total_earnings", float("inf"), "MISSING_OR_INVALID_MULTIFACTOR_INPUT"),
    ("history_total_wins", 90, "IMPOSSIBLE_FINISH_COUNTS"),
    ("history_total_seconds", 40, "IMPOSSIBLE_FINISH_COUNTS"),
    ("source_uri", None, "UNVERIFIED_FULL_FIELD_HISTORY"),
    ("full_field_history_complete", 0, "UNVERIFIED_FULL_FIELD_HISTORY"),
])
def test_invalid_features_fail_closed(column,value,code):
    c=db()
    c.execute(f"update runner_fundamental_snapshots set {column}=? where selection_id='2'",(value,))
    assert code in report(c)["blocked_reasons"]
    assert all(x["p_candidate"] is None for x in report(c)["runners"])


def test_duplicate_runner_blocks():
    c=db();c.execute("insert into runners select * from runners where selection_id='2'")
    assert "DUPLICATE_SELECTIONS" in report(c)["blocked_reasons"]


def test_missing_runner_blocks():
    c=db();c.execute("delete from runners where selection_id='2'")
    assert "FUNDAMENTAL_FIELD_MISMATCH" in report(c)["blocked_reasons"]


def test_scratch_mismatch_blocks():
    c=db();c.execute("update runners set scratched=1 where selection_id='1'")
    assert "SCRATCH_OR_IDENTITY_MISMATCH" in report(c)["blocked_reasons"]


def test_scratched_horse_excluded_when_consistent():
    c=db();c.execute("update runners set scratched=1 where selection_id='3'")
    c.execute("update runner_fundamental_snapshots set scratched=1 where selection_id='3'")
    r=report(c)
    assert r["status"]=="CANDIDATE_READY_UNCALIBRATED"
    assert r["runners"][2]["p_candidate"] is None
    assert len([x for x in r["runners"] if x["p_candidate"] is not None])==2
    assert all(x["scored_source_features"]["career_top3_rate_smoothed"] <= 1.0
               for x in r["runners"] if x["p_candidate"] is not None)


def test_no_earnings_across_races_and_invalid_coefficients():
    c=db()
    c.execute("update runner_fundamental_snapshots set history_total_earnings=history_total_earnings*1000000")
    p1=report(c)
    assert p1["status"]=="CANDIDATE_READY_UNCALIBRATED"
    with pytest.raises(ValueError):ExperimentalCoefficients(top3=1.)
    with pytest.raises(ValueError):ExperimentalCoefficients(earnings_per_start=float("nan"))


def test_zero_coefficients_exactly_equal_champion():
    c=db()
    x=analyze_multifactor(c,race_id=RACE,as_of=CUTOFF,
                          weights=ExperimentalCoefficients(0.,0.,0.))
    for item in x["runners"]:
        assert item["p_candidate"]==pytest.approx(item["p_champion"])


def test_standardize_constant_values_does_not_divide_by_zero():
    assert _standardize({"a":2.0,"b":2.0})=={"a":0.0,"b":0.0}


def test_date_scoped_card_and_missing_inputs():
    c=db()
    x=analyze_card(c,date="2026-10-30",track="Synthetic")
    assert x["races_known"]==1 and x["candidate_ready"]==1 and x["candidate_blocked"]==0
    assert analyze_card(c,date="2026-10-31")["races_known"]==0
    with pytest.raises(ValueError):analyze_card(c,date="2026-10-30",cutoff_minutes=-4)


def test_preview_context_not_scored():
    c=db()
    first=report(c)
    c.execute("update races set distance_m=1000,start_method='Volt'")
    c.execute("update runners set driver_or_jockey='Nobody',post_position=40")
    next_=report(c)
    assert [x["p_candidate"] for x in first["runners"]] == [x["p_candidate"] for x in next_["runners"]]
    assert "recent_5_starts_form" in first["unavailable_or_unscored_factors"]


def test_real_ostersund_card_read_only_when_supplied():
    path=Path(os.environ.get("HBI_CORE004_ARCHIVE", "reports/core_004_live_fixture.sqlite"))
    if not path.is_file():
        pytest.skip("Optional actual archived CORE-003 pilot fixture absent")
    c=sqlite3.connect(f"file:{path}?mode=ro",uri=True);c.row_factory=sqlite3.Row
    try:
        d=analyze_card(c,date="2026-10-30",track="Östersund")
    finally:c.close()
    assert d["races_known"]==8
    assert d["candidate_ready"]==3
    assert d["candidate_blocked"]==5
    assert all(not item["p_candidate_sum"] or abs(item["p_candidate_sum"]-1)<1e-12 for item in d["races"])
    assert all(item["bet_count"]==0 for item in d["races"])


def test_cli_real_fixture_when_supplied(tmp_path):
    path=Path(os.environ.get("HBI_CORE004_ARCHIVE", "reports/core_004_live_fixture.sqlite"))
    if not path.is_file():
        pytest.skip("Optional actual archived CORE-003 pilot fixture absent")
    dest=tmp_path/"out.json"
    assert main(["--db",str(path),"--date","2026-10-30","--track","Östersund","--out",str(dest)])==0
    assert json.loads(dest.read_text())["candidate_ready"]==3


def _source_clock_fixture(conn, *, source_at=T0, source_start="2026-10-30T14:54:00+00:00"):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS provider_payloads (
      provider TEXT, category TEXT, provider_raceday_key TEXT,
      race_number INTEGER, observed_at_utc TEXT, payload_json TEXT
    );
    CREATE TABLE IF NOT EXISTS provider_race_refs (
      race_id TEXT, provider_raceday_key TEXT
    );
    """)
    conn.execute("INSERT INTO provider_payloads VALUES (?,?,?,?,?,?)", (
        "atg", "FULL_FIELD_ONLY_V1", RACE, 1, source_at,
        json.dumps({"race_start_utc": source_start, "passed": True, "runners": []}),
    ))


def test_core004_rejects_canonical_t4_when_original_source_clock_was_earlier():
    c = db()
    _source_clock_fixture(c)
    r = report(c)
    assert "ASOF_AFTER_EARLIEST_SOURCE_T4" in r["blocked_reasons"]
    assert r["earliest_archived_source_start_utc"] == "2026-10-30T14:54:00+00:00"
    assert r["source_start_clock_conflict_seconds"] == 360
    assert r["status"] == "BLOCKED"
    assert all(x["p_candidate"] is None for x in r["runners"])
    assert r["bet_count"] == 0
    # This is not a workaround: only earlier-than-T4 input may remain provisional.
    early = report(c, as_of=T0)
    assert "ASOF_AFTER_EARLIEST_SOURCE_T4" not in early["blocked_reasons"]
    assert early["roster_point_in_time_attested"] is False


def test_source_start_revision_cannot_reopen_core004_t4_gate():
    c = db()
    _source_clock_fixture(c)
    _source_clock_fixture(
        c, source_at="2026-10-30T14:55:00+00:00",
        source_start="2026-10-30T14:59:00+00:00",
    )
    r = report(c)
    assert "ASOF_AFTER_EARLIEST_SOURCE_T4" in r["blocked_reasons"]
    assert r["earliest_archived_source_start_utc"] == "2026-10-30T14:54:00+00:00"


def test_invalid_atg_source_clock_blocks_even_if_factors_are_complete():
    c = db()
    _source_clock_fixture(c, source_start="not-a-time")
    r = report(c)
    assert "INVALID_ARCHIVED_SOURCE_CLOCK" in r["blocked_reasons"]
    assert r["status"] == "BLOCKED"
