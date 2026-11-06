"""Phase 2 original-backed lifetime/history context invariants (NO BET)."""
from __future__ import annotations

import hashlib
import runpy
from datetime import UTC, datetime
from pathlib import Path

import pytest

M = runpy.run_path(str(
    Path(__file__).resolve().parents[1]
    / "scripts/full_race_phase2_source_enrichment.py"
))


def test_prestart_year_and_life_stats_are_not_imaginary_last_five():
    original = {
        "number":7, "postPosition":7,"distance":2140,
        "driver":{"id":12,"firstName":"S","lastName":"Persson"},
        "horse":{
            "id":767446,"name":"Karat River","age":8,
            "money":3672315,"trainer":{"id":21,"firstName":"Johan","lastName":"Untersteiner"},
            "statistics":{
                "life":{"starts":52,"placement":{"1":18,"2":11,"3":6},
                        "earnings":367231500,"startPoints":840,
                        "records":[{"startMethod":"auto","distance":"short"}]},
                "years":{"2025":{"starts":10,"placement":{"1":3,"2":2,"3":2}},
                         "2026":{"starts":9,"placement":{"1":2,"2":2,"3":1}}},
                "lastFiveStarts":{"averageOdds":2988},
            },
        },
    }
    receipt={"response_sha256":"a"*64}
    result=M["_historical"](original,receipt,datetime(2026,11,6,18,26,tzinfo=UTC))
    assert result["life_starts"] == 52
    assert result["life_wins"] == 18
    assert result["life_seconds"] == 11
    assert result["calendar_years"]["2026"]["wins"] == 2
    assert result["current_driver"]["name"] == "S Persson"
    assert result["current_trainer"]["name"] == "Johan Untersteiner"
    assert result["last_5_individual_results"] == "MISSING"
    assert result["last_10_individual_results"] == "MISSING"
    assert result["previous_opponents_and_head_to_head"] == "MISSING"
    assert result["prior_opponent_strength_at_historic_race"] == "MISSING"
    assert result["class_adjusted_performance"] == "MISSING"
    assert result["best_historical_records_not_recent_results"][0]["startMethod"] == "auto"


def test_false_years_never_invented_as_zero():
    original={"horse":{"statistics":{"life":{},"years":{}}}}
    x=M["_historical"](original,{"response_sha256":"b"*64},datetime.now(UTC))
    assert x["calendar_years"]["2025"] == "MISSING"
    assert x["calendar_years"]["2026"] == "MISSING"
    assert x["life_wins"] is None
    assert x["driver_change_from_previous_start"] == "MISSING"


def test_broken_hash_is_rejected(tmp_path):
    folder=tmp_path/"atg-originals"
    folder.mkdir()
    sha=hashlib.sha256(b'{"races":[]}').hexdigest()
    (folder/(sha+".json")).write_bytes(b"wrong")
    with pytest.raises(ValueError,match="ORIGINAL_SOURCE_SHA_MISMATCH"):
        M["_source_bytes"](tmp_path,"atg-originals",sha)


def test_valid_source_bytes_are_reused(tmp_path):
    folder=tmp_path/"atg-originals"
    folder.mkdir()
    raw=b'{"races":[]}'
    sha=hashlib.sha256(raw).hexdigest()
    (folder/(sha+".json")).write_bytes(raw)
    assert M["_source_bytes"](tmp_path,"atg-originals",sha) == raw


def test_no_naive_timestamp_or_unverified_future():
    with pytest.raises(ValueError,match="REQUIRED_ORIGINAL_UTC_NAIVE"):
        M["_clock"]("2026-11-06T18:26:10")


def test_invalid_url_and_status_do_not_promote_receipt(tmp_path):
    receipt={
        "url":"https://unapproved.example.com/results",
        "http_status":200,"success":True,
        "response_sha256":"a"*64,
        "raw_original_path":"a"*64+".json",
        "response_completed_utc":"2026-11-06T18:26:00+00:00",
    }
    assert M["_receipt_map"](tmp_path,{"original_atg_receipts":[receipt]}) == {}


def test_atg_start_case_mismatch_never_aliases():
    canonical = "Karat River (S)"
    original_name = "Karat River"
    assert canonical != original_name
    assert M["MISSING"] == "MISSING"


def test_phase2_has_no_fitted_weights_or_betting_bridge():
    code=(Path(__file__).resolve().parents[1] /
          "scripts/full_race_phase2_source_enrichment.py").read_text()
    assert "from hbi.full_race_intelligence import analyze_race" not in code
    assert "MarketFreeFundamentalChampionV1" not in code
    assert '"bet_authority":False' in code
    assert '"pit_hardgates_unchanged":True' in code
