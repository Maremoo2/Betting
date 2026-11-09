"""DATA-005: immutable documentary corroboration cannot become verified ID/PIT.

This test validates the **claim schema only**. It does NOT assert that the
independent DNT catalog was SHA archived or that a live DNT registry record
was queried. Source publication and source URL are research provenance.
"""
from __future__ import annotations

import json
from pathlib import Path


def evidence() -> dict:
    path = (Path(__file__).resolve().parents[1]
            / "research/data005/identity_documentary_2026-11-08.json")
    return json.loads(path.read_bytes())


def test_dnt_independent_documentary_matched_exact_ueln_but_no_verified_id():
    info = evidence()
    assert info["schema"] == "DATA_005_INDEPENDENT_DOCUMENTARY_IDENTITY_RESEARCH_V1"
    assert info["independent_dnt_catalog_corrob_count"] == 2
    assert info["verified_permanent_registry_identity_count"] == 0
    assert info["cohort_klosterskogen_active"] == 78
    assert info["cohort_active_runners"] == 180
    assert info["no_name_only_match"] is True
    assert info["source_corpus"]["dnt_catalog_raw_sha256"] is None
    assert info["source_corpus"]["dnt_registry_record_sha256"] is None
    assert info["source_corpus"]["independent_dnt_registry_lookup_performed"] is False
    assert {x["ueln"] for x in info["evidence"]} == {
        "578001020230323", "578001020230009",
    }
    assert {x["horse_name"] for x in info["evidence"]} == {
        "Holter Bork", "Tysvær Tjerand",
    }
    for row in info["evidence"]:
        assert row["target_physical_race_id"] == "RIKSTOTO:KL_NR_2026-11-07:2"
        assert row["identity_status"] == "PROVISIONAL_MATCH"
        assert row["cross_source_documentary_match"] == "STRONG_EXACT_UELN_MATCH"
        assert row["ueln"].startswith("57800102023")
        assert len(row["ueln"]) == 15
        assert row["sex"] == "H"
        assert row["birth_year"] == 2023
        assert row["pedigree"]["sire"]
        assert row["pedigree"]["dam"]
        assert row["rikstoto_original_exact_registration_match"] is True
        assert row["dnt_catalog_exact_registration_match"] is True
        assert row["authoritative_registry_crosscheck"] == "MISSING"
        assert row["verified_id"] is False
        assert row["model_feature_authority"] is False
        assert row["pit_certified_for_historic_performance"] is False
        assert row["bet_authority"] is False


def test_hardgates_are_not_changed_by_documentary_match():
    info = evidence()
    assert info["champion_unchanged"] is True
    assert info["challenger_v2_shadow_only"] is True
    assert info["pit_hardgates_unchanged"] is True
    assert info["auto_bet"] is False
    assert info["bet_authority"] is False
    assert info["auto_merge"] is False
    assert info["not_a_change_to_previous_900_line_outcome_validation"] is True
