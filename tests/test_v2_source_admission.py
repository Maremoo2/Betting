"""Synthetic receipt-review contracts. No real source pins or PIT claims are added."""
import hashlib
import json
from datetime import timedelta

import pytest
from test_daily_v2 import NOW, collector_case  # noqa: F401 (shared synthetic Collector fixture)

from hbi import admission_originals
from hbi.benchmark002_shadow import freeze_fundamental
from hbi.daily_v2 import ARTIFACT, ARTIFACT_SHA256, collector_packet, execute, qualified_market
from hbi.v2_feature_state import advance
from hbi.v2_limited_research import packet_for_field
from hbi.v2_source_admission import assess_sources
from hbi.v2_source_recovery import load_bundle


@pytest.fixture
def admitted_contract(collector_case, monkeypatch):  # noqa: F811 (pytest fixture injection)
    request, _, _ = collector_case
    root = request.output.parent
    current = collector_packet(request.collector_root, request.race_id, now=NOW)
    old_key = "BI_NR_2026-11-18"
    roster = [{**r, "raceKey": old_key+"#1"} for r in current["roster"]]
    starts = root/"prior_starts.json"
    starts.write_text(json.dumps({"success": True, "result": {"1": roster}}))
    results = [{**r, "place": n, "order": n, "kmTime": "15,1a" if n==1 else "15,9a",
                "distance": 2100, "prize": 100000 if n==1 else 50000} for n, r in enumerate(roster, 1)]
    raw = json.dumps({"success": True, "result": {"startTime": "2026-11-18T12:00:00",
        "startMethod": "A", "isComplete": True, "results": results}}).encode()
    result = root/"prior_result.raw"
    result.write_bytes(raw)
    receipt = root/"prior_result_receipt.json"
    receipt.write_text(json.dumps({"raw_sha256": hashlib.sha256(raw).hexdigest(), "http_status": 200,
        "source_uri": f"https://www.rikstoto.no/api/results/raceDays/{old_key}/1/completeresults",
        "observed_at_utc": "2026-11-19T10:00:00+00:00"}))
    bundle = root/"graph.json"
    bundle.write_text(json.dumps({"races": [{"race_id": "RIKSTOTO:"+old_key+":1",
        "race_number": 1, "country": "NO", "roster_file": str(starts),
        "roster_sha256": hashlib.sha256(starts.read_bytes()).hexdigest(),
        "candidates": [{"raw_file": str(result), "receipt_file": str(receipt)}]}]}))
    fields, _ = load_bundle(bundle)
    empty = {"last_day": "2014-12-31", "histories": {}, "ratings": {}, "event_refs": {},
             "identities": {}, "applied_races": {}, "known_gaps": []}
    state, _ = advance(root, empty, fields, "2026-11-20T11:00:00+00:00")
    state_raw = json.dumps(state).encode()
    request.state.write_bytes(state_raw)
    state_sha = hashlib.sha256(state_raw).hexdigest()
    request.state_sha256 = state_sha
    packet = packet_for_field(state, current["key"], 1, current["starts_raw"], current["starts_receipt"],
        current["start_at"], country="NO")
    packet["original_program_sha256"] = current["source_hashes"]["program"]
    packet["collector_source_hashes"] = current["source_hashes"]
    packet.update(scope="PROSPECTIVE", clock_offset_ms=0., canonical_collector_row={"race_id": request.race_id})
    coverage = {"schema": "VERIFIED_V2_COMPLETE_STATE_V1", "race_id": packet["race_id"],
        "start_at": packet["start_at"], "state_sha256": state_sha, "model_artifact_sha256": ARTIFACT_SHA256,
        "source_policy": "RIKSTOTO_ONLY", "collector_source_hashes": current["source_hashes"],
        "graph_bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "complete_careers_and_opponent_graph": True, "exact_versions_available_before_cutoff": True}
    registry = {"schema": "VERIFIED_V2_REGISTRY_FIELD_V1", "race_id": packet["race_id"],
        "startlist_sha256": packet["startlist_sha256"], "runners": [
            {"selection_id": r["selection_id"], "native_registration": r["registration"],
             "horse_id": "FIXTURE_REGISTER:"+r["selection_id"], "source": "synthetic independent registry",
             "source_version": "CONTRACT_TEST_ONLY"} for r in packet["runners"]]}
    scratches = {"schema": "VERIFIED_INDEPENDENT_SCRATCH_V1", "race_id": packet["race_id"],
                "roster": [[r["selection_id"], r["scratched"]] for r in packet["runners"]]}
    evidence = {"graph_bundle": str(bundle), "collector_root": str(request.collector_root)}
    pins = []
    for key, role, doc in [("coverage", "V2_STATE_COVERAGE", coverage),
                           ("registry", "REGISTRY_BINDING", registry),
                           ("scratchings", "INDEPENDENT_SCRATCH", scratches)]:
        file = root/(key+".json")
        file.write_text(json.dumps(doc))
        sha = hashlib.sha256(file.read_bytes()).hexdigest()
        uri = f"https://contract-test.example/{key}"
        evidence[key] = {"uri": uri, "sha256": sha, "original_file": str(file),
                         "observed_at_utc": "2026-11-20T11:00:00+00:00"}
        pins.append((role, uri, sha, NOW-timedelta(hours=1)))
    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", frozenset(pins))
    file = root/"evidence.json"
    file.write_text(json.dumps(evidence))
    request.source_evidence = file
    request.source_evidence_sha256 = hashlib.sha256(file.read_bytes()).hexdigest()
    return request, packet, state_raw, evidence


def test_reviewed_bound_originals_and_raw_graph_can_qualify_contract(admitted_contract):
    request, _, _, _ = admitted_contract
    report = execute(request, now=NOW, clock_reader=lambda host: 0.)
    assert report["status"] == "PIT_QUALIFIED_FUNDAMENTAL"
    assert report["PIT_CERTIFIED"] is True and report["BET_AUTHORITY"] is False
    assert report["active_runners"] == 2 and report["fundamental_sum"] == pytest.approx(1)
    assert report["WIN_read"] is False


@pytest.mark.parametrize("attack", ["no_review", "wrong_hash", "late", "naive", "same_feed",
                                   "changed_state", "changed_packet", "missing_graph"])
def test_fabricated_late_or_conflicting_source_cannot_qualify(admitted_contract, monkeypatch, attack):
    request, packet, raw, evidence = admitted_contract
    if attack == "no_review":
        monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", frozenset())
    elif attack == "wrong_hash":
        evidence["registry"]["sha256"] = "0"*64
    elif attack == "late":
        evidence["coverage"]["observed_at_utc"] = "2026-11-20T17:56:00+00:00"
    elif attack == "naive":
        evidence["scratchings"]["observed_at_utc"] = "2026-11-20T11:00:00"
    elif attack == "same_feed":
        evidence["scratchings"]["uri"] = "https://www.rikstoto.no/api/scratchings"
    elif attack == "changed_state":
        raw = raw.replace(b'0.075', b'0.175')
    elif attack == "changed_packet":
        packet["state"][packet["runners"][0]["horse_id"]]["rating"] += .1
    elif attack == "missing_graph":
        evidence["graph_bundle"] = str(request.output.parent/"absent")
    admission = assess_sources(packet, raw, request.state_sha256, evidence,
        artifact_sha256=ARTIFACT_SHA256, moment=NOW)
    assert admission["qualified"] is False and admission["blockers"]
    encoded = json.dumps(packet).encode()
    with pytest.raises(ValueError, match="BLOCKED_SOURCE"):
        freeze_fundamental(ARTIFACT.read_bytes(), ARTIFACT_SHA256, encoded,
            hashlib.sha256(encoded).hexdigest(), request.output.parent/"must_not_exist.json", NOW,
            source_state_raw=raw, source_state_sha256=request.state_sha256,
            source_evidence=evidence, runtime_clock=lambda: NOW)
    assert not (request.output.parent/"must_not_exist.json").exists()


def test_long_verification_cannot_backdate_past_cutoff(admitted_contract):
    request, packet, raw, evidence = admitted_contract
    encoded = json.dumps(packet).encode()
    with pytest.raises(ValueError, match="T4"):
        freeze_fundamental(ARTIFACT.read_bytes(), ARTIFACT_SHA256, encoded,
            hashlib.sha256(encoded).hexdigest(), request.output.parent/"late.json", NOW,
            source_state_raw=raw, source_state_sha256=request.state_sha256, source_evidence=evidence,
            runtime_clock=lambda: NOW+timedelta(hours=6))
    assert not (request.output.parent/"late.json").exists()


def test_approved_pit_then_original_win_retention_before_shadow_ev(admitted_contract):
    from hbi.providers.rikstoto import OriginalBytesFetchResult

    request, _packet, raw, evidence = admitted_contract
    report = execute(request, now=NOW, clock_reader=lambda host: 0.)
    assert report["PIT_CERTIFIED"] is True
    market = {"success": True, "result": [{"startNumber": n, "odds": p,
              "lastUpdated": (NOW+timedelta(seconds=1)).isoformat()} for n, p in [(1, 3.), (2, 2.)]]}
    wire = json.dumps(market).encode()
    fetch = OriginalBytesFetchResult(url="https://www.rikstoto.no/api/game/BI_NR_2026-11-20/betdistribution/winodds/1",
        payload=market, success=True, status_code=200, latency_ms=0., raw_body=wire,
        response_body_sha256=hashlib.sha256(wire).hexdigest(), response_completed_at=NOW+timedelta(seconds=2))
    freeze = request.output/"fundamental_freeze.json"
    packet_raw = (request.output/"input_packet.json").read_bytes()
    assert hashlib.sha256(packet_raw).hexdigest() == json.loads(freeze.read_bytes())["packet_sha256"]
    decision = qualified_market(freeze, ARTIFACT.read_bytes(), request.output/"market.json",
        now=NOW+timedelta(seconds=3), reader=lambda: fetch, source_state_raw=raw,
        source_packet_raw=packet_raw, source_evidence=evidence, archive_root=request.output/"win")
    assert decision["PIT_CERTIFIED"] is True and decision["BET_AUTHORITY"] is False
    assert sum(r["combined_p"] for r in decision["rows"]) == pytest.approx(1)
    assert all(r["EV"] == pytest.approx(r["combined_p"]*r["WIN"]-1) for r in decision["rows"])
    assert list((request.output/"win").glob("*.body"))


def test_asserted_pit_flag_cannot_trigger_a_market_read(tmp_path):
    path = tmp_path/"forged.json"
    path.write_text(json.dumps({"scope": "PROSPECTIVE", "pit_certified": True,
        "packet_sha256": "0"*64, "created_at": NOW.isoformat()}))
    with pytest.raises((ValueError, KeyError)):
        qualified_market(path, ARTIFACT.read_bytes(), tmp_path/"out", now=NOW,
            reader=lambda: pytest.fail("unreviewed source triggered market read"), archive_root=tmp_path/"win")


def _review_test_revision(evidence, key, role, doc, monkeypatch):
    """Test-only independent review. Production pins are never written."""
    from pathlib import Path

    item = evidence[key]
    path = Path(item["original_file"])
    path.write_text(json.dumps(doc))
    item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS",
        admission_originals._REVIEWED_RECEIPTS | {(role, item["uri"], item["sha256"], NOW-timedelta(hours=1))})


