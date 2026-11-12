"""Read-only validation of one existing Collector daily release ZIP.

No provider requests, source modification, SQLite writes or betting authority.
A matching local hash proves byte consistency, never independent PIT timing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

ZIP_NAME = re.compile(r"rikstoto-(\d{4}-\d{2}-\d{2})-(\d{8}T\d{12}Z)\.zip\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_UNCOMPRESSED_BYTES = 800_000_000
MAX_FILES = 20_000


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_release(archive: Path, checksum: Path) -> dict[str, object]:
    """Require exact ZIP/checksum/readback matching; never certify a PIT decision."""
    match = ZIP_NAME.fullmatch(archive.name)
    if match is None or checksum.name != archive.name + ".sha256":
        raise ValueError("CLOUD_ARCHIVE_NAME_OR_SIDECAR_INVALID")
    if any(p.is_symlink() or not p.is_file() for p in (archive, checksum)):
        raise ValueError("CLOUD_ARCHIVE_FILE_UNSAFE_OR_MISSING")
    expected_line = checksum.read_text(encoding="ascii")
    expected_sha = expected_line.split("  ", 1)[0]
    if not SHA256.fullmatch(expected_sha) or expected_line != f"{expected_sha}  {archive.name}\n":
        raise ValueError("CLOUD_ARCHIVE_CHECKSUM_FORMAT_INVALID")
    if _digest(archive) != expected_sha:
        raise ValueError("CLOUD_ARCHIVE_SHA256_MISMATCH")

    day, run_id = match.groups()
    manifest_path = f"{day}/{run_id}/manifest.json"
    with zipfile.ZipFile(archive) as zf:
        entries = zf.infolist()
        if not entries or len(entries) > MAX_FILES:
            raise ValueError("CLOUD_ARCHIVE_FILE_COUNT_INVALID")
        paths = [entry.filename for entry in entries]
        if len(paths) != len(set(paths)):
            raise ValueError("CLOUD_ARCHIVE_DUPLICATE_MEMBERS")
        total = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                    or len(path.parts) < 3 or path.parts[:2] != (day, run_id)
                    or stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK):
                raise ValueError("CLOUD_ARCHIVE_UNSAFE_MEMBER")
            total += entry.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("CLOUD_ARCHIVE_UNCOMPRESSED_LIMIT")
        if paths.count(manifest_path) != 1:
            raise ValueError("CLOUD_ARCHIVE_MANIFEST_MISSING")
        manifest_bytes = zf.read(manifest_path)
        manifest = json.loads(manifest_bytes)
        if (not isinstance(manifest, dict) or manifest.get("date_oslo") != day
                or manifest.get("run_id") != run_id
                or not isinstance(manifest.get("meetings"), list)
                or not isinstance(manifest.get("status"), str)):
            raise ValueError("CLOUD_ARCHIVE_MANIFEST_IDENTITY_MISMATCH")
        original_pdfs = sum(p.endswith("/full_program.pdf") for p in paths)
    if _digest(archive) != expected_sha:
        raise ValueError("CLOUD_ARCHIVE_CHANGED_DURING_READBACK")
    return {
        "schema": "CLOUD_RUN001_SOURCE_ARCHIVE_V1",
        "status": "SOURCE_BYTES_VERIFIED_RESEARCH_ONLY",
        "archive_name": archive.name,
        "archive_sha256": expected_sha,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "date_oslo": day,
        "run_id": run_id,
        "collector_status": manifest["status"],
        "reported_meetings": len(manifest["meetings"]),
        "original_program_pdf_files": original_pdfs,
        "source_bytes_readback_verified": True,
        "complete_race_coverage_verified": False,
        "live_win_verified": False,
        "independent_t4_attested": False,
        "permanent_horse_identity_attested": False,
        "primary_pit_qualified": False,
        "bet_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_release(args.archive, args.checksum)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
