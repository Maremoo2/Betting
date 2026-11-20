"""One authentic frozen field for parity; synthetic cases exercise source gates."""
import hashlib
import json
import subprocess
import sys
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hbi.daily_v2 import ARTIFACT, ARTIFACT_SHA256, execute, qualified_market
from hbi.v2_limited_research import VARIANT

FIXTURES = Path(__file__).with_name("fixtures")
NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


def args(tmp_path, **values):
    return Namespace(race_id="RIKSTOTO:BI_NR_2026-11-20:1", artifact=ARTIFACT,
        collector_root=None, state=None, state_sha256=None, output=tmp_path/"result",
        limited_protocol=None, parity_packet=None, parity_packet_sha256=None,
        market_cache=None, **values)


def test_authentic_trained_fold_matches_original_frozen_field(tmp_path):
    packet = FIXTURES/"trained_v2_2024_packet.json"
    expected = json.loads((FIXTURES/"trained_v2_2024_expected.json").read_bytes())
    request = args(tmp_path)
    request.race_id = expected["race_id"]
    request.parity_packet = packet
    request.parity_packet_sha256 = hashlib.sha256(packet.read_bytes()).hexdigest()
    report = execute(request, now=NOW)
    assert report["status"] == "RETROSPECTIVE_PARITY"
    assert report["active_runners"] == 7 and report["fundamental_sum"] == pytest.approx(1)
    assert report["artifact_sha256"] == ARTIFACT_SHA256
    for row in report["rows"]:
        p = expected["fundamental"][row["selection_id"]]
        assert row["fundamental_p"] == pytest.approx(p, abs=1e-15)
        assert row["fundamental_fair_odds"] == pytest.approx(1/p)
        assert row["EV"] is None and row["signal"] == "PARITY_ONLY"
    assert report["PIT_CERTIFIED"] is False and report["WIN_read"] is False


@pytest.fixture
def collector_case(tmp_path, monkeypatch):
    from hbi import collector_handoff
    root = tmp_path/"collector"
    prefix = "day/run/"
    key = "BI_NR_2026-11-20"
    roster = [{"startNumber": n, "horseRegistrationNumber": "57800102017000"+str(n),
        "horseName": "Test-only horse "+str(n), "isScratched": False,
        "raceNumber": 1, "raceKey": key+"#1"} for n in (1, 2)]
    starts = {"success": True, "result": {"1": roster}}
    calendar = {"success": True, "result": [{"raceDayKey": key, "countryIsoCode": "NO",
        "sportType": "T", "isMultiTrack": False, "races": [{"raceNumber": 1,
        "raceKey": key+"#1", "startTime": "2026-11-20T19:00:00"}]}]}
    originals = {"meetings/"+key+"/starts.raw.json": json.dumps(starts).encode(),
        "meetings/"+key+"/full_program.pdf": b"%PDF synthetic contract only",
        "discovery.raw.json": json.dumps(calendar).encode()}
    urls = [f"https://www.rikstoto.no/api/racedays/{key}/starts",
            f"https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/{key}",
            "https://www.rikstoto.no/api/racedays"]
    records = []
    for (name, raw), url in zip(originals.items(), urls):
        f = root/prefix/name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(raw)
        records.append({"url": url, "status": "PDF_OK" if name.endswith(".pdf") else "JSON_OK",
            "raw_path": prefix+name, "path": prefix+name, "sha256": hashlib.sha256(raw).hexdigest(),
            "at_utc": "2026-11-20T10:00:00+00:00"})
    manifest = root/prefix/"manifest.json"
    manifest.write_text(json.dumps({"date_oslo": "2026-11-20", "requests": records}))
    monkeypatch.setattr(collector_handoff, "pdf_field", lambda *a: "2026-11-20T18:00:00+00:00")
    histories = {"RIKSTOTO_REG:"+r["horseRegistrationNumber"]:
        [["2026-11-18", False, .2, 10., 0.]] for r in roster}
    state = {"last_day": "2026-11-18", "histories": histories,
        "ratings": {h: 0. for h in histories}, "event_refs": {h: ["previous"] for h in histories},
        "applied_races": {"previous": {"race_date": "2026-11-18", "archived_at": "2026-11-19T10:00:00+00:00"}},
        "identities": {}, "known_gaps": ["TEST_ONLY_INCOMPLETE_GRAPH"],
        "PIT_CERTIFIED": False, "FULL_F3_COVERAGE": False, "cutoff_utc": "2026-11-19T11:00:00+00:00"}
    request = args(tmp_path)
    request.collector_root = root
    request.state = tmp_path/"state.json"
    request.state.write_text(json.dumps(state))
    request.state_sha256 = hashlib.sha256(request.state.read_bytes()).hexdigest()
    return request, manifest, state


