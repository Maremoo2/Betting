"""MVP-016 exact-byte reader. No network, credentials or publication.

Only the pinned pilot identity is supported. An authorized private transport
must stage the original ZIP separately. This code cannot attest access rights.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path
from typing import Any

PILOT_ID = ("Maremoo2/Betting", 41796128435, 13304793845,
            "bet-mvp-shadow-41796128435")
PILOT_ZIP_SHA = "2b2683ba14774b637237f99484f1b8256321744c0552c0d30a5635bd549a6cfa"
PILOT_MEMBER_SHA = "ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0"
PILOT_MEMBER = "cohort-index.json"
MAX_MEMBER_BYTES = 1024 * 1024


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def validate_pilot_manifest(manifest: dict[str, Any]) -> None:
    """Pin identity independently of caller-provided manifest values."""
    _require(isinstance(manifest, dict)
             and manifest.get("schema") == "HBI_ORIGINAL_EVIDENCE_MANIFEST_V1",
             "EVIDENCE_MANIFEST_INVALID")
    entries = manifest.get("entries")
    _require(isinstance(entries, list) and len(entries) == 1
             and isinstance(entries[0], dict), "EVIDENCE_MANIFEST_INVALID")
    entry = entries[0]
    identity = tuple(entry.get(k) for k in (
        "repository", "run_id", "artifact_id", "artifact_name"))
    _require(identity == PILOT_ID and type(entry.get("run_id")) is int
             and type(entry.get("artifact_id")) is int, "EVIDENCE_IDENTITY_MISMATCH")
    _require(entry.get("zip_sha256") == PILOT_ZIP_SHA
             and entry.get("member_sha256") == PILOT_MEMBER_SHA
             and entry.get("member_name") == PILOT_MEMBER
             and type(entry.get("zip_size_bytes")) is int
             and entry["zip_size_bytes"] == 575,
             "EVIDENCE_PIN_MISMATCH")


def _read_exact_member(raw: bytes, *, zip_sha: str, member_sha: str,
                       member_name: str) -> bytes:
    """Internal verification primitive; production entry point fixes all pins."""
    _require(re.fullmatch(r"[0-9a-f]{64}", zip_sha) is not None
             and re.fullmatch(r"[0-9a-f]{64}", member_sha) is not None,
             "EVIDENCE_PIN_INVALID")
    _require(_hash(raw) == zip_sha, "EVIDENCE_ZIP_HASH_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            _require(len(members) == 1, "EVIDENCE_ZIP_MEMBER_COUNT")
            info = members[0]
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            _require(info.filename == member_name and "/" not in member_name
                     and "\\" not in member_name and member_name not in {".", ".."}
                     and not info.is_dir() and kind in {0, stat.S_IFREG}
                     and not (info.flag_bits & 1)
                     and 0 < info.file_size <= MAX_MEMBER_BYTES,
                     "EVIDENCE_ZIP_MEMBER_INVALID")
            with archive.open(info) as stream:
                content = stream.read(MAX_MEMBER_BYTES + 1)
            _require(len(content) == info.file_size
                     and len(content) <= MAX_MEMBER_BYTES,
                     "EVIDENCE_ZIP_MEMBER_SIZE")
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as exc:
        raise ValueError("EVIDENCE_ZIP_INVALID") from exc
    _require(_hash(content) == member_sha, "EVIDENCE_MEMBER_HASH_MISMATCH")
    return content


def read_pilot(manifest: dict[str, Any], source_zip: Path) -> bytes:
    validate_pilot_manifest(manifest)
    _require(source_zip.is_file() and not source_zip.is_symlink(),
             "ORIGINAL_EVIDENCE_UNAVAILABLE")
    try:
        with source_zip.open("rb") as stream:
            raw = stream.read(576)
    except OSError as exc:
        raise ValueError("ORIGINAL_EVIDENCE_UNAVAILABLE") from exc
    _require(len(raw) == 575, "EVIDENCE_ZIP_SIZE_MISMATCH")
    return _read_exact_member(raw, zip_sha=PILOT_ZIP_SHA,
                              member_sha=PILOT_MEMBER_SHA, member_name=PILOT_MEMBER)


def stage_pilot(manifest: dict[str, Any], source_zip: Path, output_dir: Path) -> None:
    # Never extract arbitrary paths; require a new operator-selected directory.
    content = read_pilot(manifest, source_zip)
    _require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
             and not output_dir.exists() and not output_dir.is_symlink(),
             "EVIDENCE_OUTPUT_NOT_NEW")
    output_dir.mkdir(mode=0o700, exist_ok=False)
    target = output_dir / PILOT_MEMBER
    with target.open("xb") as stream:
        stream.write(content)
    _require(target.read_bytes() == content, "EVIDENCE_READBACK_MISMATCH")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    stage_pilot(json.loads(args.manifest.read_bytes()), args.source_zip, args.output_dir)
    print("MVP016_EXACT_ORIGINAL_VERIFIED_AND_STAGED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
