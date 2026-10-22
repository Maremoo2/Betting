"""Real PDF manual-reference checks; all intentional mutations are TEST_ONLY."""
import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from hbi.pdf_semantic_validation import (
    BUNDLE_SHA,
    FIELDS,
    classify,
    compare,
    official_review,
    read_sources,
    truth_data,
)
from hbi.pdf_validation import physical_candidates

FIXTURES = Path(__file__).parent / "fixtures"
TRUTH_PATH = FIXTURES / "m7a1-ground-truth-v1.json"
TRUTH_SHA = "82ca3f9e043cfc76c672b7efe15efe9da93090387972c762f4e306ffdaf1e39d"
OFFICIAL = FIXTURES / "m7a1-atg-results-v1.zip"
OFFICIAL_SHA = "f717e0ab2767abc436cadcf0ceecfbbe524233bb162db2ad1d6e71b9d3ebeabf"


@pytest.fixture(scope="module")
def truth():
    return truth_data(TRUTH_PATH, TRUTH_SHA)


@pytest.fixture(scope="module")
def sources():
    return read_sources(FIXTURES / "m7a-pdf-validation.zip")


def archived_comparison(truth, sources):
    # This is explicitly archived parser output, not a CI claim of live replay.
    parsed = {h: [(d, physical_candidates(d, meta["canonical_starts"])) for d in meta["archived_parser_output"]]
        for h, (meta, _) in sources.items()}
    return compare(truth["rows"], parsed, {h: pages for h, (_, pages) in sources.items()})


def test_real_manual_truth_all_sixty_sources_and_denominators(truth, sources):
    report = archived_comparison(truth, sources)
    assert report["rows"] == report["history_lines_found"] == 60
    assert report["source_localization"] == report["structural_assignment"] == {"CORRECT": 60}
    assert report["field_metrics"]["historical_date"]["correct_numerator"] == 60
    assert report["field_metrics"]["historical_race_number"]["correct_numerator"] == 60
    expected = {"historical_track": 60, "distance_m": 60, "start_method": 35, "placing": 50,
        "km_time": 49, "gallop_flag": 14, "disqualification_flag": 1, "qualification_flag": 2}
    for field, denominator in expected.items():
        metric = report["field_metrics"][field]
        assert metric["correct_numerator"] == 0
        assert metric["scorable_denominator"] == denominator
        assert metric["counts"]["NOT_EXTRACTED"] == denominator
        assert sum(metric["counts"].values()) == 60
    assert not report["representative"] and report["model_eligible"] == 0


def test_real_uncertain_codes_and_qualifiers_are_not_fabricated(truth):
    rows = truth["rows"]
    eire = next(r for r in rows if r["raw_codes"]["km_time"] == "frd8a")
    assert eire["placing"] == eire["km_time"] == "UNKNOWN"
    gdk = [r for r in rows if r["qualification_flag"] is True]
    assert len(gdk) == 2 and all(r["placing"] == "NOT_APPLICABLE" for r in gdk)
    assert all(r["disqualification_flag"] == "NOT_REPORTED" for r in rows if r["target_horse_name"] == "GOFFA")
    assert all(r["model_eligible"] is False for r in rows)
    assert sum(r["start_method"] == "UNKNOWN" for r in rows) == 25


@pytest.mark.parametrize("expected,actual,status", [(1, True, "INCORRECT"), (71.1, None, "NOT_EXTRACTED"),
    ("UNKNOWN", None, "AMBIGUOUS_SOURCE"), ("NOT_APPLICABLE", None, "NOT_APPLICABLE"),
    ("UNPLACED", 0, "INCORRECT"), (True, None, "NOT_EXTRACTED"), (60, float("nan"), "INCORRECT")])
def test_test_only_status_accounting(expected, actual, status):
    assert classify(expected, actual) == status


