"""CLOUD-RUN-005: private content-addressed originals captured before JSON parsing.

Only an owner-approved research archive. No PIT, model admission, or betting rights.
The existing immutable MVP017 archive primitives enforce private ACLs and write-once
files; source bytes are never placed in logs or in the SQLite JSON observations.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .mvp017_private_original_archive import _directory, _guard_sensitive, _write_once
from .storage import SQLiteStore

SCHEMA = "CLOUD_RUN005_ORIGINAL_RECEIPT_V1"
CATEGORY = "CLOUD_RUN005_ORIGINAL_RECEIPT_V1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
RACE = re.compile(r"RIKSTOTO:([A-Z0-9_]+_\d{4}-\d{2}-\d{2}):([1-9]\d*)\Z")
RIK_PATH = re.compile(r"/api/racedays/([A-Z0-9_]+_\d{4}-\d{2}-\d{2})/(?:starts|scratched)\Z")
ATG_CAL = re.compile(r"/api-public/v0/calendar/day/\d{4}-\d{2}-\d{2}\Z")
ATG_RACE = re.compile(r"/services/racinginfo/v1/api/games/vinnare_[A-Za-z0-9_-]+\Z")
APPROVAL = "CLOUD_RUN005_HQ_2026-11-12_RESEARCH_ONLY"


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(record: dict[str, object]) -> bytes:
    return (json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _valid_source(provider: str, url: str, race_id: str) -> tuple[str, str]:
    match = RACE.fullmatch(race_id)
    if match is None:
        raise ValueError("ORIGINAL_RACE_ID_INVALID")
    key, number = match.groups()
    parts = urlsplit(url)
    if parts.username or parts.password or parts.fragment:
        raise ValueError("ORIGINAL_URL_CREDENTIALS_FORBIDDEN")
    if provider == "rikstoto":
        if parts.scheme != "https" or parts.netloc != "www.rikstoto.no" or parts.query:
            raise ValueError("ORIGINAL_RIKSTOTO_SOURCE_UNAUTHORIZED")
        found = RIK_PATH.fullmatch(parts.path)
        if found is None or found.group(1) != key:
            raise ValueError("ORIGINAL_RIKSTOTO_RACE_DAY_MISMATCH")
        source_type = parts.path.rsplit("/", 1)[-1].upper()
    elif provider == "atg":
        if parts.scheme != "https" or parts.netloc not in {
            "www.atg.se", "horse-betting-info.prod.c1.atg.cloud"
        }:
            raise ValueError("ORIGINAL_ATG_SOURCE_UNAUTHORIZED")
        if parts.netloc == "www.atg.se":
            if ATG_RACE.fullmatch(parts.path) is None or parts.query:
                raise ValueError("ORIGINAL_ATG_RACE_SOURCE_UNAUTHORIZED")
            source_type = "ATG_RACE"
        else:
            if ATG_CAL.fullmatch(parts.path) is None or parts.query not in {
                "", "headToHeadEnabled=true"
            }:
                raise ValueError("ORIGINAL_ATG_CALENDAR_SOURCE_UNAUTHORIZED")
            source_type = "ATG_CALENDAR"
    else:
        raise ValueError("ORIGINAL_PROVIDER_UNAUTHORIZED")
    return f"{key}:{number}", source_type


class OriginalCapture:
    """Private write-once blobs + linked HBI provider_payloads; one race scope."""

    def __init__(self, store: SQLiteStore, root: Path, race_id: str, *,
                 approval_id: str = APPROVAL):
        if approval_id != APPROVAL:
            raise ValueError("ORIGINAL_HQ_APPROVAL_REQUIRED")
        self.store = store
        self.root = Path(root)
        self.race_id = race_id
        self.approval_id = approval_id
        self.receipts: list[dict[str, object]] = []
        _directory(self.root)
        _directory(self.root / "sha256")
        _directory(self.root / "receipts")

    def capture(self, provider: str, url: str, raw: bytes, at: datetime,
                headers: Mapping[str, str | None], status: int) -> dict[str, object]:
        """Must be invoked synchronously after HTTP read and BEFORE JSON decoding."""
        key, source_type = _valid_source(provider, url, self.race_id)
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("ORIGINAL_FETCH_CLOCK_NAIVE")
        if status != 200:
            raise ValueError("ORIGINAL_HTTP_NOT_200")
        _guard_sensitive(raw)
        completed = at.astimezone(UTC).isoformat()
        body_sha = _hash(raw)
        prefix = self.root / "sha256" / body_sha[:2]
        _directory(prefix)
        blob = prefix / body_sha
        if not blob.exists():
            try:
                _write_once(blob, raw)
            except FileExistsError:
                pass
        if blob.is_symlink() or blob.read_bytes() != raw:
            raise ValueError("ORIGINAL_EXISTING_BLOB_CONFLICT")
        # Only explicit safe HTTP headers; never Authorization/Cookie/query secrets.
        allowed_headers = {
            key: headers.get(key) for key in (
                "Content-Type", "Date", "ETag", "Last-Modified", "Content-Length"
            ) if headers.get(key) is not None
        }
        receipt = {
            "schema": SCHEMA, "provider": provider, "race_id": self.race_id,
            "provider_race_key": key, "source_type": source_type,
            "source_uri": url, "body_sha256": body_sha, "body_bytes": len(raw),
            "observed_at_utc": completed, "http_status": status,
            "http_metadata": allowed_headers,
            "source_version": (allowed_headers.get("ETag")
                               or allowed_headers.get("Last-Modified") or body_sha),
            "content_type": allowed_headers.get("Content-Type"),
            "archive_blob_relative": f"sha256/{body_sha[:2]}/{body_sha}",
            "approval_id": self.approval_id,
            "original_file_persistent_external": False,
            "identity_attested": False, "independent_t4_attested": False,
            "pit_certified": False, "bet_authorized": False,
        }
        encoded = _canonical(receipt)
        receipt_sha = _hash(encoded)
        record_path = self.root / "receipts" / f"{receipt_sha}.json"
        if not record_path.exists():
            try:
                _write_once(record_path, encoded)
            except FileExistsError:
                pass
        if record_path.is_symlink() or record_path.read_bytes() != encoded:
            raise ValueError("ORIGINAL_RECEIPT_CONFLICT")
        readback = verify_original(self.root, receipt_sha)
        if readback["body_sha256"] != body_sha:
            raise ValueError("ORIGINAL_IMMEDIATE_READBACK_FAILED")

        # Append a source observation in the EXISTING research journal, linked by
        # receipt SHA and exact source URL, without copying raw private bodies.
        fields = ("payload_id", "provider", "category", "provider_raceday_key",
                  "race_number", "product", "observed_at_utc", "source_uri", "payload_json")
        race_key, race_no = key.rsplit(":", 1)
        values = (
            receipt_sha, provider, CATEGORY, race_key, int(race_no), source_type,
            completed, url, encoded.decode("utf-8").rstrip("\n"),
        )
        with self.store.connect() as db:
            prior = db.execute("SELECT * FROM provider_payloads WHERE payload_id=?",
                               (receipt_sha,)).fetchone()
            if prior is None:
                db.execute(
                    f"INSERT INTO provider_payloads ({','.join(fields)}) "
                    f"VALUES ({','.join('?' for _ in fields)})", values,
                )
            elif tuple(prior[field] for field in fields) != values:
                raise ValueError("ORIGINAL_SQLITE_RECEIPT_HASH_CONFLICT")
            read = db.execute("SELECT * FROM provider_payloads WHERE payload_id=?",
                              (receipt_sha,)).fetchone()
            if read is None or tuple(read[field] for field in fields) != values:
                raise ValueError("ORIGINAL_SQLITE_LINK_READBACK_FAILED")
        self.receipts.append({"receipt_sha256": receipt_sha, "body_sha256": body_sha,
                              "source_type": source_type, "provider": provider,
                              "race_id": self.race_id})
        return receipt


def verify_original(root: Path, receipt_sha256: str) -> dict[str, object]:
    """Reopen original content and receipt, reject missing/truncated/tampered data."""
    if HEX.fullmatch(receipt_sha256) is None:
        raise ValueError("ORIGINAL_RECEIPT_SHA_INVALID")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("ORIGINAL_ARCHIVE_ROOT_INVALID")
    path = root / "receipts" / f"{receipt_sha256}.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("ORIGINAL_RECEIPT_MISSING")
    encoded = path.read_bytes()
    if _hash(encoded) != receipt_sha256:
        raise ValueError("ORIGINAL_RECEIPT_HASH_MISMATCH")
    receipt = json.loads(encoded)
    if (not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA
            or receipt.get("pit_certified") is not False
            or receipt.get("bet_authorized") is not False
            or _canonical(receipt) != encoded):
        raise ValueError("ORIGINAL_RECEIPT_SCHEMA_INVALID")
    body_sha = receipt.get("body_sha256")
    if not isinstance(body_sha, str) or HEX.fullmatch(body_sha) is None:
        raise ValueError("ORIGINAL_BODY_SHA_INVALID")
    rel = f"sha256/{body_sha[:2]}/{body_sha}"
    if receipt.get("archive_blob_relative") != rel:
        raise ValueError("ORIGINAL_BLOB_PATH_MISMATCH")
    blob = root / rel
    if blob.is_symlink() or not blob.is_file():
        raise ValueError("ORIGINAL_BODY_MISSING")
    data = blob.read_bytes()
    if _hash(data) != body_sha or len(data) != receipt.get("body_bytes"):
        raise ValueError("ORIGINAL_BODY_HASH_OR_LENGTH_MISMATCH")
    _valid_source(str(receipt["provider"]), str(receipt["source_uri"]),
                  str(receipt["race_id"]))
    return receipt


def verify_all(root: Path) -> dict[str, object]:
    receipts = sorted((Path(root) / "receipts").glob("*.json"))
    if not receipts:
        raise ValueError("ORIGINAL_ARCHIVE_EMPTY")
    body_ids = set()
    providers = set()
    for receipt in receipts:
        meta = verify_original(root, receipt.stem)
        body_ids.add(meta["body_sha256"])
        providers.add(meta["provider"])
    return {
        "status": "ORIGINAL_BYTES_READBACK_VERIFIED_RESEARCH_ONLY",
        "receipts": len(receipts),
        "unique_originals": len(body_ids),
        "providers": sorted(providers),
        "pit_certified": False, "bet_authorized": False,
        "permanent_external_retention": False,
    }
