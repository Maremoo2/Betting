from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.github.com"


def _request(url: str, token: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "horse-betting-intelligence",
        },
    )


def _report_github_artifact_error(exc: urllib.error.HTTPError, *, stage: str) -> None:
    """Classify external API failures without masking them or creating new state.

    GitHub can return HTTP 403 for installation-wide rate limits as well as
    access-policy denials. Emit an evidence-only marker; preserve the original
    HTTPError so canonical state restore *always* fails closed.
    """
    if exc.code not in {403, 429}:
        return
    body = exc.read(4096)
    message = body.decode("utf-8", errors="replace").lower()
    kind = (
        "INSTALLATION_RATE_LIMIT"
        if "rate limit" in message
        else "HTTP_ACCESS_OR_SCOPE_UNVERIFIED"
    )
    headers = exc.headers or {}
    remaining = headers.get("X-RateLimit-Remaining", "UNVERIFIED")
    reset = headers.get("X-RateLimit-Reset", "UNVERIFIED")
    if not str(remaining).isdigit():
        remaining = "UNVERIFIED"
    if not str(reset).isdigit():
        reset = "UNVERIFIED"
    print(
        f"EXTERNAL_ACCESS_FAILURE stage={stage} http={exc.code} "
        f"classification={kind} rate_remaining={remaining} "
        f"rate_reset_unix={reset} "
        "source_state=NOT_RESTORED no_bootstrap=true",
        file=sys.stderr,
    )


def restore_latest_state(
    *,
    repository: str,
    token: str,
    target_path: str | Path,
    artifact_name: str = "hbi-state",
    branch: str | None = None,
    receipt_path: str | Path | None = None,
    audit_workflow_run_id: int | None = None,
    audit_code_sha: str | None = None,
) -> bool:
    """Restore the newest non-expired HBI SQLite database artifact.

    GitHub-hosted runners are ephemeral. This makes the previous successful state
    available to the next scheduled run without committing binary databases to git.
    """
    if receipt_path is not None and (
        type(audit_workflow_run_id) is not int
        or audit_workflow_run_id <= 0
        or not isinstance(audit_code_sha, str)
        or re.fullmatch(r"[0-9a-fA-F]{40}", audit_code_sha) is None
    ):
        raise ValueError("V1_AUDIT_RUN_AND_CODE_SHA_NOT_ATTESTED")
    url = f"{API}/repos/{repository}/actions/artifacts?name={artifact_name}&per_page=100"
    try:
        with urllib.request.urlopen(_request(url, token), timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _report_github_artifact_error(exc, stage="ARTIFACT_INVENTORY")
        raise

    artifacts = [
        item
        for item in payload.get("artifacts", [])
        if not item.get("expired", False)
        and (
            branch is None
            or item.get("workflow_run", {}).get("head_branch") == branch
        )
    ]
    if not artifacts:
        return False

    artifacts.sort(key=lambda item: item["created_at"], reverse=True)
    latest = artifacts[0]
    if receipt_path is not None:
        source_run = latest.get("workflow_run") or {}
        if (
            type(latest.get("id")) is not int
            or not isinstance(source_run, dict)
            or type(source_run.get("id")) is not int
            or (branch is not None and source_run.get("head_branch") != branch)
            or not isinstance(source_run.get("head_sha"), str)
            or re.fullmatch(r"[0-9a-fA-F]{40}", source_run["head_sha"]) is None
        ):
            raise ValueError("STATE_RESTORE_ORIGINAL_ARTIFACT_METADATA_NOT_ATTESTED")
    archive_request = _request(latest["archive_download_url"], token)

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(archive_request, timeout=60) as response:
            archive = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            _report_github_artifact_error(exc, stage="ARTIFACT_ZIP")
            raise
        location = exc.headers.get("Location")
        if not location:
            raise RuntimeError("artifact download redirect missing Location header") from exc

        # GitHub redirects artifact downloads to a signed object-storage URL. Do not
        # forward the GitHub Authorization header to that host; some storage backends
        # reject the request when both a signed URL and an unrelated bearer token are
        # present.
        clean_request = urllib.request.Request(
            location,
            headers={"User-Agent": "horse-betting-intelligence"},
        )
        with urllib.request.urlopen(clean_request, timeout=60) as response:
            archive = response.read()

    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    database_sha256 = hashlib.sha256()
    database_size = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        candidates = [
            name
            for name in zf.namelist()
            if not name.endswith("/") and Path(name).name == target.name
        ]
        if len(candidates) != 1:
            raise RuntimeError("STATE_RESTORE_DATABASE_MEMBER_NOT_UNIQUE")
        with zf.open(candidates[0]) as source, target.open("wb") as output:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                database_sha256.update(chunk)
                database_size += len(chunk)
                output.write(chunk)
    if receipt_path is not None:
        source_run = latest["workflow_run"]
        receipt = {
            "schema": "HBI_STATE_RESTORE_RECEIPT_V1",
            "restored_at_utc": datetime.now(UTC).isoformat(),
            "audit_workflow_run_id": audit_workflow_run_id,
            "audit_code_sha": audit_code_sha,
            "read_only_provenance": True,
            "repository": repository,
            "artifact_name": artifact_name,
            "artifact_id": latest["id"],
            "artifact_created_at_utc": latest["created_at"],
            "source_workflow_run_id": source_run["id"],
            "source_head_branch": source_run.get("head_branch"),
            "source_head_sha": source_run.get("head_sha"),
            "restore_branch_filter": branch,
            "selection_rule": "NEWEST_NON_EXPIRED_MATCHING_GITHUB_ARTIFACT",
            "artifact_zip_sha256": hashlib.sha256(archive).hexdigest(),
            "restored_database_sha256": database_sha256.hexdigest(),
            "restored_database_size_bytes": database_size,
            "bet_authority": False,
            "historical_decisions_modified": False,
        }
        receipt_file = Path(receipt_path)
        receipt_file.parent.mkdir(parents=True, exist_ok=True)
        # Never advertise an artifact ID/SHA before the exact restored bytes exist.
        receipt_file.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    return True


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    target = os.environ.get("HBI_DB_PATH", "data/hbi.sqlite")
    branch = os.environ.get("GITHUB_REF_NAME")
    receipt_path = os.environ.get("HBI_RESTORE_RECEIPT_PATH") or None
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    restored = restore_latest_state(
        repository=repository,
        token=token,
        target_path=target,
        branch=branch,
        receipt_path=receipt_path,
        audit_workflow_run_id=(
            int(os.environ["GITHUB_RUN_ID"]) if receipt_path is not None else None
        ),
        audit_code_sha=(
            os.environ.get("GITHUB_SHA") if receipt_path is not None else None
        ),
    )
    # A scheduled canonical watcher must never silently begin with a fresh DB
    # when the previous state archive is missing, expired, or not selectable.
    # Keep opt-in bootstrap behavior for separate research/first-run workflows.
    if not restored and os.environ.get("HBI_RESTORE_REQUIRED") == "1":
        raise SystemExit("STATE_RESTORE_REQUIRED_BUT_NO_VERIFIED_ARTIFACT")
    print("STATE_RESTORE=RESTORED" if restored else "STATE_RESTORE=EMPTY")


if __name__ == "__main__":
    main()
