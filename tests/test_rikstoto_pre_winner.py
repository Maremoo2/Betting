import io
import json
from copy import deepcopy

import pytest

from rikstoto_crawler.extract import extract_race
from rikstoto_crawler.job import crawl, freeze, horse_name, january, post, validate_sample
from rikstoto_crawler.transport import ArchiveClient, write_json


@pytest.fixture
def archive():
    key = "S1_NR_2025-12-26"
    meeting = {"raceDay": key, "raceDayName": "Track", "countryIsoCode": "SE", "sportType": "T"}
    race = {"raceNumber": 1, "startTime": "2025-12-26T12:00:00", "progressStatus": "Finished",
            "isAbandoned": False, "isMerged": True}
    starts = [{"raceNumber": 1, "startNumber": n, "horseName": f"Horse {n}",
               "horseRegistrationNumber": f"ID-{n}", "raceKey": key+"#1", "isScratched": False}
              for n in (1, 2, 3)]
    win = [{"startNumber": n, "odds": o, "lastUpdated": "2025-12-26T12:01:00"}
           for n, o in ((1, 4), (2, 2), (3, 10))]
    place = [{"startNumber": n, "minOdds": 1.5, "maxOdds": 2,
              "lastUpdated": "2025-12-26T12:05:00"} for n in (1, 2, 3)]
    pk = key + "#V4#1"
    pools = {pk: {"raceKey": key+"#1", "raceNumber": 1, "product": "V4", "leg": 1,
                  "pool_start_race": 1, "pool_race_numbers": [1, 2, 3, 4],
                  "updatedTime": "2025-12-26T12:01:15",
                  "investmentDistribution": [{"startNumber": n, "percentage": p}
                                              for n, p in ((1, 60), (2, 30), (3, 10))]}}
    totals = [{"raceDay": key, "product": p, "raceNumber": 1, "poolKey": key+f"#{p}#1",
               "totalInvestment": 1234500} for p in ("V", "P", "V4")]
    return [meeting, race, starts, {"distance": 2100}, {}, win, place, pools, totals]


def test_full_field_extraction_and_scratches(archive):
    row = extract_race(*archive)
    assert sum(row["pWIN"].values()) == pytest.approx(1)
    assert row["turnover"]["V"]["nok"] == 12345
    assert row["provider_is_merged"] is True  # This flag alone does not invalidate a safe field match.
    assert not row["prospective"] and not row["executable"]
    assert next(iter(row["collective"].values()))["contemporaneous"]
    archive[2][2]["isScratched"] = True
    row = extract_race(*archive)
    assert row["active_field"] == ["1", "2"]
    assert row["runners"]["3"]["scratched"]
    assert "3" not in row["pWIN"]


@pytest.mark.parametrize("mutate", [
    lambda a: a[5].pop(),
    lambda a: a[6].pop(),
    lambda a: a[5][0].update(odds=float("nan")),
    lambda a: a[5][0].update(odds=0),
    lambda a: a[6][0].update(minOdds=3),
    lambda a: a[2][1].update(startNumber=1),
    lambda a: a[2][0].update(raceKey="other"),
    lambda a: a[2][0].update(horseName=""),
    lambda a: a[2][0].pop("isScratched"),
    lambda a: a[7][next(iter(a[7]))]["investmentDistribution"].pop(),
    lambda a: a[8].pop(),
    lambda a: a[1].update(isAbandoned=True),
])
def test_incomplete_or_ambiguous_data_fails_closed(archive, mutate):
    mutate(archive)
    with pytest.raises((ValueError, TypeError)):
        extract_race(*archive)


def test_misaligned_collective_is_preserved_but_labelled(archive):
    archive[7][next(iter(archive[7]))]["updatedTime"] = "2025-12-26T10:00:00"
    row = extract_race(*archive)
    assert not next(iter(row["collective"].values()))["contemporaneous"]
    assert not row["executable"]


