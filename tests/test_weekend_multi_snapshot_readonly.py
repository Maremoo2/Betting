"""TEST_ONLY regression contract for original-backed weekend comparison."""
import hashlib
import json
import runpy
from pathlib import Path

import pytest

mod = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "scripts/weekend_multi_snapshot_readonly.py"
))
compare = mod["compare"]
read = mod["_read_snapshot"]


def _write_source(root, path, data, observed):
    body = json.dumps(data, sort_keys=True).encode()
    digest = hashlib.sha256(body).hexdigest()
    originals = root / "originals"
    originals.mkdir(exist_ok=True)
    (originals / f"{digest}.json").write_bytes(body)
    return {
        "request_path": path, "response_sha256": digest,
        "response_completed_utc": observed,
        "original_relative_path": f"originals/{digest}.json",
        "success": True, "http_status": 200,
    }


def snapshot(root, *, observed="2026-11-06T09:32:40+00:00",
             odds=(2.4, 0.0), scratched=(), pool="S1_NR_2026-11-07#V85#5", number=5,
             race_key="S1_NR_2026-11-07", shares=(0.6, 0.4),
             provider_updated="2026-11-06T10:31:00"):
    root.mkdir()
    rows = [
        {"startNumber": n, "horseName": f"Runner {n}",
         "horseRegistrationNumber": f"TMP-{n}",
         "isScratched": n in scratched}
        for n in (1, 2)
    ]
    starts = _write_source(root, f"/racedays/{race_key}/starts",
                           {"result": {str(number): rows}}, observed)
    raw_win = {"result": [
        {"startNumber": n, "odds": odds[n - 1],
         "lastUpdated": provider_updated} for n in (1, 2)
    ]}
    win = _write_source(root, f"/game/{race_key}/betdistribution/winodds/{number}",
                        raw_win, observed)
    scratch = _write_source(root, f"/racedays/{race_key}/scratched",
                            {"result": {str(number): list(scratched)}}, observed)
    anchor = pool.rsplit("#", 1)[-1] if "#" in pool else "5"
    collective = _write_source(
        root, f"/game/{race_key}/betdistribution/investment/V85?raceNumber={anchor}",
        {"result": [{
            "raceNumber": number, "raceKey": f"{race_key}#{number}",
            "updatedTime": provider_updated,
            "investmentDistribution": [
                {"startNumber": n, "percentage": shares[n - 1] * 100}
                for n in (1, 2)
            ],
        }]}, observed,
    )
    leg = {
        "leg": 1, "race_no": number,
        "physical_race_id": f"RIKSTOTO:{race_key}:{number}",
        "pool_key": pool, "race_start_utc": "2026-11-07T14:00:00+00:00",
        "runners": [{
            "number": n, "name": f"Runner {n}", "active": n not in scratched,
            "horse_registration": f"TMP-{n}", "collective_share": (
                shares[n - 1] / sum(shares[k - 1] for k in (1, 2)
                                  if k not in scratched)
                if n not in scratched else None
            ),
        } for n in (1, 2)],
    }
    report = {
        "schema": "WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1",
        "bet_authority": False, "new_model_invocations": 0,
        "model_predictions_made": 0,
        "source_as_of_utc": "2026-11-06T09:32:00+00:00",
        "source_observation_completed_utc": observed,
        "original_receipts": [starts, win, scratch, collective],
        "weekend_rounds": [{"name": "BERGSAKER_V85",
                            "product": "V85", "legs": [leg]}],
        "composite_pool_wrappers_not_physical_races": [
            {"key": "X1_NR_2026-11-07", "name": "Klosterskogen/Bergsåker"}
        ],
    }
    (root / "weekend-race-intelligence.json").write_text(json.dumps(report))
    return root