def test_asserted_pit_cannot_open_canonical_gate_or_win(collector_case, monkeypatch):
    from rikstoto_crawler.transport import ArchiveClient
    request, _, state = collector_case
    state.update(PIT_CERTIFIED=True, FULL_F3_COVERAGE=True, known_gaps=[])
    request.state.write_text(json.dumps(state))
    request.state_sha256 = hashlib.sha256(request.state.read_bytes()).hexdigest()
    request.market_cache = request.output.parent/"market"
    monkeypatch.setattr(ArchiveClient, "get", lambda *a, **kw: pytest.fail("WIN read before PIT"))
    report = execute(request, now=NOW, clock_reader=lambda host: 0.)
    assert report["status"] == "BLOCKED" and report["WIN_read"] is False
    assert any("V2_LIVE_STATE_ADAPTER_NOT_ATTESTED" in r for r in report["blockers"])
    assert all(row["fundamental_p"] is None for row in report["rows"])
    assert not (request.output/"fundamental_freeze.json").exists()


def test_explicit_limited_mode_keeps_qualification_and_ev_blocked(collector_case):
    request, _, _ = collector_case
    request.limited_protocol = request.output.parent/"protocol.json"
    request.limited_protocol.write_text(json.dumps({"variant": VARIANT}))
    report = execute(request, now=NOW, clock_reader=lambda host: 0.)
    assert report["status"] == "LIMITED_RESEARCH" and report["fundamental_sum"] == pytest.approx(1)
    assert report["PIT_CERTIFIED"] is False and report["WIN_read"] is False
    assert all(r["fundamental_p"] is None and r["conditional_fundamental_p"] > 0
               and r["EV"] is None for r in report["rows"])


@pytest.mark.parametrize("attack", ["source_sha", "country", "clock", "race", "pdf_clock"])
def test_collector_original_contract_attacks_block(collector_case, monkeypatch, attack):
    from hbi import collector_handoff
    request, manifest, _ = collector_case
    body = json.loads(manifest.read_bytes())
    if attack == "source_sha":
        body["requests"][0]["sha256"] = "0"*64
    elif attack == "clock":
        body["requests"][0]["at_utc"] = "2026-11-20T17:56:00+00:00"
    elif attack == "race":
        request.race_id = request.race_id[:-1]+"2"
    elif attack == "pdf_clock":
        monkeypatch.setattr(collector_handoff, "pdf_field", lambda *a: "2026-11-20T17:00:00+00:00")
    else:
        cal = request.collector_root/body["requests"][2]["raw_path"]
        doc = json.loads(cal.read_bytes())
        doc["result"][0]["countryIsoCode"] = "FR"
        cal.write_text(json.dumps(doc))
        body["requests"][2]["sha256"] = hashlib.sha256(cal.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(body))
    report = execute(request, now=NOW, clock_reader=lambda host: pytest.fail("clock not needed"))
    assert report["status"] == "BLOCKED" and report["WIN_read"] is False
    assert not (request.output/"fundamental_freeze.json").exists()


def test_missing_horse_history_preserves_full_field_and_never_infers(collector_case):
    request, _, state = collector_case
    state["histories"].pop(next(iter(state["histories"])))
    request.state.write_text(json.dumps(state))
    request.state_sha256 = hashlib.sha256(request.state.read_bytes()).hexdigest()
    report = execute(request, now=NOW, clock_reader=lambda host: pytest.fail("blocked input"))
    assert report["active_runners"] == 2 and report["status"] == "BLOCKED"
    assert "MISSING_OBSERVED_HISTORY" in report["blockers"]
    assert all(row["fundamental_p"] is None for row in report["rows"])


