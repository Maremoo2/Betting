"""PIT-003A offline regression: no network and no live PIT claims."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from hbi.core_shadow_pilot import plan_t4_source_receipts
from hbi.core_t4_receipt import capture_one, digest, run_attestation
from hbi.core_pit_roster_verification import attest_t4_receipt
from hbi.providers.rikstoto import FetchResult


START = datetime(2026, 11, 3, 11, 20, tzinfo=UTC)
T4 = START - timedelta(minutes=4)
EARLY = T4 - timedelta(seconds=35)
KEY = "S1_NR_2026-11-03"
RACE = "RIKSTOTO:S1_NR_2026-11-03:1"


def _target():
    return {
        "race_id": RACE, "raceday_key": KEY, "race_number": 1,
        "canonical_start_utc": START.isoformat(),
        "effective_t4_utc": T4.isoformat(),
        "earliest_source_start_utc": None,
    }


def _payloads(*, scratch=False, duplicate=False, clock=None, registration=None):
    names = [
        {"startNumber": 1, "horseName": "Aurora",
         "raceNumber": 1, "raceKey": KEY + "#1",
         "horseRegistrationNumber": registration or "12345", "isScratched": False},
        {"startNumber": 2 if not duplicate else 1, "horseName": "Brage",
         "raceNumber": 1, "raceKey": KEY + "#1",
         "horseRegistrationNumber": "67890", "isScratched": scratch},
    ]
    return {
        "racedays": {
            "result": [{
                "raceDayKey": KEY, "raceDayName": "Eskilstuna",
                "countryIsoCode": "SE", "trackCode": "S1", "sportType": "T",
                "races": [{"raceNumber": 1,
                           "startTime": (clock or START).isoformat()}],
            }],
        },
        "starts": {"success": True, "result": {"1": names}},
        "scratched": {"success": True, "result": {"1": [2] if scratch else []}},
    }


class FakeClient:
    def __init__(self, payloads, observed=EARLY, raw_override=None):
        self.payloads = payloads
        self.observed = observed
        self.raw_override = raw_override
        self.calls = []

    def _get(self, role):
        self.calls.append(role)
        body = json.dumps(self.payloads[role], sort_keys=True).encode()
        supplied = body if self.raw_override is None else self.raw_override
        return FetchResult(
            url="https://www.rikstoto.no/api/" + role,
            payload=self.payloads[role], success=True, status_code=200,
            latency_ms=1, response_completed_at=self.observed,
            response_body_sha256=digest(body),
            raw_body=supplied,
        )

    def racedays(self, *, retain_raw_body=False):
        assert retain_raw_body is True
        return self._get("racedays")

    def starts(self, key, *, retain_raw_body=False):
        assert key == KEY and retain_raw_body is True
        return self._get("starts")

    def scratched(self, key, *, retain_raw_body=False):
        assert key == KEY and retain_raw_body is True
        return self._get("scratched")


def _capture(tmp_path, **kwargs):
    payloads = _payloads(
        scratch=kwargs.pop("scratch", False),
        duplicate=kwargs.pop("duplicate", False),
        clock=kwargs.pop("start_clock", None),
        registration=kwargs.pop("registration", None),
    )
    client = FakeClient(payloads, observed=kwargs.pop("observed", EARLY),
                        raw_override=kwargs.pop("raw_override", None))
    now = kwargs.pop("now", EARLY)
    assert not kwargs
    root = tmp_path / "capture"
    root.mkdir()
    report = capture_one(_target(), client=client, out=root,
                         clock=lambda: now, sleeper=lambda _: None)
    return report, client, root


def _model():
    return {
        "race": {"race_id": RACE}, "as_of_utc": (T4 - timedelta(minutes=8)).isoformat(),
        "report_created_at_utc": (T4 - timedelta(minutes=7)).isoformat(),
        "model_status": "MODEL_READY", "bet_authority": False,
        "run_kind": "PROSPECTIVE_ATTEMPT",
        "champion_p_sum": 1.0, "core004_p_sum": 1.0,
        "runners": [
            {"start_number": 1, "horse_name": "Aurora", "scratched": False,
             "history_source_uri": "https://www.atg.se/stats/12345"},
            {"start_number": 2, "horse_name": "Brage", "scratched": False,
             "history_source_uri": "https://www.atg.se/stats/67890"},
        ],
    }


def _archive():
    return {
        "race_id": RACE,
        "original_bytes_sha256_verified": True,
        "full_field_pdf_startlist_reconciled": True,
        "observed_at_utc": (T4 - timedelta(hours=3)).isoformat(),
        "origin_authenticated_independently": True,
        "version_identical_to_t4": True,
    }


def test_source_receipt_preserves_original_bytes_and_distinguishes_certification(tmp_path):
    report, client, path = _capture(tmp_path)
    assert report["status"] == "SOURCE_OBSERVED_BEFORE_T4"
    assert client.calls == ["racedays", "starts", "scratched"]
    assert report["pit_status"] == "PIT_NOT_CERTIFIED"
    for role, row in report["sources"].items():
        assert row["raw_sha256"] == digest((path / (role + ".raw.json")).read_bytes())
        assert row["source_published_at_utc"] is None
    assert "SOURCE_PUBLICATION_UNATTESTED" in report["blockers"]


def test_positive_offline_contract_and_negative_live_authority(tmp_path):
    receipt, _, directory = _capture(tmp_path)
    model = _model()
    raw = json.dumps(model, sort_keys=True).encode()
    positive = attest_t4_receipt(
        receipt, receipt_dir=directory, model_report=model, model_raw=raw,
        collector_archive=_archive(), provenance_mode="TEST_ONLY"
    )
    assert positive["status"] == "TEST_ONLY_CONTRACT_PASS"
    assert positive["model_report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert positive["independent_pit_certified"] is False
    assert positive["bet_authority"] is False
    blocked = attest_t4_receipt(
        receipt, receipt_dir=directory, model_report=model, model_raw=raw,
        collector_archive=_archive(), provenance_mode="LIVE"
    )
    assert blocked["pit_status"] == "PIT_NOT_CERTIFIED"
    assert "INDEPENDENT_COLLECTOR_ORIGIN_GATE_NOT_WIRED" in blocked["blockers"]


@pytest.mark.parametrize(("mutate", "expected"), [
    ({"now": T4}, "MISSED_T4"),
    ({"observed": T4}, "RESPONSE_AFTER_T4"),
    ({"raw_override": b"wrong"}, "RAW_BODY_HASH_MISMATCH_OR_MISSING"),
    ({"duplicate": True}, "DUPLICATE_START_NUMBER"),
    ({"registration": "TMP999"}, "STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED"),
    ({"start_clock": START - timedelta(minutes=2)}, "START_CLOCK_CONFLICT"),
])
def test_negative_source_captures(tmp_path, mutate, expected):
    report, client, _ = _capture(tmp_path, **mutate)
    assert expected in report["blockers"]
    assert report["status"] != "SOURCE_OBSERVED_BEFORE_T4"
    if expected == "MISSED_T4":
        assert not client.calls


def test_over_capacity_and_missing_known_future_roster():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE races
        (race_id TEXT,track TEXT,country TEXT,race_no INTEGER,
         start_time_utc TEXT,discipline TEXT)""")
    conn.execute("""CREATE TABLE provider_race_refs
        (race_id TEXT,provider TEXT,provider_raceday_key TEXT,discovered_at_utc TEXT)""")
    for race_no in (1, 2, 3):
        rid = "RIKSTOTO:S1_NR_2026-11-03:" + str(race_no)
        conn.execute("INSERT INTO races VALUES(?,?,?,?,?,?)",
                     (rid, "Eskilstuna", "SE", race_no,
                      START.isoformat(), "trot"))
        conn.execute("INSERT INTO provider_race_refs VALUES(?,?,?,?)",
                     (rid, "rikstoto", KEY, (T4 - timedelta(hours=4)).isoformat()))
    plan = plan_t4_source_receipts(
        conn, now=T4 - timedelta(minutes=2), max_races=1
    )
    assert len(plan["eligible"]) == 1
    assert sum(x["reason"] == "NOT_PROCESSED_CAPACITY" for x in plan["excluded"]) == 2


