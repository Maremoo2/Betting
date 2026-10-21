"""Real archive evidence; mutations below are negative test inputs, not source truth."""
import copy
import json
from pathlib import Path

import pytest

from hbi.date_overview import DailyArchive, inspect_race, run_overview
from hbi.fundamental_view import analyze_race, verified_counts
from hbi.storage import SQLiteStore

ARCHIVE = Path(__file__).parent / "fixtures/rikstoto-2026-10-20.zip"
SHA = "a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e"


def source():
    archive = DailyArchive(ARCHIVE, SHA, "2026-10-20")
    doc = copy.deepcopy(archive.data["races"][0])
    starts = archive.read("meetings/BJ_NR_2026-10-20/starts.json")
    entry, _ = inspect_race(archive, doc, archive.manifest["meetings"][0], starts)
    entry["source_entry_id"] = f"{SHA}:races:0"
    return archive, doc, starts, entry


def test_actual_overview_fundamentals_and_no_model_writes(tmp_path):
    report, text = run_overview("2026-10-20", ARCHIVE, SHA, tmp_path / "view", fundamental=True)
    assert len(report["races"]) == 55
    assert report["counts"]["fully_analyzed"] == 0
    assert report["descriptive_analysis"]["verified_horses"] == 75
    first = report["races"][0]
    analysis = first["fundamental_analysis"]
    assert len(analysis["horses"]) == 12
    assert all(h["identity"]["status"] == "VERIFIED" for h in analysis["horses"])
    assert analysis["horses"][10]["facts"]["currentYear"]["value"] == {
        "starts": 21, "wins": 7, "seconds": 3, "thirds": 2}
    assert analysis["horses"][10]["facts"]["starting_distance_m"]["value"] == 2180
    assert analysis["horses"][0]["facts"]["days_since_latest_listed_start"]["value"] == 109
    assert "HAGE BALDER | identitet=VERIFIED | VERIFIED_FACT år: 21 starter, 7 seire" in text
    assert first["betting_runtime"]["report"]["allowed"] is False
    assert first["betting_runtime"]["report"]["errors"] == ["INVALID_V33_INPUT:'fundamental'"]
    assert len(analysis["comparisons"][0]["horses"]) == 12
    for h in analysis["horses"]:
        for start in h["history"]:
            assert start["historical_race_identity"] == "UNRESOLVED"
            assert not start["model_eligible"] and start["historical_published_at"] is None
        assert h["facts"]["validated_individual_results"]["kind"] == "MISSING_DATA"
    store = SQLiteStore(tmp_path / "view/hbi.sqlite")
    for table in ["predictions", "outcomes", "decisions", "market_snapshots"]:
        assert store.count(table) == 0
    # Every evidence pointer resolves in the hashed source, rather than a fabricated selector.
    for h in analysis["horses"]:
        for ref in h["identity"]["source_refs"]:
            node = json.loads(analysis_archive_bytes(ref["member"]))
            for token in ref["json_pointer"].split("/")[1:]:
                node = node[int(token)] if isinstance(node, list) else node[token]
            assert node


def analysis_archive_bytes(member):
    import zipfile
    with zipfile.ZipFile(ARCHIVE) as archive:
        return archive.read(member)


@pytest.mark.parametrize("mutation,expected", [
    ("registration", "CONFLICT"), ("parent", "CONFLICT"),
    ("missing_parent", "UNRESOLVED"), ("duplicate_id", "UNRESOLVED"),
    ("late", "UNRESOLVED"), ("temporary_id", "UNRESOLVED"),
])
def test_identity_and_time_fail_closed(mutation, expected):
    archive, doc, starts, entry = source()
    original = archive.read
    program = original("meetings/BJ_NR_2026-10-20/race_01.json")
    rows = program["response"]["result"][0]["starts"]
    if mutation == "registration":
        rows[0]["horseRegistrationNumber"] = "WRONG"
    elif mutation == "parent":
        rows[0]["father"] = "OTHER"
    elif mutation == "missing_parent":
        rows[0]["father"] = None
    elif mutation == "duplicate_id":
        rows[1]["horseRegistrationNumber"] = rows[0]["horseRegistrationNumber"]
    elif mutation == "late":
        program["fetched_utc"] = "2026-10-20T18:00:00+00:00"
    else:
        rows[0]["horseRegistrationNumber"] = "TMP_TEST"
    archive.read = lambda member: program if member.endswith("race_01.json") else original(member)
    result = analyze_race(archive, doc, entry, starts)
    h = result["horses"][0]
    assert h["identity"]["status"] == expected
    assert h["facts"]["currentYear"]["kind"] == "MISSING_DATA"
    assert not result["comparisons"] if mutation in {"late", "duplicate_id"} else True


@pytest.mark.parametrize("day", [None, "2026-10-20", "2026-10-21", "invalid", "2026-07-03"])
def test_future_undated_or_duplicate_history_withheld(day):
    archive, doc, starts, entry = source()
    doc["entrants"][0]["past_starts"][0]["date"] = day
    # Source index remains the archived entry, not equality matching of mutated objects.
    result = analyze_race(archive, doc, entry, starts)
    assert result["horses"][0]["history"][0]["raw_text"] is None
    assert result["horses"][0]["history"][0]["display_eligible"] is False


def test_odds_and_unparsed_result_codes_never_become_features():
    archive, doc, starts, entry = source()
    baseline = analyze_race(archive, doc, entry, starts)
    doc["win_odds"] = [{"odds": 1.01}]
    for h in doc["entrants"]:
        for p in h["past_starts"]:
            p["raw_text"] = "0 dg br P market 9999"
    changed = analyze_race(archive, doc, entry, starts)
    assert [h["facts"] for h in baseline["horses"]] == [h["facts"] for h in changed["horses"]]
    assert baseline["comparisons"] == changed["comparisons"]
    assert all(h["facts"]["validated_individual_results"]["value"] is None for h in changed["horses"])


def test_invalid_or_unmatched_stats_not_facts():
    for values in [(2, 3, 0, 0), (-1, 0, 0, 0), (True, 0, 0, 0), (2, 1, 0, 0)]:
        stats = dict(zip(["numberOfStarts", "numberOfFirstPlaces", "numberOfSecondPlaces", "numberOfThirdPlaces"], values, strict=True))
        assert verified_counts(stats, "Tot: 9-1-0-0", "Tot:") is None


@pytest.mark.parametrize("change", ["naive_time", "wrong_distance", "missing_program"])
def test_missing_program_and_source_contract(change):
    archive, doc, starts, entry = source()
    original = archive.read
    program = original("meetings/BJ_NR_2026-10-20/race_01.json")
    if change == "naive_time":
        program["fetched_utc"] = "2026-10-20T05:00:00"
    elif change == "wrong_distance":
        program["response"]["result"][0]["distance"] = 9999

    def read(member):
        if member.endswith("race_01.json"):
            if change == "missing_program":
                raise KeyError(member)
            return program
        return original(member)

    archive.read = read
    if change == "naive_time":
        with pytest.raises(ValueError, match="UNKNOWN_SOURCE_TIMEZONE"):
            analyze_race(archive, doc, entry, starts)
    else:
        result = analyze_race(archive, doc, entry, starts)
        assert result["blockers"] and not result["comparisons"]
        assert all(h["identity"]["verified_registration"] is None for h in result["horses"])