@pytest.mark.parametrize("seconds", [0, 1])
def test_at_or_after_t4_cannot_create_a_freeze(collector_case, seconds):
    request, _, _ = collector_case
    request.limited_protocol = request.output.parent/"protocol.json"
    request.limited_protocol.write_text(json.dumps({"variant": VARIANT}))
    report = execute(request, now=datetime(2026, 11, 20, 17, 56, tzinfo=UTC)+timedelta(seconds=seconds))
    assert report["status"] == "BLOCKED" and "MODEL_AT_OR_AFTER_T4" in report["blockers"]


def test_model_bytes_cannot_be_changed(collector_case):
    request, _, _ = collector_case
    doc = json.loads(ARTIFACT.read_bytes())
    doc["fundamental_weights"][0] += .01
    request.artifact = request.output.parent/"changed.json"
    request.artifact.write_text(json.dumps(doc))
    report = execute(request, now=NOW)
    assert report["status"] == "BLOCKED" and any("ARTIFACT_" in b for b in report["blockers"])


def test_unverified_freeze_does_not_even_open_market(tmp_path):
    freeze_path = tmp_path/"unqualified.json"
    freeze_path.write_text(json.dumps({"scope": "PROSPECTIVE", "pit_certified": False}))
    with pytest.raises(ValueError, match="WIN_NOT_READ"):
        qualified_market(freeze_path, ARTIFACT.read_bytes(), tmp_path/"out", now=NOW,
                         reader=lambda: pytest.fail("market read"))


def test_existing_output_cannot_be_replaced(collector_case):
    request, _, _ = collector_case
    request.output.mkdir()
    (request.output/"original.txt").write_text("original")
    with pytest.raises(FileExistsError):
        execute(request, now=NOW)
    assert (request.output/"original.txt").read_text() == "original"


def test_bad_history_still_reports_every_active_runner(collector_case):
    request, _, state = collector_case
    state["histories"][next(iter(state["histories"]))] = [[]]
    request.state.write_text(json.dumps(state))
    request.state_sha256 = hashlib.sha256(request.state.read_bytes()).hexdigest()
    report = execute(request, now=NOW)
    assert report["active_runners"] == 2 and report["status"] == "BLOCKED"
    assert "INVALID_OBSERVED_HISTORY_SHAPE" in report["blockers"]
    assert all(row["race_blockers"] for row in report["rows"])


def test_runtime_cutoff_is_rechecked_after_clock_measurement(collector_case, monkeypatch):
    from hbi import daily_v2
    request, _, _ = collector_case
    current = [NOW]

    class RuntimeClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current[0]

    def slow_clock(host):
        current[0] = datetime(2026, 11, 20, 17, 56, tzinfo=UTC)
        return 0.

    monkeypatch.setattr(daily_v2, "datetime", RuntimeClock)
    report = execute(request, clock_reader=slow_clock)
    assert report["status"] == "BLOCKED" and "MODEL_AT_OR_AFTER_T4" in report["blockers"]
    assert not (request.output/"fundamental_freeze.json").exists()


def test_cli_help_does_not_import_optional_numpy():
    script = """
import builtins
old = builtins.__import__
def guarded(name, *a, **kw):
    if name.split('.')[0] == 'numpy': raise ModuleNotFoundError('numpy', name='numpy')
    return old(name, *a, **kw)
builtins.__import__ = guarded
from hbi.cli import build_parser
build_parser().parse_args(['daily-v2', '--help'])
"""
    script = "import sys; sys.path.insert(0, " + repr(str(Path(__file__).parents[1]/"src")) + ");\n" + script
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "--collector-root" in result.stdout


def test_parity_mode_never_reads_live_state_or_market(tmp_path):
    request = args(tmp_path)
    request.parity_packet = FIXTURES/"trained_v2_2024_packet.json"
    request.parity_packet_sha256 = hashlib.sha256(request.parity_packet.read_bytes()).hexdigest()
    request.market_cache = tmp_path/"DO_NOT_OPEN"
    report = execute(request, now=NOW)
    assert report["status"] == "BLOCKED" and not report["WIN_read"]
