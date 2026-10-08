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
    pools = {pk: {"raceKey": key+"#1", "raceNumber": 1, "updatedTime": "2025-12-26T12:01:15",
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
