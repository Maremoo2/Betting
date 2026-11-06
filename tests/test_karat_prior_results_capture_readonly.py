"""Karat past-race evidence must be verified independently of discovery hints."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

M=runpy.run_path(str(Path(__file__).resolve().parents[1] /
                     "scripts/karat_prior_results_capture_readonly.py"))


def past_race():
    return {
        "races":[{
            "id":"2026-06-06_7_8", "date":"2026-06-06",
            "status":"results", "name":"Prior race", "number":8,
            "track":{"name":"Mantorp"},"distance":2640,"startMethod":"auto",
            "prize":"source-prize","terms":"source-class",
            "starts":[
                {"number":10,"postPosition":10,
                 "horse":{"id":767446,"name":"Karat River",
                          "statistics":{"life":{"starts":999,"placement":{"1":999}}}},
                 "driver":{"firstName":"Johan","lastName":"Untersteiner"},
                 "result":{"finishOrder":6,"place":6,"galloped":True,
                           "kilometreTime":{"minutes":1,"seconds":14,"tenths":4}}},
                {"number":2,"horse":{"id":101,"name":"Opponent",
                                     "money":100000},
                 "result":{"finishOrder":1,"place":1}},
            ],
        }],
    }


def test_exact_past_result_available_without_current_statistics_leak():
    result=M["_first_party_result"](past_race(),"2026-06-06_7_8")
    assert result["result"]["finishOrder"] == 6
    assert result["result"]["galloped"] is True
    assert result["race_date"] == "2026-06-06"
    assert result["start_number"] == 10
    assert len(result["opponents_in_same_historic_race"])==2
    assert result["opponent_actual_previous_strength"] is None
    assert result["opponent_strength_blocker"]=="NO_PIT_PAST_RESULTS_FOR_ALL_OPPONENTS"
    assert "statistics" not in result["opponents_in_same_historic_race"][0]
    assert result["opponents_in_same_historic_race"][0][
        "do_not_use_current_horse_statistics_as_pit"
    ] is True


def test_historical_result_without_exact_id_cannot_be_accepted():
    source=past_race()
    source["races"][0]["starts"][0]["horse"]["id"]=999
    with pytest.raises(ValueError,match="KARAT_HORSE_ID_NOT_UNIQUELY_VERIFIED"):
        M["_first_party_result"](source,"2026-06-06_7_8")


def test_result_not_final_fails_closed():
    source=past_race()
    source["races"][0]["status"]="upcoming"
    with pytest.raises(ValueError,match="HISTORICAL_RESULT_NOT_FINAL"):
        M["_first_party_result"](source,"2026-06-06_7_8")


def test_historic_source_missing_actual_result_cannot_be_filled_by_stats():
    source=past_race()
    source["races"][0]["starts"][0].pop("result")
    with pytest.raises(TypeError,match="HISTORIC_KARAT_RESULT_MISSING"):
        M["_first_party_result"](source,"2026-06-06_7_8")


def test_historical_search_bounded_and_only_prestart_events():
    assert len(M["CANDIDATES"])<=10
    assert M["MAX_REQUESTS"]==20
    assert all(x[0]<M["TARGET_RACE_START"][:10] for x in M["CANDIDATES"])
    assert M["HORSE_ID"]==767446
