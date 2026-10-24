"""Real-source offline study; deliberate mutations are TEST_ONLY."""
import copy
import json
from pathlib import Path

import pytest

from hbi.history_availability import (
    MISSING,
    compare_versions,
    historical_replay,
    load_new,
    pit_decision,
    run,
)
from hbi.history_feasibility import archive_index
from hbi.pdf_semantic_validation import read_sources

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def reports():
    return run(ROOT)


@pytest.fixture
def record(reports):
    return copy.deepcopy(reports["M7B2B_GATE_REPORT.json"]["cutoff_observations"][0]["pdf_contract"])


def test_real_all_51_availability_and_correction_records(reports):
    a = reports["M7B2B_AVAILABILITY_LEDGER.json"]["observations"]
    c = reports["M7B2B_CORRECTION_AUDIT.json"]["observations"]
    assert len(a) == len(c) == len({r["observation_id"] for r in a}) == 51
    assert all(r["published_at"] == r["result_official_at"] == MISSING for r in a)
    assert all(r["pdf_generated_at"]["value"] != MISSING and r["pdf_evidence"]["sha256"] for r in a)
    assert all(not r["changes"] and r["full_correction_history"].startswith("UNKNOWN") for r in c)
    assert sum(r["provider_version_before"] != r["provider_version_after"] for r in c) == 32
    assert all(r["before_source"]["sha256"] and r["after_source"]["sha256"] for r in c)


def test_real_control_scope_and_identity_limitations(reports):
    r = reports["M7B2B_IDENTITY_REVIEW.json"]
    assert len(r["observations"]) == 8
    assert all(x["status"] == "SOURCE_FIRST_CORROBORATED" for x in r["observations"])
    assert sum("profile_source" in x for x in r["observations"]) == 4
    assert not r["human"] and not r["organizationally_independent"] and not r["blinded"]
    assert r["all_51_mechanically_checked"] and not r["prior_status_used_as_lookup_truth"]


def test_real_cutoff_counts_do_not_rewrite_baseline(reports):
    r = reports["M7B2B_GATE_REPORT.json"]
    assert r["A_C"] == 33 and r["existing_gate_admission"] == "CLOSED_UNCHANGED"
    for cutoff in r["cutoffs"].values():
        assert cutoff["pdf_pit_verified"] == 51
        assert cutoff["chain_pit_counts"] == {"PIT_VERIFIED": 18, "PIT_UNPROVEN": 33}
        assert cutoff["A_E_research"] == 9 and cutoff["A_C_D"] == 33
    assert r["publication_times_verified"] == r["documented_scoped_corrections"] == 0
    assert r["publication_times_unknown"] == 51
    for d in r["cutoff_observations"]:
        assert not d["model_eligible"]
        assert "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED" in d["exclusion_reasons"]


def test_real_completed_target_original_source_replay(reports):
    r = reports["M7B2B_HISTORICAL_REPLAY.json"]
    assert r["target_race_id"] == "RIKSTOTO:S1_NR_2026-10-21:9"
    assert r["field_size"] == 12 and r["raw_history_lines"] == 60
    assert r["authentic_source_replay_scenarios"] == 4
    assert r["verified_historical_input_replay_scenarios"] == 0
    assert all(s["verified_historical_result_input_replay"] == "REPLAY_NOT_PROVEN" for s in r["scenarios"])
    frozen = r["original_frozen_basis"]
    assert all(h["original_registration"].startswith("TMP-") for h in frozen["roster"])
    assert "result" not in frozen and "ATG_HORSE" not in json.dumps(frozen)


@pytest.mark.parametrize("field", ["published_at", "source_snapshot_at", "first_observed_at"])
def test_test_only_late_values_rejected(record, field):
    record[field] = "2026-10-25T12:00:00+00:00"
    assert pit_decision(record)["pit_decision"] == "PIT_VIOLATION"


def test_test_only_corrected_result_without_asof_version(record):
    record["correction_status"] = "CORRECTED_WITHOUT_ASOF_VERSION"
    assert pit_decision(record)["pit_decision"] == "PIT_UNPROVEN"


