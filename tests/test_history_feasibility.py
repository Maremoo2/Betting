"""Real archived feasibility replay; constructed mutations are TEST_ONLY."""
import copy
import json
from pathlib import Path

import pytest

from hbi.history_feasibility import (
    MISSING,
    combined,
    local_instant,
    pit_check,
    run,
    se_identity,
    select_asof,
)

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = "2026-10-20T18:00:00+00:00"


def ref(at="2026-10-19T12:00:00+00:00", digest="a" * 64):
    return {"url": "https://example.test/TEST_ONLY", "sha256": digest, "observed_at": at}


@pytest.fixture(scope="module")
def reports():
    return run(ROOT)


def test_real_51_original_observations_reproduced(reports):
    identity = reports["M7B2A_IDENTITY_LEDGER.json"]["observations"]
    races = reports["M7B2A_RACE_IDENTITY_LEDGER.json"]["observations"]
    evidence = reports["M7B2A_PIT_EVIDENCE.json"]["observations"]
    assert len(identity) == len(races) == len(evidence) == 51
    assert len({r["observation_id"] for r in identity}) == 51
    assert all(r["status"] == "IDENTITY_VERIFIED" and r["pdf"]["raw_history_line"] for r in identity)
    assert len({r["research_race_identifier"] for r in races}) == 50
    assert all(e["result_official_at"] == e["source_published_at"] == MISSING for e in evidence)
    assert all(r["original_registration"] and not r["model_eligible"] for r in identity)
    assert all(r["status"] == "PHYSICAL_RACE_VERIFIED" and r["external_race_identifier"] for r in races)


def test_real_four_scenarios_keep_semantics_and_pit_separate(reports):
    audit = reports["M7B2A_CUTOFF_AUDIT.json"]["observations"]
    assert len(audit) == 204
    for m in (1440, 60, 15, 4):
        rows = [r for r in audit if r["minutes_before_scheduled_start"] == m]
        assert len(rows) == 51
        assert sum(r["A_C"] for r in rows) == sum(r["A_D"] for r in rows) == 33
        assert sum(r["pit_status"] == "PIT_VERIFIED" for r in rows) == 18
        assert sum(r["pit_status"] == "PIT_VIOLATION" for r in rows) == 33
        assert sum(r["A_E"] for r in rows) == 9
        assert all(r["pdf_only_availability"]["pit_status"] == "PIT_VERIFIED" for r in rows)
        assert all(r["retrospective_label_research_usable"] and not r["model_eligible"] for r in rows)
        assert all("HISTORY_FEATURE_CONTRACT_NOT_VALIDATED" in r["exclusion_reasons"] for r in rows)
        assert any(r["gates"]["D"] == "PASS" and r["gates"]["B"] != "PASS" for r in rows)
        assert any(r["A_C"] and r["gates"]["E"] == "FAIL" for r in rows)


def test_real_same_horse_multiple_dates_and_shared_physical_race(reports):
    ids = reports["M7B2A_IDENTITY_LEDGER.json"]["observations"]
    custer = [r for r in ids if r["names"]["pdf"] == "CUSTER"]
    assert len(custer) == 4 and len({r["stable_identity"] for r in custer}) == 1
    races = reports["M7B2A_RACE_IDENTITY_LEDGER.json"]["observations"]
    shared = [r for r in races if r["observation_id"] in ("M7B1-H-003", "M7B1-H-008")]
    assert len({r["research_race_identifier"] for r in shared}) == 1
    assert len({r["research_race_identifier"] for r in races if r["venue"]["name"] == "Bjerke Travbane"}) > 1


@pytest.fixture
def identity_case():
    # TEST_ONLY constructed identity case; not an empirical source observation.
    def horse(hid, name):
        return {"id": hid, "name": name, "age": 5, "sex": "gelding",
            "pedigree": {"father": {"name": "Sire"}, "mother": {"name": "Dam"}}}
    starts = [{"number": 1, "horse": horse(1, "Alpha")}, {"number": 2, "horse": horse(2, "Beta")}]
    pdf = [{"program_number": i, "name": n, "identity_text": "5-års brun v e Sire - Dam e Other"} for i, n in [(1, "Alpha"), (2, "Beta")]]
    return pdf, {"starts": copy.deepcopy(starts)}, {"starts": copy.deepcopy(starts)}


@pytest.mark.parametrize("mutation,expected", [("same_name", "IDENTITY_AMBIGUOUS"), ("renamed", "IDENTITY_CONFLICT"),
    ("other_id", "IDENTITY_NOT_FOUND"), ("id_collision", "IDENTITY_AMBIGUOUS"), ("pedigree", "IDENTITY_CONFLICT"),
    ("missing_bio", "IDENTITY_CANDIDATE")])
def test_test_only_identity_negatives(identity_case, mutation, expected):
    pdf, target, historical = identity_case
    if mutation == "same_name":
        historical["starts"][1]["horse"]["name"] = "Alpha"
    elif mutation == "renamed":
        historical["starts"][0]["horse"]["name"] = "Former Alpha"
    elif mutation == "other_id":
        historical["starts"][0]["horse"]["id"] = 999
    elif mutation == "id_collision":
        historical["starts"][1]["horse"]["id"] = 1
    elif mutation == "pedigree":
        historical["starts"][0]["horse"]["pedigree"]["mother"]["name"] = "Other Dam"
    else:
        pdf[0]["identity_text"] = "UNKNOWN"
    assert se_identity(pdf, target, historical, 1, 1)["status"] == expected


