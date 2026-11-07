"""DATA-005 historical form adapter: source, identity and point-in-time gates."""
from __future__ import annotations

import pytest

from hbi.data005_form_adapter import form_candidate

DIGEST="3c43c7df700504befa1c82435848b33ced6085006401d0d87594075e6fe028c0"
RACE="RIKSTOTO:S1_NR_2026-11-07:5"
DATES=("2026-08-07","2026-08-16","2026-09-06","2026-10-05","2026-10-28")


def entries():
    return [
        {"horse":"WARHOL","selection_id":"3","original_sha256":DIGEST,
         "historical_date":stamp,"historical_track_code":track,
         "historical_race_number":i+1,"raw_placing_code":str(place),
         "raw_km_time_token":"14,8a","historical_distance_m":2140,
         "gallop_marked_in_time":False,"disqualification_marked":False,
         "driver_abbrev":"Sve He","original_line_sha256":f"{i+1:064x}",
         "source_field_evidence_status":"PDF_TEXT_LAYER_PARTIAL",
         "independent_official_result_verified":False}
        for i,(stamp,track,place) in enumerate(zip(
            DATES,("Ös","D","D","Sä","B"),(7,1,4,4,2),strict=True
        ))
    ]


def research(**overrides):
    params={
        "race_id":RACE,"horse_selection_id":"3","horse_name":"WARHOL",
        "race_start_utc":"2026-11-07T14:00:00+00:00",
        "model_cutoff_utc":"2026-11-07T13:56:00+00:00",
        "source_original_pdf_sha256":DIGEST,
        "source_observed_at_utc":"2026-11-07T06:18:23+00:00",
        "source_published_at_utc":None,
        "national_registration":None,
        "independent_identity_attested":False,
        "original_entries":entries(),
    }
    params.update(overrides)
    return form_candidate(**params)


def test_five_rows_research_only_not_challenger_feature():
    result=research()
    assert result["schema"]=="DATA005_FORM_RESEARCH_ADAPTER_V1"
    assert result["dated_rows"]==5
    assert result["status"]=="PARTIAL"
    assert result["last_5_full_verified"] is False
    assert len(result["historical_rows"])==5
    assert result["previous_10"]=="MISSING"
    assert result["previous_20"]=="MISSING"
    assert result["model_feature_authority"] is False
    assert result["source_pit_certified"] is False
    assert result["bet_authority"] is False
    assert result["model_invocations"]==0
    assert "INDEPENDENT_PERMANENT_HORSE_ID_UNATTESTED" in result["blockers"]


def test_after_cutoff_source_cannot_be_promoted():
    result=research(
        source_observed_at_utc="2026-11-07T13:57:00+00:00",
    )
    assert result["status"]=="NOT_AVAILABLE_AT_PIT"
    assert result["model_feature_authority"] is False
    assert "HISTORICAL_SOURCE_OBSERVED_AFTER_FEATURE_CUTOFF" in result["blockers"]


@pytest.mark.parametrize("bad",["x"*64,"bad_sha",""])
def test_original_digest_never_guessed(bad):
    with pytest.raises(ValueError,match="DATA005_PHYSICAL_RACE_SOURCE_OR_SELECTION_INVALID"):
        research(source_original_pdf_sha256=bad)


def test_source_row_sha_cannot_cross_to_another_pdf():
    rows=entries()
    rows[1]["original_sha256"]="f"*64
    with pytest.raises(ValueError,match="DATA005_SOURCE_HORSE_IDENTITY_OR_SHA_MISMATCH"):
        research(original_entries=rows)


def test_name_and_selection_must_match_original():
    rows=entries()
    rows[2]["horse"]="DIFFERENT"
    with pytest.raises(ValueError,match="DATA005_SOURCE_HORSE_IDENTITY_OR_SHA_MISMATCH"):
        research(original_entries=rows)
    rows=entries()
    rows[0]["selection_id"]="4"
    with pytest.raises(ValueError,match="DATA005_SOURCE_HORSE_IDENTITY_OR_SHA_MISMATCH"):
        research(original_entries=rows)


def test_future_historic_race_never_backfilled():
    rows=entries()
    rows[4]["historical_date"]="2026-11-07"
    with pytest.raises(ValueError,match="DATA005_HISTORIC_EVENT_NOT_BEFORE_TARGET"):
        research(original_entries=rows)


def test_duplicate_past_race_identity_refused():
    rows=entries()
    rows[2]["historical_date"]=rows[1]["historical_date"]
    rows[2]["historical_race_number"]=rows[1]["historical_race_number"]
    rows[2]["historical_track_code"]=rows[1]["historical_track_code"]
    with pytest.raises(ValueError,match="DATA005_DUPLICATE_HISTORIC_START_ID"):
        research(original_entries=rows)


def test_even_full_official_paperwork_never_activates_model_automatically():
    rows=entries()
    for row in rows:
        row["source_field_evidence_status"]="MANUALLY_VERIFIED_ORIGINAL"
        row["independent_official_result_verified"]=True
    result=research(
        national_registration="5781234567",
        independent_identity_attested=True,
        source_published_at_utc="2026-11-07T06:15:00+00:00",
        original_entries=rows,
    )
    assert result["status"]=="READY_FOR_RESEARCH_BUT_NOT_MODEL_ENABLED"
    assert result["last_5_full_verified"] is True
    assert result["model_feature_authority"] is False
    assert result["source_pit_certified"] is False
    assert result["bet_authority"] is False


def test_short_history_stays_partial_not_full_last_five():
    rows=entries()[:4]
    result=research(original_entries=rows)
    assert result["dated_rows"]==4
    assert "NO_CHRONOLOGICALLY_COMPLETE_FIVE_SOURCE_ROWS" in result["blockers"]
    assert result["last_5_full_verified"] is False


def test_history_must_be_ascending_without_reordering_or_lookahead():
    rows=entries()
    rows[1],rows[2]=rows[2],rows[1]
    result=research(original_entries=rows)
    assert result["status"]=="PARTIAL"
    assert "NO_CHRONOLOGICALLY_COMPLETE_FIVE_SOURCE_ROWS" in result["blockers"]
    assert result["model_feature_authority"] is False


def test_future_historical_result_relative_to_source_observation_is_rejected():
    result_rows=entries()
    # A PDF supposedly observed on 25 Oct cannot already contain the 28 Oct result.
    with pytest.raises(
        ValueError,match="DATA005_HISTORICAL_EVENT_NOT_BEFORE_SOURCE_OBSERVATION"
    ):
        research(
            original_entries=result_rows,
            source_observed_at_utc="2026-10-25T06:18:23+00:00",
        )


def test_each_original_history_line_requires_source_sha():
    result_rows=entries()
    result_rows[0]["original_line_sha256"]="MISSING"
    with pytest.raises(ValueError,match="DATA005_ORIGINAL_HISTORY_LINE_SHA_MISSING"):
        research(original_entries=result_rows)
