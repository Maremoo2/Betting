"""TEST_ONLY M5 partition serialization and strict lockbox/label segregation."""
# ruff: noqa: I001  # Preserve TEST_ONLY fixture import grouping across classifiers.
from __future__ import annotations

import hashlib
import json

import pytest

from hbi.mvp023a_dataset_partitions import build_partitioned_dataset, main


KEY = "BJ_NR_2020-01-04"
RID = "RIKSTOTO:" + KEY + ":1"


def setup_m5(tmp_path, *, year=2020):
    directory = tmp_path / "m5"
    directory.mkdir()
    key = f"BJ_NR_{year}-01-04"
    rid = f"RIKSTOTO:{key}:1"
    source = {
        "url": f"https://www.rikstoto.no/api/racedays/{key}/starts",
        "body_sha256": "a" * 64,
        "fetched_at": "2026-10-10T09:00:00+00:00", "published_at": None,
    }
    result_source = {
        "url": f"https://www.rikstoto.no/api/results/raceDays/{key}/1/completeresults",
        "body_sha256": "b" * 64,
        "fetched_at": "2026-10-10T09:01:00+00:00",
    }
    horses = [
        {"selection_id": str(n), "name": f"Horse {n}",
         "registration_observed": f"H{n}", "identity_status": "IDENTITY_VERIFIED",
         "scratched": False,
         "features": {"driver": {
             "value": f"Driver {n}", "status": "UNRESOLVED",
             "source_url": source["url"], "source_body_sha256": source["body_sha256"],
             "source_observed_at": source["fetched_at"], "published_at": None,
         }, "extra_distance_m": None}}
        for n in (1, 2)
    ]
    row = {
        "race_id": rid, "raceday_key": key, "date": f"{year}-01-04",
        "country": "NO", "track": "Bjerke", "discipline": "trot",
        "event_time": f"{year}-01-04T12:00:00+01:00",
        "full_field_identity_verified": True, "authoritative_result_verified": True,
        "roster": horses, "source_refs": [source, result_source],
        "labels": [
            {"selection_id": str(n), "registration": f"H{n}",
             "placing": n, "km_time_raw": f"1{n},0",
             "role": "RETROSPECTIVE_LABEL_ONLY"}
            for n in (1, 2)
        ],
        "model_candidate": {
            "schema": "HBI_RACE_MODEL_CANDIDATE_V1", "race_id": rid,
            "data_ready": False, "model_eligible": False,
        },
    }
    raw = (json.dumps(row) + "\n").encode()
    (directory / "dataset.jsonl").write_bytes(raw)
    manifest = {
        "schema": "HBI_RESEARCH_DATASET_V1", "model_eligible": 0,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "per_month": {f"{year}-01": {"races": 1}},
    }
    (directory / "model-readiness.json").write_text(json.dumps(manifest))
    return directory, row


def rewrite(directory, row):
    raw = (json.dumps(row) + "\n").encode()
    (directory / "dataset.jsonl").write_bytes(raw)
    manifest = json.loads((directory / "model-readiness.json").read_text())
    manifest["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    (directory / "model-readiness.json").write_text(json.dumps(manifest))


def test_research_partition_inputs_separated_from_late_results(tmp_path):
    directory, row = setup_m5(tmp_path)
    manifest, inputs, labels = build_partitioned_dataset(directory)
    assert manifest["races"] == 1
    assert manifest["partitions"]["DEVELOPMENT_2015_2022"]["race_ids"] == [RID]
    assert manifest["model_training_eligible"] == 0
    assert inputs[0]["market_input"] is None
    assert inputs[0]["active_runner_ids"] == ["1", "2"]
    assert inputs[0]["runners"][0]["features"]["extra_distance_m"] is None
    assert "labels" not in json.dumps(inputs)
    assert "km_time_raw" not in json.dumps(inputs)
    assert "results" not in json.dumps(inputs)
    assert labels[0]["status"] == "RETROSPECTIVE_LABEL_ONLY"
    assert labels[0]["results"][0]["placing"] == 1
    assert row["labels"][0]["km_time_raw"] == "11,0"
    assert manifest["input_dataset_sha256"] != manifest["label_dataset_sha256"]
    assert build_partitioned_dataset(directory)[0] == manifest


def test_candidate_lockbox_refused_before_dataset_file_read(tmp_path):
    directory, _ = setup_m5(tmp_path)
    manifest = json.loads((directory / "model-readiness.json").read_text())
    manifest["per_month"] = {"2025-01": {"races": 1}}
    (directory / "model-readiness.json").write_text(json.dumps(manifest))
    (directory / "dataset.jsonl").write_bytes(b"UNOPENED_2025_LOCKBOX_NOT_JSON")
    with pytest.raises(ValueError, match="LOCKBOX_EXPOSURE_AUDIT_REQUIRED"):
        build_partitioned_dataset(directory)


def test_dataset_original_sha_change_refused(tmp_path):
    directory, _ = setup_m5(tmp_path)
    (directory / "dataset.jsonl").write_text("altered")
    with pytest.raises(ValueError, match="M5_ORIGINAL_DATASET_SHA_MISMATCH"):
        build_partitioned_dataset(directory)


def test_post_race_feature_leakage_refused(tmp_path):
    directory, row = setup_m5(tmp_path)
    row["roster"][0]["features"]["closing_odds"] = {"value": 4.5}
    rewrite(directory, row)
    with pytest.raises(ValueError, match="RESULT_OR_MARKET_FEATURE_LEAKAGE"):
        build_partitioned_dataset(directory)


def test_missing_registered_start_source_ref_refused(tmp_path):
    directory, row = setup_m5(tmp_path)
    row["source_refs"] = [row["source_refs"][1]]
    rewrite(directory, row)
    with pytest.raises(ValueError, match="M5_PRE_RACE_STARTS_SOURCE_NOT_UNIQUE"):
        build_partitioned_dataset(directory)


def test_duplicate_physical_race_rejected(tmp_path):
    directory, row = setup_m5(tmp_path)
    raw = (json.dumps(row) + "\n") * 2
    (directory / "dataset.jsonl").write_text(raw)
    m = json.loads((directory / "model-readiness.json").read_text())
    m["dataset_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    (directory / "model-readiness.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE"):
        build_partitioned_dataset(directory)


def test_write_once_cli_and_original_unchanged(tmp_path):
    directory, _ = setup_m5(tmp_path)
    original = (directory / "dataset.jsonl").read_bytes()
    output = tmp_path / "research-out"
    assert main(["--dataset-dir", str(directory), "--output-dir", str(output)]) == 0
    assert original == (directory / "dataset.jsonl").read_bytes()
    manifest = json.loads((output / "manifest.json").read_text())
    inputs = json.loads((output / "fundamental-inputs.json").read_text())
    labels = json.loads((output / "retrospective-labels.json").read_text())
    assert manifest["races"] == len(inputs) == len(labels) == 1
    assert manifest["bet_authority"] is False
    with pytest.raises(FileExistsError):
        main(["--dataset-dir", str(directory), "--output-dir", str(output)])
