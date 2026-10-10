import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_provider_capability import NOW, START, setup_collector

from hbi.fundamental import run_and_persist_fundamental
from hbi.october_tracker import SHADOW, _economics, build_tracker
from hbi.shadow import run_win_shadow_decision
from hbi.storage import SQLiteStore
from hbi.tracker_view import render_tracker

OBSERVED = datetime(2026, 10, 2, 10, tzinfo=UTC)
SCHEMA = Path(__file__).parents[1] / "db/schema.sql"


def cohort(tmp_path):
    store, collector, race, kw = setup_collector(tmp_path)
    collector.collect_fundamentals(**kw)
    collector.collect_market(**kw)
    run_and_persist_fundamental(store, race_id=race.race_id, created_at=NOW)
    run_win_shadow_decision(store, race_id=race.race_id, provider_raceday_key=race.raceday_key,
                            race_start_at=START, decision_time=NOW)
    run = store.fetch_table("shadow_decision_runs")[0]
    store.upsert_decision_provenance({
        "decision_run_id": run["decision_run_id"], "market_odds_json": '{"1":3,"2":2}',
        "decision_policy_json": '{"minimum_edge":0.05,"safety_margin":0.05}',
        "combination_policy_json": '{"fundamental_weight":0.5,"market_weight":0.5}',
        "code_sha": "frozen-code", "governance_hash": "frozen-governance",
        "recorded_at_utc": NOW.isoformat(),
    })
    with store.connect() as c:
        c.execute("INSERT INTO outcomes (race_id,winner_selection_id,settled_at_utc) VALUES (?,?,?)",
                  (race.race_id, "1", "2026-09-27T18:10:00+00:00"))
        dump = "\n".join(c.iterdump()).replace("2026-09-27", "2026-10-01")
    path = tmp_path / "october.sqlite"
    with sqlite3.connect(path) as c:
        c.executescript(dump)
    return SQLiteStore(path)


