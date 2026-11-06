"""TEST_ONLY historical as-of original-envelope replay. No PIT certified."""
import copy
import hashlib
import json

import pytest

from hbi.mvp023b_asof_audit import assess_one, audit, main
from rikstoto_crawler.transport import HOST, digest

PRIOR = "/results/raceDays/BJ_NR_2020-01-02/1/completeresults"
SHA_NAME = hashlib.sha256(PRIOR.encode()).hexdigest() + ".json"
MEMBER = "raw-results/" + SHA_NAME


def initial(tmp_path):
    root = tmp_path / "original"
    source = root / MEMBER
    source.parent.mkdir(parents=True)
    envelope = {
        "path": PRIOR,
        "url": HOST + "/api" + PRIOR,
        "body": {"success": True, "result": {"isComplete": True}},
        "fetched_at": "2020-01-03T08:01:00+00:00",
        "source_published_at_utc": "2020-01-03T08:00:00+00:00",
        "version_history_attested": True,
    }
    envelope["body_sha256"] = digest(envelope["body"])
    record = {
        "target_race_id": "RIKSTOTO:BJ_NR_2020-02-02:1",
        "target_scheduled_start_at_utc": "2020-02-02T12:00:00+00:00",
        "target_timezone": "Europe/Oslo",
        "historical_date": "2020-01-02",
        "historical_event_at_utc": "2020-01-02T08:00:00+00:00",
        "horse_identity": "DNT_REGISTRATION:578001020205025",
        "previous_horse_identity": "DNT_REGISTRATION:578001020205025",
        "source_role": "PRIOR_OFFICIAL_RESULT",
        "identity_proof_observed_at_utc": "2020-01-03T10:00:00+00:00",
        "prior_race_number": 1,
        "features": {"observed_prior_start": 1},
        "model_eligible": False, "bet_authority": False,
        "original_capture": {
            "member": MEMBER, "provider_path": PRIOR,
            "body_sha256": envelope["body_sha256"],
            "provider_published_at_utc": envelope["source_published_at_utc"],
            "immutable_version_timeline_attested": True,
        },
    }
    rewrite(source, record, envelope)
    return root, record, envelope


def rewrite(source, record, envelope):
    raw = json.dumps(envelope, sort_keys=True).encode()
    source.write_bytes(raw)
    record["original_capture"]["raw_file_sha256"] = hashlib.sha256(raw).hexdigest()


def test_test_only_source_original_replay_is_not_production_pit(tmp_path):
    root, record, envelope = initial(tmp_path)
    result = assess_one(record, root=root)
    assert result["research_level"] == "TEST_ONLY_HISTORICAL_ASOF_VERIFIED"
    assert result["historical_asof_source_ready"] is True
    assert result["production_pit_certified"] is False
    assert result["model_eligible"] is False and result["bet_authority"] is False
    assert result["research_cutoff_t4_at_utc"] == "2020-02-02T11:56:00+00:00"
    assert audit([record], root=root)["production_pit_certified"] == 0
    assert envelope["source_published_at_utc"] < record["target_scheduled_start_at_utc"]


def test_test_only_missing_raw_original_cannot_be_asof(tmp_path):
    _, record, _ = initial(tmp_path)
    result = assess_one(record, root=None)
    assert result["research_level"] == "RETROSPECTIVE_PERFORMANCE_RECONSTRUCTION"
    assert "HISTORICAL_ORIGINAL_BYTES_NOT_REPLAYED" in result["blockers"]
    assert result["historical_asof_source_ready"] is False


