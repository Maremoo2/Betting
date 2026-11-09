"""DATA-009 source-to-shadow evidence audit. No capture, model or betting mutations.

A local archive receipt proves byte identity and observation time only. It does
not certify provider publication, actual race start or PIT eligibility.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PRE_ROLES = ("PROGRAM", "ROSTER", "WIN", "MODEL")
POST_ROLES = ("RESULT", "SETTLEMENT")


def utc(s: str) -> datetime:
    if not isinstance(s, str):
        raise TypeError("TIME_MISSING")
    d = datetime.fromisoformat(s)
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(UTC)


def source_record(
    item: dict[str, Any], *, root: Path, race_id: str,
    latest: datetime | None,
) -> tuple[bool, list[str]]:
    issues = []
    if item.get("race_id") != race_id:
        issues.append("SOURCE_RACE_ID_MISMATCH")
    try:
        t = utc(item["observed_at"])
        if latest is not None and t > latest:
            issues.append("SOURCE_OBSERVED_AFTER_CUTOFF")
    except (ValueError, TypeError, KeyError):
        issues.append("SOURCE_CLOCK_INVALID")
    sha = item.get("source_hash")
    filename = item.get("member")
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or any(c not in "0123456789abcdef" for c in sha)
    ):
        issues.append("SOURCE_SHA_INVALID")
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).is_absolute()
        or ".." in Path(filename).parts
    ):
        issues.append("SOURCE_MEMBER_INVALID")
    if not issues:
        path = root / filename
        if path.is_symlink() or not path.is_file():
            issues.append("SOURCE_BYTES_MISSING")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            issues.append("SOURCE_BYTES_SHA_CONFLICT")
    return not issues, issues


def audit(race: dict[str, Any], root: Path) -> dict[str, Any]:
    """Validate source contract. Never issue PIT certificates or betting authority."""
    issues = []
    race_id = race.get("race_id")
    if not isinstance(race_id, str) or not race_id.strip():
        raise ValueError("PHYSICAL_RACE_ID_REQUIRED")
    start = utc(race["scheduled_start_at"])
    cutoff = utc(race["decision_cutoff"])
    if start - cutoff != timedelta(minutes=4):
        issues.append("NOT_T_MINUS_FOUR")
    sources = race.get("sources", {})
    checked = {}
    for role in PRE_ROLES + POST_ROLES:
        item = sources.get(role)
        if not isinstance(item, dict):
            issues.append("MISSING_" + role)
            checked[role] = False
            continue
        ok, errors = source_record(
            item, root=root, race_id=race_id,
            latest=cutoff if role in PRE_ROLES else None,
        )
        issues.extend(role + ":" + e for e in errors)
        checked[role] = ok
        if role in POST_ROLES:
            try:
                if utc(item["observed_at"]) <= start:
                    issues.append("POST_SOURCE_NOT_AFTER_START")
            except (KeyError, ValueError):
                pass
    runner_ids = race.get("active_field", [])
    if (
        not isinstance(runner_ids, list)
        or len(runner_ids) < 2
        or any(not isinstance(x, str) or not x for x in runner_ids)
        or len(set(runner_ids)) != len(runner_ids)
    ):
        issues.append("INVALID_ACTIVE_FIELD")
    model = race.get("model_probabilities")
    odds = race.get("win_odds")
    if isinstance(runner_ids, list) and len(
        {str(x) for x in runner_ids}
    ) == len(runner_ids):
        for label, values in (("MODEL", model), ("WIN", odds)):
            if not isinstance(values, dict) or set(values) != set(runner_ids):
                issues.append(label + "_FIELD_INCOMPLETE")
            elif any(
                type(v) not in (int, float)
                or not math.isfinite(v)
                or (v <= 0 if label == "MODEL" else v <= 1)
                for v in values.values()
            ):
                issues.append(label + "_VALUES_INVALID")
        if (
            isinstance(model, dict)
            and set(model) == set(runner_ids)
            and all(type(v) in (int, float) and math.isfinite(v) for v in model.values())
            and abs(sum(model.values()) - 1) > 1e-9
        ):
            issues.append("MODEL_NOT_NORMALIZED")
    for field, reason in (
        ("scratches_independently_verified", "SCRATCHES_UNVERIFIED"),
        ("actual_start_independently_verified", "ACTUAL_START_UNVERIFIED"),
        ("source_publication_or_asof_attested", "SOURCE_PUBLICATION_UNATTESTED"),
        ("provider_identity_verified", "IDENTITY_UNATTESTED"),
    ):
        if not race.get(field):
            issues.append(reason)
    if race.get("winner_selection_id") not in runner_ids:
        issues.append("OFFICIAL_WINNER_NOT_IN_ACTIVE_FIELD")
    normalized = None
    if (
        isinstance(odds, dict)
        and runner_ids
        and set(odds) == set(runner_ids)
        and all(
            type(v) in (int, float) and math.isfinite(v) and v > 1
            for v in odds.values()
        )
    ):
        total = sum(1 / odds[x] for x in runner_ids)
        normalized = {x: (1 / odds[x]) / total for x in runner_ids}
    return {
        "schema": "DATA009_PIPELINE_AUDIT_V1",
        "race_id": race_id,
        "scheduled_start_at": start.isoformat(),
        "decision_cutoff": cutoff.isoformat(),
        "source_status": checked,
        "normalized_win_probability": normalized,
        "blockers": sorted(set(issues)),
        "pit_evidence_status": "PIT_UNPROVEN",
        "contract_complete": not issues,
        "evaluation_eligible": False,
        "bet_authority": False,
        "auto_bet": False,
        "model_changed": False,
    }