def test_missing_db_and_naive_time_fail_without_creating_state(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        build_tracker(path, now=OBSERVED)
    assert not path.exists()
    with pytest.raises(ValueError, match="aware"):
        build_tracker(path, now=datetime(2026, 10, 2, tzinfo=UTC).replace(tzinfo=None))  # rejection test


def test_paired_cohort_is_read_only_and_lifetime_is_not_start_history(tmp_path):
    store = cohort(tmp_path)
    before = store.path.read_bytes()
    report = build_tracker(store.path, now=OBSERVED)
    assert store.path.read_bytes() == before
    assert report["qualified_races_n"] == report["paired_races_n"] == 1
    assert report["history"]["starts"] is None
    assert report["history"]["status"] == "NOT_IMPLEMENTED"
    assert report["paired_evaluation"] == report["evaluation_by_country"]["SE"]
    p = json.loads(store.fetch_table("shadow_decision_runs")[0]["fundamental_probabilities_json"])
    assert report["paired_evaluation"]["layers"]["fundamental"]["log_loss"] == pytest.approx(
        -math.log(p["1"]))
    assert not report["automatic_promotion"] and not report["real_money_execution"]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("sql", [
    "UPDATE shadow_decision_runs SET combined_probabilities_json='{}'",
    "UPDATE shadow_decision_runs SET fundamental_probabilities_json='{\"1\":0.5,\"2\":0.5}'",
    "UPDATE decision_provenance SET decision_policy_json='not-json'",
    "UPDATE decision_provenance SET code_sha=NULL",
    "UPDATE runner_fundamental_snapshots SET data_quality='FIELD_ONLY'",
    "UPDATE provider_payloads SET payload_json='{}' WHERE category='FULL_FIELD_ONLY_V1'",
])
def test_incomplete_or_unreproducible_cohorts_cannot_inflate_sample(tmp_path, sql):
    store = cohort(tmp_path)
    with store.connect() as c:
        c.execute(sql)
    report = build_tracker(store.path, now=OBSERVED)
    assert report["qualified_races_n"] == report["paired_races_n"] == 0
    assert sum(report["excluded_decisions"].values()) == 1


def test_outcome_from_future_or_before_start_cannot_supply_evidence(tmp_path):
    store = cohort(tmp_path)
    for stamp in ("2026-10-03T10:00:00+00:00", "2026-10-01T17:00:00+00:00"):
        with store.connect() as c:
            c.execute("UPDATE outcomes SET settled_at_utc=?", (stamp,))
        report = build_tracker(store.path, now=OBSERVED)
        assert report["qualified_races_n"] == 1
        assert report["paired_races_n"] == 0


def test_calendar_never_certifies_completion_and_unknown_pnl_is_not_zero(tmp_path):
    store = SQLiteStore(tmp_path / "empty.sqlite")
    store.initialize(SCHEMA)
    report = build_tracker(store.path, now=datetime(2026, 11, 1, tzinfo=UTC))
    assert report["milestones"][0]["status"] == "REVIEW_REQUIRED"
    assert report["milestones"][1]["status"] == "NOT_STARTED"
    assert report["milestones"][3]["status"] == "BLOCKED"
    assert report["economics"]["paper_pnl_nok"] is None
    assert not any(m["status"] == "COMPLETE" for m in report["milestones"])


def test_price_proof_excludes_stale_or_collapsed_price_and_keeps_unknown_clv():
    run = {"decision_run_id": "d", "created_at_utc": "2026-10-01T09:56:00+00:00",
           "source_market_observed_at_utc": "2026-10-01T09:55:00+00:00",
           "race_start_time_utc": "2026-10-01T10:00:00+00:00"}
    qualified = {"r": (run, {"combined": {"1": .5, "2": .5}})}
    provenance = {"d": {"market_odds_json": '{"1":3}',
                         "decision_policy_json": '{"minimum_edge":0.05,"safety_margin":0.05}'}}
    t = {"race_id": "r", "decision": "BET", "product": "V", "model_version": SHADOW,
         "selections_json": '["1"]', "decision_time_utc": run["created_at_utc"],
         "source_snapshot_time_utc": run["source_market_observed_at_utc"],
         "available_price": 3, "status": "SETTLED", "settled_at_utc": "2026-10-01T10:10:00+00:00",
         "stake_nok": 10, "gross_return_nok": 0, "net_pnl_nok": -10,
         "closing_price": None, "clv": None}
    result = _economics([t], qualified, provenance, OBSERVED)
    assert result["paper_pnl_nok"] == -10
    assert result["missing_clv_n"] == 1 and result["mean_clv"] is None
    for changed in ({"available_price": 2},
                    {"source_snapshot_time_utc": "2026-10-01T09:50:00+00:00"}):
        result = _economics([{**t, **changed}], qualified, provenance, OBSERVED)
        assert result["settled_verified_price_n"] == 0
        assert result["excluded"] == {"UNVERIFIED_EXECUTABLE_PRICE": 1}


def test_challenger_has_its_own_forward_clock(tmp_path):
    store = cohort(tmp_path)
    rid = store.fetch_table("races")[0]["race_id"]
    with store.connect() as c:
        c.execute("INSERT INTO challenger_registry VALUES (?,?,?,?,?,?,?,?,?)",
                  ("candidate", "Test", "test-v1", "2026-10-01T19:00:00+00:00",
                   "2026-10-01T16:00:00+00:00", "2026-10-01T17:00:00+00:00", 500,
                   "FORWARD_TESTING", "test only"))
        c.execute("INSERT INTO challenger_forward_events VALUES (?,?,?,?,?,?)",
                  ("candidate", rid, "2026-10-01T18:00:00+00:00",
                   "2026-10-01T18:10:00+00:00", 1, None))
    report = build_tracker(store.path, now=OBSERVED)
    assert report["challengers"][0]["forward_n"] == 0  # Race predates registration.
    assert report["paired_races_n"] == 1


def test_dashboard_cannot_inject_script_from_provider_data(tmp_path):
    store = SQLiteStore(tmp_path / "empty.sqlite")
    store.initialize(SCHEMA)
    report = build_tracker(store.path, now=OBSERVED)
    attack = '</script><script>alert("provider")</script>'
    report["history"]["reason"] = attack
    html = render_tracker(report)
    assert attack not in html
    assert "\\u003c/script>" in html
    assert '<select id="country">' in html
