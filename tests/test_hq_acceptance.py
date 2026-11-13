import hashlib

import pytest

from hbi.hq_acceptance import pinned_zip


def test_pinned_archive_replay_rejects_changed_bytes(tmp_path):
    original = tmp_path / "123.zip"
    body = b"fixture bytes"
    original.write_bytes(body)
    pin = hashlib.sha256(body).hexdigest()
    assert pinned_zip(tmp_path, "123", pin) == original
    assert pinned_zip(tmp_path, "123", pin) == original
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA mismatch"):
        pinned_zip(tmp_path, "123", pin)


def test_archive_id_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError, match="artifact ID"):
        pinned_zip(tmp_path, "../123", "0" * 64)
