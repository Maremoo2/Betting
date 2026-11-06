"""P0: bounded ATG original probe never equates names with independent identity."""
import hashlib
import json
import runpy
from pathlib import Path

import pytest

from hbi.providers.atg import AtgFetchResult

module = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "scripts/weekend_atg_readiness_readonly.py"
))


def _source(folder, *, scratch=()):
    folder.mkdir()
    originals = folder / "originals"
    originals.mkdir()
    key = "S1_NR_2026-11-07"
    data = {}
    roster = [
        {"startNumber": n, "horseName": f"Horse {n}",
         "horseRegistrationNumber": f"TMP-{n}",
         "raceNumber": 5, "raceKey": f"{key}#5",
         "isScratched": n in scratch}
        for n in (1, 2)
    ]
    for path, payload in [
        (f"/racedays/{key}/starts", {"result": {"5": roster}}),
        (f"/racedays/{key}/scratched", {"result": {"5": list(scratch)}}),
    ]:
        raw = json.dumps(payload).encode()
        sha = hashlib.sha256(raw).hexdigest()
        (originals / f"{sha}.json").write_bytes(raw)
        data[path] = {
            "request_path": path, "http_status": 200,
            "response_sha256": sha, "original_relative_path": f"originals/{sha}.json",
            "response_completed_utc": "2026-11-06T10:00:02+00:00",
        }
    report = {
        "schema": "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1",
        "bet_authority": False, "new_model_invocations": 0,
        "source_as_of_utc": "2026-11-06T10:00:00+00:00",
        "original_receipts": list(data.values()),
        "weekend_rounds": [{
            "name": "BERGSAKER_V85", "source_raceday_keys": [key],
            "legs": [{
                "leg": 1, "race_no": 5,
                "physical_race_id": f"RIKSTOTO:{key}:5",
                "race_start_utc": "2026-11-07T14:00:00+00:00",
                "active_runners": 2 - len(scratch),
            }],
        }],
    }
    (folder / "weekend-race-intelligence.json").write_text(json.dumps(report))
    return folder


def test_public_atg_calendar_without_race_is_not_fundamental_admission(
    monkeypatch, tmp_path,
):
    source = _source(tmp_path / "source")
    def calendar(url, folder):
        assert "calendar/day/2026-11-07" in url
        return AtgFetchResult(
            url=url, payload={"tracks": []},
            success=True, status_code=200, latency_ms=1.0,
        ), {
            "url": url, "http_status": 200,
            "response_completed_utc": "2026-11-06T10:01:00+00:00",
        }
    monkeypatch.setitem(module["audit"].__globals__, "_get_original", calendar)
    result = module["audit"](source, tmp_path / "result")
    leg = result["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["active_runners"] == 2
    assert leg["atg_race_id"] is None
    assert leg["atg_valid_lifetime_name_number_matches"] == 0
    assert leg["atg_full_field_match_count"] == 0
    assert leg["independent_registration_attested"] == 0
    assert leg["pit_certified"] is False
    assert leg["model_eligible"] is False
    assert result["model_invocations"] == 0
    assert result["bet_authority"] is False


def test_rikstoto_original_sha_tamper_rejected_before_atg(monkeypatch, tmp_path):
    source = _source(tmp_path / "source")
    originals = list((source / "originals").glob("*.json"))
    originals[0].write_bytes(b"not the original bytes")
    def no_fetch(*args, **kwargs):
        raise AssertionError("ATG cannot be fetched before original SHA verification")
    monkeypatch.setitem(module["audit"].__globals__, "_get_original", no_fetch)
    with pytest.raises(ValueError, match="ORIGINAL_RIKSTOTO_SHA_MISMATCH"):
        module["audit"](source, tmp_path / "output")


def test_scratched_original_conflict_rejected(monkeypatch, tmp_path):
    source = _source(tmp_path / "source", scratch=(1,))
    report_path = source / "weekend-race-intelligence.json"
    report = json.loads(report_path.read_text())
    report["weekend_rounds"][0]["legs"][0]["active_runners"] = 2
    report_path.write_text(json.dumps(report))
    def calendar(url, folder):
        return AtgFetchResult(
            url=url, payload={"tracks": []}, success=True,
            status_code=200, latency_ms=1,
        ), {"http_status": 200, "url": url}
    monkeypatch.setitem(module["audit"].__globals__, "_get_original", calendar)
    with pytest.raises(ValueError, match="ORIGINAL_CANONICAL_SCRATCH_CONFLICT"):
        module["audit"](source, tmp_path / "output")
