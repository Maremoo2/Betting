"""Fetch only the reviewed original from authenticated, non-expiring private Git.

No latest/fallback source, source approval, model input, or production changes.
The archive contains one index; referenced upstream bytes are separate evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "docs/MVP016_SOURCE_ARCHIVE.json"


def verify_original(raw: bytes, contract: dict) -> bytes:
    if len(raw) != contract["zip_size"] or hashlib.sha256(raw).hexdigest() != contract["zip_sha256"]:
        raise ValueError("MVP016_ORIGINAL_ZIP_SHA_OR_SIZE_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != [contract["member"]] or archive.testzip() is not None:
            raise ValueError("MVP016_ORIGINAL_ZIP_MEMBERS_OR_CRC_INVALID")
        original = archive.read(contract["member"])
    if hashlib.sha256(original).hexdigest() != contract["member_sha256"]:
        raise ValueError("MVP016_ORIGINAL_INDEX_SHA_MISMATCH")
    index = json.loads(original)
    if (index.get("schema") != "BET_MVP_002_FIXED_COHORT_INDEX_V1"
            or index.get("bet_authority") is not False or index.get("pit_certified") is not False
            or any(index.get(key) != [] for key in ("original_cohort", "processed", "not_processed"))
            or any(index.get(key) != value for key, value in contract["upstream_hashes"].items())):
        raise ValueError("MVP016_ORIGINAL_INDEX_CONTRACT_MISMATCH")
    return original


def api_read(path: str, token: str, *, raw: bool = False) -> bytes:
    # Fixed API origin; never accept caller-provided credential destinations.
    request = urllib.request.Request("https://api.github.com/" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "User-Agent": "Betting-MVP016-Original-Recovery",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read(1024 * 1024)


def recover(root: Path, *, local_zip: Path | None = None) -> dict:
    contract = json.loads(CONTRACT.read_bytes())
    if local_zip is None:
        token = os.environ.get("RESEARCH_ARCHIVE_READ_TOKEN", "")
        if not token:
            raise ValueError("MVP016_PRIVATE_ARCHIVE_READ_CREDENTIAL_MISSING")
        repository = json.loads(api_read("repos/" + contract["repository"], token))
        if repository.get("private") is not True or repository.get("full_name") != contract["repository"]:
            raise ValueError("MVP016_ARCHIVE_MUST_REMAIN_PRIVATE")
        raw = api_read("repos/" + contract["repository"] + "/contents/" + contract["path"]
                       + "?ref=" + contract["commit"], token, raw=True)
    else:
        raw = local_zip.read_bytes()
    original = verify_original(raw, contract)
    root.mkdir(parents=True, exist_ok=False)
    with (root / contract["member"]).open("xb") as stream:
        stream.write(original)
    if hashlib.sha256((root / contract["member"]).read_bytes()).hexdigest() != contract["member_sha256"]:
        raise ValueError("MVP016_DISK_READBACK_SHA_MISMATCH")
    receipt = {"schema": contract["schema"], "source_run": contract["source_run"],
               "source_artifact": contract["source_artifact"], "private_commit": contract["commit"],
               "zip_sha256": contract["zip_sha256"], "member_sha256": contract["member_sha256"],
               "transport": "PRIVATE_GIT" if local_zip is None else "LOCAL_ORIGINAL_TEST",
               "upstream_references_preserved_not_reverified": contract["upstream_hashes"],
               "all_upstream_bytes_verified": False, "pit_certified": False, "bet_authority": False}
    (root / "source-recovery-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    # Used only by isolated original/negative tests, never a CI fallback.
    parser.add_argument("--local-zip", type=Path)
    args = parser.parse_args()
    print(json.dumps(recover(args.root, local_zip=args.local_zip)))
