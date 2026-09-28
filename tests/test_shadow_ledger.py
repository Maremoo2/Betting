import json
from datetime import UTC, datetime
from pathlib import Path

from hbi.nightly import build_daily_report, settle_open_shadow_tickets
from hbi.providers.rikstoto import FetchResult, RikstotoClient
from hbi.shadow import ShadowPolicy, run_win_shadow_decision
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race(
        {
            "race_id": "r1",
            "race_date": "2026-09-27",
            "country": "NO",
            "track": "Bjerke",
            "race_no": 1,
            "start_time_utc": "2026-09-27T18:00:00+00:00",
            "discipline": "trot",
            "distance_m": 2100,
            "start_method": "auto",
            "race_class": None,
            "created_at_utc": "2026-09-27T10:00:00+00:00",
        }
    )
    return store


def _market(store):
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    for selection, odds in (("1", 3.0), ("2", 2.0)):
        store.insert_provider_market_snapshot(
            snapshot_id=f"s-{selection}",
            provider="rikstoto",
            race_id="r1",
            product="V",
            selection_key=selection,
            observed_at=observed,
            provider_updated_at=observed,
            source_uri="https://example/win",
            odds_decimal=odds,
        )


def test_shadow_decision_requires_fundamental_probabilities(tmp_path):
    store = _store(tmp_path)
    _market(store)
    result = run_win_shadow_decision(
        store,
        race_id="r1",
        provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=datetime(2026, 9, 27, 18, 0, tzinfo=UTC),
        decision_time=datetime(2026, 9, 27, 17, 56, tzinfo=UTC),
    )
    assert result.status == "NOT_EXECUTABLE"
    rows = store.fetch_table("shadow_tickets")
    assert rows[0]["reject_reason"] == "NO_FUNDAMENTAL_PREDICTIONS"
    decisions = store.fetch_table("shadow_decision_runs")
    assert len(decisions) == 1
    assert decisions[0]["decision_status"] == "NOT_EXECUTABLE"
    assert decisions[0]["reason"] == "NO_FUNDAMENTAL_PREDICTIONS"


def test_shadow_decision_can_create_frozen_paper_bet(tmp_path):
    store = _store(tmp_path)
    _market(store)
    created = datetime(2026, 9, 27, 17, 50, tzinfo=UTC)
    for selection, probability in (("1", 0.7), ("2", 0.3)):
        store.insert_prediction(
            prediction_id=f"p-{selection}",
            race_id="r1",
            selection_id=selection,
            created_at=created,
            model_name="fundamental",
            model_version="test",
            layer="FUNDAMENTAL",
            probability=probability,
            feature_as_of=created,
        )

    result = run_win_shadow_decision(
        store,
        race_id="r1",
        provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=datetime(2026, 9, 27, 18, 0, tzinfo=UTC),
        decision_time=datetime(2026, 9, 27, 17, 56, tzinfo=UTC),
        policy=ShadowPolicy(material_conflict_threshold=100.0),
    )
    assert result.status == "SHADOW_BET"
    ticket = store.fetch_table("shadow_tickets")[0]
    assert ticket["product"] == "V"
    assert ticket["status"] == "SHADOW_BET"
    assert json.loads(ticket["selections_json"]) == ["1"]
    assert ticket["stake_nok"] == 25.0
    decision = store.fetch_table("shadow_decision_runs")[0]
    assert decision["decision_status"] == "SHADOW_BET"
    assert decision["ticket_count"] == 1
    assert json.loads(decision["fundamental_probabilities_json"]) == {
        "1": 0.7,
        "2": 0.3,
    }
    assert json.loads(decision["market_probabilities_json"])
    assert json.loads(decision["combined_probabilities_json"])


class SettlementClient(RikstotoClient):
    def raceday_results(self, raceday_key):
        return FetchResult(
            url="https://example/raceresults",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": {
                    "finalOdds": {
                        "winOdds": {"1": {"1": {"odds": 2.5}}},
                        "placeOdds": {},
                    }
                }
            },
        )

    def complete_results(self, raceday_key, race_number):
        return FetchResult(
            url="https://example/complete",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": {
                    "results": [
                        {"startNumber": 1, "place": 1},
                        {"startNumber": 2, "place": 2},
                    ]
                }
            },
        )


