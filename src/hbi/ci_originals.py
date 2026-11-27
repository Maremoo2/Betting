"""Retained, reviewed CI sources only; no collector/model/production authority."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

CATALOG = Path(__file__).resolve().parents[2] / "docs/CI_HISTORICAL_SOURCES.json"
PRIVATE_REPO = "Maremoo2/betting-hq-private-research"
MAX_ZIP_BYTES = 100_000_000
MAX_MEMBER_BYTES = 300_000_000  # Existing canonical replay archive limit.


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def catalog():
    doc = json.loads(CATALOG.read_bytes())
    if (doc.get("schema") != "CI_HISTORICAL_ORIGINALS_V1"
            or doc.get("private_repository") != PRIVATE_REPO
            or not re.fullmatch(r"[a-f0-9]{40}", doc.get("private_commit", ""))):
        raise ValueError("CI_ORIGINAL_CATALOG_INVALID")
    seen = set()
    for entry in doc["sources"]:
        ident = entry.get("artifact_id")
        if (type(ident) is not int or ident <= 0 or ident in seen
                or entry.get("zip_filename") != str(ident) + ".zip"
                or entry.get("state") not in {"VERIFIED_ORIGINAL", "SOURCE_UNRECOVERABLE"}
                or not re.fullmatch(r"[a-f0-9]{64}", entry.get("zip_sha256", ""))):
            raise ValueError("CI_ORIGINAL_CATALOG_SOURCE_INVALID")
        seen.add(ident)
        if entry["state"] == "VERIFIED_ORIGINAL":
            path = entry.get("archive_path", "")
            if (not path.startswith("archive/") or ".." in PurePosixPath(path).parts
                    or any(c in path for c in "\\?#:") or not path.endswith("/" + str(ident) + ".zip")):
                raise ValueError("CI_ORIGINAL_CATALOG_ARCHIVE_PATH_INVALID")
    return doc


def find_source(*, artifact_id=None, run_id=None, name=None, repository=None):
    rows = [e for e in catalog()["sources"]
            if (artifact_id is None or e["artifact_id"] == int(artifact_id))
            and (run_id is None or e["run_id"] == int(run_id))
            and (name is None or e["artifact_name"] == name)
            and (repository is None or e["repository"] == repository)]
    if len(rows) != 1:
        raise ValueError("CI_ORIGINAL_NOT_REGISTERED_OR_AMBIGUOUS")
    entry = rows[0]
    if entry["state"] != "VERIFIED_ORIGINAL":
        raise ValueError("SOURCE_UNRECOVERABLE:" + str(entry["artifact_id"]))
    return entry


def verify_zip(path, entry):
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or path.stat().st_size != entry["source_bytes"]
            or digest(path) != entry["zip_sha256"]):
        raise ValueError("CI_ORIGINAL_ZIP_SHA_OR_SIZE_MISMATCH")
    expected = {m["path"]: m for m in entry["members"]}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError("CI_ORIGINAL_ZIP_CRC_OR_DUPLICATE")
        files = set()
        for member in archive.infolist():
            name = member.filename
            item = PurePosixPath(name)
            if (item.is_absolute() or ".." in item.parts or "\\" in name or ":" in name
                    or (member.external_attr >> 16) & 0o170000 == 0o120000
                    or member.file_size > MAX_MEMBER_BYTES):
                raise ValueError("CI_ORIGINAL_UNSAFE_MEMBER")
            if member.is_dir():
                continue
            files.add(name)
            actual = archive.read(member)
            if (name not in expected or len(actual) != expected[name]["bytes"]
                    or hashlib.sha256(actual).hexdigest() != expected[name]["sha256"]):
                raise ValueError("CI_ORIGINAL_MEMBER_SHA_MISMATCH")
        if files != set(expected):
            raise ValueError("CI_ORIGINAL_MEMBER_SET_MISMATCH")
    return path


def cached_archive(entry):
    root = os.environ.get("CI_ORIGINAL_CACHE")
    if not root:
        raise ValueError("CI_ORIGINAL_CACHE_REQUIRED_NO_NETWORK_FALLBACK")
    source = find_source(artifact_id=entry["artifact_id"])
    if any(source[k] != entry[v] for k, v in (
            ("repository", "repository"), ("run_id", "run_id"), ("zip_sha256", "sha256"))):
        raise ValueError("REPLAY_ARTIFACT_PROVENANCE_MISMATCH")
    if entry.get("commit") is not None and source["workflow_run_head"] != entry["commit"]:
        raise ValueError("REPLAY_ARTIFACT_PROVENANCE_MISMATCH")
    return verify_zip(Path(root) / source["zip_filename"], source)


def extract(entry, destination):
    root = os.environ.get("CI_ORIGINAL_CACHE")
    if not root:
        raise ValueError("CI_ORIGINAL_CACHE_REQUIRED_NO_NETWORK_FALLBACK")
    archive_path = verify_zip(Path(root) / entry["zip_filename"], entry)
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("CI_ORIGINAL_DESTINATION_SYMLINK")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in entry["members"]:
            target = destination / member["path"]
            if any(p.is_symlink() for p in (target, *target.parents)):
                raise ValueError("CI_ORIGINAL_DESTINATION_SYMLINK")
            raw = archive.read(member["path"])
            if target.exists():
                if not target.is_file() or digest(target) != member["sha256"]:
                    raise ValueError("CI_ORIGINAL_APPEND_ONLY_CONFLICT")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
            if digest(target) != member["sha256"]:
                raise ValueError("CI_ORIGINAL_DISK_READBACK_MISMATCH")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the private credential to another host.
        return None


def api(path, token, limit, *, raw=False):
    request = urllib.request.Request("https://api.github.com/" + path, headers={
        "Authorization": "Bearer " + token, "User-Agent": "Betting-Retained-CI-Originals",
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
    })
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=120) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise ValueError("CI_PRIVATE_ARCHIVE_HTTP_" + str(error.code)) from None
    if len(data) > limit:
        raise ValueError("CI_PRIVATE_ORIGINAL_OVERSIZED")
    return data


def transport_context():
    keys = ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    values = {key: os.environ.get(key, "") for key in keys}
    if not all(values.values()):
        raise ValueError("CI_READBACK_CONTEXT_MISSING")
    return json.dumps(values, sort_keys=True, separators=(",", ":")).encode()


def fetch(root):
    token = os.environ.get("RESEARCH_ARCHIVE_READ_TOKEN", "")
    if not token:
        raise ValueError("CI_PRIVATE_ARCHIVE_READ_CREDENTIAL_MISSING")
    repo = json.loads(api("repos/" + PRIVATE_REPO, token, 1_000_000))
    if repo.get("private") is not True or repo.get("full_name") != PRIVATE_REPO:
        raise ValueError("CI_PRIVATE_ARCHIVE_MUST_REMAIN_PRIVATE")
    doc = catalog()
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    # The credential never leaves this controlled fetch process. A distinct,
    # run/attempt-bound transport key is used only for encrypted CI handoff.
    key = hmac.digest(token.encode(), b"CI_READBACK_AESGCM_V1\0" + transport_context(), "sha256")
    fd = os.open(root / ".readback-key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(key)
    verified = []
    missing = []
    for entry in doc["sources"]:
        if entry["state"] != "VERIFIED_ORIGINAL":
            missing.append(entry["artifact_id"])
            continue
        size = entry["source_bytes"]
        if size <= 0 or size > MAX_ZIP_BYTES:
            raise ValueError("CI_PRIVATE_ORIGINAL_SIZE_NOT_APPROVED")
        path = "repos/" + PRIVATE_REPO + "/contents/" + entry["archive_path"] + "?ref=" + doc["private_commit"]
        data = api(path, token, size, raw=True)
        target = root / entry["zip_filename"]
        with target.open("xb") as stream:
            stream.write(data)
        verify_zip(target, entry)
        verified.append(entry["artifact_id"])
    result = {"scope": "VERIFIED_ORIGINALS_ONLY_NOT_ALL_MANDATORY_REPLAYS",
              "verified": verified, "source_unrecoverable": missing,
              "status": "PARTIAL" if missing else "ALL_REGISTERED_ORIGINALS_AVAILABLE",
              "private_commit": doc["private_commit"]}
    (root / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def verify_cache():
    root = Path(os.environ["CI_ORIGINAL_CACHE"])
    verified = []
    for entry in catalog()["sources"]:
        if entry["state"] == "VERIFIED_ORIGINAL":
            verify_zip(root / entry["zip_filename"], entry)
            verified.append(entry["artifact_id"])
    return {"scope": "VERIFIED_ORIGINALS_ONLY", "verified_count": len(verified), "ids": verified}


APPROVED_LOSS = CATALOG.with_name("CI_APPROVED_SOURCE_LOSS_20261127.json")
APPROVED_LOSS_SHA = "35543d7f52085438fee3b8d725ffc1c95d84fd1dd45d711c41a9890211dc70af"


def approved_loss():
    if digest(APPROVED_LOSS) != APPROVED_LOSS_SHA:
        raise ValueError("SOURCE_LOSS_APPROVAL_SHA_MISMATCH")
    return json.loads(APPROVED_LOSS.read_bytes())


def historical_status(outcomes=None):
    """Only HQ's exact lost bytes are exempt; test failures and new gaps are not."""
    approval = approved_loss()
    rows = []
    error = None
    try:
        entries = {str(e["artifact_id"]): e for e in catalog()["sources"]}
        if {k: e["zip_sha256"] for k, e in entries.items()} != approval["original_zip_pins"]:
            raise ValueError("HISTORICAL_SOURCE_PIN_SET_CHANGED")
        missing = set()
        for ident, entry in entries.items():
            if entry["state"] != "SOURCE_UNRECOVERABLE":
                continue
            pin = {"zip_sha256": entry["zip_sha256"], "locked_members": entry.get("locked_members", {})}
            if approval["lost_originals"].get(ident) != pin:
                raise ValueError("NEW_OR_CHANGED_SOURCE_GAP")
            missing.add(int(ident))
        verify_cache()  # Corrupt/deleted retained originals remain blocking.
    except (ValueError, OSError, KeyError) as exc:
        missing, error = set(), str(exc)
    keys = {g["key"] for g in approval["groups"]}
    if outcomes is not None and set(outcomes) != keys:
        error = "HISTORICAL_TEST_OUTCOMES_INCOMPLETE"
    for group in approval["groups"]:
        absent = sorted(set(group["required_artifacts"]) & missing)
        status = "SYSTEM_ERROR" if error else "SOURCE_UNRECOVERABLE" if absent else "READY"
        actual = outcomes.get(group["key"], "") if outcomes is not None else "NOT_RUN_PLAN"
        if outcomes is not None and not error:
            if status == "READY":
                status = "PASS" if actual == "success" else "FAIL_REGRESSION"
            elif actual != "skipped":
                status = "FAIL_REGRESSION"  # No bypass or fabricated replay success.
        rows.append({"key": group["key"], "step": group["step"], "status": status,
                     "test_outcome": actual, "missing_artifacts": absent,
                     "missing_original_pins": {str(i): approval["lost_originals"][str(i)] for i in absent}})
    failed = error is not None or any(r["status"] in {"SYSTEM_ERROR", "FAIL_REGRESSION"} for r in rows)
    debt = any(r["status"] == "SOURCE_UNRECOVERABLE" for r in rows)
    return {"scope": "TECHNICAL_EXCEPTION_NOT_HISTORICAL_APPROVAL", "groups": rows, "error": error,
            "technical_status": "FAIL_REGRESSION" if failed else "READY_FOR_TESTS" if outcomes is None
            else "PASS_WITH_DOCUMENTED_SOURCE_DEBT" if debt else "PASS_ALL_RESEARCH_REPLAYS",
            "historical_status": "FAIL_REGRESSION" if failed else "SOURCE_UNRECOVERABLE" if debt
            else "NOT_RUN" if outcomes is None else "PASS", "all_research_evidence_verified": not failed and not debt and outcomes is not None}


