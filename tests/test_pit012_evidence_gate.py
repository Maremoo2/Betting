"""PIT-012 source evidence: synthetic bytes only, never real certification."""
import hashlib
import json

import pytest

from hbi.pit012_evidence_gate import audit_win_original, audit_frozen_model


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def win_case(folder):
    raw = b'{"result":{"TEST_ONLY":true}}'
    (folder / "WIN.raw.json").write_bytes(raw)
    return {
        "raceday_key": "S2_NR_2026-11-09", "race_number": 2,
        "source_uri": "https://www.rikstoto.no/api/game/S2_NR_2026-11-09/betdistribution/winodds/2",
        "http_status": 200, "market_kind": "WIN",
        "request_started_at_utc": "2026-11-09T17:37:00Z",
        "response_completed_at_utc": "2026-11-09T17:37:01Z",
        "archive_completed_at_utc": "2026-11-09T17:37:02Z",
        "member": "WIN.raw.json", "sha256": digest(raw),
    }


def check_win(folder, record):
    return audit_win_original(
        record, root=folder, cutoff="2026-11-09T17:38:00Z",
        raceday_key="S2_NR_2026-11-09", race_number=2,
    )


def model_case(folder):
    file_data = {
        "model_artifact": b"TEST_ONLY_MODEL",
        "input_dataset": b'{"features":{"1":1,"2":2}}',
        "frozen_prediction": json.dumps({
            "model_version": "TEST_ONLY_V1", "active_field": ["1", "2"],
            "probabilities": {"1": 0.4, "2": 0.6},
        }).encode(),
    }
    row = {
        "model_version": "TEST_ONLY_V1",
        "model_calculated_at": "2026-11-09T17:37:10Z",
        "model_frozen_at": "2026-11-09T17:37:11Z",
    }
    for role, raw in file_data.items():
        name = role + ".bytes"
        (folder / name).write_bytes(raw)
        row[role] = {"member": name, "sha256": digest(raw)}
    return row


def check_model(folder, row, field=None):
    return audit_frozen_model(
        row, root=folder, cutoff="2026-11-09T17:38:00Z",
        active_field=field if field is not None else ["1", "2"],
    )


def test_raw_win_sha_is_not_pit_certificate(tmp_path):
    r = check_win(tmp_path, win_case(tmp_path))
    assert r["source_bytes_verified"]
    assert r["pit_evidence_status"] == "PIT_UNPROVEN"
    assert r["bet_authority"] is False
    assert "SCRATCH_CORROBORATION_MISSING" in r["blockers"]


@pytest.mark.parametrize("field,value,reason", [
    ("request_started_at_utc", "2026-11-09T17:38:01Z", "REQUEST_STARTED_AT_UTC_AFTER_CUTOFF"),
    ("response_completed_at_utc", "2026-11-09T17:38:01Z", "RESPONSE_COMPLETED_AT_UTC_AFTER_CUTOFF"),
    ("archive_completed_at_utc", "2026-11-09T17:38:01Z", "ARCHIVE_COMPLETED_AT_UTC_AFTER_CUTOFF"),
    ("archive_completed_at_utc", None, "MISSING_OR_NAIVE_ARCHIVE_COMPLETED_AT_UTC"),
    ("response_completed_at_utc", "2026-11-09T17:36:00Z", "SOURCE_CLOCK_ORDER_INVALID"),
    ("source_uri", "https://example.com/win", "WIN_SOURCE_ENDPOINT_NOT_VERIFIED"),
    ("http_status", 500, "WIN_HTTP_NOT_200"),
    ("race_number", 3, "RACE_IDENTITY_MISMATCH"),
    ("market_kind", "PLACE", "MARKET_NOT_WIN"),
])
def test_raw_win_fail_closed(tmp_path, field, value, reason):
    case = win_case(tmp_path)
    case[field] = value
    assert reason in check_win(tmp_path, case)["blockers"]


def test_mutated_or_missing_win_is_rejected(tmp_path):
    row = win_case(tmp_path)
    (tmp_path / "WIN.raw.json").write_bytes(b"modified")
    assert "SOURCE_BYTES_SHA_MISMATCH" in check_win(tmp_path, row)["blockers"]
    (tmp_path / "WIN.raw.json").unlink()
    assert "SOURCE_RAW_BYTES_MISSING_OR_OVERSIZED" in check_win(tmp_path, row)["blockers"]


def test_duplicate_json_keys_and_traversal_rejected(tmp_path):
    row = win_case(tmp_path)
    raw = b'{"a":1,"a":2}'
    (tmp_path / "WIN.raw.json").write_bytes(raw)
    row["sha256"] = digest(raw)
    assert "RAW_WIN_JSON_INVALID" in check_win(tmp_path, row)["blockers"]
    row["member"] = "../outside.json"
    assert "SOURCE_REFERENCE_INVALID" in check_win(tmp_path, row)["blockers"]


def test_model_complete_hashes_still_not_pit(tmp_path):
    answer = check_model(tmp_path, model_case(tmp_path))
    assert answer["pit_evidence_status"] == "PIT_UNPROVEN"
    assert answer["challenger_v3_evaluated"] is False
    assert "MODEL_TRAINING_ORIGIN_UNATTESTED" in answer["blockers"]


@pytest.mark.parametrize("field,value,reason", [
    ("model_calculated_at", "2026-11-09T17:38:01Z", "MODEL_CALCULATED_AFTER_CUTOFF"),
    ("model_frozen_at", "2026-11-09T17:38:01Z", "MODEL_FROZEN_AFTER_CUTOFF"),
    ("model_calculated_at", "2026-11-09T17:37:12Z", "MODEL_CALCULATED_AFTER_FROZEN"),
    ("model_calculated_at", None, "MODEL_CALCULATED_TIME_MISSING"),
    ("model_frozen_at", None, "MODEL_FROZEN_TIME_MISSING"),
    ("model_version", "", "MODEL_VERSION_MISSING"),
])
def test_model_freeze_missing_or_late(tmp_path, field, value, reason):
    case = model_case(tmp_path)
    case[field] = value
    assert reason in check_model(tmp_path, case)["blockers"]


def test_model_mutation_and_wrong_field_rejected(tmp_path):
    case = model_case(tmp_path)
    (tmp_path / "model_artifact.bytes").write_bytes(b"MUTATED")
    assert "MODEL_ARTIFACT_SOURCE_BYTES_SHA_MISMATCH" in check_model(tmp_path, case)["blockers"]
    case = model_case(tmp_path)
    assert "PREDICTION_ACTIVE_FIELD_MISMATCH" in check_model(tmp_path, case, ["2", "1"])["blockers"]


def test_postrace_winner_in_prediction_rejected(tmp_path):
    case = model_case(tmp_path)
    p = {
        "model_version": "TEST_ONLY_V1", "active_field": ["1", "2"],
        "probabilities": {"1": .4, "2": .6}, "winner_selection_id": "2",
    }
    raw = json.dumps(p).encode()
    (tmp_path / "frozen_prediction.bytes").write_bytes(raw)
    case["frozen_prediction"]["sha256"] = digest(raw)
    assert "POST_RESULT_LEAKAGE_IN_FROZEN_PREDICTION" in check_model(tmp_path, case)["blockers"]
