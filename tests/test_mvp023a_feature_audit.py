"""TEST_ONLY M5 feature audit integrity, no real lockbox exposure."""
from __future__ import annotations

import hashlib
import json

import pytest

from hbi.mvp023a_feature_audit import audit_feature_dataset, main


def original_input(tmp_path, *, year="2020", observed="2026-10-01T11:00:00+00:00"):
    path = tmp_path / "m5"
    path.mkdir()
    source = {
        "url": "https://www.rikstoto.no/api/racedays/BJ_NR_2020-01-04/starts",
        "body_sha256": "a" * 64,
        "fetched_at": observed,
    }
    fact = {
        "value": "Driver One", "status": "PIT_VERIFIED",
        "source_url": source["url"], "source_body_sha256": source["body_sha256"],
        "source_observed_at": source["fetched_at"], "event_at": "2020-01-03T10:00:00+00:00",
        "published_at": "2020-01-03T10:00:00+00:00",
    }
    row = {
        "race_id": "RIKSTOTO:BJ_NR_2020-01-04:1", "date": year + "-01-04",
        "country": "NO", "discipline": "trot",
        "event_time": "2020-01-04T12:00:00+00:00",
        "independent_identity_attested": False,
        "source_refs": [source],
        "roster": [
            {"selection_id": str(n), "registration_observed": f"H{n}",
             "identity_status": "IDENTITY_VERIFIED", "scratched": False,
             "features": {"driver": dict(fact), "extra_distance_m": {
                 **fact, "value": 0,
             }}}
            for n in (1, 2)
        ],
        "labels": [{"selection_id": "1", "placing": 1}],
        "model_eligible": False,
    }
    raw = (json.dumps(row) + "\n").encode()
    (path / "dataset.jsonl").write_bytes(raw)
    report = {
        "schema": "HBI_RESEARCH_DATASET_V1",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "model_eligible": 0,
        "per_month": {year + "-01": {"races": 1}},
    }
    (path / "model-readiness.json").write_text(json.dumps(report))
    return path, row


def rewrite_dataset(path, row):
    raw = (json.dumps(row) + "\n").encode()
    (path / "dataset.jsonl").write_bytes(raw)
    manifest = json.loads((path / "model-readiness.json").read_text())
    manifest["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    (path / "model-readiness.json").write_text(json.dumps(manifest))


def test_real_m5_schema_shape_is_retrospective_not_pit(tmp_path):
    path, row = original_input(tmp_path)
    report = audit_feature_dataset(path)
    assert report["physical_races"] == 1
    assert report["features"]["driver"]["denominator_active_runners"] == 2
    assert report["features"]["driver"]["status_counts"] == {"RETROSPECTIVE_ONLY": 2}
    assert report["features"]["last_3_starts"]["status_counts"] == {"MISSING": 2}
    assert report["features"]["last_10_starts"]["status_counts"] == {"MISSING": 2}
    assert report["features"]["gallop_rate"]["status_counts"] == {"MISSING": 2}
    assert report["training_ready_races"] == 0
    assert report["lockbox_2025_opened"] is False
    assert not report["benter_ready"]
    assert report["feature_audit_sha256"] == audit_feature_dataset(path)["feature_audit_sha256"]
    assert "labels" not in json.dumps(report["by_race"])
    assert row["labels"][0]["placing"] == 1  # Label never crosses into report.


def test_2025_candidate_lockbox_denied_before_dataset_is_opened(tmp_path):
    path, _ = original_input(tmp_path)
    m = json.loads((path / "model-readiness.json").read_text())
    m["per_month"] = {"2025-06": {"races": 1}}
    (path / "model-readiness.json").write_text(json.dumps(m))
    (path / "dataset.jsonl").write_bytes(b"LOCKBOX_DO_NOT_OPEN")
    with pytest.raises(ValueError, match="LOCKBOX_EXPOSURE_AUDIT_REQUIRED"):
        audit_feature_dataset(path)


def test_market_or_result_inside_fundamental_features_is_rejected(tmp_path):
    path, row = original_input(tmp_path)
    row["roster"][0]["features"]["closing_odds"] = {"value": 2.4}
    rewrite_dataset(path, row)
    with pytest.raises(ValueError, match="OUTCOME_OR_MARKET_LEAKAGE"):
        audit_feature_dataset(path)


def test_source_sha_mismatch_never_admits_a_feature(tmp_path):
    path, row = original_input(tmp_path)
    row["roster"][0]["features"]["driver"]["source_body_sha256"] = "b" * 64
    rewrite_dataset(path, row)
    result = audit_feature_dataset(path)
    assert result["features"]["driver"]["status_counts"] == {
        "RETROSPECTIVE_ONLY": 1, "UNSUPPORTED": 1,
    }


def test_pre_event_fetch_without_independent_identity_is_not_pit(tmp_path):
    path, row = original_input(tmp_path)
    source = "2020-01-03T10:05:00+00:00"
    row["source_refs"][0]["fetched_at"] = source
    for runner in row["roster"]:
        for fact in runner["features"].values():
            fact["source_observed_at"] = source
    rewrite_dataset(path, row)
    result = audit_feature_dataset(path)
    assert result["features"]["driver"]["status_counts"] == {"UNVERIFIED_IDENTITY": 2}
    assert result["training_ready_races"] == 0


def test_temporary_registration_fails_even_with_pre_event_capture(tmp_path):
    path, row = original_input(tmp_path)
    source = "2020-01-03T10:05:00+00:00"
    row["independent_identity_attested"] = True
    row["source_refs"][0]["fetched_at"] = source
    row["roster"][0]["registration_observed"] = "TMP-H1"
    for runner in row["roster"]:
        for fact in runner["features"].values():
            fact["source_observed_at"] = source
    rewrite_dataset(path, row)
    result = audit_feature_dataset(path)
    assert result["features"]["driver"]["status_counts"]["UNVERIFIED_IDENTITY"] == 1
    assert result["training_ready_races"] == 0


def test_duplicate_runner_and_physical_race_rejected(tmp_path):
    path, row = original_input(tmp_path)
    row["roster"].append(row["roster"][0])
    rewrite_dataset(path, row)
    with pytest.raises(ValueError, match="DUPLICATE_OR_MISSING_RUNNERS"):
        audit_feature_dataset(path)
    row["roster"].pop()
    raw = (json.dumps(row) + "\n") * 2
    (path / "dataset.jsonl").write_text(raw)
    m = json.loads((path / "model-readiness.json").read_text())
    m["dataset_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    (path / "model-readiness.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="M5_PHYSICAL_RACE_ID_DUPLICATE"):
        audit_feature_dataset(path)


def test_changed_dataset_sha_rejected(tmp_path):
    path, row = original_input(tmp_path)
    row["roster"][0]["features"]["driver"]["value"] = "Different"
    (path / "dataset.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="M5_DATASET_ORIGINAL_SHA_MISMATCH"):
        audit_feature_dataset(path)


def test_read_only_write_once_cli(tmp_path):
    path, _ = original_input(tmp_path)
    output = tmp_path / "report" / "feature-audit.json"
    original = (path / "dataset.jsonl").read_bytes()
    assert main(["--dataset-dir", str(path), "--output", str(output)]) == 0
    assert (path / "dataset.jsonl").read_bytes() == original
    assert json.loads(output.read_text())["bet_authority"] is False
    with pytest.raises(FileExistsError):
        main(["--dataset-dir", str(path), "--output", str(output)])