@pytest.mark.parametrize("mutation", ["future", "missing", "duplicate", "model_admission"])
def test_test_only_invalid_truth_rejected(truth, tmp_path, mutation):
    value = copy.deepcopy(truth)
    if mutation == "future":
        value["rows"][0]["historical_date"] = "2027-01-01"
    elif mutation == "missing":
        value["rows"][0].pop("distance_m")
    elif mutation == "duplicate":
        value["rows"][1] = copy.deepcopy(value["rows"][0])
    else:
        value["rows"][0]["model_eligible"] = True
    path = tmp_path / "TEST_ONLY.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        truth_data(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_test_only_wrong_block_and_wrong_date_are_separate(truth, sources):
    sources = copy.deepcopy(sources)
    first = truth["rows"][0]
    meta, _pages = sources[first["pdf_sha256"]]
    horse = meta["archived_parser_output"][0]["entrants"][0]
    horse["name"] = "TEST_ONLY_WRONG_HORSE"
    next(r for r in horse["past_starts"] if r["raw_text"] == first["raw_history_line"])["date"] = "1900-01-01"
    result = archived_comparison(truth, sources)["observations"][0]
    assert result["source_localization"] == "CORRECT" and result["history_line_found"]
    assert result["structural_assignment"] == "INCORRECT"
    assert result["fields"]["historical_date"]["status"] == "INCORRECT"
    assert "INCORRECT_MODEL_INPUT:historical_date" in result["critical_findings"]


def test_real_official_six_separate_from_pdf_truth(truth):
    before = copy.deepcopy(truth)
    review = official_review(truth, OFFICIAL, OFFICIAL_SHA)
    assert truth == before
    assert review["reviewed"] == 6 and review["status_counts"] == {"RESULT_VERIFIED": 6}
    pure = next(r for r in review["observations"] if r["horse_identity"] == "ATG_HORSE:793918")
    assert pure["official_values"]["start_method"] == "VOLT"
    assert pure["pdf_values"]["start_method"] == "UNKNOWN"
    assert pure["comparison"]["start_method"] == "AMBIGUOUS_SOURCE"
    dq = next(r for r in review["observations"] if r["race_id"] == "2026-05-31_5_4")
    assert dq["official_values"]["disqualification_flag"] is True
    assert dq["pdf_values"]["disqualification_flag"] == "UNKNOWN"
    assert all(r["model_eligible"] is False and r["pit_status"] == "UNVERIFIED" for r in review["observations"])


def test_test_only_official_identity_conflict_rejected(truth, tmp_path):
    with zipfile.ZipFile(OFFICIAL) as z:
        files = {name: z.read(name) for name in z.namelist()}
    name = "atg-2026-03-04_5_9.json"
    value = json.loads(files[name])
    horse = next(s["horse"] for s in value["payload"]["races"][0]["starts"] if s["horse"]["id"] == 788027)
    horse["pedigree"]["father"]["name"] = "TEST_ONLY_CONFLICT"
    files[name] = json.dumps(value).encode()
    manifest = json.loads(files["manifest.json"])
    manifest["files_sha256"][name] = hashlib.sha256(files[name]).hexdigest()
    files["manifest.json"] = json.dumps(manifest).encode()
    path = tmp_path / "TEST_ONLY.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        official_review(truth, path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_proposed_contract_cannot_admit_models():
    contract = json.loads((FIXTURES.parents[1] / "docs/M7A1_HISTORY_FEATURE_CONTRACT.json").read_text())
    assert contract["status"] == "PROPOSED_NOT_ACTIVATED" and not contract["model_eligible"]
    assert set(contract["fields"]) == set(FIELDS)
    assert all(v["allowed_use"] == "RESEARCH_ONLY" and not v["model_eligible"] for v in contract["fields"].values())
    assert BUNDLE_SHA == "1d4108180de1a191a3df502fde0e2ff4d2b74fc3f3b6eee30b701a18cb9e81a9"


def test_test_only_wrong_page_line_pointer_rejected(truth, sources):
    truth = copy.deepcopy(truth)
    truth["rows"][0]["source_evidence"]["extracted_line_number"] = 1
    with pytest.raises(ValueError, match="SOURCE_REFERENCE"):
        archived_comparison(truth, sources)
