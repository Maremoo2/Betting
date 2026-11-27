"""PREWATCH-004B focused tests: synthetic sources NEVER constitute official gold."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from hbi.cloud_run002_import import SourceRace
from hbi.ingestion import RaceCard
from hbi.prewatch004_pack import build_race_pack
from hbi.prewatch004b_features import (
    build_feature_context,
    coverage_report,
    validate_context_for_draft,
)

MID = "S1_NR_2026-11-23"
RID = f"RIKSTOTO:{MID}:1"
RAW = "TEST_ONLY U 10.11.26-1|1 1 2 2140 17,9 999 10"


def sample(*, priors=None):
    if priors is None:
        priors = [{"date": "2026-11-10", "race_number": 1, "raw_text": RAW}]
    card = RaceCard(
        race={
            "race_id": RID, "race_date": "2026-11-23",
            "country": "SE", "track": "Romme", "race_no": 1,
            "start_time_utc": "2026-11-23T11:20:00+00:00",
            "distance_m": 2140, "start_method": "VOLT",
        },
        runners=(
            {"selection_id": "1", "horse_name": "Kvikke Åsa", "scratched": 0,
             "post_position": 1, "driver_or_jockey": "Driver A"},
            {"selection_id": "2", "horse_name": "Traver B", "scratched": 1,
             "post_position": 2, "driver_or_jockey": "Driver B"},
        ),
    )
    received = datetime(2026, 11, 23, 8, 52, tzinfo=UTC)
    item = SourceRace(
        card=card, meeting_id=MID, race_no=1, received_at=received,
        source_uri="https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/" + MID,
        payload={
            "race_id": RID, "source_ready_snapshot": True,
            **{key: "a" * 64 for key in (
                "archive_sha256", "manifest_sha256", "starts_original_sha256",
                "program_pdf_original_sha256", "structured_program_sha256",
            )},
        },
    )
    doc = {"race": {"meeting_id": MID, "race_number": 1}, "entrants": [
        {"program_number": 1, "name": "Kvikke Åsa", "past_starts": priors},
        {"program_number": 2, "name": "Traver B", "past_starts": []},
    ]}
    pack = build_race_pack({"run_id": "20261123T085111520347Z"}, item, doc)
    return pack, doc


def test_reuses_existing_semantics_without_promoting_results():
    pack, doc = sample()
    enriched = build_feature_context(pack, doc)
    assert enriched["listed_count"] == 2
    assert enriched["active_count"] == 1
    runner = enriched["runners"][0]
    assert runner["verified_racing_features"]["raw_program_history_rows"]["value"] == 1
    assert runner["verified_racing_features"]["raw_program_history_rows"]["status"] == "VERIFIED"
    assert runner["verified_racing_features"]["semantic_extracted_prior_rows"]["value"] == 1
    assert runner["verified_racing_features"]["semantic_extracted_prior_rows"]["status"] == "PARTIAL"
    assert runner["verified_racing_features"]["verified_win_rate"]["value"] == "UNKNOWN"
    assert runner["verified_racing_features"]["verified_gallop_rate"]["denominator"] == 0
    assert runner["verified_racing_features"]["last_verified_start_date"]["status"] == "UNKNOWN"
    assert runner["verified_racing_features"]["permanent_horse_id"]["status"] == "UNKNOWN"
    obs = runner["research_source_extractions"][0]
    assert obs["field_candidates"]["distance_m"]["value"] == 2140
    assert obs["field_candidates"]["start_method"]["status"] == "AMBIGUOUS"
    assert obs["field_candidates"]["gallop_flag"]["value"] == "NOT_REPORTED"
    assert obs["verified_official_result"] is False
    assert obs["pit_certified"] is False
    assert enriched["phase_a_status"] == "NOT_RUN"
    assert enriched["bet_authorized"] is False


def test_future_history_is_blocked_and_not_counted():
    prior = {"date": "2026-11-24", "race_number": 1,
             "raw_text": "TEST_ONLY U 24.11.26-1|1 1 2 2140 17,9 999 10"}
    pack, doc = sample(priors=[prior])
    result = build_feature_context(pack, doc)
    obs = result["runners"][0]["research_source_extractions"][0]
    assert obs["semantic_status"] == "BLOCKED"
    assert "MISSING_INVALID_OR_FUTURE_HISTORY_DATE" in obs["problems"]
    assert result["runners"][0]["verified_racing_features"]["semantic_extracted_prior_rows"]["value"] == 0


def test_source_raw_duplication_is_explicitly_blocked():
    original = {"date": "2026-11-10", "race_number": 1, "raw_text": RAW}
    pack, doc = sample(priors=[original, deepcopy(original)])
    result = build_feature_context(pack, doc)
    obs = result["runners"][0]["research_source_extractions"]
    assert obs[1]["semantic_status"] == "BLOCKED"
    assert "DUPLICATED_SOURCE_HISTORY_RAW_ROW" in obs[1]["problems"]


@pytest.mark.parametrize("change", ["name", "count", "sha", "clock", "race_no"])
def test_original_binding_and_clock_conflicts_fail_closed(change):
    pack, doc = sample()
    pack = deepcopy(pack)
    doc = deepcopy(doc)
    if change == "name":
        doc["entrants"][0]["name"] = "Wrong Horse"
    elif change == "count":
        doc["entrants"][0]["past_starts"] = []
    elif change == "sha":
        doc["entrants"][0]["past_starts"][0]["raw_text"] += " altered"
    elif change == "clock":
        pack["source"]["observed_at_utc"] = pack["race"]["start_time_utc"]
    else:
        doc["race"]["race_number"] = 99
    with pytest.raises((ValueError, TypeError)):
        build_feature_context(pack, doc)


def test_coverage_report_separates_all_runners_and_active():
    pack, doc = sample()
    enriched = build_feature_context(pack, doc)
    report = coverage_report([enriched])
    assert report["physical_race_count_source_discovered"] == 1
    assert report["listed_runner_coverage"]["total"] == 2
    assert report["active_runner_coverage"]["total"] == 1
    assert report["listed_runner_coverage"]["with_raw_history"] == 1
    assert report["active_runner_coverage"]["raw_history_ge3"] == 0
    assert report["active_runner_coverage"]["independently_verified_historic_results"] == 0
    assert report["active_runner_coverage"]["complete_pit_history_attested"] == 0
    assert report["phase_a_completed"] == 0
    assert report["bet_authorized"] is False
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE"):
        coverage_report([enriched, enriched])


def test_future_ai_context_rebinds_to_exact_source_and_rejects_score_promotion():
    pack, doc = sample()
    context = build_feature_context(pack, doc)
    validate_context_for_draft(pack, context)
    corrupted = deepcopy(context)
    corrupted["runners"][0]["verified_racing_features"]["verified_wins"]["value"] = 1
    corrupted["runners"][0]["verified_racing_features"]["verified_wins"]["status"] = "VERIFIED"
    with pytest.raises(ValueError, match="UNATTESTED_RESULT"):
        validate_context_for_draft(pack, corrupted)
    corrupted = deepcopy(context)
    corrupted["runners"][0]["research_source_extractions"][0]["raw_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="PROVENANCE"):
        validate_context_for_draft(pack, corrupted)
    corrupted = deepcopy(context)
    corrupted["source_race_pack_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="SOURCE_CONTEXT"):
        validate_context_for_draft(pack, corrupted)
    corrupted = deepcopy(context)
    corrupted["runners"][0]["horse_name"] = "Different Horse"
    with pytest.raises(ValueError, match="RUNNER_IDENTITY"):
        validate_context_for_draft(pack, corrupted)


def test_explicit_unplaced_and_gallop_markers_remain_research_only():
    prior = {"date": "2026-11-10", "race_number": 1,
             "raw_text": "TEST_ONLY U 10.11.26-1|1 1 0 2140 17,9g 999 10"}
    pack, doc = sample(priors=[prior])
    context = build_feature_context(pack, doc)
    prior = context["runners"][0]["research_source_extractions"][0]
    assert prior["semantic_status"] == "PARTIAL"
    assert prior["field_candidates"]["placing"]["value"] == "UNPLACED"
    assert prior["field_candidates"]["gallop_flag"]["value"] is True
    facts = context["runners"][0]["verified_racing_features"]
    assert facts["research_explicit_gallop_markers"]["value"] == 1
    assert facts["research_explicit_gallop_markers"]["status"] == "PARTIAL"
    assert facts["verified_gallop_rate"]["status"] == "UNKNOWN"
    assert facts["verified_win_rate"]["status"] == "UNKNOWN"


def test_invalid_history_date_remains_blocked():
    priors = [{"date": "2026-13-11", "race_number": 1,
               "raw_text": "TEST_ONLY U 10.11.26-1|1 1 1 2140 17,9 999 10"}]
    pack, doc = sample(priors=priors)
    context = build_feature_context(pack, doc)
    assert context["runners"][0]["research_source_extractions"][0]["semantic_status"] == "BLOCKED"
    assert context["runners"][0]["verified_racing_features"]["verified_win_rate"]["value"] == "UNKNOWN"