def test_test_only_cross_namespace_id_is_not_name_evidence(identity_case):
    pdf, target, historical = identity_case
    target["starts"][0]["horse"]["id"] = 9
    assert se_identity(pdf, target, historical, 1, 1)["status"] == "IDENTITY_CONFLICT"


@pytest.mark.parametrize("zone,local,expected", [("Europe/Oslo", "2026-10-20T20:25", "2026-10-20T18:25:00+00:00"),
    ("Europe/Stockholm", "2026-12-20T20:25", "2026-12-20T19:25:00+00:00"),
    ("America/New_York", "2026-10-20T20:25", "2026-10-21T00:25:00+00:00")])
def test_test_only_timezones_and_winter(zone, local, expected):
    assert local_instant(local, zone) == expected


@pytest.mark.parametrize("local", ["2026-10-25T02:30", "2026-03-29T02:30"])
def test_test_only_dst_ambiguous_and_gap_rejected(local):
    with pytest.raises(ValueError, match="AMBIGUOUS_OR_NONEXISTENT"):
        local_instant(local, "Europe/Stockholm")


@pytest.mark.parametrize("mutation,status", [("missing_clock", "PIT_UNKNOWN"), ("late_event", "PIT_VIOLATION"),
    ("late_observation", "PIT_VIOLATION"), ("late_publication", "PIT_VIOLATION"), ("missing_source", "PIT_DATE_ONLY"),
    ("date_only", "PIT_DATE_ONLY"), ("same_day_missing_clock", "PIT_DATE_ONLY"), ("source_conflict", "PIT_VIOLATION")])
def test_test_only_pit_negatives(mutation, status):
    source = ref()
    cutoff, day, event = CUTOFF, "2026-09-01", MISSING
    snapshots = [source]
    if mutation == "missing_clock":
        cutoff = MISSING
    elif mutation == "late_event":
        event = "2026-10-21T12:00:00+00:00"
    elif mutation == "late_observation":
        source["observed_at"] = "2026-10-21T12:00:00+00:00"
    elif mutation == "late_publication":
        source["published_at"] = "2026-10-21T12:00:00+00:00"
    elif mutation == "missing_source":
        source.pop("sha256")
    elif mutation == "date_only":
        snapshots = []
    elif mutation == "same_day_missing_clock":
        day = "2026-10-20"
    else:
        snapshots.append(ref(digest="b" * 64))
    result = pit_check(day, event, cutoff, {"TEST_ONLY": snapshots})
    assert result["pit_status"] == status
    assert result["reasons"]


def test_test_only_later_corrected_result_cannot_rewrite_asof():
    prior = ref()
    correction = ref("2026-10-21T12:00:00+00:00", "b" * 64)
    frozen = select_asof([prior], CUTOFF)
    assert select_asof([prior, correction], CUTOFF) == frozen
    assert select_asof([correction], CUTOFF) is None
    correction["corrected_result"] = "TEST_ONLY_CHANGED"
    assert select_asof([prior, correction], CUTOFF) == frozen


def test_test_only_naive_timestamp_cannot_verify_pit():
    result = pit_check("2026-09-01", MISSING, CUTOFF, {"TEST_ONLY": [ref("2026-10-19T12:00:00")]})
    assert result["pit_status"] != "PIT_VERIFIED"


def test_test_only_model_admission_stays_false():
    result = combined(dict.fromkeys("ABCDE", "PASS"), "IDENTITY_VERIFIED", "PIT_VERIFIED")
    assert result["A_E"] and not result["model_eligible"]
    assert result["allowed_use"] == "RESEARCH_ONLY"


def test_real_ledger_is_frozen_offline_source_evidence(reports):
    # Every emitted report is deterministic JSON; no clock or network retrieval in run.
    for name, report in reports.items():
        assert json.loads(json.dumps(report, allow_nan=False)) == report
        assert not report["model_eligible"]
        expected = ROOT / "docs" / name
        if expected.exists():
            assert json.loads(expected.read_text()) == report


def test_test_only_absence_of_errors_is_not_availability_evidence():
    assert pit_check("2026-09-01", MISSING, CUTOFF, {})["pit_status"] == "PIT_DATE_ONLY"


def test_test_only_utc_cutoff_equals_local_offset_and_older_date_bound():
    a = pit_check("2026-09-01", MISSING, CUTOFF, {"TEST_ONLY": [ref()]})
    b = pit_check("2026-09-01", MISSING, "2026-10-20T20:00:00+02:00", {"TEST_ONLY": [ref()]})
    assert a == b and a["pit_status"] == "PIT_VERIFIED"
    # A local date cannot be treated as UTC midnight when checking completion.
    result = pit_check("2026-10-19", MISSING, "2026-10-20T02:00:00+00:00", {"TEST_ONLY": [ref()]}, "America/New_York")
    assert result["pit_status"] == "PIT_DATE_ONLY"


@pytest.mark.parametrize("day,cutoff,zone", [("2026-10-21", CUTOFF, "Europe/Stockholm"),
    ("2026-10-20", "2026-10-20T01:00:00+00:00", "America/New_York")])
def test_test_only_future_date_is_violation_even_without_clock(day, cutoff, zone):
    assert pit_check(day, MISSING, cutoff, {"TEST_ONLY": [ref()]}, zone)["pit_status"] == "PIT_VIOLATION"
