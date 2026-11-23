"""TEST_ONLY B5 negative coverage; real originals replayed in PR Actions."""
import pytest

from hbi.prewatch004b5_evidence_recovery import assemble, source_window


def sample():
    field = {
        "schema": "PREWATCH004B4_ONE_RACE_FULLFIELD_RESEARCH_V1",
        "bet_authorized": False, "active_with_attested_permanent_identity": 0,
        "active_with_pit_qualified_history": 0,
        "archive_sha256": "a" * 64, "race_id": "R:1",
        "race": {"start_time_utc": "2026-11-23T18:52:00+00:00"},
        "source_run_id": "COLLECTOR", "listed_count": 1,
        "active_count": 1, "active_raw_ge5": 1,
        "runners": [{
            "selection_id": "1", "horse_name": "TEST_ONLY", "scratched": False,
            "identity_status": "IDENTITY_UNRESOLVED", "pit_status": "PIT_UNPROVEN",
            "verified_official_results": 0, "model_eligible": False,
            "pdf_raw_history_rows": 5, "raw_row_sha256": ["b" * 64] * 5,
        }],
    }
    source = {"archive_sha256": "a" * 64,
              "program_pdf_original_sha256": "c" * 64,
              "observed_at_utc": "2026-11-23T08:51:00+00:00"}
    retro = {"evidence_mode": "SOURCE_REPLAYED_NO_2026", "source_observations": 7,
             "unique_horses_for_target": 1, "historical_asof_verified_horses": 0,
             "bet_authority": False}
    availability = {"schema": "M7B2B_GATE_REPORT_V1", "model_eligible": False,
                    "observations": 51,
                    "cutoffs": {"4": {"pdf_pit_verified": 2,
                                      "chain_pit_counts": {"PIT_UNPROVEN": 12}}}}
    return field, source, retro, availability


def test_source_only_pre_cutoff_is_not_historical_pit():
    r = assemble(*sample())
    assert r["source_clock"]["source_captured_before_cutoff"] is True
    assert r["source_clock"]["historical_original_pit_verified"] is False
    assert r["nov23_fullfield_historical_PIT_verified_horses"] == 0
    assert r["field"][0]["pit_verified_prior_starts"] == 0
    assert r["m7b2b_existing_original_research"]["cutoff_evidence"]["4"]["pdf_source_pit_verified_M7B2B_research"] == 2
    assert r["first_genuine_historical_pit_admission"] is False
    assert r["bet_authorized"] is False
    assert assemble(*sample()) == r


def test_capture_after_cutoff_never_pit():
    r = source_window("2026-11-23T18:49:00+00:00", "2026-11-23T18:52:00+00:00")
    assert not r["source_captured_before_cutoff"]
    assert r["historical_original_pit_verified"] is False


def test_missing_timezone_rejected():
    with pytest.raises(ValueError, match="OFFSET_AWARE"):
        source_window("2026-11-23T09:00:00", "2026-11-23T18:52:00+00:00")


@pytest.mark.parametrize("kind", [
    "different_archive", "fake_identity", "fake_pit", "fake_model",
    "fake_official_result", "wrong_count", "retrospective_fabricated",
    "source_ready_without_original",
])
def test_mutations_fail_closed(kind):
    field, source, retro, availability = sample()
    if kind == "different_archive":
        source["archive_sha256"] = "d" * 64
    elif kind == "fake_identity":
        field["runners"][0]["identity_status"] = "ATTESTED"
    elif kind == "fake_pit":
        field["runners"][0]["pit_status"] = "PIT_VERIFIED"
    elif kind == "fake_model":
        field["runners"][0]["model_eligible"] = True
    elif kind == "fake_official_result":
        field["runners"][0]["verified_official_results"] = 1
    elif kind == "wrong_count":
        field["listed_count"] = 2
    elif kind == "retrospective_fabricated":
        retro["evidence_mode"] = "TEST_ONLY"
    elif kind == "source_ready_without_original":
        availability["model_eligible"] = True
    with pytest.raises(ValueError):
        assemble(field, source, retro, availability)