def test_reviewed_but_incorrect_numeric_state_fails_raw_graph_replay(admitted_contract, monkeypatch):
    from pathlib import Path

    _, packet, raw, evidence = admitted_contract
    state = json.loads(raw)
    horse = packet["runners"][0]["horse_id"]
    state["ratings"][horse] += .25
    packet["state"][horse]["rating"] = state["ratings"][horse]
    raw = json.dumps(state).encode()
    sha = hashlib.sha256(raw).hexdigest()
    coverage = json.loads(Path(evidence["coverage"]["original_file"]).read_bytes())
    coverage["state_sha256"] = sha
    _review_test_revision(evidence, "coverage", "V2_STATE_COVERAGE", coverage, monkeypatch)
    outcome = assess_sources(packet, raw, sha, evidence, artifact_sha256=ARTIFACT_SHA256, moment=NOW)
    assert outcome["qualified"] is False
    assert outcome["blockers"] == ["V2_GRAPH_REPLAY_STATE_MISMATCH"]


def test_reviewed_registry_cannot_bind_another_native_horse(admitted_contract, monkeypatch):
    from pathlib import Path

    request, packet, raw, evidence = admitted_contract
    registry = json.loads(Path(evidence["registry"]["original_file"]).read_bytes())
    registry["runners"][0]["native_registration"] = "WRONG_NATIVE_ID"
    _review_test_revision(evidence, "registry", "REGISTRY_BINDING", registry, monkeypatch)
    outcome = assess_sources(packet, raw, request.state_sha256, evidence,
        artifact_sha256=ARTIFACT_SHA256, moment=NOW)
    assert outcome["qualified"] is False
    assert outcome["blockers"] == ["V2_REGISTRY_NATIVE_ID_CONFLICT"]


