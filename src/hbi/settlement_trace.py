"""PIT-012 opt-in private, write-once settlement trace journal.

Records pre-existing settlement decisions only. Not installed in nightly jobs.
No original result payload, account details or auth headers are written.
File+digest pair is locally append-only via O_EXCL; it is NOT a signed WORM
archive and cannot establish independent official source authenticity.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

SCHEMA = "PIT012_SETTLEMENT_ATTEMPT_V1"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
ALLOWED = {
    "schema", "attempt_id", "ticket_id", "race_id", "horse_id",
    "horse_id_scope", "job_run_id", "started_at_utc", "finished_at_utc",
    "settlement_code_sha", "raceday_results", "complete_results",
    "cached_outcome_is_original_official_proof", "eligibility",
    "decision_reason", "ticket_status_before", "ticket_status_after",
    "bet_authority", "source_raw_body_retained_by_settlement",
}
SOURCE_FIELDS = {
    "source_url", "http_status", "source_observed_at_utc", "received_at_utc",
    "source_published_at_utc", "source_body_sha256",
    "original_raw_body_reference", "source_error_type", "status",
}


class PrivateTraceRejected(ValueError):
    """Unsafe or unverifiable private trace journal."""


def _root(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise PrivateTraceRejected("PRIVATE_TRACE_ROOT_MUST_BE_ABSOLUTE")
    if not path.exists() or path.is_symlink() or not path.is_dir():
        raise PrivateTraceRejected("PRIVATE_TRACE_ROOT_MISSING_OR_SYMLINK")
    if path.resolve(strict=True) != path:
        raise PrivateTraceRejected("PRIVATE_TRACE_ROOT_SYMLINK_COMPONENT")
    details = path.stat()
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) & 0o077:
        raise PrivateTraceRejected("PRIVATE_TRACE_ROOT_NOT_0700_OWNED")
    repo = Path(__file__).resolve().parents[2]
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if path.is_relative_to(repo) or (
        workspace is not None and path.is_relative_to(Path(workspace).resolve())
    ):
        raise PrivateTraceRejected("PRIVATE_TRACE_INSIDE_REPOSITORY")
    return path


def _check(event: dict[str, Any]) -> None:
    if not isinstance(event, dict) or event.get("schema") != SCHEMA:
        raise PrivateTraceRejected("TRACE_SCHEMA_INVALID")
    if set(event) != ALLOWED or not UUID.fullmatch(str(event["attempt_id"])):
        raise PrivateTraceRejected("TRACE_FIELDS_OR_ATTEMPT_ID_INVALID")
    if event["bet_authority"] is not False:
        raise PrivateTraceRejected("TRACE_BET_AUTHORITY_FORBIDDEN")
    for role in ("raceday_results", "complete_results"):
        value = event[role]
        if not isinstance(value, dict) or set(value) - SOURCE_FIELDS:
            raise PrivateTraceRejected("TRACE_SOURCE_FIELDS_FORBIDDEN")
        url = value.get("source_url", "MISSING")
        if not isinstance(url, str) or (
            url != "MISSING"
            and (not url.startswith("https://www.rikstoto.no/api/") or "?" in url)
        ):
            raise PrivateTraceRejected("TRACE_SOURCE_URL_UNSAFE")


def _private_read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise PrivateTraceRejected("TRACE_FILE_UNSAFE")
        return handle.read()


def _write_once(path: Path, body: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def verify_trace(root: Path, attempt_id: str) -> dict[str, object]:
    root = _root(root)
    if not UUID.fullmatch(attempt_id):
        raise PrivateTraceRejected("TRACE_ATTEMPT_ID_INVALID")
    blob = _private_read(root / (attempt_id + ".json"))
    expected = _private_read(root / (attempt_id + ".sha256")).decode("ascii")
    digest = hashlib.sha256(blob).hexdigest()
    if expected != digest + "\n":
        raise PrivateTraceRejected("TRACE_READBACK_SHA256_MISMATCH")
    event = json.loads(blob)
    _check(event)
    return {
        "attempt_id": attempt_id, "record_sha256": digest,
        "readback_sha256_verified": True,
        "independently_signed_or_immutable": False,
        "bet_authority": False,
    }


class PrivateAttemptJournal:
    """Explicit private diagnostic sink; does not touch the HBI database."""

    def __init__(self, root: Path):
        self.root = _root(root)

    def __call__(self, event: dict[str, Any]) -> None:
        _check(event)
        record_id = event["attempt_id"]
        blob = (json.dumps(event, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")) + "\n").encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()
        body_path = self.root / (record_id + ".json")
        digest_path = self.root / (record_id + ".sha256")
        _write_once(body_path, blob)
        _write_once(digest_path, (digest + "\n").encode("ascii"))
        verify_trace(self.root, record_id)
