"""RELEASE-004 post-commit T-4 evidence, not a PIT certificate or betting authority."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

SCHEMA = "RELEASE004_T4_POSTCOMMIT_V1"
_SHA256 = re.compile(r"[a-f0-9]{64}")


def _aware(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def classify_t4_receipt(
    *,
    race_id: str,
    race_start_utc: str,
    target_minutes: float,
    model_version: str,
    decision_row: dict[str, Any] | None,
    sources: dict[str, dict[str, Any]],
    model_finished_at_utc: str | None,
    decision_calculated_at_utc: str | None,
    persist_started_at_utc: str | None,
    persist_confirmed_at_utc: str | None,
    github_sha: str | None = None,
) -> dict[str, Any]:
    """Fail closed unless every independent runtime clock is confirmed.

    The row must be read back *after* its SQLite commit. This receipt is
    additive; historical frozen row times and settlement rules are untouched.
    """
    reasons: list[str] = []
    start = _aware(race_start_utc)
    cutoff = (
        start - timedelta(minutes=target_minutes)
        if start is not None and 0 < target_minutes <= 60 else None
    )
    if cutoff is None:
        reasons.append("RACE_CLOCK_OR_TARGET_INVALID")

    source_clocks: list[datetime] = []
    receipt_sources: dict[str, dict[str, Any]] = {}
    for name in ("WIN", "STARTS", "SCRATCHED"):
        evidence = sources.get(name) or {}
        stamp = _aware(evidence.get("response_completed_at_utc"))
        digest = evidence.get("body_sha256")
        uri = evidence.get("source_uri")
        receipt_sources[name] = {
            "source_uri": uri,
            "response_completed_at_utc": (
                None if stamp is None else stamp.isoformat()
            ),
            "body_sha256": digest,
            "raw_body_retained": False,
        }
        if (
            stamp is None or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            or not isinstance(uri, str) or not uri.startswith("https://")
        ):
            reasons.append(f"{name}_SOURCE_COMPLETION_UNATTESTED")
        else:
            source_clocks.append(stamp)

    model_end = _aware(model_finished_at_utc)
    calculated = _aware(decision_calculated_at_utc)
    persist_start = _aware(persist_started_at_utc)
    persisted = _aware(persist_confirmed_at_utc)
    phases = {
        "MODEL_FINISHED": model_end,
        "DECISION_CALCULATED": calculated,
        "PERSIST_STARTED": persist_start,
        "PERSIST_CONFIRMED": persisted,
    }
    for key, value in phases.items():
        if value is None:
            reasons.append(f"{key}_UNATTESTED")
    # Individual source fetches may overlap: check max, not source order.
    if (
        len(source_clocks) == 3
        and all(phases.values())
        and not (
            max(source_clocks) <= model_end <= calculated
            <= persist_start <= persisted
        )
    ):
        reasons.append("RUNTIME_CLOCK_ORDER_INVALID")
    if cutoff is not None:
        for name, stamp in [
            ("WIN", _aware(receipt_sources["WIN"]["response_completed_at_utc"])),
            ("STARTS", _aware(receipt_sources["STARTS"]["response_completed_at_utc"])),
            ("SCRATCHED", _aware(receipt_sources["SCRATCHED"]["response_completed_at_utc"])),
            *phases.items(),
        ]:
            if stamp is not None and stamp >= cutoff:
                reasons.append(f"{name}_AT_OR_AFTER_T4")

    status = None if decision_row is None else decision_row.get("decision_status")
    frozen_time = (
        None if decision_row is None
        else _aware(decision_row.get("created_at_utc"))
    )
    if decision_row is None or decision_row.get("race_id") != race_id:
        reasons.append("DECISION_READBACK_MISSING_OR_WRONG_RACE")
    elif status not in {"WATCH", "PASS"}:
        # SHADOW_BET never self-authorizes; it requires a separate approved
        # paper-ticket-commit protocol and must not escape as executable here.
        reasons.append("DECISION_NOT_PASS_OR_WATCH")
    if frozen_time is None:
        reasons.append("FROZEN_DECISION_CLOCK_MISSING")
    elif calculated is not None and frozen_time > calculated:
        # Frozen created_at is not post-commit proof, and cannot be in the future.
        reasons.append("FROZEN_CLOCK_AFTER_CALCULATION")
    if decision_row is not None and decision_row.get("shadow_model_version") != model_version:
        reasons.append("MODEL_VERSION_MISMATCH")
    hash_ = (
        None if decision_row is None else hashlib.sha256(
            json.dumps(decision_row, sort_keys=True, default=str).encode()
        ).hexdigest()
    )
    return {
        "schema": SCHEMA, "race_id": race_id,
        "race_start_utc": race_start_utc,
        "cutoff_utc": None if cutoff is None else cutoff.isoformat(),
        "github_sha": github_sha,
        "shadow_model_version": model_version,
        "source_receipts": receipt_sources,
        "model_finished_at_utc": model_finished_at_utc,
        "decision_calculated_at_utc": decision_calculated_at_utc,
        "persist_started_at_utc": persist_started_at_utc,
        "persist_confirmed_at_utc": persist_confirmed_at_utc,
        "readback_row_sha256": hash_,
        "decision_status": status,
        "decision_persisted_before_t4": not reasons,
        "shadow_executable": False,
        "pit_certified": False,
        "reasons": sorted(set(reasons)),
        "interpretation": (
            "READBACK_CLOCK_ONLY; private original WIN body and "
            "independent identity/scratch source remain PIT gates"
        ),
    }
