"""CLOUD-RUN-005: original bytes before decode, immutable SHA, no PIT promotion."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.cloud_run005_originals import (
    OriginalCapture,
    export_public_scratch_only,
    verify_all,
    verify_original,
)
from hbi.providers.atg import AtgClient
from hbi.providers.rikstoto import RikstotoClient
from hbi.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
RACE = "RIKSTOTO:S2_NR_2026-11-12:1"
STARTS = "https://www.rikstoto.no/api/racedays/S2_NR_2026-11-12/starts"
SCRATCHED = "https://www.rikstoto.no/api/racedays/S2_NR_2026-11-12/scratched"
ATG = ("https://www.atg.se/services/racinginfo/v1/api/games/"
       "vinnare_Bs_2026-11-12_1")


class FakeHTTP:
    status = 200

    def __init__(self, raw: bytes):
        self.raw = raw
        self.headers = {"Content-Type": "application/json", "ETag": '"v12"'}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.raw


def isolated_store(tmp_path):
    store = SQLiteStore(tmp_path / "sqlite" / "hbi.sqlite")
    (tmp_path / "sqlite").mkdir()
    store.initialize(ROOT / "db/schema.sql")
    store.apply_migrations(ROOT / "db/migrations")
    return store


def test_original_capture_before_invalid_json_parse(tmp_path, monkeypatch):
    store = isolated_store(tmp_path)
    root = tmp_path / "private"
    recorder = OriginalCapture(store, root, RACE)
    body = b'{"success":true,"result":'
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kw: FakeHTTP(body))
    result = RikstotoClient(archive_hook=recorder.capture).starts(
        "S2_NR_2026-11-12"
    )
    assert result.success is False
    assert len(recorder.receipts) == 1
    item = recorder.receipts[0]
    actual = verify_original(root, str(item["receipt_sha256"]))
    assert actual["body_bytes"] == len(body)
    assert actual["body_sha256"] == item["body_sha256"]
    assert verify_all(root)["unique_originals"] == 1
    saved = store.fetch_table("provider_payloads")
    assert len(saved) == 1
    assert body.decode() not in saved[0]["payload_json"]
    assert saved[0]["payload_id"] == item["receipt_sha256"]


def test_content_addressed_duplicate_and_tampering(tmp_path):
    store = isolated_store(tmp_path)
    root = tmp_path / "private"
    recorder = OriginalCapture(store, root, RACE)
    body = b'{"success":true,"result":{"1":[3]}}'
    observed = datetime(2026, 11, 12, 15, tzinfo=UTC)
    headers = {"Content-Type": "application/json", "ETag": '"v1"'}
    first = recorder.capture("rikstoto", SCRATCHED, body, observed, headers, 200)
    second = recorder.capture("rikstoto", SCRATCHED, body, observed, headers, 200)
    assert first == second
    assert verify_all(root)["unique_originals"] == 1
    assert verify_all(root)["receipts"] == 1
    assert len(store.fetch_table("provider_payloads")) == 1
    blob = root / first["archive_blob_relative"]
    blob.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ORIGINAL_BODY_HASH_OR_LENGTH_MISMATCH"):
        verify_original(root, str(recorder.receipts[0]["receipt_sha256"]))


def test_atg_raw_is_archived_before_json_decoding(tmp_path, monkeypatch):
    store = isolated_store(tmp_path)
    root = tmp_path / "private"
    recorder = OriginalCapture(store, root, RACE)
    raw = b'{"races":[]}'
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kw: FakeHTTP(raw))
    result = AtgClient(archive_hook=recorder.capture)._fetch(ATG)
    assert result.success is True
    assert recorder.receipts[0]["provider"] == "atg"
    assert verify_all(root)["receipts"] == 1


def test_scratch_export_excludes_atg_and_starts(tmp_path):
    store = isolated_store(tmp_path)
    root = tmp_path / "private"
    recorder = OriginalCapture(store, root, RACE)
    t = datetime(2026, 11, 12, 15, tzinfo=UTC)
    header = {"Content-Type": "application/json"}
    recorder.capture("rikstoto", SCRATCHED,
                     b'{"success":true,"result":{"1":[3]}}', t, header, 200)
    recorder.capture("rikstoto", STARTS,
                     b'{"success":true,"result":{"1":[]}}', t, header, 200)
    recorder.capture("atg", ATG, b'{"races":[]}', t, header, 200)
    report = export_public_scratch_only(root, tmp_path / "export")
    assert report["exported_receipts"] == 1
    assert report["atg_originals_exported"] == 0
    assert report["starts_originals_exported"] == 0
    assert verify_all(tmp_path / "export")["unique_originals"] == 1


def test_scratch_export_rejects_unclassified_content(tmp_path):
    store = isolated_store(tmp_path)
    root = tmp_path / "private"
    recorder = OriginalCapture(store, root, RACE)
    recorder.capture(
        "rikstoto", SCRATCHED,
        json.dumps({"success": True, "result": {"1": [3]},
                    "private_extra": "not safe"}).encode(),
        datetime(2026, 11, 12, 15, tzinfo=UTC),
        {"Content-Type": "application/json"}, 200,
    )
    with pytest.raises(ValueError, match="PUBLIC_SCRATCH_CONTENT_NOT_CLASSIFIED"):
        export_public_scratch_only(root, tmp_path / "export")


def test_unapproved_cross_source_or_endpoint_rejected(tmp_path):
    store = isolated_store(tmp_path)
    recorder = OriginalCapture(store, tmp_path / "private", RACE)
    with pytest.raises(ValueError, match="ORIGINAL_RIKSTOTO_SOURCE_UNAUTHORIZED"):
        recorder.capture(
            "rikstoto", "https://different.example/api/racedays/x/starts",
            b"{}", datetime.now(UTC), {}, 200,
        )
    with pytest.raises(ValueError, match="ORIGINAL_HQ_APPROVAL_REQUIRED"):
        OriginalCapture(store, tmp_path / "other", RACE, approval_id="UNAPPROVED")
