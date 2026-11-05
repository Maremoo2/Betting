"""TEST_ONLY source-shaped fixtures; never mislabel as genuine 2015-2026 coverage."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hbi.mvp023a_historical_coverage import HOST, build_coverage, digest, main


KEY = "BJ_NR_2020-01-04"
RID = "RIKSTOTO:" + KEY + ":1"
FETCHED = "2026-10-10T09:00:00+00:00"


def put_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def original(root, path, payload, *, result=False):
    record = {
        "path": path,
        "url": HOST + "/api" + path,
        "body_sha256": digest(payload),
        "body": payload,
        "fetched_at": FETCHED,
    }
    parent = "raw-results" if result else "raw-markets"
    location = root / parent / (hashlib.sha256(path.encode()).hexdigest() + ".json")
    put_json(location, record)
    return record


def fixture(root: Path, *, market=True, outcome=True, tmp_ids=False):
    """Synthetic representative old crawler files, NOT historical sample counts."""
    meeting = {
        "raceDayKey": KEY, "raceDayName": "Bjerke", "countryIsoCode": "NO",
        "isDomestic": True,
        "races": [{"raceNumber": 1, "startTime": "2020-01-04T12:00:00+01:00",
                   "progressStatus": "Finished"}],
    }
    month_path = "/racedays/dates/2020-01-01/2020-01-31"
    inventory = original(root, month_path, {"success": True, "result": [meeting]})
    put_json(root / "inventory" / "2020-01.json", inventory)
    if not market:
        return {}
    starts_path = f"/racedays/{KEY}/starts"
    starts = [
        {"raceNumber": 1, "raceKey": KEY + "#1", "startNumber": n,
         "horseName": f"Horse {n}", "horseRegistrationNumber":
             (f"TMP-{n}" if tmp_ids else f"H{n}"), "isScratched": False}
        for n in (1, 2)
    ]
    frozen_starts = original(root, starts_path, {"success": True, "result": {"1": starts}})
    win_path = f"/game/{KEY}/betdistribution/winodds/1"
    win = original(root, win_path, {
        "success": True, "result": [
            {"startNumber": n, "odds": 2.0, "lastUpdated": "2020-01-04T11:55:00+01:00"}
            for n in (1, 2)
        ],
    })
    row = {
        "race_id": RID, "raceday_key": KEY, "race_number": 1,
        "day": "2020-01-04", "country": "NO",
        "metadata": meeting["races"][0],
        "roster": starts, "active_field": ["1", "2"],
        "pWIN": {"1": .5, "2": .5}, "collective": [],
        "category": "WIN_ONLY",
        "sources": [
            {k: record[k] for k in ("path", "url", "body_sha256", "fetched_at")}
            for record in (frozen_starts, win)
        ],
    }
    pre = {"stage": "MARKET_ONLY", "races": [row], "sha256": digest([row])}
    put_json(root / "market-days" / "2020-01-04.json", pre)
    if not outcome:
        return {"row": row, "pre": pre, "starts": starts}
    result_path = f"/results/raceDays/{KEY}/1/completeresults"
    result = original(root, result_path, {
        "success": True, "result": {
            "isComplete": True,
            "results": [{**horse, "place": horse["startNumber"]} for horse in starts],
        },
    }, result=True)
    post = {
        "stage": "RESULTS", "pre_sha256": pre["sha256"],
        "outcomes": [{
            "race_id": RID, "status": "VERIFIED_FULL_FIELD",
            "winners": ["1"], "dead_heat": False,
            "source_sha256": result["body_sha256"],
        }],
        "summary": {"day": "2020-01-04"},
    }
    put_json(root / "result-days" / "2020-01-04.json", post)
    return {"row": row, "pre": pre, "starts": starts, "post": post}


def test_metadata_is_not_counted_as_source_or_training(tmp_path):
    fixture(tmp_path, market=False)
    report = build_coverage(tmp_path)
    assert report["counts"]["physical_races"] == 1
    row = report["by_race"][0]
    assert row["categories"]["DISCOVERED_METADATA_ONLY"]
    assert not row["categories"]["SOURCE_ARCHIVED"]
    assert not row["categories"]["PIT_MODEL_ELIGIBLE"]
    assert report["by_year"]["2020"]["coverage_denominator"] == 1
    assert report["readiness"]["eligible_race_count_verified"] == 0


def test_retrospective_market_and_official_result_not_pit_evidence(tmp_path):
    fixture(tmp_path)
    report = build_coverage(tmp_path)
    row = report["by_race"][0]
    assert row["categories"]["SOURCE_ARCHIVED"]
    assert row["categories"]["FULL_FIELD_VERIFIED"]
    assert row["categories"]["MARKET_COMPLETE"]
    assert row["categories"]["RESULT_VERIFIED"]
    assert row["provider_registrations_stable"]
    assert not row["categories"]["IDENTITY_VERIFIED"]
    assert not row["categories"]["MARKET_PRE_RACE_VERIFIED"]
    assert row["categories"]["RETROSPECTIVE_DIAGNOSTIC_ONLY"]
    assert row["result_role"] == "RETROSPECTIVE_LABEL_ONLY"
    assert row["historical_feature_status"] == "MISSING"
    assert not row["categories"]["PIT_MODEL_ELIGIBLE"]
    assert report["readiness"]["benter_combination_fit"] == "BLOCKED_SOURCE"
    assert report["data_sha256"] == build_coverage(tmp_path)["data_sha256"]
    assert report["counts"]["RESULT_VERIFIED"] == 1


def test_tmp_registration_cannot_be_promoted(tmp_path):
    fixture(tmp_path, tmp_ids=True)
    row = build_coverage(tmp_path)["by_race"][0]
    assert not row["provider_registrations_stable"]
    assert "TMP_OR_UNSTABLE_PROVIDER_REGISTRATION" in row["blockers"]
    assert not row["categories"]["IDENTITY_VERIFIED"]


def test_missing_raw_win_does_not_claim_complete_market(tmp_path):
    fixture(tmp_path, outcome=False)
    win_path = f"/game/{KEY}/betdistribution/winodds/1"
    (tmp_path / "raw-markets" / (hashlib.sha256(win_path.encode()).hexdigest() + ".json")).unlink()
    row = build_coverage(tmp_path)["by_race"][0]
    assert not row["categories"]["MARKET_COMPLETE"]
    assert not row["categories"]["SOURCE_ARCHIVED"]
    assert row["categories"]["BLOCKED_SOURCE"]


def test_mutated_raw_original_refused_not_silently_reclassified(tmp_path):
    fixture(tmp_path)
    starts_path = f"/racedays/{KEY}/starts"
    path = tmp_path / "raw-markets" / (
        hashlib.sha256(starts_path.encode()).hexdigest() + ".json"
    )
    value = json.loads(path.read_text())
    value["body"]["result"]["1"][0]["horseName"] = "Tampered"
    put_json(path, value)
    with pytest.raises(ValueError, match="SHA_OR_ORIGIN"):
        build_coverage(tmp_path)


def test_frozen_market_and_result_chain_tampering_refused(tmp_path):
    fixture(tmp_path)
    file = tmp_path / "market-days" / "2020-01-04.json"
    doc = json.loads(file.read_text())
    doc["races"][0]["pWIN"]["1"] = .9
    put_json(file, doc)
    with pytest.raises(ValueError, match="MARKET_DAY_FREEZE_SHA_INVALID"):
        build_coverage(tmp_path)


def test_duplicate_physical_race_refused(tmp_path):
    fixture(tmp_path)
    file = tmp_path / "market-days" / "2020-01-04.json"
    doc = json.loads(file.read_text())
    doc["races"].append(doc["races"][0])
    doc["sha256"] = digest(doc["races"])
    put_json(file, doc)
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE_FREEZE"):
        build_coverage(tmp_path)


def test_result_chain_sha_mismatch_refused(tmp_path):
    fixture(tmp_path)
    file = tmp_path / "result-days" / "2020-01-04.json"
    doc = json.loads(file.read_text())
    doc["pre_sha256"] = "0" * 64
    put_json(file, doc)
    with pytest.raises(ValueError, match="RESULT_DAY_FROZEN_MARKET_SHA_MISMATCH"):
        build_coverage(tmp_path)


def test_cli_write_once_and_no_source_mutation(tmp_path):
    root, output = tmp_path / "source", tmp_path / "out" / "coverage.json"
    fixture(root)
    before = (root / "market-days" / "2020-01-04.json").read_bytes()
    assert main(["--root", str(root), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["schema"] == "MVP023A_HISTORICAL_COVERAGE_V1"
    assert (root / "market-days" / "2020-01-04.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        main(["--root", str(root), "--output", str(output)])


def test_no_archives_does_not_invent_census_counts(tmp_path):
    report = build_coverage(tmp_path)
    assert report["counts"] == {}
    assert report["by_race"] == []
    assert report["readiness"]["eligible_race_count_verified"] == 0


def test_weekly_only_market_freeze_is_detected_not_pit_promoted(tmp_path):
    from zipfile import ZipFile

    from hbi.mvp023a_historical_coverage import _weekly_market_days

    fixture(tmp_path, outcome=False)
    source = tmp_path / "market-days" / "2020-01-04.json"
    raw = source.read_bytes()
    month = tmp_path / "weekly" / "2020-W01-MARKET.zip"
    month.parent.mkdir()
    manifest = {
        "stage": "MARKET_ONLY", "retrospective": True, "week": "2020-W01",
        "days": ["2020-01-04"],
        "files_sha256": {"2020-01-04.json": hashlib.sha256(raw).hexdigest()},
    }
    with ZipFile(month, "w") as archive:
        archive.writestr("MANIFEST.json", json.dumps(manifest))
        archive.writestr("2020-01-04.json", raw)
    source.unlink()
    days, count = _weekly_market_days(tmp_path)
    assert count == 1 and "2020-01-04" in days
    row = build_coverage(tmp_path)["by_race"][0]
    assert row["categories"]["MARKET_COMPLETE"]
    assert row["categories"]["RETROSPECTIVE_DIAGNOSTIC_ONLY"]
    assert not row["categories"]["PIT_MODEL_ELIGIBLE"]


def test_corrupt_weekly_member_sha_rejected(tmp_path):
    from zipfile import ZipFile

    fixture(tmp_path, outcome=False)
    raw = (tmp_path / "market-days" / "2020-01-04.json").read_bytes()
    zip_path = tmp_path / "weekly" / "2020-W01-MARKET.zip"
    zip_path.parent.mkdir()
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("MANIFEST.json", json.dumps({
            "stage": "MARKET_ONLY", "retrospective": True, "week": "2020-W01",
            "days": ["2020-01-04"],
            "files_sha256": {"2020-01-04.json": "0" * 64},
        }))
        archive.writestr("2020-01-04.json", raw)
    with pytest.raises(ValueError, match="WEEKLY_MARKET_MEMBER_SHA_MISMATCH"):
        build_coverage(tmp_path)


def test_tampered_win_normalization_is_not_market_complete(tmp_path):
    fixture(tmp_path)
    file = tmp_path / "market-days" / "2020-01-04.json"
    doc = json.loads(file.read_text())
    doc["races"][0]["pWIN"] = {"1": .8, "2": .2}
    doc["sha256"] = digest(doc["races"])
    put_json(file, doc)
    row = build_coverage(tmp_path)["by_race"][0]
    assert not row["categories"]["MARKET_COMPLETE"]
    assert "COMPLETE_ORIGINAL_WIN_MARKET_MISSING" in row["blockers"]


def test_failed_starts_meeting_row_is_not_invented_as_physical_race(tmp_path):
    fixture(tmp_path, market=False)
    failed = {"race_id": KEY, "country": "NO", "category": "RAW_OR_REJECTED",
              "reason": "HTTP 403"}
    put_json(tmp_path / "market-days" / "2020-01-04.json", {
        "stage": "MARKET_ONLY", "races": [failed],
        "sha256": digest([failed]),
    })
    report = build_coverage(tmp_path)
    assert report["counts"]["physical_races"] == 1
    assert report["by_race"][0]["categories"]["DISCOVERED_METADATA_ONLY"]
    assert report["source_file_count"]["unbound_meeting_source_failures_not_physical_races"] == 1
    assert report["readiness"]["eligible_race_count_verified"] == 0
