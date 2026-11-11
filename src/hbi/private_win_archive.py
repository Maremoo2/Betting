"""Dormant local WIN archive adapter. No watcher or workflow calls this module."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC
from pathlib import Path
from uuid import uuid4

from .mvp017_private_original_archive import _guard_sensitive
from .providers.rikstoto import OriginalBytesFetchResult, RikstotoClient

_DIGEST = re.compile(r"[0-9a-f]{64}")
_RACE = re.compile(r"RIKSTOTO:([A-Z0-9_\-]+):([1-9][0-9]*)")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _put_once(path: Path, body: bytes) -> None:
    staging = path.with_suffix(f".{uuid4().hex}.tmp")
    try:
        with staging.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staging, path)
        except FileExistsError:
            pass
        if path.is_symlink() or path.read_bytes() != body:
            raise ValueError("WIN_ARCHIVE_CONFLICT")
    finally:
        staging.unlink(missing_ok=True)


def _blob(root: Path, digest: str) -> bytes:
    if not _DIGEST.fullmatch(digest):
        raise ValueError("WIN_ARCHIVE_INVALID_DIGEST")
    path = root / f"{digest}.body"
    if path.is_symlink():
        raise ValueError("WIN_ARCHIVE_INVALID_BLOB")
    body = path.read_bytes()
    if _digest(body) != digest:
        raise ValueError("WIN_ARCHIVE_HASH_MISMATCH")
    return body


def verify_win(root: Path, receipt_sha256: str) -> dict:
    if not _DIGEST.fullmatch(receipt_sha256):
        raise ValueError("WIN_ARCHIVE_INVALID_RECEIPT")
    path = root / f"{receipt_sha256}.json"
    if path.is_symlink():
        raise ValueError("WIN_ARCHIVE_INVALID_RECEIPT")
    encoded = path.read_bytes()
    if _digest(encoded) != receipt_sha256:
        raise ValueError("WIN_ARCHIVE_RECEIPT_MISMATCH")
    receipt = json.loads(encoded)
    if len(_blob(root, receipt["body_sha256"])) != receipt["body_size"]:
        raise ValueError("WIN_ARCHIVE_SIZE_MISMATCH")
    return receipt


def archive_win(
    root: Path, fetch: OriginalBytesFetchResult, *, race_id: str, approval_id: str,
) -> str:
    """Write only an explicitly approved public response to a private, ACL-managed root."""
    if not approval_id.strip() or root.is_symlink() or not root.is_dir():
        raise ValueError("WIN_ARCHIVE_APPROVAL_AND_PRIVATE_ROOT_REQUIRED")
    match = _RACE.fullmatch(race_id)
    if match is None:
        raise ValueError("WIN_ARCHIVE_INVALID_RACE")
    key, race_no = match.groups()
    expected = f"{RikstotoClient.API}/game/{key}/betdistribution/winodds/{race_no}"
    completed = fetch.response_completed_at
    body = fetch.raw_body
    digest = _digest(body)
    if (
        fetch.url != expected or not fetch.success or fetch.status_code != 200
        or completed is None or completed.utcoffset() is None
        or not body or digest != fetch.response_body_sha256
    ):
        raise ValueError("WIN_ARCHIVE_SOURCE_UNVERIFIED")
    _guard_sensitive(body)
    receipt = {
        "race_id": race_id, "source_uri": expected, "approval_id": approval_id,
        "response_completed_at_utc": completed.astimezone(UTC).isoformat(),
        "body_sha256": digest, "body_size": len(body), "pit_certified": False,
    }
    encoded = json.dumps(receipt, sort_keys=True).encode()
    receipt_sha = _digest(encoded)
    _put_once(root / f"{digest}.body", body)
    _put_once(root / f"{receipt_sha}.json", encoded)
    verify_win(root, receipt_sha)
    return receipt_sha
