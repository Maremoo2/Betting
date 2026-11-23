"""Synthetic engineering contracts are distinct from archived replay evidence."""
import copy
import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from hbi import benchmark002_retrospective as bench
from hbi import benchmark002_shadow as shadow
from rikstoto_crawler.transport import digest


def raw(doc):
    value = json.dumps(doc).encode()
    return value, hashlib.sha256(value).hexdigest()


def model():
    return {"model": shadow.MODEL, "feature_order": list(shadow.FEATURE_ORDER),
            "training_last_year": 2022, "calibration_year": 2023, "test_year": 2024,
            "ridge": .03, "market_domain": "TERMINAL_RETROSPECTIVE",
            "fundamental_weights": [.2]*9, "market_fundamental_weights": [1., .1]}


def packet():
    runners = [{"selection_id": str(n), "registration": f"57800102013000{n}",
                "horse_id": f"RIKSTOTO_REG:57800102013000{n}", "horse_name": f"Fixture {n}",
                "scratched": False} for n in (1, 2)]
    return {"race_id": "RIKSTOTO:TEST_NR_2024-01-01:1", "day": "2024-01-01",
            "country": "NO", "sport": "T", "scope": "RETROSPECTIVE", "source_quality": "TEST_ONLY",
            "start_at": None, "runners": runners,
            "state": {r["horse_id"]: {"history": [["2023-12-01", True, 1., 10., .2]], "rating": .1}
                      for r in runners}}


def market():
    body = {"success": True, "result": [{"startNumber": 1, "odds": 3.}, {"startNumber": 2, "odds": 2.}]}
    path = "/game/TEST_NR_2024-01-01/betdistribution/winodds/1"
    return {"path": path, "url": "https://www.rikstoto.no/api"+path, "body": body,
            "body_sha256": digest(body), "fetched_at": "2026-01-01T12:00:00+00:00"}


NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)


def test_fundamental_then_market_normalizes_and_has_no_authority(tmp_path):
    m, mh = raw(model())
    p, ph = raw(packet())
    path = tmp_path/"freeze.json"
    frozen = shadow.freeze_fundamental(m, mh, p, ph, path, NOW)
    assert sum(frozen["fundamental"].values()) == pytest.approx(1)
    q, qh = raw(market())
    decision = shadow.combine_original(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                m, mh, q, qh, tmp_path/"decision.json", NOW+timedelta(seconds=1))
    assert sum(r["combined_p"] for r in decision["rows"]) == pytest.approx(1)
    assert all(r["status"].startswith("SHADOW_") and not r["bet_authority"] for r in decision["rows"])
    assert all(r["EV"] == pytest.approx(r["WIN"]*r["combined_p"]-1) for r in decision["rows"])
    assert decision["PIT_CERTIFIED"] is False
    with pytest.raises(FileExistsError):
        shadow.freeze_fundamental(m, mh, p, ph, path, NOW)


def test_feature_parity_with_existing_formula():
    p = packet()
    active, matrix = shadow.feature_matrix(p)
    h = [(date(2023, 12, 1), True, 1., 10., .2)]
    expected = bench.feature(h, .1, date(2024, 1, 1), len(active))
    assert np.array_equal(matrix[0], expected)


@pytest.mark.parametrize("change", ["identity", "missing_history", "future", "same_day", "duplicate",
                                     "scratch_all", "label", "market", "nonfinite", "lockbox"])
def test_bad_feature_packet_never_creates_a_freeze(tmp_path, change):
    p = packet()
    state = p["state"][p["runners"][0]["horse_id"]]
    if change == "identity":
        p["runners"][0]["registration"] = "WRONG"
    elif change == "missing_history":
        state["history"] = []
    elif change in {"future", "same_day"}:
        state["history"][0][0] = "2024-01-02" if change == "future" else "2024-01-01"
    elif change == "duplicate":
        p["runners"][1] = copy.deepcopy(p["runners"][0])
    elif change == "scratch_all":
        for r in p["runners"]:
            r["scratched"] = True
    elif change == "label":
        p["winner"] = "1"
    elif change == "market":
        p["market_odds"] = {"1": 3.}
    elif change == "nonfinite":
        state["rating"] = float("inf")
    elif change == "lockbox":
        state["history"][0][0] = "2025-01-01"
    m, mh = raw(model())
    data, checksum = raw(p)
    path = tmp_path/"freeze.json"
    with pytest.raises(ValueError):
        shadow.freeze_fundamental(m, mh, data, checksum, path, NOW)
    assert not path.exists()


@pytest.mark.parametrize("value", ["2026-11-19T12:00:00", "2026-11-19T12:00:00+00:00"])
def test_clock_and_t4_are_fail_closed(tmp_path, value):
    p = packet()
    p.update(scope="PROSPECTIVE", day="2026-11-19", start_at="2026-11-19T12:04:00+00:00")
    m, mh = raw(model())
    data, checksum = raw(p)
    with pytest.raises(ValueError):
        shadow.freeze_fundamental(m, mh, data, checksum, tmp_path/"freeze.json", datetime.fromisoformat(value))


