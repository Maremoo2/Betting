"""Private source transport contracts; synthetic bytes never count as originals."""
import hashlib
import io
import json
import zipfile

import pytest

from hbi import ci_originals as originals


@pytest.fixture
def source(tmp_path, monkeypatch):
    raw = io.BytesIO()
    body = b'{"SYNTHETIC_ONLY":true}'
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("source.json", body)
    raw = raw.getvalue()
    entry = {"artifact_id": 10, "repository": "Maremoo2/Betting", "run_id": 20,
             "artifact_name": "test-original", "state": "VERIFIED_ORIGINAL", "zip_filename": "10.zip",
             "zip_sha256": hashlib.sha256(raw).hexdigest(), "source_bytes": len(raw),
             "workflow_run_head": "a" * 40, "archive_path": "archive/10.zip",
             "members": [{"path": "source.json", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}]}
    catalogue = {"schema": "CI_HISTORICAL_ORIGINALS_V1", "private_repository": originals.PRIVATE_REPO,
                 "private_commit": "b" * 40, "sources": [entry, {**entry, "artifact_id": 11,
                 "artifact_name": "lost-original", "zip_filename": "11.zip", "state": "SOURCE_UNRECOVERABLE"}]}
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalogue))
    monkeypatch.setattr(originals, "CATALOG", path)
    root = tmp_path / "cache"
    root.mkdir()
    (root / "10.zip").write_bytes(raw)
    monkeypatch.setenv("CI_ORIGINAL_CACHE", str(root))
    for key, value in {"GITHUB_REPOSITORY": "Maremoo2/Betting", "GITHUB_SHA": "c" * 40,
                       "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}.items():
        monkeypatch.setenv(key, value)
    return root, entry, raw


def test_retained_bytes_idempotent_extract_and_readback(source, tmp_path):
    _, entry, _ = source
    destination = tmp_path / "restored"
    originals.extract(entry, destination)
    before = (destination / "source.json").read_bytes()
    originals.extract(entry, destination)
    assert (destination / "source.json").read_bytes() == before
    (destination / "source.json").write_bytes(b"CONFLICT")
    with pytest.raises(ValueError, match="APPEND_ONLY_CONFLICT"):
        originals.extract(entry, destination)
    assert (destination / "source.json").read_bytes() == b"CONFLICT"


def test_explicit_unrecoverable_does_not_call_network(source, monkeypatch):
    monkeypatch.setattr(originals, "api", lambda *a, **k: pytest.fail("No network fallback"))
    with pytest.raises(ValueError, match="SOURCE_UNRECOVERABLE:11"):
        originals.find_source(artifact_id=11)


@pytest.mark.parametrize("key,value", [("run_id", 21), ("repository", "Other/Repo"),
                                       ("sha256", "f" * 64), ("commit", "f" * 40)])
def test_wrong_provenance_not_replaced_by_same_races(source, key, value):
    _, entry, _ = source
    request = {"artifact_id": 10, "run_id": 20, "repository": entry["repository"],
               "sha256": entry["zip_sha256"], "commit": entry["workflow_run_head"], key: value}
    with pytest.raises(ValueError, match="PROVENANCE_MISMATCH"):
        originals.cached_archive(request)


def test_wrong_archive_sha_blocks_before_extract(source, tmp_path):
    root, entry, _ = source
    (root / "10.zip").write_bytes(b"CORRUPTED")
    with pytest.raises(ValueError, match="ZIP_SHA_OR_SIZE_MISMATCH"):
        originals.extract(entry, tmp_path / "no-output")
    assert not (tmp_path / "no-output").exists()


def test_wrong_member_pin_still_blocks(source, tmp_path):
    _, entry, _ = source
    entry["members"][0]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="MEMBER_SHA_MISMATCH"):
        originals.extract(entry, tmp_path / "no-output")


def test_traversal_rejected_even_in_signed_test_archive(source):
    root, entry, _ = source
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape", b"bad")
    data = stream.getvalue()
    (root / "10.zip").write_bytes(data)
    entry.update(zip_sha256=hashlib.sha256(data).hexdigest(), source_bytes=len(data))
    with pytest.raises(ValueError, match="UNSAFE_MEMBER"):
        originals.verify_zip(root / "10.zip", entry)


def test_private_fetch_preserves_partial_status_and_hides_credential(source, tmp_path, monkeypatch):
    _, _, raw = source
    token = "SYNTHETIC_READ_CREDENTIAL_NOT_REAL"
    monkeypatch.setenv("RESEARCH_ARCHIVE_READ_TOKEN", token)
    monkeypatch.setattr(originals, "api", lambda path, credential, limit, **kwargs:
                        raw if kwargs.get("raw") else json.dumps({"private": True,
                        "full_name": originals.PRIVATE_REPO}).encode())
    root = tmp_path / "downloaded"
    result = originals.fetch(root)
    assert result["verified"] == [10] and result["source_unrecoverable"] == [11]
    assert result["status"] == "PARTIAL"
    assert token not in json.dumps(result)
    assert (root / ".readback-key").stat().st_size == 32
    assert token.encode() not in (root / ".readback-key").read_bytes()


def test_public_archive_stays_blocked(source, tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_ARCHIVE_READ_TOKEN", "synthetic")
    monkeypatch.setattr(originals, "api", lambda *a, **k: b'{"private":false}')
    with pytest.raises(ValueError, match="MUST_REMAIN_PRIVATE"):
        originals.fetch(tmp_path / "never-created")
    assert not (tmp_path / "never-created").exists()


def test_missing_cache_never_uses_expiring_action(source, monkeypatch):
    monkeypatch.delenv("CI_ORIGINAL_CACHE")
    _, entry, _ = source
    with pytest.raises(ValueError, match="CACHE_REQUIRED_NO_NETWORK_FALLBACK"):
        originals.cached_archive({"artifact_id": entry["artifact_id"]})


@pytest.mark.parametrize("key,value", [("archive_path", "archive/../private/10.zip"),
                                       ("zip_filename", "../10.zip"), ("state", "ASSUME_VALID")])
def test_invalid_catalogue_cannot_redirect_private_reads(source, key, value):
    doc = json.loads(originals.CATALOG.read_bytes())
    doc["sources"][0][key] = value
    originals.CATALOG.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="CATALOG"):
        originals.catalog()
