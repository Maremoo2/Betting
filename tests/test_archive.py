import json

import pytest

from rikstoto_crawler.archive import (
    collect_day,
    locked_json,
    package_weeks,
    timing_quality,
    verify_outcome,
)
from rikstoto_crawler.transport import digest


def test_migration_timestamp_never_counts_as_primary():
    pool = {"provider_updated_at": "2019-01-28T08:41:18", "timing_class": "PRIMARY"}
    win = [{"lastUpdated": "2019-01-28T08:41:18"}]
    assert timing_quality("2018-01-06", "0001-01-01T00:43:00", win, pool).startswith("UNKNOWN:")
    assert timing_quality("2018-01-06", "2018-01-06T14:10:00", win, pool) == "UNKNOWN:UPDATE_ON_UNRELATED_DAY"


def test_verified_outcome_requires_complete_field_and_identity():
    roster = [{"startNumber": n, "horseName": str(n), "horseRegistrationNumber": str(n)} for n in (1, 2)]
    result = {"isComplete": True, "results": [{**r, "place": r["startNumber"]} for r in roster]}
    assert verify_outcome(roster, ["1", "2"], result)["winners"] == ["1"]
    result["results"][1]["horseRegistrationNumber"] = "wrong"
    with pytest.raises(ValueError, match="IDENTITY"):
        verify_outcome(roster, ["1", "2"], result)
    result["isComplete"] = False
    with pytest.raises(ValueError, match="NOT_COMPLETE"):
        verify_outcome(roster, ["1", "2"], result)


def test_market_freezes_before_result_endpoint_and_resume_skips_requests(tmp_path):
    key = "BJ_NR_2020-01-04"
    meeting = {"raceDayKey": key, "countryIsoCode": "NO", "pools": [], "races": [
        {"raceNumber": 1, "progressStatus": "Finished", "startTime": "2020-01-04T12:00:00"}]}
    starts = [{"raceKey": key + "#1", "raceNumber": 1, "startNumber": n,
               "horseName": str(n), "horseRegistrationNumber": str(n), "isScratched": False} for n in (1, 2)]

    class Client:
        calls = 0

        def get(self, path, *, result=False):
            self.calls += 1
            if path.endswith("starts"):
                value = {"1": starts}
            elif "winodds" in path:
                value = [{"startNumber": n, "odds": 2, "lastUpdated": "2020-01-04T11:58:00"} for n in (1, 2)]
            elif "placeodds" in path:
                value = []
            else:
                assert result and (tmp_path / "market-days/2020-01-04.json").exists()
                frozen = json.loads((tmp_path / "market-days/2020-01-04.json").read_text())
                assert frozen["sha256"] == digest(frozen["races"])
                value = {"isComplete": True, "results": [{**r, "place": r["startNumber"]} for r in starts]}
            body = {"result": value}
            return {"body": body, "body_sha256": digest(body), "path": path, "url": path,
                    "fetched_at": "2026-10-10T09:00:00Z"}

    client = Client()
    report = collect_day(tmp_path, "2020-01-04", [meeting], client)
    assert report["counts"]["verified_results"] == 1
    assert report["counts"]["WIN_ONLY"] == 1
    calls = client.calls
    assert collect_day(tmp_path, "2020-01-04", [meeting], client) == report
    assert client.calls == calls
    assert package_weeks(tmp_path) == 1
    path = tmp_path / "market-days/2020-01-04.json"
    value = json.loads(path.read_text())
    value["races"][0]["pWIN"]["1"] = .99
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="checksum"):
        collect_day(tmp_path, "2020-01-04", [meeting], client)


def test_immutable_json_normalizes_tuple_serialization(tmp_path):
    locked_json(tmp_path / "config.json", {"tiers": [("A", .5)]})
    locked_json(tmp_path / "config.json", {"tiers": [("A", .5)]})
    with pytest.raises(ValueError, match="Immutable"):
        locked_json(tmp_path / "config.json", {"tiers": [("A", .6)]})