def test_prospective_cannot_use_retrospective_scope(tmp_path):
    p = packet()
    p["day"] = "2026-11-20"
    m, mh = raw(model())
    data, checksum = raw(p)
    with pytest.raises(ValueError, match="TARGET_NOT_PAST"):
        shadow.freeze_fundamental(m, mh, data, checksum, tmp_path/"freeze.json", NOW)


def test_asserted_canonical_success_is_not_a_verified_live_adapter(tmp_path):
    p = packet()
    p.update(scope="PROSPECTIVE", day="2026-11-20", start_at="2026-11-20T12:00:00+00:00",
             clock_offset_ms=0, canonical_collector_row={"race_id": p["race_id"]})
    m, mh = raw(model())
    data, checksum = raw(p)
    with pytest.raises(ValueError, match="LIVE_STATE_ADAPTER_NOT_ATTESTED"):
        shadow.freeze_fundamental(m, mh, data, checksum, tmp_path/"freeze.json", NOW)
    assert not (tmp_path/"freeze.json").exists()


def test_missing_canonical_source_blocks_before_model(tmp_path):
    p = packet()
    p.update(scope="PROSPECTIVE", day="2026-11-20", start_at="2026-11-20T12:00:00+00:00", clock_offset_ms=0)
    m, mh = raw(model())
    data, checksum = raw(p)
    with pytest.raises(ValueError, match="CANONICAL_COLLECTOR"):
        shadow.freeze_fundamental(m, mh, data, checksum, tmp_path/"freeze.json", NOW)


@pytest.mark.parametrize("change", ["race", "body_hash", "missing_runner", "duplicate", "bad_odds", "raw_hash"])
def test_invalid_market_cannot_publish_decisions(tmp_path, change):
    m, mh = raw(model())
    p, ph = raw(packet())
    path = tmp_path/"freeze.json"
    shadow.freeze_fundamental(m, mh, p, ph, path, NOW)
    q = market()
    if change == "race":
        q["path"] = "/wrong"
    elif change == "body_hash":
        q["body_sha256"] = "f"*64
    elif change == "missing_runner":
        q["body"]["result"].pop()
    elif change == "duplicate":
        q["body"]["result"].append(q["body"]["result"][0])
    elif change == "bad_odds":
        q["body"]["result"][0]["odds"] = 1
    if change not in {"body_hash", "race"}:
        q["body_sha256"] = digest(q["body"])
    data, checksum = raw(q)
    if change == "raw_hash":
        checksum = "0"*64
    with pytest.raises(ValueError):
        shadow.combine_original(path, hashlib.sha256(path.read_bytes()).hexdigest(),
            m, mh, data, checksum, tmp_path/"decision.json", NOW)
    assert not (tmp_path/"decision.json").exists()


def test_original_hash_and_weight_shape():
    m, checksum = raw(model())
    with pytest.raises(ValueError, match="SHA"):
        shadow.load_artifact(m+b" ", checksum)
    wrong = model()
    wrong["fundamental_weights"].pop()
    m, checksum = raw(wrong)
    with pytest.raises(ValueError, match="WEIGHTS"):
        shadow.load_artifact(m, checksum)


def test_manual_command_cannot_backdate_and_preserves_freeze(tmp_path):
    m, mh = raw(model())
    p, ph = raw(packet())
    (tmp_path/"model.json").write_bytes(m)
    (tmp_path/"input.json").write_bytes(p)
    args = ["fundamental", "--artifact", str(tmp_path/"model.json"), "--artifact-sha256", mh,
            "--input", str(tmp_path/"input.json"), "--input-sha256", ph,
            "--output", str(tmp_path/"frozen.json")]
    assert shadow.main(args) == 0
    original = (tmp_path/"frozen.json").read_bytes()
    assert shadow.main(args) == 2
    assert (tmp_path/"frozen.json").read_bytes() == original


@pytest.mark.parametrize("change", ["stale", "naive", "future", "t4"])
def test_existing_research_freshness_window(change):
    f = {"created_at": "2026-11-19T11:40:00+00:00", "start_at": "2026-11-19T12:10:00+00:00"}
    q = {"fetched_at": "2026-11-19T11:59:59+00:00"}
    current = NOW
    if change == "stale":
        q["fetched_at"] = "2026-11-19T11:54:59+00:00"
    elif change == "naive":
        q["fetched_at"] = "2026-11-19T11:59:59"
    elif change == "future":
        q["fetched_at"] = "2026-11-19T12:00:01+00:00"
    elif change == "t4":
        current += timedelta(minutes=6)
    with pytest.raises(ValueError):
        shadow.check_market_clock(f, q, current)