def test_outcomes_not_leaked_into_pre(archive):
    for runner in archive[2]:
        runner.update(place=1, winner=True, payout=999, kmTime="1.00")
    row = extract_race(*archive)
    serialized = json.dumps(row)
    for forbidden in ('"place":', '"winner":', '"payout":', '"kmTime":'):
        assert forbidden not in serialized
    row["runners"]["1"]["horse_id_stable"] = False
    assert "horse_id_stable" in serialized


def test_scope_and_results_separation(tmp_path):
    client = ArchiveClient(tmp_path, delay=0)
    for path in ("https://evil.test", "/account", "/game/submit", "/../results"):
        with pytest.raises(ValueError):
            client.get(path)
    with pytest.raises(ValueError, match="PRE"):
        client.get("/results/raceDays/S1_NR_2025-12-26/1/completeresults")
    assert client.requests == 0


def test_windows_checkpoint_lock_is_retried_without_truncation(tmp_path, monkeypatch):
    from pathlib import Path

    target = tmp_path / "checkpoint.json"
    write_json(target, {"complete": "old"})
    original = Path.replace
    calls = []
    def locked(self, destination):
        calls.append(destination)
        if len(calls) < 3:
            assert json.loads(target.read_text())["complete"] == "old"
            raise PermissionError("temporary reader lock")
        return original(self, destination)
    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr("rikstoto_crawler.transport.time.sleep", lambda _: None)
    write_json(target, {"complete": "new"})
    assert len(calls) == 3
    assert json.loads(target.read_text())["complete"] == "new"


def test_cached_scoped_get_and_integrity(tmp_path, monkeypatch):
    path = "/racedays/S1_NR_2025-12-26/starts"
    calls = []
    def fetch(request, **kwargs):
        calls.append(request.get_method())
        response = io.BytesIO(json.dumps({"result": {}}).encode())
        response.url = request.full_url
        return response
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    client = ArchiveClient(tmp_path, delay=0)
    first = client.get(path)
    assert client.get(path) == first and calls == ["GET"]
    cached = next((tmp_path / "raw-markets").glob("*.json"))
    bad = json.loads(cached.read_text())
    bad["body"] = {"result": {"tamper": True}}
    write_json(cached, bad)
    with pytest.raises(ValueError, match="integrity"):
        client.get(path)


