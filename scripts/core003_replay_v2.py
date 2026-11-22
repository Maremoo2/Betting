"""Narrow CI transport/readback for CORE003_AUTHENTIC_REPLAY_V2; no source collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

CONTRACT = Path(__file__).resolve().parents[1] / "docs/CORE003_AUTHENTIC_REPLAY_V2.json"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_contract():
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value["schema"] != "CORE003_AUTHENTIC_REPLAY_V2":
        raise ValueError("REPLAY_CONTRACT_VERSION_MISMATCH")
    return value


def unpack(source, destination):
    """Reject traversal, links, duplicate entries and oversized archive members."""
    with zipfile.ZipFile(source) as archive:
        seen = set()
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.filename
                    or ":" in member.filename or member.filename in seen
                    or (member.external_attr >> 16) & 0o170000 == 0o120000
                    or member.file_size > 300_000_000):
                raise ValueError("REPLAY_ARCHIVE_UNSAFE")
            seen.add(member.filename)
        archive.extractall(destination)


def verify_inputs(root):
    contract = load_contract()
    for entry in contract["artifacts"]:
        path = Path(root) / (entry["role"] + ".zip")
        if not path.is_file() or path.is_symlink():
            raise ValueError("REPLAY_ORIGINAL_MISSING:" + entry["role"])
        if digest(path) != entry["sha256"]:
            raise ValueError("REPLAY_ORIGINAL_SHA_MISMATCH:" + entry["role"])
    return contract


def extract_inputs(root, destination):
    contract = verify_inputs(root)
    destination = Path(destination)
    for entry in contract["artifacts"]:
        unpack(Path(root) / (entry["role"] + ".zip"), destination / entry["role"])
    db = destination / "state/core003-pilot.sqlite"
    report = destination / "report/core003-pilot-report.json"
    for path, expected in [(db, contract["sqlite_sha256"]),
                           (report, contract["report_sha256"])] + [
        (destination / "model" / field["model_path"], field["model_sha256"])
        for field in contract["fields"]
    ]:
        if digest(path) != expected:
            raise ValueError("REPLAY_MEMBER_SHA_MISMATCH:" + path.name)
    return contract


def database_receipt(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("REPLAY_SQLITE_INTEGRITY")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("REPLAY_SQLITE_FOREIGN_KEYS")
        counts = {table: conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                  for table in load_contract()["counts"]}
        ledger = [list(row) for row in conn.execute(
            "SELECT * FROM schema_migrations ORDER BY 1").fetchall()]
    return {"sha256": digest(path), "counts": counts, "migration_ledger": ledger}


def gh_json(endpoint):
    process = subprocess.run(["gh", "api", endpoint], check=True, capture_output=True)
    return json.loads(process.stdout)


def download(entry, destination):
    endpoint = ("repos/" + entry["repository"] + "/actions/artifacts/"
                + str(entry["artifact_id"]))
    metadata = gh_json(endpoint)
    if (metadata["expired"] or metadata["workflow_run"]["id"] != entry["run_id"]
            or metadata["digest"] != "sha256:" + entry["sha256"]
            or metadata["workflow_run"]["head_sha"] != entry["commit"]):
        raise ValueError("REPLAY_ARTIFACT_PROVENANCE_MISMATCH")
    with Path(destination).open("xb") as target:
        subprocess.run(["gh", "api", endpoint + "/zip"], check=True, stdout=target)
    if digest(destination) != entry["sha256"]:
        raise ValueError("REPLAY_DOWNLOAD_SHA_MISMATCH")
    return metadata


def fetch(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    contract = load_contract()
    if contract["mirror"] is not None:
        mirror = root.parent / "replay-v2-pinned-mirror.zip"
        download(contract["mirror"], mirror)
        unpack(mirror, root)
        origin = "PINNED_90_DAY_MIRROR"
    else:
        # Bootstrap only; replaced with the pinned mirror before final review.
        for entry in contract["artifacts"]:
            download(entry, root / (entry["role"] + ".zip"))
        origin = "EXPLICIT_BOOTSTRAP_FROM_PINNED_ORIGINALS"
    verify_inputs(root)
    (root / "transport.json").write_text(json.dumps(
        {"schema": contract["schema"], "transport": origin,
         "legacy_status": contract["legacy"]["status"]}, indent=2), encoding="utf-8")


def readback(root):
    root = Path(root)
    expected = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    actual = database_receipt(root / "replay.sqlite")
    contract = load_contract()
    if (actual["sha256"] != contract["sqlite_sha256"]
            or actual["counts"] != contract["counts"]):
        raise ValueError("REPLAY_RESTORE_PINNED_ORIGINAL_MISMATCH")
    if actual != expected["database"]:
        raise ValueError("REPLAY_RESTORE_READBACK_MISMATCH")
    if (expected["schema"] != load_contract()["schema"]
            or expected["pit_certified"] is not False
            or expected["bet_authority"] is not False
            or expected["strict_model_admissions"] != 0):
        raise ValueError("REPLAY_RESTORE_AUTHORITY_MISMATCH")
    print("CORE003_REPLAY_V2_SEPARATE_READBACK_PASS", json.dumps(actual))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch", "readback"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "fetch":
        fetch(args.root)
    else:
        readback(args.root)


if __name__ == "__main__":
    main()
