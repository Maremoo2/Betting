"""Real full-day source fixture; mutations are explicitly negative test inputs."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from hbi.date_overview import DailyArchive, inspect_race, run_overview
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
ARCHIVE = ROOT / "tests/fixtures/rikstoto-2026-10-20.zip"
SHA256 = "a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e"
PREFIX = "2026-10-20/20261020T051747910748Z"


def test_actual_cli_whole_archived_day(tmp_path):
    output = tmp_path / "overview"
    result = subprocess.run(
        [sys.executable, "-m", "hbi.cli", "overview", "--date", "2026-10-20",
         "--archive", str(ARCHIVE), "--sha256", SHA256, "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    report = json.loads((output / "overview.json").read_text())
    assert "55 oppføringer / 628 hester" in result.stdout
    assert "1 MIO NOVA" in result.stdout and "strøket ved snapshot" in result.stdout
    assert report["counts"] == {
        "source_race_entries": 55, "source_runner_entries": 628,
        "independent_races": 48, "independent_runners": 545,
        "full_field_matched_races": 48, "independent_runners_with_raw_history": 346,
        "imported_races": 33, "imported_runners": 375,
        "screened_for_input_eligibility": 55, "betting_reviews_executed": 33,
        "blocked_before_review": 22,
        "fully_analyzed": 0,
    }
    assert report["source_counts"] == {"races": 55, "horses": 628, "prior_starts": 1855}
    assert len({r["source_entry_id"] for r in report["races"]}) == 55
    assert report["day_completeness_verified"] is False
    store = SQLiteStore(output / "hbi.sqlite")
    assert store.count("races") == store.count("provider_payloads") == 33
    for table in ["market_snapshots", "predictions", "outcomes", "decisions"]:
        assert store.count(table) == 0
    for race in report["races"]:
        assert len(race["runners"]) == race["runner_count"]
        assert race["screened"] and not race["fully_analyzed"]
        assert race["missing_inputs"]
        if race["imported"]:
            runtime = race["betting_runtime"]
            assert runtime["exit_code"] == 2
            assert runtime["report"]["allowed"] is False
            assert runtime["report"]["execution"] == "SHADOW_ONLY"
        else:
            assert race["blockers"] and race["betting_runtime"] is None
    first = report["races"][0]
    assert first["identity_coverage"]["usable_provider_ids"] == 12
    assert first["history_coverage"]["raw_rows"] == 60
    assert first["history_coverage"]["model_validated_runners"] == 0
    assert first["betting_runtime"]["report"]["errors"] == ["INVALID_V33_INPUT:'fundamental'"]
    for race in report["races"]:
        if race["history_coverage"]["raw_rows"] == 0:
            assert "RAW_HISTORY_EXCERPTS" not in race["available_inputs"]
            assert "FULL_FIELD_RAW_HISTORY" in race["missing_inputs"]
    assert sum("SCHEDULED_START_UNKNOWN" in r["blockers"] for r in report["races"]) == 15
    assert sum(r["composite_product"] for r in report["races"]) == 7
    # No existing isolated/frozen output can be overwritten.
    frozen = (output / "overview.json").read_bytes()
    with pytest.raises(FileExistsError):
        run_overview("2026-10-20", ARCHIVE, SHA256, output)
    assert frozen == (output / "overview.json").read_bytes()


@pytest.mark.parametrize("day,checksum,error", [
    ("2026-10-21", SHA256, "DATE_NOT_IN_ARCHIVE"),
    ("2026-10-20", "0" * 64, "ARCHIVE_SHA256_MISMATCH"),
])
def test_unavailable_date_or_bad_hash_no_import(tmp_path, day, checksum, error):
    with pytest.raises(ValueError, match=error):
        run_overview(day, ARCHIVE, checksum, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_corrupt_archive_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"corrupted")
    with pytest.raises(zipfile.BadZipFile):
        DailyArchive(path, hashlib.sha256(path.read_bytes()).hexdigest(), "2026-10-20")


def source_race():
    archive = DailyArchive(ARCHIVE, SHA256, "2026-10-20")
    doc = archive.data["races"][0]
    meeting = archive.manifest["meetings"][0]
    starts = archive.read("meetings/BJ_NR_2026-10-20/starts.json")
    return archive, doc, meeting, starts


@pytest.mark.parametrize("change,reason", [
    ("name", "PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH"),
    ("missing_runner", "PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH"),
    ("duplicate_runner", "PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH"),
    ("unknown_scratch", "PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH"),
    ("late_source", "SOURCE_NOT_PRE_START"),
    ("unknown_timezone", "UNKNOWN_SOURCE_TIMEZONE"),
    ("POST", "UNSUPPORTED_OR_POST_FIELDS"),
    ("missing_startlist", "PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH"),
])
def test_negative_source_eligibility(change, reason):
    archive, doc, meeting, starts = source_race()
    if change == "name":
        doc["entrants"][0]["name"] = "DIFFERENT HORSE"
    elif change == "missing_runner":
        doc["entrants"].pop()
    elif change == "duplicate_runner":
        doc["entrants"][1]["program_number"] = 1
    elif change == "unknown_scratch":
        starts["response"]["result"]["1"][0]["isScratched"] = None
    elif change == "late_source":
        starts["fetched_utc"] = "2026-10-20T18:00:00+00:00"
    elif change == "unknown_timezone":
        starts["fetched_utc"] = "2026-10-20T05:18:00"
    elif change == "POST":
        doc["winner"] = "1"
    elif change == "missing_startlist":
        starts = None
    if change == "unknown_timezone":
        with pytest.raises(ValueError, match=reason):
            inspect_race(archive, doc, meeting, starts)
    else:
        item, card = inspect_race(archive, doc, meeting, starts)
        assert card is None and reason in item["blockers"]


def test_temporary_provider_id_is_never_promoted():
    archive, doc, meeting, starts = source_race()
    starts["response"]["result"]["1"][0]["horseRegistrationNumber"] = "TMP-test"
    item, card = inspect_race(archive, doc, meeting, starts)
    assert card is not None  # canonical source import does not certify model identity
    assert item["identity_coverage"]["usable_provider_ids"] == 11
    assert item["runners"][0]["provider_identity_usable"] is False
    assert "VERIFIED_FULL_FIELD_PROVIDER_IDENTITIES" in item["missing_inputs"]


def test_source_counts_must_match(tmp_path):
    target = tmp_path / "altered.zip"
    with zipfile.ZipFile(ARCHIVE) as source, zipfile.ZipFile(target, "w") as out:
        for name in source.namelist():
            raw = source.read(name)
            if name == f"{PREFIX}/structured_program_day.json":
                data = json.loads(raw)
                data["races"].pop()
                raw = json.dumps(data).encode()
            out.writestr(name, raw)
    with pytest.raises(ValueError, match="SOURCE_COUNTS_MISMATCH"):
        DailyArchive(target, hashlib.sha256(target.read_bytes()).hexdigest(), "2026-10-20")