@pytest.mark.parametrize("change,reason", [
    (lambda r: r.update(historical_date="2025-02-02"), "2025_CANDIDATE_LOCKBOX"),
    (lambda r: r.update(target_race_id="RIKSTOTO:BJ_NR_2025-02-02:1"), "2025_CANDIDATE_LOCKBOX"),
    (lambda r: r.update(historical_date="2020-02-03"), "FUTURE_OR_SAME_DAY"),
    (lambda r: r.update(historical_date="2020-02-02"), "FUTURE_OR_SAME_DAY"),
    (lambda r: r.update(horse_identity="NAME:John"), "BLOCKED_IDENTITY"),
    (lambda r: r.update(horse_identity="TMP-123"), "BLOCKED_IDENTITY"),
    (lambda r: r.update(previous_horse_identity="ATG_HORSE:300"), "CROSS_PROVIDER_IDENTITY"),
    (lambda r: r.update(source_role="TARGET_RESULT"), "TARGET_LABEL_OR_MARKET"),
    (lambda r: r["features"].update(win_odds=6.5), "MARKET_OR_TARGET_RESULT"),
    (lambda r: r.update(target_scheduled_start_at_utc="2020-02-03T12:00:00+00:00"), "TARGET_RACEDAY_CLOCK"),
    (lambda r: r.update(historical_event_at_utc="2020-03-03T12:00:00+00:00"), "FUTURE_HISTORICAL_EVENT"),
    (lambda r: r["original_capture"].update(member="../2025/secret.json"), "UNSAFE_OR_NONRESULT_ORIGINAL"),
    (lambda r: r["original_capture"].update(raw_file_sha256="0" * 64), "ORIGINAL_RESPONSE_BYTES_SHA"),
])
def test_test_only_asof_fail_closed_attacks(tmp_path, change, reason):
    root, record, _ = initial(tmp_path)
    candidate = copy.deepcopy(record)
    change(candidate)
    with pytest.raises(ValueError, match=reason):
        assess_one(candidate, root=root)


def test_test_only_late_publication_and_capture_unverifiable(tmp_path):
    root, record, envelope = initial(tmp_path)
    source = root / MEMBER
    envelope["fetched_at"] = "2020-03-01T12:00:00+00:00"
    envelope["source_published_at_utc"] = "2020-03-01T11:59:00+00:00"
    record["original_capture"]["provider_published_at_utc"] = envelope["source_published_at_utc"]
    rewrite(source, record, envelope)
    found = assess_one(record, root=root)
    assert not found["historical_asof_source_ready"]
    assert "ORIGINAL_OBSERVED_OR_PUBLISHED_AFTER_CUTOFF" in found["blockers"]


def test_test_only_publication_must_be_in_original_not_sidecar(tmp_path):
    root, record, envelope = initial(tmp_path)
    envelope.pop("source_published_at_utc")
    rewrite(root / MEMBER, record, envelope)
    assert "FIRST_PUBLICATION_NOT_IN_IMMUTABLE_ORIGINAL" in (
        assess_one(record, root=root)["blockers"])
    envelope["source_published_at_utc"] = "2020-01-03T08:00:00+00:00"
    envelope.pop("version_history_attested")
    rewrite(root / MEMBER, record, envelope)
    assert "ORIGINAL_CORRECTION_TIMELINE_NOT_SOURCE_ATTESTED" in (
        assess_one(record, root=root)["blockers"])


def test_test_only_duplicate_physical_start_denied(tmp_path):
    root, record, _ = initial(tmp_path)
    with pytest.raises(ValueError, match="DUPLICATE_ORIGINAL_HISTORICAL_START"):
        audit([record, copy.deepcopy(record)], root=root)


def test_test_only_symlinked_original_denied(tmp_path):
    root, record, envelope = initial(tmp_path)
    source = root / MEMBER
    source.unlink()
    alternative = tmp_path / "different.json"
    alternative.write_text(json.dumps(envelope))
    source.symlink_to(alternative)
    with pytest.raises(ValueError, match="SYMLINK"):
        assess_one(record, root=root)


def test_test_only_cli_replay_not_reusable_as_betting_gate(tmp_path):
    root, record, _ = initial(tmp_path)
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(json.dumps({
        "schema": "MVP023B_PRIOR_SOURCE_ASOF_INPUT_V1", "records": [record]
    }))
    output = tmp_path / "result" / "asof.json"
    assert main(["--manifest", str(manifest), "--source-root", str(root),
                 "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["schema"] == "MVP023B_HISTORICAL_ASOF_RESEARCH_AUDIT_V1"
    assert report["historical_asof_source_ready"] == 1
    assert report["model_training_eligible"] == 0
    assert report["production_pit_certified"] == 0
    with pytest.raises(FileExistsError):
        main(["--manifest", str(manifest), "--source-root", str(root),
              "--output", str(output)])
