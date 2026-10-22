"""Genuine NO/SE source regressions; mutations are TEST_ONLY, not result truth."""
import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from hbi.pdf_validation import (
    inspect_document,
    load_parser,
    load_result_evidence,
    physical_candidates,
    verify_flying_finn,
)

FIXTURES = Path(__file__).parent / "fixtures"
RESULT_SHA = "8e0013ed4dbacb638e354807433cec4ab53a8412c957372279d1c5966bed01fc"


@pytest.fixture(scope="module")
def documents():
    values = []
    with zipfile.ZipFile(FIXTURES / "m7a-pdf-validation.zip") as z:
        for spec in json.loads(z.read("manifest.json"))["sources"]:
            metadata = json.loads(z.read(spec["metadata_member"]))
            pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(z.read(metadata["pdf_member"]))).pages]
            parsed = {"races": metadata["archived_parser_output"], "qa": {"status": "ARCHIVED_OUTPUT_NOT_REPLAY"}}
            values.append((metadata, pages, parsed))
    return values


def test_original_pdf_counts_and_source_locations(documents):
    for metadata, pages, parsed in documents:
        audit = inspect_document(metadata, pages, parsed)
        assert audit["reported_counts_match"]
        assert audit["status_counts"] == {"SOURCE_LINE_LOCATED": metadata["reported_counts"]["history_rows"]}
        assert all(r["model_eligible"] is False and r["pit_status"] == "UNRESOLVED" for r in audit["observations"])
        assert all(len(f["physical_candidates"]) == 1 for f in audit["fields"])


def test_diagnostic_dates_are_not_result_ground_truth(documents):
    expected = json.loads((FIXTURES / "m7a-diagnostic-dates.json").read_text())
    checked = 0
    for metadata, pages, parsed in documents:
        for doc in parsed["races"]:
            for h in doc["entrants"]:
                if h["name"] not in expected["horses"]:
                    continue
                assert [[p["date"], p["race_number"]] for p in h["past_starts"]] == expected["horses"][h["name"]]
                checked += len(h["past_starts"])
    assert checked == 30 and not expected["representative"]


def test_codes_qualification_and_page_boundary_remain_unresolved(documents):
    horses = {h["name"]: h for metadata, pages, parsed in documents for d in parsed["races"] for h in d["entrants"]}
    for name, token in [("EIRE", "frd8a"), ("CUSTER", "dg a"), ("GOFFA", "0 2100"), ("SINGLE LANE", "k 2140 17,0 gdk")]:
        rows = [r for r in horses[name]["past_starts"] if token in r["raw_text"]]
        assert rows and all(r["placing"] is None for r in rows)
    metadata, pages, parsed = documents[0]
    audit = inspect_document(metadata, pages, parsed)
    god = [r for r in audit["observations"] if r["horse_name"] == "GOD ONLY KNOWS"]
    assert len(god) == 5 and {p["page"] for r in god for p in r["locations"]} == {7}
    # This original version does NOT reproduce a split God Only Knows block.
    assert not any(r["cross_page_candidate"] for r in god)
    assert all(r["qualification_status"] == "UNRESOLVED" for r in audit["observations"])


def test_solvalla_l9_product_aliases_share_one_physical_field(documents):
    metadata, pages, parsed = documents[1]
    doc = next(d for d in parsed["races"] if any(h["name"] == "FLYING FINN" for h in d["entrants"]))
    assert physical_candidates(doc, metadata["canonical_starts"]) == ["S1_NR_2026-10-21#9"]
    assert "V86-6" in pages[5] and "V4-2" in pages[5]
    # Another track's L9 must not collapse into Solvalla L9.
    candidates = [physical_candidates(d, metadata["canonical_starts"]) for d in parsed["races"] if d["race"]["race_number"] == 9]
    assert len(candidates) == 2 and len({x[0] for x in candidates}) == 2


def test_test_only_ambiguous_field_and_future_line_fail_closed(documents):
    metadata, pages, parsed = copy.deepcopy(documents[0])
    canonical = copy.deepcopy(metadata["canonical_starts"])
    canonical["TEST_ONLY_DUPLICATE"] = next(iter(canonical.values()))
    assert len(physical_candidates(parsed["races"][0], canonical)) == 2
    prior = parsed["races"][0]["entrants"][0]["past_starts"][0]
    prior["date"] = "2027-01-01"
    result = inspect_document(metadata, pages, parsed)["observations"][0]
    assert result["parser_status"] == "UNRESOLVED" and not result["model_eligible"]


def result_evidence():
    return load_result_evidence(FIXTURES / "m7a-flying-finn-atg.zip", RESULT_SHA)


def test_flying_finn_independent_official_result():
    result = verify_flying_finn(result_evidence())
    assert result["place"] == 1 and result["km_time_seconds"] == 71.1
    assert result["stable_identity"] == "ATG_HORSE:788027"
    assert result["pit_status"] == "UNRESOLVED" and not result["model_eligible"]


@pytest.mark.parametrize("mutation", ["horse", "race", "result"])
def test_test_only_wrong_official_result_rejected(mutation):
    evidence = result_evidence()
    race = evidence["atg-2026-09-23_5_8.json"]["payload"]["races"][0]
    if mutation == "horse":
        race["starts"][0]["horse"]["id"] = 999
    elif mutation == "race":
        race["date"] = "2026-09-24"
    else:
        race["starts"][0]["result"]["place"] = 2
    with pytest.raises(ValueError, match="CONFLICT"):
        verify_flying_finn(evidence)


def test_test_only_unreviewed_parser_rejected(tmp_path):
    parser = tmp_path / "parser.py"
    parser.write_text("raise RuntimeError('must never execute')")
    with pytest.raises(ValueError, match="UNREVIEWED_PARSER"):
        load_parser(parser, "bad")


def test_test_only_cross_page_locator_preserves_original_line(documents):
    metadata, _pages, parsed = copy.deepcopy(documents[0])
    doc = parsed["races"][0]
    horse = doc["entrants"][0]
    # TEST_ONLY source layout mutation, not a claim about the actual PDF parser.
    raw = horse["past_starts"][0]["raw_text"]
    relocated_pages = [horse["header_text"], raw]
    parsed["races"] = [{**doc, "entrants": [{**horse, "past_starts": [horse["past_starts"][0]]}]}]
    row = inspect_document(metadata, relocated_pages, parsed)["observations"][0]
    assert row["cross_page_candidate"] and row["header_pages"] == [1]
    assert row["locations"] == [{"page": 2, "line": 1}]
    assert row["raw_history_line"] == raw and not row["model_eligible"]


def test_test_only_conflicting_official_identity_rejected():
    evidence = result_evidence()
    field = evidence["atg-2026-09-23_5_8.json"]["payload"]["races"][0]["starts"]
    field[1]["horse"]["id"] = field[0]["horse"]["id"]
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        verify_flying_finn(evidence)
