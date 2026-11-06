"""TEST_ONLY native 2020 fixture; no historical 2015-24 originals shipped here."""
# ruff: noqa: I001  # Standalone test fixture helpers use project test import roots.
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from hbi.mvp023b_archive_admission import admit_month, main
from test_mvp023a_historical_coverage import KEY, fixture, put_json

MONTH = "2020-01"


def test_test_only_month_originals_reused_full_field_result_sha_and_no_pit(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    old = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in source.rglob("*") if p.is_file()}
    report = admit_month(source, MONTH)
    assert report["physical_races"] == 1
    assert report["full_field_verified"] == 1
    assert report["official_results_verified"] == 1
    assert report["source_file_count"] >= 6
    assert report["missing_referenced_originals"] == []
    assert report["2025_lockbox_opened"] is False
    assert report["model_training_eligible"] == report["benter_fit_eligible"] == 0
    assert report["source_manifest_sha256"] == admit_month(source, MONTH)["source_manifest_sha256"]
    now = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in source.rglob("*") if p.is_file()}
    assert now == old, "must not mutate native originals"


def test_2025_candidate_lockbox_not_even_parsed(tmp_path):
    root = tmp_path / "archive"
    fixture(root)
    for directory, name in (("inventory", "2025-06.json"),
                            ("market-days", "2025-06-01.json"),
                            ("result-days", "2025-06-01.json")):
        put = root / directory / name
        put.parent.mkdir(parents=True, exist_ok=True)
        put.write_bytes(b"NOT_VALID_JSON_SECRET_LOCKBOX_MUST_NOT_READ")
    result = admit_month(root, MONTH)
    assert result["physical_races"] == 1
    assert not result["2025_lockbox_opened"]
    with pytest.raises(ValueError, match="LOCKBOX_2025"):
        admit_month(root, "2025-06")


def test_wrong_month_invalid_empty_or_unavailable(tmp_path):
    with pytest.raises(ValueError, match="LOCKBOX_2025"):
        admit_month(tmp_path, "2025-01")
    with pytest.raises(ValueError, match="2015_2024"):
        admit_month(tmp_path, "2026-10")
    with pytest.raises(ValueError, match="NO_AUTHENTIC_MONTHLY"):
        admit_month(tmp_path, "2018-05")
    with pytest.raises(ValueError, match="NATIVE_ARCHIVE_ROOT"):
        admit_month(tmp_path / "does-not-exist", "2018-05")


def test_source_sha_tampering_rejected(tmp_path):
    fixture(tmp_path)
    target = tmp_path / "inventory/2020-01.json"
    doc = json.loads(target.read_text())
    doc["body"]["result"][0]["raceDayName"] = "MALICIOUS"
    put_json(target, doc)
    with pytest.raises(ValueError, match="SHA"):
        admit_month(tmp_path, MONTH)


def test_original_cache_tamper_and_missing_are_distinct(tmp_path):
    fixture(tmp_path)
    path = "/racedays/" + KEY + "/starts"
    cache = tmp_path / "raw-markets" / (hashlib.sha256(path.encode()).hexdigest() + ".json")
    cache.unlink()
    report = admit_month(tmp_path, MONTH)
    assert report["missing_referenced_originals"]
    assert report["category_counts"]["SOURCE_ARCHIVED"] == 0
    fixture(tmp_path)
    doc = json.loads(cache.read_text())
    doc["body"]["result"]["1"][0]["horseName"] = "Tampered"
    put_json(cache, doc)
    with pytest.raises(ValueError, match="RAW_ORIGINAL_PATH_SHA_OR_SOURCE_CONFLICT"):
        admit_month(tmp_path, MONTH)


def test_duplicate_race_and_bad_freeze_rejected(tmp_path):
    fixture(tmp_path, outcome=False)
    path = tmp_path / "market-days/2020-01-04.json"
    doc = json.loads(path.read_text())
    doc["races"].append(doc["races"][0])
    from rikstoto_crawler.transport import digest

    doc["sha256"] = digest(doc["races"])
    put_json(path, doc)
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE_FREEZE"):
        admit_month(tmp_path, MONTH)


def test_symlink_or_traversal_not_read(tmp_path):
    archive = tmp_path / "archive"
    fixture(archive)
    original = archive / "inventory" / "2020-01.json"
    original.unlink()
    original.symlink_to(archive / "market-days" / "2020-01-04.json")
    with pytest.raises(ValueError, match="SYMLINK"):
        admit_month(archive, MONTH)
    original.unlink()
    fixture(archive)
    with pytest.raises(ValueError, match="UNSUPPORTED_WEEKLY_NATIVE_PATH"):
        admit_month(archive, MONTH, weekly=("../2025/secret.zip",))


def test_test_only_sha_bound_weekly_zip_reuse_and_month_scope(tmp_path):
    fixture(tmp_path)
    market = tmp_path / "market-days/2020-01-04.json"
    contents = market.read_bytes()
    archive = tmp_path / "weekly/2020-W01-MARKET.zip"
    archive.parent.mkdir(parents=True)
    manifest = {
        "stage": "MARKET_ONLY", "retrospective": True,
        "week": "2020-W01", "days": ["2020-01-04"],
        "files_sha256": {"2020-01-04.json": hashlib.sha256(contents).hexdigest()},
    }
    with ZipFile(archive, "w") as z:
        z.writestr("MANIFEST.json", json.dumps(manifest))
        z.writestr("2020-01-04.json", contents)
    market.unlink()
    got = admit_month(tmp_path, MONTH, weekly=("weekly/2020-W01-MARKET.zip",))
    assert got["full_field_verified"] == 1
    assert got["physical_races"] == 1
    assert any(x["path"] == "weekly/2020-W01-MARKET.zip" for x in got["read_only_native_files_sha256"])
    manifest["days"] = ["2020-01-04", "2025-01-01"]
    with ZipFile(archive, "w") as z:
        z.writestr("MANIFEST.json", json.dumps(manifest))
        z.writestr("2020-01-04.json", contents)
    with pytest.raises(ValueError, match="WEEKLY_OTHER_MONTH"):
        admit_month(tmp_path, MONTH, weekly=("weekly/2020-W01-MARKET.zip",))


def test_daily_cross_month_race_is_quarantined(tmp_path):
    fixture(tmp_path)
    p = tmp_path / "market-days/2020-01-04.json"
    v = json.loads(p.read_text())
    v["races"][0]["sources"][0]["path"] = "/racedays/BJ_NR_2025-01-01/starts"
    put_json(p, v)
    with pytest.raises(ValueError, match="OUT_OF_MONTH_SOURCE_RECEIPT"):
        admit_month(tmp_path, MONTH)


def test_cli_write_once_no_source_changes(tmp_path):
    src = tmp_path / "original"
    fixture(src)
    out = tmp_path / "reports" / "2020-01.json"
    args = ["--root", str(src), "--month", MONTH, "--output", str(out)]
    assert main(args) == 0
    result = json.loads(out.read_text())
    assert result["schema"] == "MVP023B_NATIVE_MONTH_ACCEPTANCE_V1"
    with pytest.raises(FileExistsError):
        main(args)


def test_authentic_2026_regression_not_misclassified_as_historical_archive(tmp_path):
    root = Path(__file__).resolve().parents[1]
    truth = root / "tests/fixtures/rikstoto-historical-truth.json"
    assert hashlib.sha256(truth.read_bytes()).hexdigest() == (
        "8086ec016e8e4f9cda7d9ad36abe44df1e09e3c2e387a9ed6c612fa61a0f8953"
    )
    with pytest.raises(ValueError, match="2015_2024"):
        admit_month(root, "2026-10")
