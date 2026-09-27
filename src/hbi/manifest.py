from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .governance import governance_hash, load_governance
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
GOVERNANCE = ROOT / "docs" / "research_governance.json"

CRITICAL_PATHS = (
    "src/hbi/fundamental.py",
    "src/hbi/probability.py",
    "src/hbi/engine.py",
    "src/hbi/decision.py",
    "src/hbi/shadow.py",
    "src/hbi/race_difficulty.py",
    "db/schema.sql",
)


def _hash_files(paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = ROOT / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.exists():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<MISSING>")
        digest.update(b"\0")
    return digest.hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_run_manifest(
    *,
    run_type: str,
    started_at: datetime,
    finished_at: datetime | None,
    status: str,
    model_version: str | None = None,
    policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    if finished_at is not None and (
        finished_at.tzinfo is None or finished_at.utcoffset() is None
    ):
        raise ValueError("finished_at must be timezone-aware")

    governance = load_governance(GOVERNANCE)
    return {
        "run_id": run_id or str(uuid4()),
        "run_type": run_type,
        "started_at_utc": started_at.astimezone(UTC).isoformat(),
        "finished_at_utc": (
            None if finished_at is None else finished_at.astimezone(UTC).isoformat()
        ),
        "status": status,
        "github_sha": os.getenv("GITHUB_SHA"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "model_version": model_version,
        "governance_hash": governance_hash(governance),
        "critical_code_hash": _hash_files(CRITICAL_PATHS),
        "db_schema_hash": file_sha256(ROOT / "db" / "schema.sql"),
        "policy_json": json.dumps(policy or {}, sort_keys=True),
        "metadata_json": json.dumps(metadata or {}, sort_keys=True, default=str),
    }


def persist_run_manifest(
    store: SQLiteStore,
    *,
    run_type: str,
    started_at: datetime,
    finished_at: datetime | None,
    status: str,
    model_version: str | None = None,
    policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    manifest = build_run_manifest(
        run_type=run_type,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        model_version=model_version,
        policy=policy,
        metadata=metadata,
        run_id=run_id,
    )
    store.upsert_system_run_manifest(manifest)
    return manifest
