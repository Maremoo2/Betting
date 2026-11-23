from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.github.com"


def write_restore_failure_status(
    path: Path, *, reason: str, run_id: str, declared_race_ids: tuple[str, ...] = (),
) -> dict:
    """Observable failure receipt; never claims a restore or sends external mail."""
    if (len(set(declared_race_ids)) != len(declared_race_ids)
            or any(not isinstance(race, str) or not race for race in declared_race_ids)):
        raise ValueError("STATE_FAILURE_DECLARED_RACE_IDENTITIES_INVALID")
    document = {
        "schema": "STATE_HANDOFF_FAILURE_V1", "status": "BLOCKED",
        "observed_at_utc": datetime.now(UTC).isoformat(), "workflow_run_id": run_id,
        "reason": reason, "alert_required": True, "notification_channel": "GITHUB_ACTIONS_ERROR",
        "restored": False, "bootstrap_allowed": False, "bet_authority": False,
        "production_activated": False,
        "declared_races": [
            {"race_id": race, "terminal_status": "SYSTEM_BLOCKED", "reason": reason}
            for race in declared_race_ids
        ],
        "declaration_is_live_discovery": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    if json.loads(path.read_bytes()) != document:
        raise ValueError("STATE_RESTORE_FAILURE_STATUS_READBACK_MISMATCH")
    return document


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
    if exc.code not in {403, 404, 410, 429}:
        return
    body = exc.read(4096)
    message = body.decode("utf-8", errors="replace").lower()
    if exc.code in {404, 410}:
        # GitHub may conceal inaccessible resources with 404. Do not claim
        # expiry/deletion or choose an older state without original evidence.
        kind = "ORIGINAL_NOT_FOUND_OR_INACCESSIBLE"
    else:
        kind = (
            "INSTALLATION_RATE_LIMIT"
            if "rate limit" in message or str((exc.headers or {}).get("X-RateLimit-Remaining")) == "0"
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


def _bounded_github_retry_delay(exc: urllib.error.HTTPError) -> float | None:
    """Retry only when GitHub explicitly supplies a *nearby* rate reset.

    Installation limits are shared across workflows. Never spin, retry
    permission failures, or remain blocked beyond a bounded runner budget.
    """
    if exc.code not in {403, 429}:
        return None
    headers = exc.headers or {}
    remaining = str(headers.get("X-RateLimit-Remaining", "")).strip()
    retry_after = str(headers.get("Retry-After", "")).strip()
    reset = str(headers.get("X-RateLimit-Reset", "")).strip()
    if remaining != "0" and exc.code != 429 and not retry_after:
        return None
    try:
        delay = float(retry_after) if retry_after else float(reset) - time.time()
    except ValueError:
        return None
    if not 0 <= delay <= 150:
        return None
    return max(1.0, delay + 1.0)


def _read_github(open_response, *, stage: str) -> bytes:
    """One request normally; at most one bounded, server-timed retry."""
    for attempt in range(2):
        try:
            with open_response() as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            delay = _bounded_github_retry_delay(exc) if attempt == 0 else None
            if delay is None:
                _report_github_artifact_error(exc, stage=stage)
                raise
            print(
                f"STATE_RESTORE_RATE_LIMIT_WAIT seconds={delay:.3f} "
                f"stage={stage} attempts_remaining=1 no_bootstrap=true",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise AssertionError("unreachable GitHub retry state")


def _inventory_json(url: str, token: str) -> dict:
    body = _read_github(
        lambda: urllib.request.urlopen(_request(url, token), timeout=30),
        stage="ARTIFACT_INVENTORY",
    )
    return json.loads(body.decode("utf-8"))


def _verify_canonical_sqlite(path: Path, *, include_wal: bool = False) -> None:
    """Strict, read-only canonical schema and SQLite integrity validation."""
    with path.open("rb") as stream:
        header = stream.read(16)
    if path.stat().st_size < 100 or header != b"SQLite format 3\x00":
        raise ValueError("STATE_RESTORE_SQLITE_HEADER_INVALID")
    # immutable=1 ignores stray WAL files in a runner and never writes to state.
    uri = path.resolve().as_uri() + ("?mode=ro" if include_wal else "?mode=ro&immutable=1")
    try:
        with closing(sqlite3.connect(uri, uri=True)) as db:
            if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise ValueError("STATE_RESTORE_SQLITE_INTEGRITY_FAILED")
            required_tables = {
                "races", "provider_race_refs", "shadow_decision_runs",
                "shadow_tickets", "schema_migrations",
            }
            present = {
                row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not required_tables.issubset(present):
                raise ValueError("STATE_RESTORE_REQUIRED_TABLES_MISSING")
    except sqlite3.DatabaseError as exc:
        raise ValueError("STATE_RESTORE_SQLITE_INTEGRITY_FAILED") from exc


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
    required: bool = False,
    validate_sqlite: bool = False,
    source_run_id: int | None = None,
    expected_zip_sha256: str | None = None,
    expected_database_sha256: str | None = None,
    source_job_name: str | None = None,
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
    for digest in (expected_zip_sha256, expected_database_sha256):
        if digest is not None and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("STATE_RESTORE_EXPECTED_SHA_INVALID")
    if source_run_id is not None:
        if type(source_run_id) is not int or source_run_id <= 0:
            raise ValueError("STATE_RESTORE_SOURCE_RUN_INVALID")
        run = _inventory_json(f"{API}/repos/{repository}/actions/runs/{source_run_id}", token)
        if (run.get("id") != source_run_id
                or (branch is not None and run.get("head_branch") != branch)):
            raise ValueError("STATE_RESTORE_SOURCE_RUN_NOT_SUCCESSFUL")
        if source_job_name is None:
            if run.get("status") != "completed" or run.get("conclusion") != "success":
                raise ValueError("STATE_RESTORE_SOURCE_RUN_NOT_SUCCESSFUL")
        else:
            # Read-only sidecars may still run after the actual state writer is
            # complete. Require GitHub's completed writer job, not a self-issued
            # success flag, and bind it to the same frozen consumer code.
            if source_job_name != "source-pilot" or run.get("head_sha") != audit_code_sha:
                raise ValueError("STATE_RESTORE_WRITER_CODE_NOT_ATTESTED")
            jobs = _inventory_json(
                f"{API}/repos/{repository}/actions/runs/{source_run_id}/jobs?per_page=100", token,
            ).get("jobs", [])
            writers = [job for job in jobs if job.get("name") == source_job_name]
            if (len(writers) != 1 or writers[0].get("status") != "completed"
                    or writers[0].get("conclusion") != "success"):
                raise ValueError("STATE_RESTORE_WRITER_JOB_NOT_SUCCESSFUL")
        # Run-scoped inventory cannot silently select a different producer.
        url = f"{API}/repos/{repository}/actions/runs/{source_run_id}/artifacts?per_page=100"
    else:
        url = f"{API}/repos/{repository}/actions/artifacts?name={artifact_name}&per_page=100"
    payload = _inventory_json(url, token)

    artifacts = [
        item
        for item in payload.get("artifacts", [])
        if not item.get("expired", False)
        and (source_run_id is None or (
            item.get("name") == artifact_name
            and (item.get("workflow_run") or {}).get("id") == source_run_id
            and (item.get("workflow_run") or {}).get("head_sha") == run.get("head_sha")
        ))
        and (
            branch is None
            or (item.get("workflow_run") or {}).get("head_branch") == branch
        )
    ]
    if not artifacts:
        if required:
            raise RuntimeError("STATE_RESTORE_REQUIRED_BUT_NO_VERIFIED_ARTIFACT")
        return False

    artifacts.sort(key=lambda item: item["created_at"], reverse=True)
    latest = artifacts[0]
    if source_run_id is not None and len(artifacts) != 1:
        raise ValueError("STATE_RESTORE_SOURCE_ARTIFACT_NOT_UNIQUE")
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
    # Selection is diagnostic evidence, never a successful restore receipt.
    # Emit only numeric identities; never a token or signed download URL.
    source_run = latest.get("workflow_run") or {}
    selected_id = latest.get("id")
    selected_run = source_run.get("id") if isinstance(source_run, dict) else None
    print(
        "STATE_RESTORE_SOURCE_SELECTED "
        f"artifact_id={selected_id if type(selected_id) is int else 'UNVERIFIED'} "
        f"source_workflow_run_id={selected_run if type(selected_run) is int else 'UNVERIFIED'} "
        "source_state=NOT_RESTORED no_bootstrap=true",
        file=sys.stderr,
    )
    archive_request = _request(latest["archive_download_url"], token)

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        archive = _read_github(
            lambda: opener.open(archive_request, timeout=60), stage="ARTIFACT_ZIP",
        )
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
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
        try:
            with urllib.request.urlopen(clean_request, timeout=60) as response:
                archive = response.read()
        except urllib.error.HTTPError as storage_error:
            _report_github_artifact_error(storage_error, stage="ARTIFACT_SIGNED_STORAGE")
            raise

    # GitHub Actions artifacts may advertise their immutable ZIP digest.
    # Verify that digest before extracting or touching the canonical state.
    advertised = latest.get("digest")
    if expected_zip_sha256 is not None and hashlib.sha256(archive).hexdigest() != expected_zip_sha256:
        raise ValueError("STATE_RESTORE_EXPECTED_ZIP_SHA_MISMATCH")
    if source_run_id is not None and advertised is None:
        raise ValueError("STATE_RESTORE_ARTIFACT_DIGEST_REQUIRED")
    if advertised is not None:
        if (not isinstance(advertised, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", advertised) is None):
            raise ValueError("STATE_RESTORE_ARTIFACT_DIGEST_INVALID")
        if hashlib.sha256(archive).hexdigest() != advertised.removeprefix("sha256:"):
            raise ValueError("STATE_RESTORE_ARTIFACT_ZIP_SHA_MISMATCH")

    target = Path(target_path)
    if target.is_symlink() or any(Path(str(target) + suffix).exists()
                                  for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("STATE_RESTORE_TARGET_BUSY_OR_SYMLINK")
    target.parent.mkdir(parents=True, exist_ok=True)
    database_sha256 = hashlib.sha256()
    database_size = 0
    temporary = None
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            candidates = [
                name
                for name in zf.namelist()
                if not name.endswith("/") and Path(name).name == target.name
            ]
            if len(candidates) != 1:
                raise RuntimeError("STATE_RESTORE_DATABASE_MEMBER_NOT_UNIQUE")
            with tempfile.NamedTemporaryFile(
                mode="w+b", prefix=f".{target.name}.restore-",
                dir=target.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                with zf.open(candidates[0]) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        database_sha256.update(chunk)
                        database_size += len(chunk)
                        output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if hashlib.sha256(temporary.read_bytes()).digest() != database_sha256.digest():
            raise ValueError("STATE_RESTORE_DATABASE_READBACK_SHA_MISMATCH")
        if validate_sqlite:
            _verify_canonical_sqlite(temporary)
        if (expected_database_sha256 is not None
                and database_sha256.hexdigest() != expected_database_sha256):
            raise ValueError("STATE_RESTORE_EXPECTED_DATABASE_SHA_MISMATCH")
        # The prior database remains byte-identical on every upstream failure.
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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
            "selection_rule": ("EXACT_SUCCESSFUL_SOURCE_RUN" if source_run_id is not None
                               else "NEWEST_NON_EXPIRED_MATCHING_GITHUB_ARTIFACT"),
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


def private_pilot_state(root: Path, target: Path, *, publish: bool = False) -> str:
    """Exchange the single-writer pilot state through an authorized private mount."""
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ValueError("CORE003_PRIVATE_ARCHIVE_ROOT_UNAVAILABLE")
    archive = root / "core003-current-state.zip"
    if archive.is_symlink():
        raise ValueError("CORE003_PRIVATE_STATE_PATH_INVALID")
    if publish:
        # CORE-003 runs as one writer. Refuse a WAL sidecar with unmerged data.
        wal = target.with_name(target.name + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise ValueError("CORE003_PRIVATE_STATE_WAL_NOT_CHECKPOINTED")
        _verify_canonical_sqlite(target)
        body = target.read_bytes()
        checksum = hashlib.sha256(body).hexdigest()
        destination = archive
    else:
        checksum, body = _read_private_pilot_state(archive)
        destination = target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if any(destination.with_name(destination.name + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("CORE003_PRIVATE_RESTORE_TARGET_BUSY")

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staging:
            temporary = Path(staging.name)
            if publish:
                with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=1) as bundle:
                    bundle.writestr("core003-pilot.sqlite", body)
                    bundle.writestr("state.sha256", checksum)
            else:
                staging.write(body)
            staging.flush()
            os.fsync(staging.fileno())
        if publish:
            _read_private_pilot_state(temporary)
        else:
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
                raise ValueError("CORE003_PRIVATE_STATE_SHA_MISMATCH")
            _verify_canonical_sqlite(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return checksum


def _read_private_pilot_state(archive: Path) -> tuple[str, bytes]:
    with zipfile.ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != ["core003-pilot.sqlite", "state.sha256"]:
            raise ValueError("CORE003_PRIVATE_STATE_MEMBERS_INVALID")
        checksum = bundle.read("state.sha256").decode("ascii")
        body = bundle.read("core003-pilot.sqlite")
    if hashlib.sha256(body).hexdigest() != checksum:
        raise ValueError("CORE003_PRIVATE_STATE_SHA_MISMATCH")
    return checksum, body


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
        # Preserve the canonical SystemExit contract in main(); the caller
        # refuses any non-restored state immediately below.
        required=False,
        validate_sqlite=os.environ.get("HBI_RESTORE_VALIDATE_SQLITE") == "1",
    )
    # A scheduled canonical watcher must never silently begin with a fresh DB
    # when the previous state archive is missing, expired, or not selectable.
    # Keep opt-in bootstrap behavior for separate research/first-run workflows.
    if not restored and os.environ.get("HBI_RESTORE_REQUIRED") == "1":
        raise SystemExit("STATE_RESTORE_REQUIRED_BUT_NO_VERIFIED_ARTIFACT")
    print("STATE_RESTORE=RESTORED" if restored else "STATE_RESTORE=EMPTY")


if __name__ == "__main__":
    main()