def test_frozen_pre_before_post_and_tamper_detection(tmp_path, archive):
    row = extract_race(*archive)
    freeze(tmp_path, [row])
    initial = (tmp_path / "pre.jsonl").read_bytes()
    freeze(tmp_path, [row])
    with pytest.raises(ValueError, match="immutable"):
        freeze(tmp_path, [])
    assert (tmp_path / "pre.jsonl").read_bytes() == initial
    (tmp_path / "pre.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        post(tmp_path)


def test_post_checks_complete_results_and_runner_identity(tmp_path, archive):
    row = extract_race(*archive)
    freeze(tmp_path, [row])
    before = (tmp_path / "pre.jsonl").read_bytes()
    class ResultClient:
        def get(self, path, **kwargs):
            assert kwargs["result"]
            return {"url": "source", "fetched_at": "now", "body": {"result": {
                "isComplete": True, "results": [{"startNumber": n, "place": n,
                                                  "horseName": f"Horse {n}",
                                                  "horseRegistrationNumber": f"ID-{n}"}
                                                 for n in (1, 2, 3)]}}}
    assert post(tmp_path, client=ResultClient())["joined"] == 1
    assert (tmp_path / "pre.jsonl").read_bytes() == before


def test_post_not_allowed_without_freeze(tmp_path):
    with pytest.raises(FileNotFoundError):
        post(tmp_path)


@pytest.mark.parametrize("variant,expected", [
    ("temporary", 1), ("contradictory_id", 0), ("wrong_name", 0),
    ("stable_missing_id", 0), ("incomplete", 0),
])
def test_post_fallback_requires_unique_name_and_unstable_pre_id(tmp_path, archive, variant, expected):
    row = extract_race(*archive)
    if variant != "stable_missing_id":
        row["runners"]["1"].update(horse_id="TMP-1", horse_id_stable=False)
    freeze(tmp_path, [row])
    class ResultClient:
        def get(self, path, **kwargs):
            results = [{"startNumber": n, "place": n, "horseName": f"Horse {n}",
                        "horseRegistrationNumber": f"ID-{n}"} for n in (1, 2, 3)]
            results[0]["horseRegistrationNumber"] = "wrong" if variant == "contradictory_id" else ""
            if variant == "wrong_name":
                results[0]["horseName"] = "Different Horse"
            return {"url": "source", "fetched_at": "now", "body": {"result": {
                "isComplete": variant != "incomplete", "results": results}}}
    report = post(tmp_path, client=ResultClient())
    assert report["joined"] == expected
    assert report["rejected"] == 1 - expected
    if expected:
        outcome = json.loads((tmp_path / "post-results.json").read_text())["rows"][0]["outcomes"]["1"]
        assert outcome["identity_method"] == "RACE_START_NUMBER_UNIQUE_NAME"
        assert not outcome["stable_identity_verified"]


def test_only_known_name_decorations_normalized():
    assert horse_name("Hard Center* (S)") == horse_name("Hard Center (SE) *")
    assert horse_name("Cartesio (IT)") == horse_name("Cartesio")
    assert horse_name("Horse (Unknown)") != horse_name("Horse")
    assert horse_name("Horse A") != horse_name("Horse B")


def test_expansion_gate_before_january(tmp_path, archive):
    quality = {"config": {"days": ["2025-12-22"], "countries": ["NO", "SE"]},
               "accepted": 1, "rejected": {}, "fetch_errors": {}, "by_country": {"SE": 1},
               "stability": {"x": {"stable": True}}}
    assert not validate_sample(quality)["allowed"]
    write_json(tmp_path / "quality.json", quality)
    freeze(tmp_path, [extract_race(*archive)])
    with pytest.raises(ValueError, match="JANUARY_BLOCKED"):
        january(tmp_path / "january", tmp_path)


def test_completed_crawl_resume_reuses_freeze_without_network(tmp_path, archive):
    row = extract_race(*archive)
    config = {"days": ["2025-12-26"], "countries": ["SE"], "max_races_per_meeting": 0}
    write_json(tmp_path / "config.json", config)
    freeze(tmp_path, [row])
    report = {"accepted": 1, "config": config}
    write_json(tmp_path / "quality.json", report)
    class NoNetwork:
        def get(self, *args, **kwargs):
            pytest.fail("completed archive must not fetch or change PRE")
    assert crawl(tmp_path, config["days"], countries=["SE"], client=NoNetwork()) == report
    with pytest.raises(ValueError, match="configuration changed"):
        crawl(tmp_path, config["days"], countries=["NO"], client=NoNetwork())


def test_uncalibrated_identity_marked_not_promoted(archive):
    archive[2][0]["horseRegistrationNumber"] = "TMP-1"
    result = extract_race(*archive)
    assert not result["runners"]["1"]["horse_id_stable"]
    assert result["runners"]["1"]["match_confidence"] == 1
    assert result["m0_m6_status"] == "NOT_CONFIGURED_PROTOCOL_NOT_RETRIEVED"
    assert "BET" not in json.dumps(result)


def test_changing_result_fields_does_not_change_pre(archive):
    baseline = extract_race(*archive)
    mutated = deepcopy(archive)
    mutated[1]["winningStartNumber"] = 2
    assert extract_race(*mutated) == baseline


def test_pre_upload_never_contains_results_or_dividends(tmp_path, archive):
    import zipfile

    from rikstoto_crawler.exports import export

    freeze(tmp_path, [extract_race(*archive)])
    write_json(tmp_path / "post-display.json", {"winner": "SECRET_OUTCOME", "dividend": 999})
    export(tmp_path)
    with zipfile.ZipFile(tmp_path / "exports" / "PRE-upload.zip") as bundle:
        assert not any("POST" in n or "post" in n for n in bundle.namelist())
        assert all(b"SECRET_OUTCOME" not in bundle.read(n) for n in bundle.namelist())
    assert "Horse 1" in (tmp_path / "exports" / "PRE.md").read_text(encoding="utf-8")


def test_published_dividend_display_does_not_qualify_settlement(archive):
    from rikstoto_crawler.exports import display_result

    row = extract_race(*archive)
    summary = {"raceDay": row["raceday_key"], "raceResults": {"1": [{"startNumber": 1, "place": 1}]},
               "finalOdds": {"winOdds": {"1": {"1": {"odds": 8.7, "payoutStatus": "Dividends"}}},
                             "placeOdds": {"1": {"1": {"odds": 2.4, "payoutStatus": "Refunded"}}},
                             "twinOdds": {"1": [{"startNumbers": "1-2", "odds": 20.8,
                                                 "payoutStatus": "Dividends"}]}}}
    data = display_result(row, summary)
    assert data["dividends"]["WIN"]["entries"][0]["dividend"] == 8.7
    assert data["dividends"]["PLACE"]["entries"][0]["dividend"] is None
    assert data["dividends"]["DUO"]["status"] == "MISSING"
    assert not data["settlement_eligible"] and not data["full_result_verified"]
    summary["raceResults"]["1"][0]["startNumber"] = 99
    with pytest.raises(ValueError, match="outside active field"):
        display_result(row, summary)


def test_summary_endpoint_forbidden_before_post(tmp_path):
    with pytest.raises(ValueError, match="PRE"):
        ArchiveClient(tmp_path).get("/results/raceDays/F2_NR_2025-12-26/raceresults")


def test_collective_products_stay_separate_and_visible(tmp_path, archive):
    from rikstoto_crawler.exports import export

    first = next(iter(archive[7].values()))
    second = deepcopy(first)
    second.update(product="V65", pool_race_numbers=[1, 2, 3, 4, 5, 6])
    second["investmentDistribution"][0]["percentage"] = 30
    second["source"] = {"url": "https://www.rikstoto.no/api/verified", "fetched_at": "now",
                        "body_sha256": "hash"}
    pk = archive[0]["raceDay"] + "#V65#1"
    archive[7][pk] = second
    archive[8].append({"poolKey": pk, "totalInvestment": 9876500})
    row = extract_race(*archive)
    assert len(row["collective"]) == 2
    assert row["collective"][pk]["leg"] == 1
    freeze(tmp_path, [row])
    export(tmp_path)
    text = (tmp_path / "exports/PRE.md").read_text(encoding="utf-8")
    assert "V4 — Avdeling 1" in text and "V65 — Avdeling 1" in text
    assert "Andel %" in text and "98765.0" in text and "Δ pp" in text
    assert "https://www.rikstoto.no/api/verified" in text


def test_bad_leg_rejected_and_place_quality_patterns_flagged(archive):
    pool = next(iter(archive[7].values()))
    pool["leg"] = 2
    with pytest.raises(ValueError, match="NO_COMPLETE_COLLECTIVE_POOL"):
        extract_race(*archive)
    pool["leg"] = 1
    for r in archive[6]:
        r["maxOdds"] = r["minOdds"]
    row = extract_race(*archive)
    assert set(row["data_quality_flags"]) == {"VP_TURNOVER_IDENTICAL",
        "PLACE_RANGE_COLLAPSED_ALL_ACTIVE", "SE_PLACE_SEMANTICS_UNVERIFIED"}
    assert not row["place_semantics_verified"]


@pytest.mark.parametrize("skew,expected", [(0, "PRIMARY"), (60, "PRIMARY"),
    (60.001, "SECONDARY"), (300, "SECONDARY"), (300.001, "EXCLUDE_DIAGNOSTIC")])
def test_frozen_timing_boundaries(skew, expected):
    from rikstoto_crawler.integrity import cohort

    assert cohort(skew) == expected
    with pytest.raises(ValueError):
        cohort(float("nan"))


def test_integrity_ignores_post_and_checks_stored_skew(tmp_path, archive):
    from rikstoto_crawler.integrity import analyze, run

    row = extract_race(*archive)
    freeze(tmp_path, [row])
    (tmp_path / "post-results.json").write_text("invalid POST MUST NOT BE READ")
    report = run(tmp_path)
    assert report["post_read"] is False
    assert report["pool_cohorts"] == {"PRIMARY": 1}
    assert run(tmp_path) == report
    pool = next(iter(row["collective"].values()))
    pool["win_skew_seconds"] = 76
    with pytest.raises(ValueError, match="timing skew mismatch"):
        analyze([row])


def test_weekly_pre_isolated_partial_and_reproducible(tmp_path, archive):
    import zipfile

    from rikstoto_crawler.weekly import weekly

    row = extract_race(*archive)
    freeze(tmp_path, [row])
    write_json(tmp_path / "quality.json", {"config": {"days": [row["date"]]},
                                         "observed_days": [row["date"]]})
    (tmp_path / "post-results.json").write_text("POST MUST NOT BE READ")
    report = weekly(tmp_path)
    assert report == weekly(tmp_path)
    with zipfile.ZipFile(report["weekly_files"][0]) as package:
        assert "POST.md" not in package.namelist()
        assert {"PRE.md", "PRE.csv", "COLLECTIVE.csv", "INTEGRITY.md", "MANIFEST.json"} <= set(package.namelist())
        manifest = json.loads(package.read("MANIFEST.json"))
        assert manifest["week"] == "2025-W52"
        assert len(manifest["missing_days"]) == 6
        assert not manifest["all_races_claimed"]
        assert manifest["race_count"] == 1


def test_weekly_iso_boundary_and_separate_results(tmp_path, archive):
    import zipfile

    from rikstoto_crawler.exports import PAYOUTS
    from rikstoto_crawler.weekly import week_id, weekly

    assert week_id("2025-12-29") == week_id("2026-01-04") == "2026-W01"
    assert week_id("2026-01-05") == "2026-W02"
    first = extract_race(*archive)
    second = deepcopy(first)
    second.update(date="2026-01-05", race_id="TEST:2026-01-05:1")
    manifest = freeze(tmp_path, [first, second])
    write_json(tmp_path / "post-display.json", {"pre_freeze": manifest, "rejected": {}, "rows": [
        {"race_id": row["race_id"], "finishers": {"1": {"place": 1}},
         "dividends": {p: {"entries": []} for p in PAYOUTS}} for row in [first, second]]})
    write_json(tmp_path / "post-results.json", {"pre_freeze": manifest, "rejected": {},
        "rows": [{"race_id": r["race_id"]} for r in [first, second]]})
    report = weekly(tmp_path, stage="both")
    assert len(report["weekly_files"]) == 4
    for path in report["weekly_files"]:
        with zipfile.ZipFile(path) as package:
            data = json.loads(package.read("MANIFEST.json"))
            assert data["race_count"] == 1
            if data["stage"] == "POST":
                assert data["full_result_verified_races"] == 1
                assert "PRE.csv" not in package.namelist()


def test_stability_ignores_only_runner_order_not_values(archive):
    from rikstoto_crawler.job import market_stability_digest

    first = {"body": {"result": list(archive[7].values()), "success": True}}
    second = deepcopy(first)
    second["body"]["result"][0]["investmentDistribution"].reverse()
    assert market_stability_digest(first) == market_stability_digest(second)
    second["body"]["result"][0]["investmentDistribution"][0]["percentage"] += 1
    assert market_stability_digest(first) != market_stability_digest(second)
    win = {"body": {"result": archive[5]}}
    reordered = deepcopy(win)
    reordered["body"]["result"].reverse()
    assert market_stability_digest(win) == market_stability_digest(reordered)
    reordered["body"]["result"][0]["odds"] += 1
    assert market_stability_digest(win) != market_stability_digest(reordered)
    reordered["body"]["result"].append(reordered["body"]["result"][0])
    with pytest.raises(ValueError, match="ambiguous runner"):
        market_stability_digest(reordered)
