"""DATA-006: 5 official DNT race rows, strict chronological research-only match."""
from __future__ import annotations

from copy import deepcopy

import pytest

from hbi.data006_historic_crosswalk import compare_historic_five

SHA = "020eedb5bfb3f5cea0e2d55bac6622a01f3fe51a473c8a33bd9ecaa93c1f222a"
START = "2026-11-07T18:00:00+00:00"
OBS = "2026-11-07T06:18:01+00:00"
DATES = ("2026-06-04","2026-07-03","2026-08-07","2026-09-15","2026-10-16")
RACE_NUMS = (8,1,7,4,7)
NUMS = (3,4,5,3,4)
PLACES = ("DG","0","5","5","5")
PACEs = (None,"31,4","33,9","34,8 g","35,2 g")
GALLOPS = (True,False,False,True,True)


def original():
    return [{
        "horse_name":"Tysvær Tjerand","selection_id":"9",
        "ueln":"578001020230009","source_pdf_sha256":SHA,
        "date":DATES[i],"track_code":"J","race_number":RACE_NUMS[i],
        "start_number":NUMS[i],"distance_m":2100,
        "placing_code":PLACES[i],"km_time":PACEs[i],
        "gallop":GALLOPS[i],"disqualified":i==0,
    } for i in range(5)]


def official():
    return [{
        "horse_name":"Tysvær Tjerand",
        "official_result_url":f"https://old.travsport.no/Sport/Resultater/Jarlsberg-Travbane/?date={d.replace('-','')}",
        "date":DATES[i],"track_code":"J","race_number":RACE_NUMS[i],
        "start_number":NUMS[i],"distance_m":2100,
        "placing_code":PLACES[i],"km_time":PACEs[i],
        "gallop":GALLOPS[i],"disqualified":i==0,
        "official_original_sha256":None,
        "official_original_sha_attested":False,
        "official_observed_at_utc":"2026-11-08T17:29:41+00:00",
        "official_published_at_utc":None,
    } for i,d in enumerate(DATES)]


def score(prior=None, dnt=None, **changes):
    args={
        "source_race_id":"RIKSTOTO:KL_NR_2026-11-07:2",
        "source_runner_selection":"9",
        "source_horse_name":"Tysvær Tjerand",
        "source_ueln":"578001020230009",
        "source_pdf_sha256":SHA,"source_observed_at_utc":OBS,
        "target_start_utc":START,
        "target_cutoff_utc":"2026-11-07T17:56:00+00:00",
        "original_rows":original() if prior is None else prior,
        "official_rows":official() if dnt is None else dnt,
        "national_registry_independently_verified":False,
    }
    args.update(changes)
    return compare_historic_five(**args)


def test_five_official_rows_match_but_not_pit_and_not_model_enabled():
    r=score()
    assert r["official_historic_rows_matched"]==5
    assert r["status"]=="VERIFIED_RETROSPECTIVE_OFFICIAL_ROWS_ONLY"
    assert [z["placing_code"] for z in r["rows"]]==["DG","0","5","5","5"]
    assert r["pit_certified"] is False
    assert r["feature_ready"] is False
    assert r["bet_authority"] is False
    assert r["champion_unchanged"] is True
    assert all(z["model_feature_authority"] is False for z in r["rows"])


@pytest.mark.parametrize("key,bad",[
    ("placing_code","1"),("km_time","14,4"),("gallop",True),
    ("disqualified",True),("distance_m",1640),
])
def test_mismatch_is_never_silently_reconciled(key,bad):
    o=official()
    o[1][key]=bad
    with pytest.raises(ValueError,match="DATA006_OFFICIAL_RESULT_FIELD_CONFLICT"):
        score(dnt=o)


def test_future_web_result_never_backdated():
    result=score()
    assert all(z["publication_pre_cutoff_proved"] is False for z in result["rows"])
    assert all(z["source_pre_cutoff_observed"] is False for z in result["rows"])


def test_mismatched_race_or_runner_identity_blocks():
    o=official()
    o[2]["race_number"]=12
    with pytest.raises(ValueError,match="DATA006_OFFICIAL_SOURCE_EVENT_MISMATCH"):
        score(dnt=o)
    p=original()
    p[2]["ueln"]="578001020230323"
    with pytest.raises(ValueError,match="DATA006_ORIGINAL_HORSE_OR_SHA_MISMATCH"):
        score(prior=p)


def test_duplicate_source_row_fails():
    p=original()
    p[3]=deepcopy(p[2])
    with pytest.raises(ValueError,match="DATA006_DUPLICATE_PRIOR_EVENT"):
        score(prior=p)


def test_wrong_source_clock_and_pdf_hash_fail():
    with pytest.raises(ValueError,match="DATA006_PRESTART_FROZEN_SOURCE_CLOCK_INVALID"):
        score(source_observed_at_utc="2026-11-07T18:10:00+00:00")
    with pytest.raises(ValueError,match="DATA006_ORIGINAL_RACE_ID_OR_REGISTRATION_INVALID"):
        score(source_pdf_sha256="UNKNOWN")


def test_five_vs_four_not_eligible():
    with pytest.raises(ValueError,match="DATA006_NEEDS_FIVE_SOURCE"):
        score(prior=original()[:4])


def test_after_race_result_observation_cannot_be_pit_even_if_other_flags_asserted():
    o=official()
    for r in o:
        r["official_original_sha256"]="a"*64
        r["official_original_sha_attested"]=True
        r["official_published_at_utc"]="2026-11-07T07:00:00+00:00"
    result=score(dnt=o,national_registry_independently_verified=True)
    assert result["pit_certified"] is False
    assert result["feature_ready"] is False