def test_clock_can_drift_during_source_verification(admitted_contract):
    request, packet, raw, evidence = admitted_contract
    encoded = json.dumps(packet).encode()
    with pytest.raises(ValueError, match="CLOCK_OFFSET_EXCEEDS_250_MS"):
        freeze_fundamental(ARTIFACT.read_bytes(), ARTIFACT_SHA256, encoded,
            hashlib.sha256(encoded).hexdigest(), request.output.parent/"drift.json", NOW,
            source_state_raw=raw, source_state_sha256=request.state_sha256,
            source_evidence=evidence, runtime_clock=lambda: NOW, clock_offset_reader=lambda: 251.)
    assert not (request.output.parent/"drift.json").exists()


@pytest.mark.parametrize("changed", ["race_id", "artifact_sha256", "active", "fundamental"])
def test_changed_freeze_cannot_trigger_win(admitted_contract, changed):
    request, _, raw, evidence = admitted_contract
    report = execute(request, now=NOW, clock_reader=lambda host: 0.)
    assert report["PIT_CERTIFIED"] is True
    path = request.output/"fundamental_freeze.json"
    frozen = json.loads(path.read_bytes())
    if changed == "active":
        frozen[changed][0]["horse_name"] = "WRONG_HORSE"
    elif changed == "fundamental":
        frozen[changed]["1"] += .1
    else:
        frozen[changed] = "WRONG_BINDING"
    tampered = request.output/"tampered.json"
    tampered.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="CONFLICT"):
        qualified_market(tampered, ARTIFACT.read_bytes(), request.output/"market.json", now=NOW,
            reader=lambda: pytest.fail("changed freeze triggered WIN"), source_state_raw=raw,
            source_packet_raw=(request.output/"input_packet.json").read_bytes(), source_evidence=evidence,
            archive_root=request.output/"win")
