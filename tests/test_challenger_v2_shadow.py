"""Challenger V2 shadow and historic PIT original fail-closed regressions."""
from __future__ import annotations

import hashlib
import json
import math

import pytest

from hbi.challenger_v2_shadow import (
    MODEL_VERSION,
    CandidatePolicy,
    estimate_shadow,
)
from hbi.historical_intelligence_v2 import (
    history_coverage,
    verified_past_race,
)

START = "2026-11-07T14:00:00+00:00"
NOW = "2026-11-07T07:05:00+00:00"
OBS = "2026-11-06T18:25:00+00:00"
SHA = "f" * 64


def rows() -> list[dict]:
    return [
        {"selection_id":sid,"scratched":False,
         "atg_horse_id":id_,"historical_source_sha256":SHA,
         "historical_observed_at_utc":OBS,
         "career_starts":starts,"career_wins":wins,
         "season_starts":ss,"season_wins":sw,
         "independent_registration_attested":False}
        for sid,id_,starts,wins,ss,sw in [
            ("1",101,30,9,10,4),("3",103,45,8,9,1),
            ("7",107,70,14,11,3),
        ]
    ]


def run(data=None, **kw):
    return estimate_shadow(
        race_id="RIKSTOTO:S1_NR_2026-11-07:5",
        start_at_utc=kw.get("start",START),
        as_of_utc=kw.get("asof",NOW),
        runners=rows() if data is None else data,
    )


def test_v2_separate_market_free_normalized_full_field_and_zero_bet():
    result=run()
    assert result["model_version"]==MODEL_VERSION
    assert result["role"]=="SHADOW_CHALLENGER"
    assert result["status"]=="MODEL_RESEARCH_ONLY_NO_PIT_OR_IDENTITY_AUTHORITY"
    assert result["p_win_sum"]==pytest.approx(1.)
    assert len([x for x in result["runners"] if x["p_win_challenger"]])==3
    assert all(x["decision"]=="NOT_EXECUTABLE" for x in result["runners"])
    assert result["bet_authority"] is False
    assert result["pit_certified"] is False
    assert "INDEPENDENT_REGISTRATION_NOT_ATTESTED" in result["blockers"]
    assert result["model_uses_market_features"] is False
    assert result["model_uses_result_features"] is False
    assert result["training_cutoff"]=="NOT_FITTED_OR_TUNED"


def test_no_odds_betting_share_or_outcome_can_affect_model():
    a=rows()
    b=rows()
    for x in b:
        x["win_odds"]=125.0
        x["V85_share"]=.99
        x["result"]="WINNER"
        x["closing_odds"]=999.
    x,y=run(a),run(b)
    assert x["model_run_sha256"]==y["model_run_sha256"]
    assert [z["p_win_challenger"] for z in x["runners"]]==[
        z["p_win_challenger"] for z in y["runners"]]


def test_new_season_residual_zero_for_all_zero_season_starts():
    data=rows()
    for x in data:
        x["season_starts"]=x["season_wins"]=0
    result=run(data)
    p={x["selection_id"]:x["p_win_challenger"] for x in result["runners"]}
    weights={
        x["selection_id"]:(x["career_wins"]+6/3)/(x["career_starts"]+6)
        for x in data
    }
    total=math.fsum(weights.values())
    for k,w in weights.items():
        assert p[k]==pytest.approx(w/total)


@pytest.mark.parametrize("change,expected",[
    ({"atg_horse_id":None},"PROVIDER_PERMANENT_HORSE_ID_MISSING"),
    ({"historical_source_sha256":None},"ORIGINAL_HISTORICAL_SOURCE_SHA_MISSING"),
    ({"historical_observed_at_utc":"2026-11-07T16:00:00+00:00"},
     "SOURCE_OBSERVED_AFTER_FEATURE_CUTOFF"),
    ({"season_wins":55},"SEASON_CAREER_COUNTS_MISSING_OR_IMPOSSIBLE"),
    ({"season_starts":None},"SEASON_CAREER_COUNTS_MISSING_OR_IMPOSSIBLE"),
])
def test_missing_provenance_or_years_blocks_entire_field(change,expected):
    data=rows()
    data[0].update(change)
    result=run(data)
    assert result["status"]=="BLOCKED_SHADOW_NO_COMPLETE_FIELD"
    assert expected in result["blockers"]
    assert result["p_win_sum"] is None
    assert all(x["p_win_challenger"] is None for x in result["runners"])