def test_partial_win_distinguishes_missing_prices_from_missing_runners(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00")
    result = compare(a, b)
    leg = result["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["status"] == "COMPARABLE"
    assert leg["after"]["win_status"] == "MARKET_PARTIAL"
    assert leg["after"]["valid_win"] == 1
    assert leg["runners"][1]["win_odds"] is None
    assert leg["runners"][1]["win_odds_raw"] == 0.0
    assert all(r["model_status"] == "NOT_ASSESSED" for r in leg["runners"])
    assert all(r["decision"] == "NOT_EXECUTABLE" for r in leg["runners"])
    assert result["bet_signals"] == 0


def test_new_scratch_is_real_change_not_missing_price(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00",
                 scratched=(2,), odds=(2.8, -0.02))
    leg = compare(a, b)["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["new_scratches"] == [
        {"number": 2, "name": "Runner 2", "before": False, "after": True}
    ]
    assert leg["after"]["active"] == 1
    assert leg["runners"][1]["decision"] == "NOT_APPLICABLE"


def test_pool_key_change_blocks_market_comparison(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00",
                 pool="S1_NR_2026-11-07#V85#6")
    leg = compare(a, b)["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["status"] == "POOL_KEY_CHANGED"
    assert "price_changes" not in leg


def test_physical_race_id_change_blocks_comparison(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00", number=6)
    leg = compare(a, b)["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["status"] == "PHYSICAL_RACE_ID_CHANGED"


def test_duplicate_observation_clock_rejected(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b")
    with pytest.raises(ValueError, match="OBSERVATION_CLOCK_NOT_ADVANCING"):
        compare(a, b)


def test_missing_or_naive_utc_rejected(tmp_path):
    a = snapshot(tmp_path / "a")
    file = a / "weekend-race-intelligence.json"
    report = json.loads(file.read_text())
    report["source_as_of_utc"] = "2026-11-06T09:32:00"
    file.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="SOURCE_TIME_UNVERIFIED"):
        read(a)


def test_sha_mismatch_rejected(tmp_path):
    a = snapshot(tmp_path / "a")
    receipt = json.loads((a / "weekend-race-intelligence.json").read_text())["original_receipts"][1]
    (a / receipt["original_relative_path"]).write_text("tampered")
    with pytest.raises(ValueError, match="ORIGINAL_SHA_MISMATCH"):
        read(a)


def test_late_non_t4_is_not_certified(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-07T13:59:00+00:00")
    result = compare(a, b)
    assert result["actual_t4_captures"] == 0
    assert result["t4_certified"] is False
    assert result["model_assessed_runners"] == 0


def test_false_model_approval_rejected(tmp_path):
    a = snapshot(tmp_path / "a")
    file = a / "weekend-race-intelligence.json"
    report = json.loads(file.read_text())
    report["new_model_invocations"] = 1
    file.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="UNQUALIFIED_OR_MODELLED_SOURCE_REPORT"):
        read(a)


def test_x1_composite_is_not_extra_physical_leg(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00")
    result = compare(a, b)
    assert list(result["rounds"]) == ["BERGSAKER_V85"]
    assert len(result["rounds"]["BERGSAKER_V85"]["legs"]) == 1


def test_collective_changes_are_not_probabilities(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00",
                 shares=(0.35, 0.65), odds=(3.2, 4.5))
    leg = compare(a, b)["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert len(leg["collective_share_changes"]) == 2
    assert len(leg["price_changes"]) == 2
    assert all(r["p_win"] is None and r["model_market_deviation"] is None
               for r in leg["runners"])
    assert all(r["frozen_min_odds"] is None for r in leg["runners"])


def test_provider_naive_timestamp_never_certifies_complete_market(tmp_path):
    a = snapshot(tmp_path / "a", odds=(2.5, 4.5))
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00",
                 odds=(2.5, 4.5))
    leg = compare(a, b)["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["after"]["win_status"] == "SOURCE_TIME_UNVERIFIED"
    assert leg["latest_leg_readiness"]["win_full_field_ready"] is False


def test_unrelated_market_runner_is_a_join_defect(tmp_path):
    a = snapshot(tmp_path / "a")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00")
    p = b / "weekend-race-intelligence.json"
    report = json.loads(p.read_text())
    receipt = report["original_receipts"][1]
    # Restore consistency of original and SHA, then verify join failure.
    raw = {"result": [
        {"startNumber": 1, "odds": 2.2, "lastUpdated": "2026-11-06T10:31:00"},
        {"startNumber": 3, "odds": 4.1, "lastUpdated": "2026-11-06T10:31:00"},
    ]}
    replacement = _write_source(b, receipt["request_path"], raw,
                                receipt["response_completed_utc"])
    report["original_receipts"][1] = replacement
    p.write_text(json.dumps(report))
    leg = compare(a, b)["rounds"]["BERGSAKER_V85"]["legs"][0]
    assert leg["after"]["win_status"] == "JOIN_DEFECT"

def test_tampered_reported_collective_share_is_rejected(tmp_path):
    a = snapshot(tmp_path / "a")
    file = a / "weekend-race-intelligence.json"
    report = json.loads(file.read_text())
    report["weekend_rounds"][0]["legs"][0]["runners"][0]["collective_share"] = 0.99
    file.write_text(json.dumps(report))
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00")
    with pytest.raises(ValueError, match="REPORTED_COLLECTIVE_SHARE_NOT_ORIGINAL_VERIFIED"):
        compare(a, b)


def test_scratch_status_must_match_original_scratched_endpoint(tmp_path):
    a = snapshot(tmp_path / "a")
    file = a / "weekend-race-intelligence.json"
    report = json.loads(file.read_text())
    report["weekend_rounds"][0]["legs"][0]["runners"][0]["active"] = False
    file.write_text(json.dumps(report))
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00")
    with pytest.raises(ValueError, match="ORIGINAL_RUNNER_IDENTITY_OR_SCRATCH_MISMATCH"):
        compare(a, b)


def test_wrong_collective_pool_key_is_rejected(tmp_path):
    a = snapshot(tmp_path / "a", pool="UNTRUSTED_POOL")
    b = snapshot(tmp_path / "b", observed="2026-11-06T09:34:00+00:00")
    with pytest.raises(ValueError, match="POOL_KEY_OR_RACEDAY_CONFLICT"):
        compare(a, b)
