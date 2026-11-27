"""Exact readback bytes with authenticated encryption; no published key/state."""
import hashlib
import json

import pytest

from hbi import ci_readback_transport as transport


@pytest.fixture
def sample(tmp_path, monkeypatch):
    cache = tmp_path / "private-cache"
    cache.mkdir()
    (cache / ".readback-key").write_bytes(b"S" * 32)
    monkeypatch.setenv("CI_ORIGINAL_CACHE", str(cache))
    for key, value in {"GITHUB_REPOSITORY": "Maremoo2/Betting", "GITHUB_SHA": "a" * 40,
                       "GITHUB_RUN_ID": "2", "GITHUB_RUN_ATTEMPT": "1"}.items():
        monkeypatch.setenv(key, value)
    source = tmp_path / "source"
    source.mkdir()
    (source / "replay.sqlite").write_bytes(b"PRIVATE_SYNTHETIC_STATE_NOT_REAL" * 100)
    (source / "receipt.json").write_bytes(b'{"SYNTHETIC_ONLY":true}')
    encrypted = tmp_path / "public-artifact"
    transport.seal(source, encrypted)
    return source, encrypted, cache


def test_exact_bytes_roundtrip_without_plaintext_or_key_in_public_artifact(sample, tmp_path):
    source, encrypted, _ = sample
    assert sorted(p.name for p in encrypted.iterdir()) == ["readback.aesgcm", "transport.json"]
    assert b"PRIVATE_SYNTHETIC_STATE_NOT_REAL" not in (encrypted / "readback.aesgcm").read_bytes()
    assert b"S" * 32 not in (encrypted / "transport.json").read_bytes()
    restored = tmp_path / "restored"
    transport.open_transport(encrypted, restored)
    for name in transport.FILES:
        assert (restored / name).read_bytes() == (source / name).read_bytes()


def test_wrong_key_fails_without_output(sample, tmp_path):
    _, encrypted, cache = sample
    (cache / ".readback-key").write_bytes(b"X" * 32)
    with pytest.raises(ValueError, match="AUTHENTICATION_FAILED"):
        transport.open_transport(encrypted, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_wrong_attempt_cannot_reuse_previous_ciphertext(sample, tmp_path, monkeypatch):
    _, encrypted, _ = sample
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    with pytest.raises(ValueError, match="CONTEXT_MISMATCH"):
        transport.open_transport(encrypted, tmp_path / "not-created")


def test_modified_ciphertext_rejected_even_with_recomputed_public_digest(sample, tmp_path):
    _, encrypted, _ = sample
    path = encrypted / "readback.aesgcm"
    raw = path.read_bytes()
    raw = bytes([raw[0] ^ 1]) + raw[1:]
    path.write_bytes(raw)
    meta = json.loads((encrypted / "transport.json").read_text())
    meta["ciphertext_sha256"] = hashlib.sha256(raw).hexdigest()
    (encrypted / "transport.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="AUTHENTICATION_FAILED"):
        transport.open_transport(encrypted, tmp_path / "not-created")


def test_sealed_transport_does_not_overwrite_history(sample):
    source, encrypted, _ = sample
    with pytest.raises(FileExistsError):
        transport.seal(source, encrypted)
