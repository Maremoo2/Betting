"""Full race intelligence mathematical/regression admission tests (NO BET)."""
from __future__ import annotations

import copy
import math

import pytest

from hbi.full_race_intelligence import _dutch_simulation, analyze_race


def original_field():
    return {
        "physical_race_id":"RIKSTOTO:S2_NR_2026-11-06:4",
        "round_name":"FARJESTAD_V64", "leg":1,
        "start_utc":"2026-11-06T18:30:00+00:00",
        "model_run_id":"original-authentic-run",
        "model_frozen_at_utc":"2026-11-06T18:13:45+00:00",
        "full_field_win_verified":True,
        "pit_certified":False,
        "runners":[
            {
                "selection_id":str(n), "horse_name":name,
                "scratched":False, "identity_attested":False,
                "p_win_frozen":p, "win_odds_raw":odd,
                "win_observed_at_utc":"2026-11-06T18:13:10+00:00",
                "collective_share":v, "lifetime_starts":27,
                "lifetime_wins":4,
            }
            for n,name,p,odd,v in [
                (1,"Favourite",.2,3.0,.5),
                (2,"Challenger A",.3,4.0,.3),
                (3,"Challenger B",.5,5.0,.2),
            ]
        ],
    }


def test_original_full_field_model_and_market_separated():
    result = analyze_race(original_field(),decision_time_utc="2026-11-06T18:15:00+00:00")
    assert result["full_field_model_valid"] is True
    assert result["p_win_sum"] == pytest.approx(1.)
    assert result["win_full_field_verified"] is True
    assert result["win_favourite"]["selection_id"] == "1"
    assert result["collective_favourite_separate"]["selection_id"] == "1"
    assert result["anti_favourite"]["p_favourite_loses"] == pytest.approx(.8)
    assert result["best_single_win_research_only"]["selection_id"] == "3"
    assert result["decision"] == "NOT_EXECUTABLE"
    assert result["bet_authority"] is False
    assert result["v85_system_ev"] == "NOT_ESTABLISHED"
    assert all(x["decision"] == "NOT_EXECUTABLE" for x in result["runners"])
    assert all(x["historical_factors"]["recent_5_starts"] == "MISSING"
               for x in result["runners"])


def test_dutch_net_for_every_winner_and_probability_total_loss():
    result = analyze_race(original_field(),decision_time_utc="2026-11-06T18:15:00+00:00")
    scenario = next(x for x in result["dutching_scenarios"]
                    if x["name"] == "TOP_2_CHALLENGERS_BY_FROZEN_P")
    assert scenario["status"] == "ARITHMETIC_RESEARCH_ONLY"
    assert sum(x["stake_nok_hypothetical"] for x in scenario["stakes"]) == pytest.approx(100.)
    assert scenario["probability_any_selected_wins"] == pytest.approx(.8)
    assert scenario["probability_total_loss"] == pytest.approx(.2)
    outcomes = {x["selection_id"]:x for x in scenario["net_if_each_active_horse_wins_nok"]}
    assert set(outcomes) == {"1","2","3"}
    assert outcomes["1"]["net_if_wins"] == -100
    assert abs(outcomes["2"]["net_if_wins"]-outcomes["3"]["net_if_wins"]) <= .1
    expected = math.fsum(
        x["probability"] * x["net_if_wins"] for x in outcomes.values()
    )
    assert expected == pytest.approx(scenario["ev_nok_hypothetical"])
    assert scenario["actual_provider_minimum_and_rounding"] == "UNVERIFIED"
    assert scenario["bet_authority"] is False


def test_partial_market_not_called_complete_or_executable():
    race = original_field()
    race["runners"][2]["win_odds_raw"] = None
    race["full_field_win_verified"] = False
    result = analyze_race(race,decision_time_utc="2026-11-06T18:15:00+00:00")
    assert result["win_full_field_verified"] is False
    assert result["win_favourite"] is None
    assert result["win_quoted_leader_provisional"]["selection_id"] == "1"
    scenario = result["dutching_scenarios"][0]
    assert scenario["status"] == "NOT_CALCULABLE"
    assert scenario["reason"] == "SET_HAS_UNQUOTED_OR_INVALID_WIN_ODDS"
    assert "FULL_FIELD_WIN_MARKET_UNVERIFIED" in result["hardgate_blockers"]


def test_future_market_quote_is_excluded_from_model_edge():
    race = original_field()
    race["runners"][2]["win_observed_at_utc"] = "2026-11-06T18:29:00+00:00"
    result = analyze_race(race,decision_time_utc="2026-11-06T18:15:00+00:00")
    assert result["win_full_field_verified"] is False
    assert result["runners"][2]["win_odds_raw"] is None
    assert result["runners"][2]["research_ev_roi_arithmetic"] is None
    assert "WIN_SOURCE_AFTER_ANALYSIS_CUTOFF" in result["runners"][2]["blockers"]


def test_model_recorded_after_start_never_promoted():
    race = original_field()
    race["model_frozen_at_utc"] = "2026-11-06T18:31:00+00:00"
    result = analyze_race(race,decision_time_utc="2026-11-06T18:32:00+00:00")
    assert result["full_field_model_valid"] is False
    assert result["p_win_sum"] is None
    assert all(x["p_win"] is None for x in result["runners"])
    assert "FROZEN_MODEL_CLOCK_NOT_ATTESTED" in result["hardgate_blockers"]
    assert "RACE_ALREADY_STARTED_AT_ANALYSIS_TIME" in result["hardgate_blockers"]


def test_wrong_full_field_probability_mass_is_not_renormalized():
    race = original_field()
    race["runners"][0]["p_win_frozen"] = .3
    result = analyze_race(race,decision_time_utc="2026-11-06T18:15:00+00:00")
    assert result["full_field_model_valid"] is False
    assert all(x["p_win"] is None for x in result["runners"])
    assert result["dutching_scenarios"] == []


def test_colliding_numbers_fail_closed():
    race = original_field()
    race["runners"][1]["selection_id"] = "1"
    with pytest.raises(ValueError,match="DUPLICATE_OR_EMPTY_PHYSICAL_FIELD"):
        analyze_race(race,decision_time_utc="2026-11-06T18:15:00+00:00")


def test_model_without_real_original_clock_not_full_field():
    race = original_field()
    race.pop("model_frozen_at_utc")
    result = analyze_race(race,decision_time_utc="2026-11-06T18:15:00+00:00")
    assert result["full_field_model_valid"] is False
    assert result["bet_authority"] is False


def test_stakes_round_never_invented_as_provider_minimum():
    race = original_field()
    result = analyze_race(race,decision_time_utc="2026-11-06T18:15:00+00:00")
    for case in result["dutching_scenarios"]:
        if case["status"] == "ARITHMETIC_RESEARCH_ONLY":
            assert case["actual_provider_minimum_and_rounding"] == "UNVERIFIED"
            assert case["decision"] == "NOT_EXECUTABLE"


def test_invalid_simulation_unit_refused():
    field = analyze_race(original_field(),decision_time_utc="2026-11-06T18:15:00+00:00")
    with pytest.raises(ValueError,match="DUTCH_BUDGET_NOT_MULTIPLE"):
        _dutch_simulation("arbitrary",field["runners"][1:],
                          field["runners"],budget=100.01,quantum=.02)