def test_missing_independent_archive_leaves_provenance_blocked(tmp_path):
    report, _, directory = _capture(tmp_path)
    model = _model()
    output = attest_t4_receipt(
        report, receipt_dir=directory, model_report=model,
        model_raw=json.dumps(model).encode(),
    )
    assert "COLLECTOR_ARCHIVE_UNAVAILABLE" in output["blockers"]
    assert not output["independent_pit_certified"]


def test_future_model_freeze_and_field_revision_fail_closed(tmp_path):
    report, _, directory = _capture(tmp_path)
    model = _model()
    model["report_created_at_utc"] = (T4 + timedelta(seconds=5)).isoformat()
    model["runners"][0]["scratched"] = True
    output = attest_t4_receipt(
        report, receipt_dir=directory,
        model_report=model, model_raw=json.dumps(model).encode(),
        collector_archive=_archive(), provenance_mode="TEST_ONLY",
    )
    assert "MODEL_ASOF_OR_FREEZE_AFTER_T4" in output["blockers"]
    assert "MODEL_ROSTER_NOT_T4_MATCHED" in output["blockers"]
    assert output["pit_status"] == "PIT_NOT_CERTIFIED"


def test_hash_tamper_cannot_replay(tmp_path):
    report, _, directory = _capture(tmp_path)
    (directory / "starts.raw.json").write_bytes(b"changed after capture")
    model = _model()
    result = attest_t4_receipt(
        report, receipt_dir=directory,
        model_report=model, model_raw=json.dumps(model).encode(),
        collector_archive=_archive(), provenance_mode="TEST_ONLY"
    )
    assert "ORIGINAL_RAW_HASH_MISMATCH" in result["blockers"]


def test_pending_near_t4_is_not_a_failed_run(tmp_path):
    client = FakeClient(_payloads())
    root = tmp_path / "capture"
    root.mkdir()
    report = capture_one(
        _target(), client=client, out=root,
        clock=lambda: T4 - timedelta(minutes=8),
        sleeper=lambda _: None,
    )
    assert report["status"] == "PENDING"
    assert "T4_NOT_YET_IN_CAPTURE_WINDOW" in report["blockers"]
    assert not client.calls