def test_no_model_after_start_or_duplicate_selection():
    assert "PREDICTION_NOT_BEFORE_RACE" in run(asof=START)["blockers"]
    duplicate=rows()
    duplicate[1]["selection_id"]="1"
    assert "DUPLICATE_SELECTION_ID" in run(duplicate)["blockers"]


def test_frozen_fixed_illustrative_weights_reject_invalid():
    assert CandidatePolicy().season_residual_weight==.25
    with pytest.raises(ValueError,match="SHADOW_CANDIDATE_POLICY_INVALID"):
        CandidatePolicy(season_residual_weight=1.4)


def _past_payload() -> bytes:
    return json.dumps({"races":[{
        "id":"2026-06-06_5_8","status":"results",
        "date":"2026-06-06","track":{"name":"Mantorp"},
        "distance":2140,"startMethod":"auto","terms":"Gulddivisionen",
        "prize":{"1":500000},
        "starts":[
            {"number":7,"postPosition":7,
             "horse":{"id":767446,"name":"Karat River",
                      "statistics":{"life":{"starts":9999}}},
             "result":{"place":6,"time":"1.14,4"}},
            {"number":10,"postPosition":10,
             "horse":{"id":123456,"name":"Other"},
             "result":{"place":5,"time":"1.14,2"}},
        ],
    }]}).encode()


def test_hist_result_original_retains_all_opponents_without_future_stats():
    raw=_past_payload()
    result=verified_past_race(
        raw,claimed_sha256=hashlib.sha256(raw).hexdigest(),
        claimed_atg_race_id="2026-06-06_5_8",
        source_uri="https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-06-06_5_8",
        observed_at_utc="2026-11-07T07:00:00+00:00",
        source_published_at_utc=None,
        model_cutoff_utc=NOW,
        current_race_start_utc=START,
        horse_id=767446,
    )
    assert result["status"]=="VERIFIED"
    assert result["fields"]["placing"]==6
    assert result["fields"]["race_class"]=="Gulddivisionen"
    assert len(result["opponents"])==2
    assert result["opponent_prior_strength_at_that_race"]=="MISSING"
    assert result["dynamic_horse_statistics_ignored"] is True
    assert result["provider_publication_attested"] is False
    assert result["bet_authority"] is False


def test_source_observed_only_after_forecast_can_never_backfill():
    raw=_past_payload()
    result=verified_past_race(
        raw,claimed_sha256=hashlib.sha256(raw).hexdigest(),
        claimed_atg_race_id="2026-06-06_5_8",
        source_uri="https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-06-06_5_8",
        observed_at_utc="2026-11-07T19:00:00+00:00",
        source_published_at_utc=None,model_cutoff_utc=NOW,
        current_race_start_utc=START,horse_id=767446,
    )
    assert result["status"]=="NOT_AVAILABLE_AT_PIT"
    assert result["fields"]["placing"]=="MISSING"
    assert result["opponents"]==[]


def test_history_9_result_hints_do_not_establish_last_5_or_10():
    partial=[
        {"horse_id":767446,"status":"VERIFIED",
         "source_uri":f"https://atg/prev/{i}",
         "source_observed_at_utc":OBS,
         "source_published_at_utc":None}
        for i in range(9)
    ]
    result=history_coverage(
        partial,current_horse_id=767446,current_model_cutoff_utc=NOW,
        original_history_index_complete=False,
    )
    assert result["status"]=="PARTIAL"
    assert result["verified_historical_results"]==9
    assert result["last_5"]=="MISSING"
    assert result["last_10"]=="MISSING"
    assert result["last_20"]=="MISSING"
    assert result["source_published_at_attested"] is False


def test_missing_permanent_horse_id_blocks_history():
    assert history_coverage(
        [],current_horse_id=None,current_model_cutoff_utc=NOW,
    )["status"]=="IDENTITY_UNRESOLVED"
