"""Synthetic engineering attacks; authentic evidence is kept in the task output."""
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from hbi import benchmark002_retrospective as bench
from hbi.benchmark002_shadow import FEATURE_ORDER, MODEL
from hbi.v2_feature_state import advance, append_research_ledger, freeze_state, normalize_original
from hbi.v2_limited_research import VARIANT, combine_limited, freeze_limited, packet_for_field
from hbi.v2_result_codes import result_code


def source(day="2024-01-01"):
    key = "TEST_NR_"+day
    roster = [{"startNumber": i, "horseRegistrationNumber": f"57800102013000{i}",
               "horseName": f"Fixture {i}", "isScratched": False, "raceNumber": 1, "raceKey": key+"#1"}
              for i in (1, 2)]
    rows = [{**r, "place": i, "order": i, "kmTime": "15,1a" if i==1 else "15,9a",
             "distance": 2100, "prize": 100000 if i==1 else 50000} for i, r in enumerate(roster, 1)]
    body = {"success": True, "result": {"startTime": day+"T12:00:00", "startMethod": "A",
                                         "isComplete": True, "results": rows}}
    raw = json.dumps(body).encode()
    receipt = {"raw_sha256": hashlib.sha256(raw).hexdigest(), "http_status": 200,
               "source_uri": f"https://www.rikstoto.no/api/results/raceDays/{key}/1/completeresults",
               "observed_at_utc": day+"T13:00:00+00:00"}
    return raw, receipt, roster


def empty():
    return {"last_day": "2023-12-31", "histories": {}, "ratings": {}, "event_refs": {},
            "identities": {}, "applied_races": {}, "known_gaps": []}


def field(day="2024-01-01"):
    raw, receipt, roster = source(day)
    return normalize_original(raw, receipt, roster, country="NO", source_id="TEST_ONLY")


def test_incremental_equals_bulk_and_prior_freeze_unchanged(tmp_path):
    first, second = field(), field("2024-01-02")
    cutoff = "2024-01-03T10:00:00+00:00"
    bulk, _ = advance(tmp_path, empty(), [second, first], cutoff)
    part, _ = advance(tmp_path, empty(), [first], cutoff)
    path = tmp_path/"old.json"
    checksum = freeze_state(path, part)
    streamed, _ = advance(tmp_path, part, [second], cutoff)
    assert streamed == bulk
    assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    repeat, receipt = advance(tmp_path, streamed, [first, second], cutoff)
    assert receipt["new_fields"] == 0 and repeat == streamed
    assert len(part["histories"][first["events"][0]["horse_id"]]) == 1
    assert bulk["PIT_CERTIFIED"] is False and bulk["FULL_F3_COVERAGE"] is False


def test_rating_has_original_day_delayed_step_and_normalization(tmp_path):
    state, _ = advance(tmp_path, empty(), [field()], "2024-01-02T12:00:00+00:00")
    assert sorted(state["ratings"].values()) == pytest.approx([-.075, .075])
    assert sorted(len(v) for v in state["histories"].values()) == [1, 1]
    assert all(len(v)==1 for v in state["event_refs"].values())


def test_same_local_day_pending_even_across_utc_midnight(tmp_path):
    state, receipt = advance(tmp_path, empty(), [field()], "2024-01-01T23:30:00+00:00")
    # Oslo is already 2 January: original 1 January event can be committed.
    assert receipt["new_fields"] == 1
    state, receipt = advance(tmp_path, empty(), [field()], "2024-01-01T13:30:00+00:00")
    assert receipt["new_fields"] == 0 and receipt["pending_same_day"]
    assert state["histories"] == {}


@pytest.mark.parametrize("clock", ["2024-01-01T13:00:00+00:00", "2024-01-01T12:59:59+00:00"])
def test_source_at_or_after_cutoff_excluded(tmp_path, clock):
    state, receipt = advance(tmp_path, empty(), [field()], clock)
    assert state["histories"] == {} and receipt["excluded"]


def test_naive_and_base_availability_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="CUTOFF"):
        advance(tmp_path, empty(), [field()], "2024-01-03T12:00:00")
    state, _ = advance(tmp_path, empty(), [field()], "2024-01-03T12:00:00+00:00")
    state["applied_races"][field()["race_id"]]["archived_at"] = "2026-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="BASE_SOURCE"):
        advance(tmp_path, state, [], "2024-01-03T12:00:00+00:00")


