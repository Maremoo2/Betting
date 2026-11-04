"""MVP-017 local-only, explicit-approval private immutable original archive.

NEVER invoked by production workflows. It creates no remote storage, no
model/odds/settlement data and no PIT or betting authority. Every original
is copied byte-for-byte with its SHA-256; claimed metadata are NOT independent
provider attestations. Only store explicitly approved, non-sensitive sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "MVP017_PRIVATE_ORIGINAL_ARCHIVE_RECEIPT_V1"
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
REDACTION_GUARD = re.compile(
    r"Bearer\s+[A-Za-z0-9._~+/-]{12,}|[\"']?"
    r"(?:access_token|refresh_token|client_secret|private_key|authorization)"
    r"[\"']?\s*[:=]",
    flags=re.IGNORECASE,
)
MAX_ORIGINAL_BYTES = 100 * 1024 * 1024


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def _clock(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("OBSERVATION_CLOCK_MISSING")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("OBSERVATION_CLOCK_INVALID") from exc
    if parsed.utcoffset() is None:
        raise ValueError("OBSERVATION_CLOCK_NAIVE")
    return parsed.astimezone(UTC).isoformat()


def _directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("ARCHIVE_SYMLINK_FORBIDDEN")
    if path.exists() and not path.is_dir():
        raise ValueError("ARCHIVE_PATH_NOT_DIRECTORY")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or (stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ValueError("ARCHIVE_DIRECTORY_NOT_PRIVATE")


def _write_once(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _validate_origin(provider: str, endpoint: str, approved_id: str) -> None:
    if not all(isinstance(v, str) and IDENTIFIER.fullmatch(v)
               for v in (provider, approved_id)):
        raise ValueError("ARCHIVE_PROVIDER_OR_APPROVAL_INVALID")
    if (not isinstance(endpoint, str) or not endpoint.startswith("/")
            or len(endpoint) > 240 or "?" in endpoint or "#" in endpoint
            or not re.fullmatch(r"/[A-Za-z0-9_./:-]+", endpoint)):
        raise ValueError("ARCHIVE_ENDPOINT_WITH_POTENTIAL_SECRET")


def _guard_sensitive(raw: bytes) -> None:
    if not raw or len(raw) > MAX_ORIGINAL_BYTES:
        raise ValueError("ARCHIVE_ORIGINAL_SIZE_INVALID")
    # Conservative detector, NOT a guarantee that arbitrary raw bytes have no
    # sensitive fields. Operator must classify source before calling ingest.
    text = raw.decode("utf-8", errors="ignore")
    if REDACTION_GUARD.search(text):
        raise ValueError("ARCHIVE_POSSIBLE_SENSITIVE_ORIGINAL")


def store_original(
    *, archive_root: Path, source_file: Path, source_provider: str,
    endpoint: str, observed_at_utc: str, source_run_id: int,
    source_artifact_id: int, approval_id: str,
    physical_race_id: str | None = None,
    model_sha256: str | None = None,
    publication_at_utc: str | None = None,
    original_decision: str = "RESEARCH_ONLY_UNCERTIFIED",
) -> dict[str, Any]:
    """Store only caller-approved bytes locally; receipt is append-only.

    Identical bytes may have multiple distinct original provenance receipts.
    A byte-identical duplicate provenance attempt raises FileExistsError.
    """
    _validate_origin(source_provider, endpoint, approval_id)
    if type(source_run_id) is not int or source_run_id <= 0:
        raise ValueError("ARCHIVE_RUN_ID_INVALID")
    if type(source_artifact_id) is not int or source_artifact_id <= 0:
        raise ValueError("ARCHIVE_ARTIFACT_ID_INVALID")
    if physical_race_id is not None and (
        not isinstance(physical_race_id, str)
        or IDENTIFIER.fullmatch(physical_race_id) is None
    ):
        raise ValueError("ARCHIVE_RACE_ID_INVALID")
    if model_sha256 is not None and (
        not isinstance(model_sha256, str) or HEX_SHA.fullmatch(model_sha256) is None
    ):
        raise ValueError("ARCHIVE_MODEL_SHA_INVALID")
    if original_decision != "RESEARCH_ONLY_UNCERTIFIED":
        raise ValueError("ARCHIVE_MUST_NOT_CLAIM_ADMISSION_OR_PIT")
    if source_file.is_symlink() or not source_file.is_file():
        raise ValueError("ARCHIVE_SOURCE_NOT_REGULAR")
    raw = source_file.read_bytes()
    _guard_sensitive(raw)
    observed = _clock(observed_at_utc)
    published = _clock(publication_at_utc) if publication_at_utc is not None else None
    root = Path(archive_root)
    _directory(root)
    blob_root = root / "sha256"
    _directory(blob_root)
    key = _hash(raw)
    prefix = blob_root / key[:2]
    _directory(prefix)
    blob = prefix / key
    if blob.exists():
        if blob.is_symlink() or not blob.is_file() or _hash(blob.read_bytes()) != key:
            raise ValueError("ARCHIVE_EXISTING_BLOB_CORRUPT")
    else:
        _write_once(blob, raw)
    receipts_dir = root / "receipts"
    _directory(receipts_dir)
    provenance = {
        "schema": SCHEMA,
        "source_sha256": key,
        "source_size_bytes": len(raw),
        "source_provider_claim": source_provider,
        "endpoint_path_no_query": endpoint,
        "observed_at_utc_claim": observed,
        "published_at_utc_claim": published,
        "independent_provider_clock_attested": False,
        "source_github_run_id": source_run_id,
        "source_github_artifact_id": source_artifact_id,
        "physical_race_id_claim": physical_race_id,
        "model_sha256_claim": model_sha256,
        "approval_id": approval_id,
        "original_decision": original_decision,
        "source_data_classification": "EXPLICIT_APPROVAL_REQUIRED_LOCAL_ONLY",
        "pit_certified": False,
        "bet_authority": False,
    }
    encoded = _canonical(provenance)
    receipt_key = _hash(encoded)
    _write_once(receipts_dir / (receipt_key + ".json"), encoded)
    return {"receipt_sha256": receipt_key, "original_sha256": key,
            "source_size_bytes": len(raw), "bet_authority": False}


def verify_archive(root: Path) -> dict[str, Any]:
    """Rehash every receipt and referenced raw source, never repair anything."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("ARCHIVE_ROOT_NOT_AVAILABLE")
    records = root / "receipts"
    if records.is_symlink() or not records.is_dir():
        raise ValueError("ARCHIVE_RECEIPTS_NOT_AVAILABLE")
    files = sorted(records.glob("*.json"))
    if not files:
        raise ValueError("ARCHIVE_HAS_NO_RECEIPTS")
    referenced: set[str] = set()
    for file in files:
        if file.is_symlink() or not file.is_file():
            raise ValueError("ARCHIVE_RECEIPT_NOT_REGULAR")
        raw = file.read_bytes()
        if file.name != _hash(raw) + ".json":
            raise ValueError("ARCHIVE_RECEIPT_SHA_MISMATCH")
        item = json.loads(raw)
        if (not isinstance(item, dict) or item.get("schema") != SCHEMA
                or _canonical(item) != raw or item.get("bet_authority") is not False
                or item.get("pit_certified") is not False):
            raise ValueError("ARCHIVE_RECEIPT_CONTRACT_INVALID")
        key = item.get("source_sha256")
        if not isinstance(key, str) or not HEX_SHA.fullmatch(key):
            raise ValueError("ARCHIVE_ORIGINAL_SHA_INVALID")
        blob = root / "sha256" / key[:2] / key
        if blob.is_symlink() or not blob.is_file() or _hash(blob.read_bytes()) != key:
            raise ValueError("ARCHIVE_ORIGINAL_BYTES_MISSING_OR_CHANGED")
        if blob.stat().st_size != item.get("source_size_bytes"):
            raise ValueError("ARCHIVE_ORIGINAL_SIZE_CHANGED")
        referenced.add(key)
    return {"schema": "MVP017_LOCAL_ARCHIVE_VERIFICATION_V1",
            "status": "LOCAL_BYTES_VERIFIED_NO_PROVIDER_ATTESTATION",
            "original_source_blobs": len(referenced),
            "distinct_provenance_receipts": len(files),
            "permanent_external_retention_configured": False,
            "pit_certified": False, "bet_authority": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    ingest = sub.add_parser("store")
    ingest.add_argument("--source-file", type=Path, required=True)
    ingest.add_argument("--source-provider", required=True)
    ingest.add_argument("--endpoint", required=True)
    ingest.add_argument("--observed-at-utc", required=True)
    ingest.add_argument("--source-run-id", type=int, required=True)
    ingest.add_argument("--source-artifact-id", type=int, required=True)
    ingest.add_argument("--approval-id", required=True)
    ingest.add_argument("--physical-race-id")
    ingest.add_argument("--model-sha256")
    ingest.add_argument("--publication-at-utc")
    sub.add_parser("verify")
    args = parser.parse_args(argv)
    if args.action == "verify":
        result = verify_archive(args.root)
    else:
        result = store_original(
            archive_root=args.root, source_file=args.source_file,
            source_provider=args.source_provider, endpoint=args.endpoint,
            observed_at_utc=args.observed_at_utc,
            source_run_id=args.source_run_id,
            source_artifact_id=args.source_artifact_id,
            approval_id=args.approval_id,
            physical_race_id=args.physical_race_id,
            model_sha256=args.model_sha256,
            publication_at_utc=args.publication_at_utc,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
