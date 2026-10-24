"""All generated acquisition data in these tests are TEST_ONLY."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from hbi.prospective_pit import (
    capture,
    cutoff,
    encode,
    init_store,
    privacy_check,
    replay,
    roster_check,
    seal,
    validate_plan,
    write_once,
)
from hbi.prospective_pit_demo import demo
from hbi.prospective_pit_demo import test_body as body
from hbi.prospective_pit_demo import test_plan as plan_fixture


@pytest.fixture
def campaign(tmp_path):
    plan = plan_fixture()
    path = tmp_path / "plan.json"
    path.write_bytes(encode(plan))
    root = tmp_path / "store"
    receipt = init_store(path, root)
    return root, receipt["plan_sha256"], plan


def observe(campaign, *, minutes=1440, offset=-1, transform=None, status=200):
    root, digest, plan = campaign
    target = plan["targets"][0]
    raw = body(target)
    if transform:
        raw = encode(transform(json.loads(raw)))
    instant = cutoff(target, minutes) + timedelta(seconds=offset)
    return capture(root, digest, target["race_id"], minutes,
        fetch=lambda url: (status, {"Date": "TEST_ONLY_NOT_PUBLICATION"}, raw), clock=lambda: instant)


def lock_report(campaign):
    root, digest, _ = campaign
    receipt = seal(root, digest)
    return replay(root, receipt["seal_sha256"])


def test_test_only_demo_is_deterministic_and_honest(tmp_path):
    a = demo(tmp_path / "a")
    b = demo(tmp_path / "b")
    assert a == b
    r = a["report"]
    assert r["mode"] == "TEST_ONLY" and r["prospective_collection"] == "NOT_YET_OBSERVED"
    assert r["planned_snapshot_rounds"] == 8 and r["actual_attempts"] == 4
    assert r["hash_verified_sources"] == 5 and r["stored_source_observations"] == 5
    assert r["complete_historical_replays"] == 0 and r["complete_replay"] == "NOT_PROVEN"
    assert sum(v["missing_role_inputs"] for v in r["cutoff_coverage"].values()) == 13
    assert r["existing_model_gates"] == "CLOSED_UNCHANGED" and not r["model_eligible"]
    assert all(not row["model_eligible"] for row in r["observations"])


def test_test_only_missing_is_not_observed(campaign):
    report = lock_report(campaign)
    assert report["actual_attempts"] == report["hash_verified_sources"] == 0
    assert all(r["slot_status"] == "NOT_OBSERVED" and len(r["missing_roles"]) == 2 for r in report["observations"])


@pytest.mark.parametrize("offset,selected", [(-1, True), (0, False), (1, False), (-301, False)])
def test_test_only_actual_time_is_not_planned_time(campaign, offset, selected):
    observe(campaign, offset=offset)
    row = lock_report(campaign)["observations"][0]
    assert (len(row["selected_sources"]) == 2) is selected
    assert row["slot_status"] == "ATTEMPTED" and row["attempts_in_slot"] == 1


def test_test_only_unavailable_provider_is_error_not_snapshot(campaign):
    receipt = observe(campaign, status=403)
    assert all(r["http_status"] == 403 and r["status"] == "ERROR" and not r["body_file"] for r in receipt["records"])
    assert lock_report(campaign)["hash_verified_sources"] == 0


@pytest.mark.parametrize("mutation", ["body", "metadata", "plan", "add", "remove", "nested_seal"])
def test_test_only_changed_locked_snapshot_rejected(campaign, mutation):
    observe(campaign)
    root, digest, _ = campaign
    receipt = seal(root, digest)
    f = next(root.glob("captures/*/*/*/PROGRAM.json"))
    if mutation == "body":
        f.chmod(0o644);f.write_bytes(b'{}')
    elif mutation == "metadata":
        f = f.parent / "capture.json";f.chmod(0o644);f.write_bytes(b'{}')
    elif mutation == "plan":
        f = root / "plan.json";f.chmod(0o644);f.write_bytes(b'{}')
    elif mutation == "remove":
        f.unlink()
    else:
        (f.parent / ("seal.json" if mutation == "nested_seal" else "extra.json")).write_bytes(b'{}')
    with pytest.raises(ValueError, match="CHANGED"):
        replay(root, receipt["seal_sha256"])


def test_test_only_wrong_external_seal_hash_rejected(campaign):
    root, digest, _ = campaign
    seal(root, digest)
    with pytest.raises(ValueError, match="SEAL_CHANGED"):
        replay(root, "f" * 64)


def test_test_only_capture_cannot_overwrite_sealed_store(campaign):
    lock_report(campaign)
    with pytest.raises(ValueError, match="SEALED"):
        observe(campaign)


def test_test_only_attempts_and_writes_are_bounded(campaign, tmp_path):
    observe(campaign);observe(campaign)
    with pytest.raises(ValueError, match="BUDGET"):
        observe(campaign)
    p = tmp_path / "once"
    write_once(p, b'a')
    with pytest.raises(FileExistsError):
        write_once(p, b'b')


@pytest.mark.parametrize("mutation,reason", [("collision", "IDENTITY_COLLISION"), ("missing_id", "HORSE_IDENTITY_MISSING"),
    ("partial", "INCOMPLETE_OR_CHANGED_FIELD"), ("scratch_unknown", "SCRATCH_STATE_UNKNOWN"),
    ("result", "RESULT_LABEL_NOT_PRE_RACE_INPUT"), ("clock", "SCHEDULE_NOT_CORROBORATED")])
def test_test_only_source_field_negatives(campaign, mutation, reason):
    def change(p):
        r = p["races"][0]
        if mutation == "collision":r["starts"][1]["horse"]["id"] = 101
        elif mutation == "missing_id":r["starts"][0]["horse"].pop("id")
        elif mutation == "partial":r["starts"].pop()
        elif mutation == "scratch_unknown":r["starts"][0].pop("scratched")
        elif mutation == "clock":r.pop("scheduledStartTime")
        else:r["starts"][0]["result"] = {"place": 1}
        return p
    observe(campaign, transform=change)
    row = lock_report(campaign)["observations"][0]
    if mutation == "result":
        assert "PROGRAM:RESULT_LABEL_NOT_PRE_RACE_INPUT" in row["exclusions"]
    else:
        assert reason in row["roster"]["reasons"]
    assert row["source_replay"] == "NOT_PROVEN" and row["historical_replay"] == "REPLAY_NOT_PROVEN"


def test_test_only_unavailable_identity_proof_not_inferred_from_names(campaign):
    t = campaign[2]["targets"][0]
    t["expected_runner_ids"] = None
    assert "EXPECTED_FULL_FIELD_UNKNOWN" in roster_check(body(t), t)["reasons"]


@pytest.mark.parametrize("mutation", ["timezone", "dst_gap", "dst_fold", "missing_clock", "automatic", "model", "url"])
def test_test_only_invalid_plan_is_rejected(mutation):
    p = plan_fixture()
    if mutation == "timezone":p["targets"][0]["timezone"] = "America/New_York"
    elif mutation == "dst_gap":p["targets"][0]["scheduled_start_local"] = "2026-03-29T02:30:00"
    elif mutation == "dst_fold":p["targets"][0]["scheduled_start_local"] = "2026-10-25T02:30:00"
    elif mutation == "missing_clock":p["targets"][0]["scheduled_start_local"] = "UNKNOWN"
    elif mutation == "automatic":p["automatic_collection"] = True
    elif mutation == "model":p["model_eligible"] = True
    else:p["targets"][0]["sources"]["PROGRAM"]["url"] = "https://example.invalid/private"
    with pytest.raises(ValueError):validate_plan(p)


def test_test_only_real_plan_dst_conversion():
    p = json.loads((Path(__file__).resolve().parents[1] / "examples/prospective-pit/no-se-2026-10-25.json").read_text())
    validate_plan(p)
    assert cutoff(p["targets"][1], 0).isoformat() == "2026-10-25T12:45:00+00:00"


@pytest.mark.parametrize("raw", [b'{"owner":{"name":"TEST_ONLY_PERSON"}}', b'{"email":"x@example.test"}', b'%PDF-OPAQUE_UNREVIEWED', b'<html>not approved</html>'])
def test_test_only_personal_or_unreviewed_content_is_not_stored(raw):
    with pytest.raises((ValueError, UnicodeError)):privacy_check(raw)


def test_test_only_control_label_is_excluded(campaign):
    root, _, p = campaign
    p["targets"][0]["sources"]["HISTORY"]["purpose"] = "CONTROL_LABEL"
    # Reinitialize an isolated TEST_ONLY campaign before any observation.
    path = root.parent / "control-plan.json";path.write_bytes(encode(p));other = root.parent / "control"
    receipt = init_store(path, other)
    observe((other, receipt["plan_sha256"], p))
    r = lock_report((other, receipt["plan_sha256"], p))["observations"][0]
    assert "HISTORY:LABEL_OR_CONTROL_EXCLUDED" in r["exclusions"] and r["missing_roles"] == ["HISTORY"]


def test_test_only_real_capture_rejects_clock_or_transport_injection(tmp_path):
    p = json.loads((Path(__file__).resolve().parents[1] / "examples/prospective-pit/no-se-2026-10-25.json").read_text())
    path = tmp_path / "real.json";path.write_bytes(encode(p));root=tmp_path / "real"
    receipt = init_store(path, root)
    with pytest.raises(ValueError, match="CANNOT_BE_INJECTED"):
        capture(root, receipt["plan_sha256"], p["targets"][0]["race_id"], 1440, fetch=lambda x: None)


def test_test_only_corrected_later_source_without_original_not_backfilled(campaign):
    def corrected(p):
        p["races"][0]["starts"][0]["horse"]["id"] = 999
        return p
    observe(campaign, offset=1, transform=corrected)
    row = lock_report(campaign)["observations"][0]
    assert row["selected_sources"] == {} and row["historical_replay"] == "REPLAY_NOT_PROVEN"
    assert "PROGRAM:POST_CUTOFF_EXCLUDED" in row["exclusions"]


def test_test_only_partial_write_cannot_be_sealed(campaign):
    root, digest, _ = campaign
    p = root / "captures/TEST_ONLY_NO/1440/1/PROGRAM.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b'{}')
    with pytest.raises(ValueError, match="INCOMPLETE_CAPTURE"):
        seal(root, digest)


def test_test_only_future_update_cannot_change_frozen_replay(campaign):
    observe(campaign)
    root, digest, _ = campaign
    receipt = seal(root, digest)
    before = replay(root, receipt["seal_sha256"])
    with pytest.raises(ValueError, match="SEALED"):
        observe(campaign, offset=1)
    assert replay(root, receipt["seal_sha256"]) == before


@pytest.mark.parametrize("archive,receipt,expected,sha256", [
    ("m7b2c-test-only-snapshots.zip", "M7B2C_TEST_ONLY_RECEIPT.json", "M7B2C_TEST_ONLY_REPORT.json", "9afdec13fe885e56a7b820a1ee4e286ad0b3069e068bb0f76bd3ab1205d0c5c4"),
    ("m7b2c-unobserved-plan-store.zip", "M7B2C_LIVE_RECEIPT.json", "M7B2C_LIVE_COVERAGE.json", "224e1ea0d0f4350fd85934eaac9c3f231bfb8437e9701b3e350c407a9d602a32"),
])
def test_archived_evidence_replays_offline(tmp_path, archive, receipt, expected, sha256):
    import zipfile

    from hbi.pdf_validation import sha
    root = Path(__file__).resolve().parents[1]
    raw = (root / "tests/fixtures" / archive).read_bytes()
    if sha256:
        assert sha(raw) == sha256
    with zipfile.ZipFile(root / "tests/fixtures" / archive) as z:
        for name in z.namelist():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
            p = tmp_path / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(z.read(name))
    anchor = json.loads((root / "docs" / receipt).read_text())
    assert replay(tmp_path, anchor["seal_sha256"]) == json.loads((root / "docs" / expected).read_text())


def test_test_only_body_hash_conflict_even_before_seal(campaign):
    observe(campaign)
    root, digest, _ = campaign
    p = next(root.glob("captures/*/*/*/PROGRAM.json"));p.chmod(0o644);p.write_bytes(b'{}')
    anchor = seal(root, digest)
    with pytest.raises(ValueError, match="BODY_HASH"):
        replay(root, anchor["seal_sha256"])


def test_test_only_missing_start_number_is_not_full_field(campaign):
    target = campaign[2]["targets"][0]
    data = json.loads(body(target));data["races"][0]["starts"][0].pop("number")
    assert "START_NUMBER_MISSING_OR_INVALID" in roster_check(encode(data), target)["reasons"]


def test_test_only_unknown_fields_cannot_bypass_data_minimization():
    with pytest.raises(ValueError, match="UNREVIEWED"):
        privacy_check(b'{"mystery":"TEST_ONLY_UNREVIEWED_CONTENT"}')


def test_test_only_target_label_hidden_in_history_role_is_excluded(campaign):
    root, digest, plan = campaign
    target = plan["targets"][0]
    calls = []
    def fetch(url):
        data = json.loads(body(target))
        if calls:
            data["races"][0]["status"] = "results"
            data["races"][0]["starts"][0]["result"] = {"place": 1}
        calls.append(url)
        return 200, {}, encode(data)
    at = cutoff(target, 1440) - timedelta(seconds=1)
    capture(root, digest, target["race_id"], 1440, fetch=fetch, clock=lambda: at)
    row = lock_report(campaign)["observations"][0]
    assert row["missing_roles"] == ["HISTORY"]
    assert "HISTORY:RESULT_LABEL_NOT_PRE_RACE_INPUT" in row["exclusions"]


def test_test_only_malformed_structures_are_errors_not_snapshots(campaign):
    for bad in [b'[]', b'null', b'{"races":[7]}', b'{"races":[{"starts":null}]}']:
        with pytest.raises((ValueError, TypeError)):
            privacy_check(bad)