def test_revision_and_backfill_require_rebuild_not_update(tmp_path):
    first = field()
    state, _ = advance(tmp_path, empty(), [first, field("2024-01-03")], "2024-01-04T12:00:00+00:00")
    changed = copy.deepcopy(first)
    changed["source_sha256"] = "f"*64
    with pytest.raises(ValueError, match="REVISION"):
        advance(tmp_path, state, [changed], "2024-01-05T12:00:00+00:00")
    with pytest.raises(ValueError, match="BACKFILL"):
        advance(tmp_path, state, [field("2024-01-02")], "2024-01-05T12:00:00+00:00")


@pytest.mark.parametrize("attack", ["hash", "identity", "incomplete", "source", "unknown_code", "dead_heat", "country", "2025"])
def test_original_adapter_fail_closed(attack):
    raw, receipt, roster = source("2025-01-01" if attack=="2025" else "2024-01-01")
    doc = json.loads(raw)
    if attack == "hash":
        receipt["raw_sha256"] = "0"*64
    elif attack == "identity":
        roster[0]["horseRegistrationNumber"] = "578001020999999"
    elif attack == "incomplete":
        doc["result"]["isComplete"] = False
    elif attack == "source":
        receipt["source_uri"] = receipt["source_uri"].replace("www.rikstoto.no", "other.example")
    elif attack == "unknown_code":
        doc["result"]["results"][0]["kmTime"] = "UNKNOWN_CODE"
    elif attack == "dead_heat":
        doc["result"]["results"][1]["place"] = 1
    if attack not in {"hash", "identity", "source", "country", "2025"}:
        raw = json.dumps(doc).encode()
        receipt["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        normalize_original(raw, receipt, roster, country="FR" if attack=="country" else "NO", source_id="TEST_ONLY")


def test_literal_unknown_status_is_not_false_or_imputed():
    value = result_code({"place": 0, "kmTime": "", "order": 5}, False)
    assert value["gallop_status"] is None and value["disqualified"] is None
    assert value["race_time"]["value"] is None


def test_2026_explicit_adapter_does_not_open_2025(tmp_path):
    f = field("2026-01-01")
    state, receipt = advance(tmp_path, empty(), [f], "2026-01-02T12:00:00+00:00")
    assert receipt["new_fields"] == 1 and state["last_day"] == "2026-01-01"
    with pytest.raises(ValueError):
        bench.historical_day("2026-01-01")  # old benchmark default remains frozen
    bad = copy.deepcopy(f)
    bad["day"] = "2025-01-01"
    with pytest.raises(ValueError, match="LOCKBOX"):
        advance(tmp_path, empty(), [bad], "2026-01-02T12:00:00+00:00")


def test_ledger_idempotence_conflict_and_no_rewrite(tmp_path):
    path = tmp_path/"ledger.csv"
    assert append_research_ledger(path, "r1", {"x": 1})
    original = path.read_bytes()
    assert not append_research_ledger(path, "r1", {"x": 1})
    with pytest.raises(ValueError, match="CONFLICT"):
        append_research_ledger(path, "r1", {"x": 2})
    assert path.read_bytes() == original
    assert append_research_ledger(path, "r2", {"x": 2})
    path.write_text(path.read_text(encoding="utf-8").replace('""x"": 2', '""x"": 3'), encoding="utf-8")
    with pytest.raises(ValueError, match="TAMPERED"):
        append_research_ledger(path, "r1", {"x": 1})


def test_limited_research_is_not_qualified_even_when_math_is_complete(tmp_path):
    cutoff = "2026-11-18T12:00:00+00:00"
    state, _ = advance(tmp_path, empty(), [field("2026-11-17")], cutoff)
    _, _, roster = source("2026-11-19")
    starts = json.dumps({"success": True, "result": {"1": roster}}).encode()
    receipt = {"url": "https://www.rikstoto.no/api/racedays/TEST_NR_2026-11-19/starts",
               "sha256": hashlib.sha256(starts).hexdigest(), "status": 200, "completed_at": cutoff}
    packet = packet_for_field(state, "TEST_NR_2026-11-19", 1, starts, receipt,
                              "2026-11-19T18:00:00+00:00", country="NO")
    model = {"model": MODEL, "feature_order": list(FEATURE_ORDER), "training_last_year": 2022,
             "calibration_year": 2023, "test_year": 2024, "ridge": .03,
             "market_domain": "TERMINAL_RETROSPECTIVE", "fundamental_weights": [.1]*9,
             "market_fundamental_weights": [1., .1]}
    raw = json.dumps(model).encode()
    now = datetime(2026, 11, 19, 12, tzinfo=UTC)
    args = (tmp_path/"limited.json", raw, hashlib.sha256(raw).hexdigest(), packet, "b"*64, {"variant": VARIANT})
    with pytest.raises(ValueError, match="OPT_IN"):
        freeze_limited(*args, now=now, clock_offset_ms=0)
    frozen = freeze_limited(*args, now=now, clock_offset_ms=0, explicit_research_opt_in=True)
    assert sum(frozen["conditional_fundamental_p"].values()) == pytest.approx(1)
    assert frozen["qualified_full_field"] is False and frozen["PIT_CERTIFIED"] is False
    market = json.dumps({"success": True, "result": [
        {"startNumber": 1, "odds": 3., "lastUpdated": now.isoformat()},
        {"startNumber": 2, "odds": 2., "lastUpdated": now.isoformat()}]}).encode()
    mreceipt = {"url": "https://www.rikstoto.no/api/game/TEST_NR_2026-11-19/betdistribution/winodds/1",
                "status": 200, "sha256": hashlib.sha256(market).hexdigest(),
                "started_at": (now+timedelta(seconds=1)).isoformat(), "completed_at": (now+timedelta(seconds=2)).isoformat()}
    fraw = (tmp_path/"limited.json").read_bytes()
    result = combine_limited(fraw, hashlib.sha256(fraw).hexdigest(), raw, hashlib.sha256(raw).hexdigest(),
                             market, mreceipt, now=now+timedelta(seconds=3))
    assert result["qualified_signals"] == 0
    assert all(r["qualified_decision"]=="BLOCKED_SOURCE" for r in result["rows"])
    assert sum(r["conditional_combined_p"] for r in result["rows"]) == pytest.approx(1)
    bad = dict(mreceipt, completed_at=(now-timedelta(seconds=2)).isoformat())
    with pytest.raises(ValueError, match="ORDER"):
        combine_limited(fraw, hashlib.sha256(fraw).hexdigest(), raw, hashlib.sha256(raw).hexdigest(),
                         market, bad, now=now+timedelta(seconds=3))


@pytest.mark.parametrize("attack", [None, "race", "identity", "before_result", "freeze_sha", "probability"])
def test_result_append_preserves_forecast_and_checks_original(tmp_path, attack):
    from hbi.v2_limited_research import append_limited_result
    raw, receipt, roster = source("2026-11-19")
    frozen = {"schema": "V2_LIMITED_RESEARCH_FREEZE_V1", "variant": VARIANT,
              "qualified_full_field": False, "race_id": "RIKSTOTO:TEST_NR_2026-11-19:1",
              "start_at": "2026-11-19T12:00:00+00:00", "frozen_at_utc": "2026-11-19T11:00:00+00:00",
              "runners": [{"selection_id": str(i), "horse_id": "RIKSTOTO_REG:"+r["horseRegistrationNumber"]}
                          for i, r in enumerate(roster, 1)], "conditional_fundamental_p": {"1": .6, "2": .4}}
    if attack == "race": frozen["race_id"] += "9"
    if attack == "identity": frozen["runners"][0]["horse_id"] = "RIKSTOTO_REG:578001020999999"
    if attack == "before_result": receipt["observed_at_utc"] = "2026-11-19T11:59:59+00:00"
    if attack == "probability": frozen["conditional_fundamental_p"]["1"] = -.6
    fraw = json.dumps(frozen).encode(); fsha = hashlib.sha256(fraw).hexdigest()
    if attack == "freeze_sha": fsha = "0"*64
    ledger = tmp_path/"research.csv"
    append_research_ledger(ledger, "fixture|PRE", {"record_type": "LIMITED_RESEARCH_FORECAST",
        "race_id": frozen["race_id"], "fundamental_freeze_sha256": fsha,
        "conditional_fundamental_p": frozen["conditional_fundamental_p"],
        "frozen_at_utc": frozen["frozen_at_utc"]})
    before = ledger.read_bytes()
    if attack:
        with pytest.raises(ValueError):
            append_limited_result(ledger, fraw, fsha, raw, receipt, roster, country="NO")
        assert ledger.read_bytes() == before
    else:
        assert append_limited_result(ledger, fraw, fsha, raw, receipt, roster, country="NO")
        old = ledger.read_bytes()
        assert not append_limited_result(ledger, fraw, fsha, raw, receipt, roster, country="NO")
        assert ledger.read_bytes() == old and fraw == json.dumps(frozen).encode()
        assert "LIMITED_RESEARCH_RESULT" in ledger.read_text()


@pytest.mark.parametrize("kind", ["valid_and_incomplete", "two_valid_conflicting", "bad_hash", "duplicates"])
def test_recovery_validates_originals_before_version_conflict(kind):
    from hbi.v2_source_recovery import recover_versions
    raw, receipt, roster = source()
    other = json.loads(raw)
    if kind == "valid_and_incomplete": other["result"]["results"] = other["result"]["results"][:1]
    if kind == "two_valid_conflicting": other["result"]["results"][0]["prize"] += 1
    second = json.dumps(other).encode()
    rec2 = dict(receipt, raw_sha256=hashlib.sha256(second).hexdigest())
    if kind == "bad_hash": rec2["raw_sha256"] = "0"*64
    candidates = [(raw, receipt, "original"), (second, rec2, "other")]
    if kind == "bad_hash": candidates = candidates[1:]
    result, audit = recover_versions(candidates, roster, country="NO")
    assert (result is not None) == (kind in {"valid_and_incomplete", "duplicates"})
    if kind == "two_valid_conflicting": assert audit["reason"] == "MULTIPLE_VALID_RESULT_VERSIONS"
    if kind in {"bad_hash", "two_valid_conflicting"}: assert audit["status"] == "SOURCE_DATA_INVALID"
    if kind == "valid_and_incomplete": assert audit["rejected"]


@pytest.fixture
def pricing_case(tmp_path):
    state, _ = advance(tmp_path, empty(), [field("2026-11-17")], "2026-11-18T12:00:00+00:00")
    _, _, roster = source("2026-11-19")
    starts = json.dumps({"success": True, "result": {"1": roster}}).encode()
    packet = packet_for_field(state, "TEST_NR_2026-11-19", 1, starts,
        {"url": "https://www.rikstoto.no/api/racedays/TEST_NR_2026-11-19/starts", "status": 200,
         "sha256": hashlib.sha256(starts).hexdigest(), "completed_at": "2026-11-18T12:00:00+00:00"},
        "2026-11-19T18:00:00+00:00", country="NO")
    model = {"model": MODEL, "feature_order": list(FEATURE_ORDER), "training_last_year": 2022,
        "calibration_year": 2023, "test_year": 2024, "ridge": .03, "market_domain": "TERMINAL_RETROSPECTIVE",
        "fundamental_weights": [.1]*9, "market_fundamental_weights": [1., .1]}
    artifact = json.dumps(model).encode(); artifact_sha = hashlib.sha256(artifact).hexdigest()
    now = datetime(2026, 11, 19, 12, tzinfo=UTC)
    path=tmp_path/"frozen.json"
    freeze_limited(path, artifact, artifact_sha, packet, "b"*64, {"variant": VARIANT},
        now=now, clock_offset_ms=0, explicit_research_opt_in=True)
    raw=path.read_bytes()
    return raw,hashlib.sha256(raw).hexdigest(),artifact,artifact_sha,packet,now


@pytest.mark.parametrize("stamp", [None,"2026-11-19T12:00:00","2026-11-19T11:54:00+00:00","2026-11-19T12:01:00+00:00"])
def test_limited_pricing_rejects_unverified_stale_or_future_provider_clocks(pricing_case, stamp):
    raw, sha, artifact, asha, _, now = pricing_case
    market=json.dumps({"success":True,"result":[{"startNumber":n,"odds":3.,"lastUpdated":stamp} for n in [1,2]]}).encode()
    receipt={"url":"https://www.rikstoto.no/api/game/TEST_NR_2026-11-19/betdistribution/winodds/1",
        "status":200,"sha256":hashlib.sha256(market).hexdigest(),
        "started_at":(now+timedelta(seconds=1)).isoformat(),"completed_at":(now+timedelta(seconds=2)).isoformat()}
    with pytest.raises(ValueError,match="PROVIDER_MARKET"):
        combine_limited(raw,sha,artifact,asha,market,receipt,now=now+timedelta(seconds=3))


def test_full_market_audit_does_not_assume_timezone_or_drop_scratches(pricing_case):
    from hbi.v2_source_recovery import audit_market
    _,_,_,_,packet,now=pricing_case
    packet["runners"].append({"selection_id":"3","scratched":True})
    body={"success":True,"result":[{"startNumber":n,"odds":3.,"lastUpdated":"2026-11-19T12:00:00"} for n in [1,2]]+
        [{"startNumber":3,"odds":-.02,"lastUpdated":"2026-11-19T12:00:00"}]}
    raw=json.dumps(body).encode()
    receipt={"status":200,"sha256":hashlib.sha256(raw).hexdigest(),
        "url":"https://www.rikstoto.no/api/game/TEST_NR_2026-11-19/betdistribution/winodds/1",
        "started_at":now.isoformat(),"completed_at":now.isoformat()}
    audit=audit_market(raw,receipt,packet,now=now)
    assert audit["active_quote_count"]==2 and audit["known_scratched_quote_selections"]==["3"]
    assert audit["qualified_combination_allowed"] is False
    assert any(e.startswith("PROVIDER_CLOCK_NAIVE") for e in audit["errors"])


def test_pre_required_and_entire_chain_checked_before_post(pricing_case, tmp_path):
    from hbi.v2_limited_research import require_registered_pre
    raw,sha,_,_,_,_=pricing_case;frozen=json.loads(raw);ledger=tmp_path/"journal.csv"
    with pytest.raises(ValueError,match="PRE_MISSING"):
        require_registered_pre(ledger,raw,sha)
    payload={"record_type":"LIMITED_RESEARCH_FORECAST","race_id":frozen["race_id"],
        "fundamental_freeze_sha256":sha,"conditional_fundamental_p":frozen["conditional_fundamental_p"],
        "frozen_at_utc":frozen["frozen_at_utc"]}
    append_research_ledger(ledger,"PRE",payload)
    append_research_ledger(ledger,"OTHER",{"x":1})
    assert require_registered_pre(ledger,raw,sha)==frozen
    ledger.write_text(ledger.read_text().replace('""x"": 1','""x"": 2'))
    with pytest.raises(ValueError,match="TAMPERED"):
        require_registered_pre(ledger,raw,sha)


def test_manual_source_command_verifies_bytes_and_never_overwrites(tmp_path):
    from hbi.v2_source_recovery import main
    raw,receipt,roster=source()
    paths={}
    for name,body in {"state":empty(),"roster":{"result":{"1":roster}},"receipt":receipt}.items():
        paths[name]=tmp_path/(name+".json");paths[name].write_text(json.dumps(body))
    result=tmp_path/"original.raw";result.write_bytes(raw)
    bundle=tmp_path/"sources.json";bundle.write_text(json.dumps({"races":[{
        "race_id":"RIKSTOTO:TEST_NR_2024-01-01:1","race_number":1,"country":"NO",
        "roster_file":str(paths["roster"]),"roster_sha256":hashlib.sha256(paths["roster"].read_bytes()).hexdigest(),
        "candidates":[{"raw_file":str(result),"receipt_file":str(paths["receipt"])}]}]}))
    args=["--state",str(paths["state"]),"--state-sha256",hashlib.sha256(paths["state"].read_bytes()).hexdigest(),
        "--source-bundle",str(bundle),"--workspace",str(tmp_path),"--output",str(tmp_path/"next")]
    assert main(args)==0
    receipt2=json.loads((tmp_path/"next/receipt.json").read_bytes())
    assert receipt2["new_fields"]==1 and receipt2["PIT_CERTIFIED"] is False
    assert receipt2["MANUAL_EXECUTION_ONLY"] is True
    with pytest.raises(ValueError,match="OUTPUT_EXISTS"):
        main(args)