def technical_acceptance(needs):
    """Mandatory aggregate rejects cancelled, absent or failed required jobs."""
    if any(needs.get(k, {}).get("result") != "success" for k in ("test", "replay-v2-independent-readback")):
        raise ValueError("REQUIRED_TECHNICAL_JOB_NOT_PASS")
    history = needs.get("historical-research-evidence", {})
    status = history.get("outputs", {}).get("technical_status")
    if (status, history.get("result")) not in {
        ("PASS_WITH_DOCUMENTED_SOURCE_DEBT", "failure"), ("PASS_ALL_RESEARCH_REPLAYS", "success"),
    }:
        raise ValueError("HISTORICAL_REGRESSION_OR_UNVERIFIED_STATUS")
    return {"technical_acceptance": "PASS", "historical_status": status,
            "all_ci_checks_pass": status == "PASS_ALL_RESEARCH_REPLAYS", "bet_authority": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "extract", "copy", "verify-cache", "historical-plan", "historical-summary", "technical-gate"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--artifact-id", type=int)
    parser.add_argument("--run", type=int)
    parser.add_argument("--name")
    parser.add_argument("--dir", type=Path)
    args = parser.parse_args()
    if args.action in {"historical-plan", "historical-summary"}:
        outcomes = json.loads(os.environ["HISTORICAL_OUTCOMES"]) if args.action == "historical-summary" else None
        result = historical_status(outcomes)
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.writelines(row["key"] + "=" + row["status"] + "\n" for row in result["groups"])
                stream.write("technical_status=" + result["technical_status"] + "\n")
                stream.write("historical_status=" + result["historical_status"] + "\n")
        print(json.dumps(result))
        if result["technical_status"] == "FAIL_REGRESSION":
            raise SystemExit(1)
    elif args.action == "technical-gate":
        print(json.dumps(technical_acceptance(json.loads(os.environ["CI_NEEDS"]))))
    elif args.action == "fetch":
        print(json.dumps(fetch(args.root)))
    elif args.action == "verify-cache":
        print(json.dumps(verify_cache()))
    else:
        entry = find_source(artifact_id=args.artifact_id, run_id=args.run, name=args.name)
        if args.action == "extract":
            extract(entry, args.dir)
        else:
            source = verify_zip(Path(os.environ["CI_ORIGINAL_CACHE"]) / entry["zip_filename"], entry)
            if args.dir.exists():
                raise ValueError("CI_ORIGINAL_COPY_DESTINATION_EXISTS")
            shutil.copyfile(source, args.dir)


if __name__ == "__main__":
    main()
