"""Historical DEV009 benchmark and forward-only V2 result-scoring acceptance."""
from __future__ import annotations

import pytest

from hbi.challenger_v2_validation import (
    dev009_benchmark,
    score_existing_challenger,
)

RACE="RIKSTOTO:S1_NR_2026-11-07:5"


def report():
    return {
        "schema":"CHALLENGER_V2_SHADOW_ORIGINAL_REPORT_V1",
        "bet_authority":False,
        "calibration_status":"UNVALIDATED_NOT_FITTED",
        "status":"MODEL_RESEARCH_ONLY_NO_PIT_OR_IDENTITY_AUTHORITY",
        "race_id":RACE,
        "start_at_utc":"2026-11-07T14:00:00+00:00",
        "as_of_utc":"2026-11-07T07:00:00+00:00",
        "runners":[
            {"selection_id":"1","scratched":False,"p_win_challenger":.25},
            {"selection_id":"2","scratched":False,"p_win_challenger":.75},
        ],
    }


def score(**changes):
    return score_existing_challenger(
        changes.get("model",report()),
        model_original_artifact_created_at_utc=changes.get(
            "artifact","2026-11-07T07:01:00+00:00"),
        official_result=changes.get("result",{
            "source_verified_full_field":True,
            "same_physical_race_id":RACE,
            "winner_selection_id":"2",
        }),
        result_observed_at_utc=changes.get(
            "result_time","2026-11-07T14:30:00+00:00"),
        validation_holdout_start_utc=changes.get(
            "holdout","2026-11-07T00:00:00+00:00"),
    )


def test_independently_stored_shadow_can_be_scored_only_after_outcome():
    result=score()
    assert result["status"]=="PROSPECTIVE_SHADOW_EVALUABLE_NOT_BET"
    assert result["winner_p"]==.75
    assert result["multiclass_brier"]==pytest.approx(.125)
    assert result["bet_authority"] is False
    assert result["pit_certified"] is False


@pytest.mark.parametrize("case,reason",[
    ({"artifact":"2026-11-07T14:01:00+00:00"},
     "MODEL_NOT_INDEPENDENTLY_ARCHIVED_BEFORE_START_OR_NOT_HOLDOUT"),
    ({"result_time":"2026-11-07T13:59:00+00:00"},
     "MODEL_NOT_INDEPENDENTLY_ARCHIVED_BEFORE_START_OR_NOT_HOLDOUT"),
    ({"holdout":"2026-11-07T12:00:00+00:00"},
     "MODEL_NOT_INDEPENDENTLY_ARCHIVED_BEFORE_START_OR_NOT_HOLDOUT"),
    ({"result":{"source_verified_full_field":False,
                "same_physical_race_id":RACE,"winner_selection_id":"2"}},
     "OFFICIAL_RESULT_NOT_INDEPENDENTLY_ATTESTED"),
])
def test_no_model_outcome_or_holdout_lookahead(case,reason):
    assert score(**case)["reason"]==reason


def test_partial_v2_field_never_evaluable():
    model=report()
    model["runners"][1]["p_win_challenger"]=None
    assert score(model=model)["reason"]=="NO_VALID_FROZEN_V2_FULL_FIELD"


def test_research_dev009_not_mislabelled_as_challenger_benchmark():
    index={
        "schema":"DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1",
        "bet_authority":False,"pit_certification_performed":False,
        "status":"INCOMPLETE_ORIGINAL_COVERAGE",
        "counts":{"paired_champion_core004":2},
        "calibration":{"status":"SPARSE_BINS_NO_CALIBRATION_CLAIM"},
        "records":[
            {"race_id":f"RIKSTOTO:S1_NR_2026-11-03:{i}",
             "status":"EVALUABLE_RESEARCH_ONLY",
             "score":{
                 "champion_log_loss":2.0,
                 "market_log_loss":1.8,
                 "champion_multiclass_brier":.7,
                 "market_multiclass_brier":.65,
             }}
            for i in (1,2)
        ],
    }
    result=dev009_benchmark(index,bootstrap_replicates=200)
    assert result["paired_champion_market_count"]==2
    assert result["paired_differences"]["log_loss"][
        "champion_minus_market"]==pytest.approx(.2)
    assert result["v2_independent_outcome_score_count"]==0
    assert result["v2_vs_market"]=="NOT_ESTABLISHED"
    assert result["bet_authority"] is False


def test_rejects_untrusted_or_pit_claim_in_existing_dev009():
    with pytest.raises(ValueError,match="DEV009_SOURCE_INDEX_NOT_AUTHENTIC"):
        dev009_benchmark({
            "schema":"DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1",
            "bet_authority":True,"pit_certification_performed":False,
        })


def test_no_double_count_duplicate_historical_race():
    index={
        "schema":"DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1",
        "bet_authority":False,"pit_certification_performed":False,
        "records":[
            {"race_id":"a","status":"EVALUABLE_RESEARCH_ONLY",
             "score":{
                 "champion_log_loss":1., "market_log_loss":1.,
                 "champion_multiclass_brier":.5,"market_multiclass_brier":.5,
             }},
            {"race_id":"a","status":"EVALUABLE_RESEARCH_ONLY",
             "score":{
                 "champion_log_loss":1., "market_log_loss":1.,
                 "champion_multiclass_brier":.5,"market_multiclass_brier":.5,
             }},
        ],
    }
    with pytest.raises(ValueError,match="DUPLICATE_PHYSICAL_RACE"):
        dev009_benchmark(index)
