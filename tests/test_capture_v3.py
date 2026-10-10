from datetime import UTC, datetime

import pytest

from rikstoto_crawler.capture import assess, collect
from rikstoto_crawler.transport import ArchiveClient, digest
from rikstoto_crawler.watch import checkpoint_status


def fixture():
    starts = [{"startNumber": n, "raceNumber": 1, "raceKey": "FO_NR_2026-09-30#1", "horseName": str(n),
               "horseRegistrationNumber": str(n), "isScratched": False} for n in (1, 2)]
    wins = [{"startNumber": n, "odds": 2, "lastUpdated": "2026-09-30T12:00:00Z"} for n in (1, 2)]
    return starts, wins


def test_place_failure_does_not_discard_win():
    starts, wins = fixture()
    row = assess("FO_NR_2026-09-30", 1, starts, wins, [], [])
    assert row["pWIN"] == {"1": .5, "2": .5}
    assert row["markets"]["PLACE"]["status"] == "INVALID_OR_INCOMPLETE"


def test_zero_win_never_normalizes_partial_field():
    starts, wins = fixture()
    wins[0]["odds"] = 0
    assert assess("FO_NR_2026-09-30", 1, starts, wins, [], [])["pWIN"] is None


def test_alias_retains_provider_pool_identity():
    starts, wins = fixture()
    meta = {"poolKey": "FO_NR_2026-09-30#V5A#1", "product": "V5A", "raceNumbers": [1, 2]}
    dist = [{"raceKey": "FO_NR_2026-09-30#1", "raceNumber": 1,
             "updatedTime": "2026-09-30T12:01:00Z",
             "investmentDistribution": [{"startNumber": 1, "percentage": 70},
                                        {"startNumber": 2, "percentage": 30}]}]
    result = assess("FO_NR_2026-09-30", 1, starts, wins, [], [(meta, dist)])["collective"][0]
    assert result["product"] == "V5" and result["provider_product"] == "V5A"
    assert result["pool_id"] == meta["poolKey"] and result["timing_class"] == "PRIMARY"
    dist[0]["investmentDistribution"].pop()
    result = assess("FO_NR_2026-09-30", 1, starts, wins, [], [(meta, dist)])["collective"][0]
    assert result["status"] == "INVALID_OR_INCOMPLETE" and "pCOL" not in result


def test_snapshot_window_never_retroactively_labels():
    start = "2026-10-08T12:00:00Z"
    assert checkpoint_status(start, datetime(2026, 10, 8, 11, 44, tzinfo=UTC), 15) == "WAITING"
    assert checkpoint_status(start, datetime(2026, 10, 8, 11, 45, tzinfo=UTC), 15) == "DUE"
    assert checkpoint_status(start, datetime(2026, 10, 8, 11, 47, tzinfo=UTC), 15) == "MISSED"
    assert checkpoint_status(start, datetime(2026, 10, 8, 12, tzinfo=UTC), 1) == "MISSED"


def test_frozen_output_cannot_be_reused(tmp_path):
    (tmp_path / "freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="read-only"):
        collect(tmp_path, [])


def test_payout_endpoint_forbidden_in_pre(tmp_path):
    with pytest.raises(ValueError, match="forbidden in PRE"):
        ArchiveClient(tmp_path).get("/game/prizepayout/FO_NR_2026-09-30/V65?raceNumber=6")


def test_collect_preserves_failed_place_and_cached_replay(tmp_path):
    starts, wins = fixture()
    key = "FO_NR_2026-09-30"
    meeting = {"raceDay": key, "countryIsoCode": "NO", "races": [
        {"raceNumber": 1, "startTime": "2026-09-30T12:00:00Z"}], "pools": [
        {"poolKey": key + "#VP#1", "product": "VP", "raceNumbers": [1], "raceNumber": 1},
        {"poolKey": key + "#QPlus#1", "product": "QPlus", "raceNumbers": [1], "raceNumber": 1}]}

    class Client:
        def get(self, path, **kwargs):
            if "/placeodds/" in path:
                raise OSError("PLACE unavailable")
            if path.endswith("/list"):
                result = [{"raceDays": [meeting]}]
            elif path.endswith("/starts"):
                result = {"1": starts}
            elif path.endswith("/totalInvestment"):
                result = []
            elif "/winodds/" in path:
                result = wins
            else:
                raise AssertionError(path)
            body = {"success": True, "result": result}
            return {"path": path, "url": "https://www.rikstoto.no/api" + path,
                    "fetched_at": "2026-10-08T12:00:00Z", "body": body, "body_sha256": digest(body)}

    report = collect(tmp_path, ["2026-09-30"], client=Client())
    assert report["win_complete"] == 1 and report["place_complete"] == 0
    assert report["unsupported_products"] == ["QPlus"]
    collect(tmp_path, ["2026-09-30"], client=Client())
    assert len(list((tmp_path / "captures").glob("*/*.json"))) == 1


def test_selected_race_does_not_request_unrelated_endpoints(tmp_path):
    from rikstoto_crawler.transport import digest

    class Client:
        def get(self, path, **kwargs):
            assert path.endswith("/list")
            body = {"result": [{"raceDays": [{"raceDay": "FO_NR_2026-09-30", "countryIsoCode": "NO",
                    "races": [{"raceNumber": 1}], "pools": []}]}]}
            return {"path": path, "url": "https://www.rikstoto.no/api" + path,
                    "fetched_at": "2026-10-08T12:00:00Z", "body": body, "body_sha256": digest(body)}

    assert collect(tmp_path, ["2026-09-30"], client=Client(), race_numbers={2})["captures"] == 0


def test_weekly_manifest_uses_exact_zip_member_names(tmp_path):
    import json
    from zipfile import ZipFile

    from rikstoto_crawler.capture_exports import weekly_v3

    row = {"day": "2026-10-10", "race_id": "RIKSTOTO:HA_NR_2026-10-10:1"}
    path = tmp_path / "captures" / "2026-10-10" / "sample.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(row))
    with ZipFile(weekly_v3(tmp_path)[0]) as archive:
        manifest = json.loads(archive.read("MANIFEST.json"))
        for name, checksum in manifest["files"].items():
            assert "\\" not in name
            assert digest(json.loads(archive.read(name))) == checksum
