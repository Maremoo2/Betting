from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOVERNANCE_SCHEMA_VERSION = "HBI_RESEARCH_GOVERNANCE_V1"

_ALLOWED_P0 = {
    "PASS",
    "ENGINEERING_PASS_EVIDENCE_ACCUMULATING",
    "SHADOW_VALIDATING",
    "BLOCKED",
    "NOT_STARTED",
}
_ALLOWED_P1 = {
    "PASS",
    "READY_FOR_MANUAL_REVIEW",
    "BLOCKED",
    "BLOCKED_BY_P0",
    "BLOCKED_BY_FORWARD_EVIDENCE",
    "NOT_STARTED",
}


@dataclass(frozen=True)
class GovernanceValidation:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def load_governance(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("governance document must be a JSON object")
    return payload


def governance_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_governance(payload: dict[str, Any]) -> GovernanceValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != GOVERNANCE_SCHEMA_VERSION:
        errors.append("unexpected_governance_schema_version")
    if payload.get("execution_authority") is not False:
        errors.append("execution_authority_must_be_false")
    if payload.get("real_money_execution") is not False:
        errors.append("real_money_execution_must_be_false")
    if payload.get("auto_promotion_enabled") is not False:
        errors.append("auto_promotion_must_be_false")
    if payload.get("adaptive_switching_enabled") is not False:
        errors.append("adaptive_switching_must_be_false")
    if payload.get("manual_approval_required") is not True:
        errors.append("manual_approval_must_be_true")

    p0 = payload.get("p0")
    p1 = payload.get("p1")
    if not isinstance(p0, dict):
        errors.append("p0_missing")
        p0 = {}
    if not isinstance(p1, dict):
        errors.append("p1_missing")
        p1 = {}

    required_p0 = {
        "temporal_integrity",
        "provider_integrity",
        "settlement_integrity",
        "runtime_replay_parity",
    }
    for gate in sorted(required_p0):
        status = p0.get(gate)
        if status is None:
            errors.append(f"p0_missing:{gate}")
        elif status not in _ALLOWED_P0:
            errors.append(f"p0_invalid_status:{gate}:{status}")

    for gate, status in p1.items():
        if status not in _ALLOWED_P1:
            errors.append(f"p1_invalid_status:{gate}:{status}")

    forbidden = set(payload.get("forbidden_automatic_actions") or [])
    for action in (
        "place_real_money_bets",
        "promote_challenger",
        "change_strategy_thresholds",
        "change_model_weights",
    ):
        if action not in forbidden:
            errors.append(f"missing_forbidden_action:{action}")

    if payload.get("strategic_validity") == "VALIDATED":
        non_pass = [gate for gate, status in p0.items() if status != "PASS"]
        if non_pass:
            errors.append(
                "strategic_validity_cannot_be_validated_with_nonpass_p0:"
                + ",".join(sorted(non_pass))
            )

    if p0 and all(status == "PASS" for status in p0.values()) and payload.get(
        "strategic_validity"
    ) != "VALIDATED":
        warnings.append("all_p0_pass_but_strategic_validity_not_validated")

    return GovernanceValidation(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def promotion_blockers(payload: dict[str, Any]) -> list[str]:
    validation = validate_governance(payload)
    blockers = list(validation.errors)
    p0 = payload.get("p0") if isinstance(payload.get("p0"), dict) else {}
    blockers.extend(
        f"p0_not_pass:{gate}:{status}"
        for gate, status in sorted(p0.items())
        if status != "PASS"
    )
    if payload.get("manual_approval_required") is not True:
        blockers.append("manual_approval_not_required")
    if payload.get("auto_promotion_enabled") is not False:
        blockers.append("auto_promotion_enabled")
    return blockers
