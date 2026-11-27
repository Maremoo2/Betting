"""Authenticated encryption of the existing CI SQLite handoff, not new state."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .ci_originals import MAX_MEMBER_BYTES, transport_context

FILES = ("replay.sqlite", "receipt.json")
MAX_CIPHERTEXT = 100_000_000


def read_key():
    path = Path(os.environ["CI_ORIGINAL_CACHE"]) / ".readback-key"
    if path.is_symlink() or not path.is_file():
        raise ValueError("CI_READBACK_KEY_MISSING")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("CI_READBACK_KEY_INVALID")
    return key


def seal(source, destination):
    source, destination = Path(source), Path(destination)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in FILES:
            path = source / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MEMBER_BYTES:
                raise ValueError("CI_READBACK_SOURCE_INVALID")
            archive.write(path, name)
    nonce = os.urandom(12)
    context = transport_context()
    encrypted = AESGCM(read_key()).encrypt(nonce, data.getvalue(), context)
    if len(encrypted) > MAX_CIPHERTEXT:
        raise ValueError("CI_READBACK_TRANSPORT_TOO_LARGE")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "readback.aesgcm").write_bytes(encrypted)
    (destination / "transport.json").write_text(json.dumps({
        "schema": "CI_SQLITE_AESGCM_V1", "context": json.loads(context), "nonce": nonce.hex(),
        "ciphertext_sha256": hashlib.sha256(encrypted).hexdigest(),
        "plaintext_files": list(FILES), "key_published": False,
    }, indent=2), encoding="utf-8")


def open_transport(source, destination):
    source, destination = Path(source), Path(destination)
    meta = json.loads((source / "transport.json").read_bytes())
    context = transport_context()
    if (meta.get("schema") != "CI_SQLITE_AESGCM_V1" or meta.get("context") != json.loads(context)
            or meta.get("plaintext_files") != list(FILES)):
        raise ValueError("CI_READBACK_TRANSPORT_CONTEXT_MISMATCH")
    data = (source / "readback.aesgcm").read_bytes()
    if len(data) > MAX_CIPHERTEXT or hashlib.sha256(data).hexdigest() != meta["ciphertext_sha256"]:
        raise ValueError("CI_READBACK_CIPHERTEXT_MISMATCH")
    try:
        raw = AESGCM(read_key()).decrypt(bytes.fromhex(meta["nonce"]), data, context)
    except (InvalidTag, ValueError):
        raise ValueError("CI_READBACK_AUTHENTICATION_FAILED") from None
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != list(FILES) or archive.testzip() is not None:
            raise ValueError("CI_READBACK_ARCHIVE_INVALID")
        if any(m.file_size > MAX_MEMBER_BYTES for m in archive.infolist()):
            raise ValueError("CI_READBACK_ARCHIVE_TOO_LARGE")
        destination.mkdir(parents=True, exist_ok=False)
        for name in FILES:
            with (destination / name).open("xb") as stream:
                stream.write(archive.read(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "open"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.source, args.destination)
    else:
        open_transport(args.source, args.destination)


if __name__ == "__main__":
    main()