def test_nightly_settlement_and_report(tmp_path):
    store = _store(tmp_path)
    _market(store)
    now = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    store.create_shadow_ticket(
        {
            "ticket_id": "t1",
            "dedupe_key": "d1",
            "created_at_utc": now.isoformat(),
            "decision_time_utc": now.isoformat(),
            "race_id": "r1",
            "provider": "rikstoto",
            "provider_raceday_key": "BJ_NR_2026-09-27",
            "product": "V",
            "decision": "BET",
            "status": "SHADOW_BET",
            "selections_json": '["1"]',
            "stake_nok": 25.0,
            "number_of_rows": 1,
            "available_price": 3.0,
            "model_version": "test",
        }
    )
    settled = settle_open_shadow_tickets(
        store,
        client=SettlementClient(),
        settled_at=datetime(2026, 9, 27, 20, 0, tzinfo=UTC),
    )
    assert settled.settled == 1
    ticket = store.fetch_table("shadow_tickets")[0]
    assert ticket["gross_return_nok"] == 62.5
    assert ticket["net_pnl_nok"] == 37.5
    assert ticket["clv"] > 0

    report = build_daily_report(store, datetime(2026, 9, 27, tzinfo=UTC).date())
    assert report["tickets"] == 1
    assert report["winning_tickets"] == 1
    assert report["net_pnl_nok"] == 37.5



def test_first_t4_decision_is_frozen_across_repeated_watcher_runs(tmp_path):
    store = _store(tmp_path)
    _market(store)
    race_start = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)
    first_time = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    first = run_win_shadow_decision(
        store,
        race_id="r1",
        provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=race_start,
        decision_time=first_time,
    )
    assert first.status == "NOT_EXECUTABLE"

    for selection, probability in (("1", 0.7), ("2", 0.3)):
        store.insert_prediction(
            prediction_id=f"late-{selection}",
            race_id="r1",
            selection_id=selection,
            created_at=datetime(2026, 9, 27, 17, 57, tzinfo=UTC),
            model_name="fundamental",
            model_version="late",
            layer="FUNDAMENTAL",
            probability=probability,
            feature_as_of=datetime(2026, 9, 27, 17, 57, tzinfo=UTC),
        )

    second = run_win_shadow_decision(
        store,
        race_id="r1",
        provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=race_start,
        decision_time=datetime(2026, 9, 27, 17, 58, tzinfo=UTC),
    )

    assert second.status == "NOT_EXECUTABLE"
    assert store.count("shadow_decision_runs") == 1
    assert store.count("shadow_tickets") == 1



def test_shadow_decision_fails_closed_when_market_snapshot_is_after_decision(tmp_path):
    store = _store(tmp_path)
    observed = datetime(2026, 9, 27, 17, 57, tzinfo=UTC)
    for selection, odds in (("1", 3.0), ("2", 2.0)):
        store.insert_provider_market_snapshot(
            snapshot_id=f"future-{selection}",
            provider="rikstoto",
            race_id="r1",
            product="V",
            selection_key=selection,
            observed_at=observed,
            provider_updated_at=observed,
            source_uri="https://example/win",
            odds_decimal=odds,
        )
    created = datetime(2026, 9, 27, 17, 50, tzinfo=UTC)
    for selection, probability in (("1", 0.7), ("2", 0.3)):
        store.insert_prediction(
            prediction_id=f"future-p-{selection}",
            race_id="r1",
            selection_id=selection,
            created_at=created,
            model_name="fundamental",
            model_version="test",
            layer="FUNDAMENTAL",
            probability=probability,
            feature_as_of=created,
        )

    result = run_win_shadow_decision(
        store,
        race_id="r1",
        provider_raceday_key="BJ_NR_2026-09-27",
        race_start_at=datetime(2026, 9, 27, 18, 0, tzinfo=UTC),
        decision_time=datetime(2026, 9, 27, 17, 56, tzinfo=UTC),
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == "MARKET_AFTER_DECISION"
    decision = store.fetch_table("shadow_decision_runs")[0]
    assert decision["reason"] == "MARKET_AFTER_DECISION"
