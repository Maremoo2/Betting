import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.observatory import build_research_observatory
from hbi.providers.rikstoto import FetchResult, RikstotoClient
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


class ResultClient(RikstotoClient):
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


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race(
        {
            "race_id": "r1",
            "race_date": "2026-09-27",
            "country": "SE",
            "track": "Mantorp",
            "race_no": 1,
            "start_time_utc": "2026-09-27T18:00:00+00:00",
            "discipline": "trot",
            "distance_m": 2140,
            "start_method": "auto",
            "race_class": None,
            "created_at_utc": "2026-09-27T08:00:00+00:00",
        }
    )
    store.upsert_provider_race_ref(
        provider="rikstoto",
        provider_raceday_key="MP_NR_2026-09-27",
        race_number=1,
        race_id="r1",
        provider_track_code="MP",
        provider_start_time_raw="2026-09-27T20:00:00",
        discovered_at=datetime(2026, 9, 27, 8, 0, tzinfo=UTC),
    )
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    for selection, odds, wins in (("1", 2.5, 8), ("2", 4.0, 3)):
        store.insert_provider_market_snapshot(
            snapshot_id=f"m-{selection}",
            provider="rikstoto",
            race_id="r1",
            product="V",
            selection_key=selection,
            observed_at=observed,
            provider_updated_at=observed,
            source_uri="https://example/win",
            odds_decimal=odds,
        )
        store.insert_runner_fundamental_snapshot(
            {
                "snapshot_id": f"f-{selection}",
                "race_id": "r1",
                "selection_id": selection,
                "observed_at_utc": observed.isoformat(),
                "feature_as_of_utc": observed.isoformat(),
                "source_uri": "https://example/atg",
                "horse_name": f"Horse {selection}",
                "history_total_starts": 20,
                "history_total_wins": wins,
                "scratched": 0,
                "data_quality": "FULL_FIELD_HISTORY_ATG",
                "enrichment_provider": "atg",
                "identity_match_method": "REGISTRATION_ID",
                "identity_match_confidence": 1.0,
                "full_field_history_complete": 1,
            }
        )

    store.insert_fundamental_model_run(
        {
            "run_id": "fr1",
            "race_id": "r1",
            "model_name": "market_free_empirical_win",
            "model_version": "FUNDAMENTAL_CHAMPION_V1_1",
            "role": "SHADOW_CHAMPION",
            "feature_set_version": "TEST",
            "created_at_utc": observed.isoformat(),
            "feature_as_of_utc": observed.isoformat(),
            "field_size": 2,
            "active_runners": 2,
            "known_history_runners": 2,
            "history_coverage": 1.0,
            "shadow_eligible": 1,
            "status": "OK",
            "reason": None,
            "probabilities_json": json.dumps({"1": 0.70, "2": 0.30}),
            "metadata_json": "{}",
        }
    )
    store.insert_shadow_decision_run(
        {
            "decision_run_id": "dr1",
            "race_id": "r1",
            "provider_raceday_key": "MP_NR_2026-09-27",
            "product": "V",
            "created_at_utc": observed.isoformat(),
            "race_start_time_utc": "2026-09-27T18:00:00+00:00",
            "decision_status": "SHADOW_BET",
            "reason": None,
            "shadow_model_version": "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL",
            "fundamental_model_version": "FUNDAMENTAL_CHAMPION_V1_1",
            "source_market_observed_at_utc": observed.isoformat(),
            "target_minutes_to_start": 4.0,
            "actual_minutes_to_start": 4.0,
            "execution_latency_seconds": 0.0,
            "field_size": 2,
            "fundamental_probabilities_json": json.dumps({"1": 0.70, "2": 0.30}),
            "market_probabilities_json": json.dumps({"1": 0.60, "2": 0.40}),
            "combined_probabilities_json": json.dumps({"1": 0.65, "2": 0.35}),
            "model_market_conflict_score": 10.0,
            "ticket_count": 1,
        }
    )
    store.create_shadow_ticket(
        {
            "ticket_id": "t1",
            "dedupe_key": "d1",
            "created_at_utc": observed.isoformat(),
            "decision_time_utc": observed.isoformat(),
            "race_id": "r1",
            "provider": "rikstoto",
            "provider_raceday_key": "MP_NR_2026-09-27",
            "product": "V",
            "decision": "BET",
            "status": "SHADOW_BET",
            "selections_json": '["1"]',
            "stake_nok": 25.0,
            "number_of_rows": 1,
            "available_price": 3.0,
            "model_version": "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL",
            "target_minutes_to_start": 4.0,
            "actual_minutes_to_start": 4.0,
            "execution_latency_seconds": 0.0,
        }
    )
    store.settle_shadow_ticket(
        ticket_id="t1",
        settled_at=datetime(2026, 9, 27, 19, 0, tzinfo=UTC),
        gross_return_nok=62.5,
        net_pnl_nok=37.5,
        settlement_source_uri="https://example/results",
        result={"won": True, "finish": 1},
        closing_price=2.5,
        clv=0.18,
    )
    store.record_provider_fetch(
        fetch_id="fetch-ok",
        provider="rikstoto",
        endpoint="https://example/win",
        fetched_at=observed,
        success=True,
        status_code=200,
        latency_ms=10.0,
        error_message=None,
    )
    return store


def test_observatory_materializes_outcome_metrics_and_health(tmp_path):
    store = _store(tmp_path)
    report = build_research_observatory(
        store,
        datetime(2026, 9, 27, tzinfo=UTC).date(),
        client=ResultClient(),
        generated_at=datetime(2026, 9, 28, 0, 30, tzinfo=UTC),
    )

    assert report["outcome_collection"]["persisted"] == 1
    assert report["race_evaluations_materialized"] == 1

    health = report["data_health"]
    assert health["races"] == 1
    assert health["races_with_starts"] == 1
    assert health["races_with_v_odds"] == 1
    assert health["known_history_runner_coverage"] == pytest.approx(1.0)
    assert health["atg_runner_coverage"] == pytest.approx(1.0)
    assert health["decision_status_counts"]["SHADOW_BET"] == 1
    assert health["t4_latency_seconds_median"] == pytest.approx(0.0)
    assert health["settlement_rate"] == pytest.approx(1.0)

    evaluation = report["evaluation"]
    assert evaluation["race_evaluations_n"] == 1
    assert evaluation["fundamental_n"] == 1
    assert evaluation["market_n"] == 1
    assert evaluation["combined_n"] == 1
    assert evaluation["combined_log_loss"] < evaluation["market_log_loss"]
    assert evaluation["combined_brier"] < evaluation["market_brier"]
    assert evaluation["roi"] == pytest.approx(1.5)
    assert evaluation["mean_clv"] == pytest.approx(0.18)
    assert evaluation["positive_clv_rate"] == pytest.approx(1.0)
    assert evaluation["calibration"]["combined"]

    assert store.count("outcomes") == 1
    assert store.count("race_research_evaluations") == 1
    assert store.count("research_daily_reports") == 1
    assert "Small-N results" in report["markdown"]


def test_observatory_is_idempotent_for_same_race_and_model(tmp_path):
    store = _store(tmp_path)
    report_date = datetime(2026, 9, 27, tzinfo=UTC).date()
    generated = datetime(2026, 9, 28, 0, 30, tzinfo=UTC)

    build_research_observatory(
        store,
        report_date,
        client=ResultClient(),
        generated_at=generated,
    )
    build_research_observatory(
        store,
        report_date,
        client=ResultClient(),
        generated_at=generated,
    )

    assert store.count("race_research_evaluations") == 1
    assert store.count("research_daily_reports") == 1
