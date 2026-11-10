"""PIT-012 offline, research-only evidence admission diagnostics.

Reuses original response bytes and pre-registered T-4 receipt metadata.
Never issues PIT certificates: source publication, official stable identity,
scratch independence and trained-model authority require external review.
No network access, new schedule, result insertion, odds interpolation or BET.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def stamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(UTC) if dt.utcoffset() is not None else None
    except ValueError:
        return None


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_bound_bytes(root: Path, member: object, expected: object) -> tuple[bytes | None, str | None]:
    """No paths outside the provided existing archive root, no symlinks."""
    if (not isinstance(member, str) or not member or Path(member).name != member
            or not isinstance(expected, str) or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)):
        return None, "SOURCE_REFERENCE_INVALID"
    if not root.is_dir() or root.is_symlink() or root.resolve() != root:
        return None, "ARCHIVE_ROOT_UNTRUSTED"
    candidate = root / member
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 2_000_000:
        return None, "SOURCE_RAW_BYTES_MISSING_OR_OVERSIZED"
    actual = candidate.read_bytes()
    if digest(actual) != expected:
        return None, "SOURCE_BYTES_SHA_MISMATCH"
    return actual, None


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("DUPLICATE_JSON_KEYS")
        values[key] = value
    return values


def audit_win_original(
    record: dict[str, Any], *, root: Path, cutoff: str,
    raceday_key: str, race_number: int,
) -> dict[str, Any]:
    """Evidence readback only; no synthetic/retrospective PIT promotion."""
    blockers: list[str] = []
    deadline = stamp(cutoff)
    if deadline is None:
        raise ValueError("AWARE_CUTOFF_REQUIRED")
    if record.get("raceday_key") != raceday_key or record.get("race_number") != race_number:
        blockers.append("RACE_IDENTITY_MISMATCH")
    url = record.get("source_uri")
    parsed = urlsplit(url) if isinstance(url, str) else None
    expected_path = f"/api/game/{raceday_key}/betdistribution/winodds/{race_number}"
    if (parsed is None or parsed.scheme != "https"
            or parsed.hostname != "www.rikstoto.no" or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment or parsed.query
            or parsed.path != expected_path):
        blockers.append("WIN_SOURCE_ENDPOINT_NOT_VERIFIED")
    if record.get("http_status") != 200:
        blockers.append("WIN_HTTP_NOT_200")
    times = {}
    for key in ("request_started_at_utc", "response_completed_at_utc",
                "archive_completed_at_utc"):
        value = stamp(record.get(key))
        times[key] = value
        if value is None:
            blockers.append("MISSING_OR_NAIVE_" + key.upper())
        elif value > deadline:
            blockers.append(key.upper() + "_AFTER_CUTOFF")
    if all(t is not None for t in times.values()):
        if not times["request_started_at_utc"] <= times["response_completed_at_utc"] <= times["archive_completed_at_utc"]:
            blockers.append("SOURCE_CLOCK_ORDER_INVALID")
    raw, err = read_bound_bytes(root, record.get("member"), record.get("sha256"))
    if err:
        blockers.append(err)
    if raw is not None:
        try:
            payload = json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONSTANDARD_NUMBER")),
            )
            if not isinstance(payload, dict):
                blockers.append("RAW_WIN_NOT_OBJECT")
        except (ValueError, UnicodeError):
            blockers.append("RAW_WIN_JSON_INVALID")
    if record.get("market_kind") != "WIN":
        blockers.append("MARKET_NOT_WIN")
    # The source provider's Last-Modified/Date is not proof of each quote's
    # original publication timestamp. Do not reconstruct it from receipt time.
    if not record.get("source_publication_independently_attested"):
        blockers.append("SOURCE_PUBLICATION_UNATTESTED")
    if not record.get("independent_scratch_corroboration"):
        blockers.append("SCRATCH_CORROBORATION_MISSING")
    if not record.get("stable_identity_independently_attested"):
        blockers.append("IDENTITY_UNATTESTED")
    # Provenance of an external parser/full-field join must be verified by
    # independent raw-byte replay; caller flags alone are not sufficient.
    blockers.append("INDEPENDENT_RAW_WIN_FULL_FIELD_REPLAY_REQUIRED")
    return {
        "schema": "PIT012_WIN_SOURCE_AUDIT_V1",
        "status": "BLOCKED" if blockers else "RESEARCH_SOURCE_READBACK_ONLY",
        "source_bytes_verified": raw is not None and err is None,
        "source_sha256": record.get("sha256") if raw is not None else None,
        "blockers": sorted(set(blockers)),
        "pit_evidence_status": "PIT_UNPROVEN",
        "bet_authority": False,
    }


def audit_frozen_model(
    record: dict[str, Any], *, root: Path, cutoff: str,
    active_field: list[str],
) -> dict[str, Any]:
    """Check model, input and predictions against original hashes and clocks."""
    deadline = stamp(cutoff)
    if deadline is None:
        raise ValueError("AWARE_CUTOFF_REQUIRED")
    issues: list[str] = []
    version = record.get("model_version")
    if not isinstance(version, str) or not version.strip():
        issues.append("MODEL_VERSION_MISSING")
    for name in ("model_artifact", "input_dataset", "frozen_prediction"):
        evidence = record.get(name)
        if not isinstance(evidence, dict):
            issues.append(name.upper() + "_RECEIPT_MISSING")
            continue
        raw, error = read_bound_bytes(root, evidence.get("member"), evidence.get("sha256"))
        if error is not None:
            issues.append(name.upper() + "_" + error)
        elif name == "frozen_prediction":
            try:
                payload = json.loads(raw)
                if payload.get("model_version") != version:
                    issues.append("PREDICTION_MODEL_VERSION_MISMATCH")
                if payload.get("active_field") != active_field:
                    issues.append("PREDICTION_ACTIVE_FIELD_MISMATCH")
                probabilities = payload.get("probabilities")
                if (not isinstance(probabilities, dict)
                        or set(probabilities) != set(active_field)
                        or any(type(x) not in (int, float) or not math.isfinite(x)
                               or not 0 < x < 1 for x in probabilities.values())
                        or not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-9, rel_tol=0)):
                    issues.append("PREDICTION_FIELD_OR_NORMALIZATION_INVALID")
                if "winner_selection_id" in payload or "official_result" in payload:
                    issues.append("POST_RESULT_LEAKAGE_IN_FROZEN_PREDICTION")
            except (ValueError, TypeError, AttributeError, UnicodeError):
                issues.append("PREDICTION_UNREADABLE")
    calculated = stamp(record.get("model_calculated_at"))
    frozen = stamp(record.get("model_frozen_at"))
    if calculated is None:
        issues.append("MODEL_CALCULATED_TIME_MISSING")
    if frozen is None:
        issues.append("MODEL_FROZEN_TIME_MISSING")
    if calculated is not None and calculated > deadline:
        issues.append("MODEL_CALCULATED_AFTER_CUTOFF")
    if frozen is not None and frozen > deadline:
        issues.append("MODEL_FROZEN_AFTER_CUTOFF")
    if calculated is not None and frozen is not None and calculated > frozen:
        issues.append("MODEL_CALCULATED_AFTER_FROZEN")
    if record.get("trained_model_independently_attested") is not True:
        issues.append("MODEL_TRAINING_ORIGIN_UNATTESTED")
    return {
        "schema": "PIT012_MODEL_ORIGINAL_AUDIT_V1",
        "status": "BLOCKED" if issues else "RESEARCH_SOURCE_READBACK_ONLY",
        "blockers": sorted(set(issues)),
        "hashes_readback_checked": True,
        "pit_evidence_status": "PIT_UNPROVEN",
        "challenger_v3_evaluated": False,
        "bet_authority": False,
    }
