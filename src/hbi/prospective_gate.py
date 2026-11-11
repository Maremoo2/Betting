"""RELEASE-005: single fail-closed gate for primary prospective research.

Historical rows remain LEGACY_UNCERTIFIED; this never retroactively grants PIT.
A watcher timestamp or a matching SHA alone is insufficient.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

from .t4_evidence import SCHEMA as RECEIPT_SCHEMA
from .t4_evidence import classify_t4_receipt

GATE_SCHEMA = "RELEASE005_PRIMARY_PROSPECTIVE_GATE_V1"
# PR187 merge time: previous materialized historical regime is unchanged.
# New races require an actual postcommit receipt; old rows are NEVER PIT.
LEGACY_BOUNDARY_UTC = datetime(2026, 11, 11, 10, 52, 18, tzinfo=UTC)
PRIMARY_PIT_QUALIFIED = "PRIMARY_PIT_QUALIFIED"
RESEARCH_DIAGNOSTIC_ONLY = "RESEARCH_DIAGNOSTIC_ONLY"
LEGACY_UNCERTIFIED = "LEGACY_UNCERTIFIED"
REJECTED_OR_INCOMPLETE = "REJECTED_OR_INCOMPLETE"
SUPPORTED_STATUSES = frozenset({"PASS", "WATCH"})


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(UTC)


def _row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, default=str).encode()
    ).hexdigest()


def _normalized(value: object, field_size: int | None) -> bool:
    if not isinstance(value, str):
        return False
    try:
        data = json.loads(value)
        if not isinstance(data, dict) or len(data) < 2:
            return False
        if field_size is not None and len(data) != field_size:
            return False
        values = [float(v) for v in data.values()]
        return (
            all(math.isfinite(x) and 0 < x <= 1 for x in values)
            and abs(sum(values) - 1.0) <= 1e-6
        )
    except (ValueError, TypeError, OverflowError):
        return False


def is_new_regime(row: dict[str, Any]) -> bool:
    start = _utc(row.get("race_start_time_utc"))
    # No timestamp is an explicit failure, never an old-regime bypass.
    return start is None or start >= LEGACY_BOUNDARY_UTC


def index_from_manifest_rows(
    manifests: list[dict[str, Any]],
) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    result: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for manifest in manifests:
        if manifest.get("run_type") != "WATCHER" or manifest.get("status") != "OK":
            continue
        try:
            data = json.loads(str(manifest.get("metadata_json") or ""))
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        attempts = data.get("t4_attempts")
        if not isinstance(attempts, list):
            continue
        for receipt in attempts:
            if not isinstance(receipt, dict):
                continue
            digest = receipt.get("readback_row_sha256")
            if isinstance(digest, str) and len(digest) == 64:
                result.setdefault(digest, []).append((receipt, manifest))
    return result


def qualification_index(store: Any) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    """Read-only index built once per reporting job; no historical mutation."""
    return index_from_manifest_rows(store.fetch_table("system_run_manifests"))


def qualify_prospective(
    row: dict[str, Any],
    index: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
) -> dict[str, Any]:
    """Require matching immutable row, source times and independent readback."""
    result: dict[str, Any] = {
        "schema": GATE_SCHEMA,
        "qualified": False,
        "pit_certified": False,
        "shadow_executable": False,
        "regime": "PROSPECTIVE_T4_V1" if is_new_regime(row) else "LEGACY_UNCERTIFIED",
        "population": REJECTED_OR_INCOMPLETE,
        "reasons": [],
    }
    if not is_new_regime(row):
        result["population"] = LEGACY_UNCERTIFIED
        result["reasons"] = ["LEGACY_NOT_RETROACTIVELY_CERTIFIED"]
        return result
    if row.get("decision_status") == "T4_PENDING_ATTESTATION":
        result["population"] = RESEARCH_DIAGNOSTIC_ONLY
    if row.get("decision_status") not in SUPPORTED_STATUSES:
        result["reasons"] = ["DECISION_STATUS_NOT_ELIGIBLE"]
        return result
    try:
        field_size = int(row["field_size"]) if row.get("field_size") is not None else None
    except (ValueError, TypeError):
        field_size = None
    if field_size is None or field_size < 2 or not all(
        _normalized(row.get(f"{layer}_probabilities_json"), field_size)
        for layer in ("fundamental", "market", "combined")
    ):
        result["reasons"] = ["FULL_FIELD_PROBABILITIES_UNATTESTED"]
        return result
    matches = index.get(_row_hash(row), [])
    if not matches:
        result["reasons"] = ["POSTCOMMIT_READBACK_RECEIPT_MISSING"]
        return result
    failures: list[str] = []
    for receipt, manifest in matches:
        if receipt.get("schema") != RECEIPT_SCHEMA:
            failures.append("RECEIPT_SCHEMA_MISMATCH")
            continue
        if (
            receipt.get("race_id") != row.get("race_id")
            or receipt.get("shadow_model_version") != row.get("shadow_model_version")
            or receipt.get("decision_status") != row.get("decision_status")
            or receipt.get("race_start_utc") != row.get("race_start_time_utc")
            or receipt.get("readback_row_sha256") != _row_hash(row)
        ):
            failures.append("RACE_MODEL_OR_ROW_MISMATCH")
            continue
        code_sha = receipt.get("github_sha")
        if (
            not isinstance(code_sha, str) or not code_sha
            or code_sha != manifest.get("github_sha")
        ):
            failures.append("ATTESTED_CODE_SHA_MISMATCH")
            continue
        after_commit = _utc(receipt.get("persist_confirmed_at_utc"))
        finished = _utc(manifest.get("finished_at_utc"))
        if after_commit is None or finished is None or finished < after_commit:
            failures.append("MANIFEST_NOT_AFTER_COMMIT")
            continue
        sources = receipt.get("source_receipts")
        if not isinstance(sources, dict):
            failures.append("SOURCE_RECEIPTS_MISSING")
            continue
        derived = classify_t4_receipt(
            race_id=str(row["race_id"]),
            race_start_utc=str(row["race_start_time_utc"]),
            target_minutes=float(row.get("target_minutes_to_start") or 0),
            model_version=str(row["shadow_model_version"]),
            decision_row=row,
            sources=sources,
            model_finished_at_utc=receipt.get("model_finished_at_utc"),
            decision_calculated_at_utc=receipt.get("decision_calculated_at_utc"),
            persist_started_at_utc=receipt.get("persist_started_at_utc"),
            persist_confirmed_at_utc=receipt.get("persist_confirmed_at_utc"),
            github_sha=code_sha,
        )
        if derived["decision_persisted_before_t4"] and receipt.get("decision_persisted_before_t4") is True:
            # Watcher receipts attest clocks only. They never retain original WIN
            # bytes or carry an independently verified full-field identity binding.
            result["population"] = RESEARCH_DIAGNOSTIC_ONLY
            result["reasons"] = [
                "ORIGINAL_WIN_BYTES_UNVERIFIED",
                "PERMANENT_FULL_FIELD_IDENTITY_UNATTESTED",
            ]
            result["receipt_sha256"] = hashlib.sha256(
                json.dumps(receipt, sort_keys=True).encode()
            ).hexdigest()
            return result
        failures.extend(derived["reasons"])
    result["reasons"] = sorted(set(failures or ["RECEIPT_INVALID"]))
    return result


def qualifies_primary(
    row: dict[str, Any], index: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
) -> bool:
    return qualify_prospective(row, index)["population"] == PRIMARY_PIT_QUALIFIED