@pytest.mark.parametrize("mutation", ["identity_collision", "wrong_zone", "wrong_offset", "reconstructed", "label_as_feature", "model"])
def test_test_only_forbidden_upgrade(record, mutation):
    if mutation == "identity_collision":
        record["identity_evidence"]["conflict"] = True
    elif mutation == "wrong_zone":
        record["target_timezone"] = "America/New_York"
    elif mutation == "wrong_offset":
        record["decision_cutoff_at"] = record["decision_cutoff_at"].replace("+00:00", "+02:00")
    elif mutation == "reconstructed":
        record["origin"] = "RECONSTRUCTED_FROM_CURRENT_RESPONSE"
    elif mutation == "label_as_feature":
        record["purpose"] = "RETROSPECTIVE_LABEL_ONLY"
    else:
        record["model_eligible"] = True
    result = pit_decision(record)
    assert result["pit_decision"] == "PIT_VIOLATION" and not result["model_eligible"]


@pytest.mark.parametrize("mutation", ["no_observation", "unknown_snapshot", "missing_hash", "no_identity", "no_cutoff", "faked_old_snapshot"])
def test_test_only_unknown_is_not_verified(record, mutation):
    if mutation == "no_observation":
        record["availability_evidence"] = {}
    elif mutation == "unknown_snapshot":
        record["source_snapshot_at"] = MISSING
    elif mutation == "missing_hash":
        record["source_version"].pop("sha256")
    elif mutation == "no_identity":
        record["identity_evidence"] = {}
    elif mutation == "no_cutoff":
        record["decision_cutoff_at"] = MISSING
    else:
        record["source_version"]["observed_at"] = "2026-10-25T12:00:00+00:00"
    assert pit_decision(record)["pit_decision"] == "PIT_UNPROVEN"


def test_test_only_missing_publication_requires_positive_other_evidence(record):
    assert record["published_at"] == MISSING
    assert pit_decision(record)["pit_decision"] == "PIT_VERIFIED"
    record["first_observed_at"] = MISSING
    assert pit_decision(record)["pit_decision"] == "PIT_UNPROVEN"


@pytest.mark.parametrize("clock", ["2026-03-29T02:30:00", "2026-10-25T02:30:00"])
def test_test_only_dst_ambiguity_rejected(record, clock):
    record["target_schedule_local"] = clock
    with pytest.raises(ValueError, match="AMBIGUOUS_OR_NONEXISTENT"):
        pit_decision(record)


def test_test_only_real_change_is_not_hidden_by_version_tokens():
    before = {"place": 1, "time": "11,1"}
    after = {"place": 2, "time": "11,2"}
    r = compare_versions(before, after)
    assert r["interval_status"] == "SCOPED_CHANGE_OBSERVED" and len(r["changes"]) == 2


def test_test_only_future_control_container_does_not_rewrite_original_basis(reports):
    fixtures = ROOT / "tests/fixtures"
    originals = read_sources(fixtures / "m7a-pdf-validation.zip")
    _, targets = archive_index(fixtures)
    new = load_new(fixtures)
    # TEST_ONLY later control container changes; original starts bytes/provenance stay locked.
    for ref, _ in new.values():
        ref["archive_sha256"] = "f" * 64
    current = historical_replay(originals, targets, new, reports["M7B2B_GATE_REPORT.json"]["cutoff_observations"])
    assert current["frozen_basis_sha256"] == reports["M7B2B_HISTORICAL_REPLAY.json"]["frozen_basis_sha256"]


def test_test_only_outside_scope_never_admits_models():
    assert pit_decision({"evaluate": False}) == {"pit_decision": "PIT_NOT_EVALUATED", "reasons": ["OUTSIDE_EVALUATED_SCOPE"], "model_eligible": False}


def test_real_committed_reports_equal_execution(reports):
    for name, result in reports.items():
        assert not result["model_eligible"]
        assert json.loads((ROOT / "docs" / name).read_text()) == result


def test_test_only_future_historical_date_without_clock_is_violation(record):
    record.update(event_time=MISSING, event_date="2026-10-25")
    assert pit_decision(record)["pit_decision"] == "PIT_VIOLATION"


def test_test_only_unknown_event_time_and_date_do_not_pass(record):
    record.update(event_time=MISSING, event_date=MISSING)
    assert pit_decision(record)["pit_decision"] == "PIT_UNPROVEN"
