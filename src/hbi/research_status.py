from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


_P0_KEYS = (
    "temporal_integrity",
    "provider_integrity",
    "runtime_replay_parity",
    "settlement_integrity",
)


def build_effective_research_status(
    *,
    governance: dict[str, Any],
    v1_audit: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Combine static governance policy with live audit evidence.

    The governance document remains the policy authority. This artifact is the
    current evidence status and may change automatically as new runs arrive.
    It never grants execution or promotion authority.
    """
    current = generated_at or datetime.now(UTC)
    effective_p0: dict[str, str] = {}
    evidence: dict[str, dict[str, object]] = {}

    for key in _P0_KEYS:
        section = v1_audit.get(key)
        if not isinstance(section, dict):
            effective_p0[key] = "NO_EVIDENCE"
            evidence[key] = {"status": "NO_EVIDENCE"}
            continue
        status = str(section.get("status") or "NO_EVIDENCE")
        effective_p0[key] = status
        evidence[key] = {
            "status": status,
            "checked_rows": section.get("checked_rows"),
            "checked_decisions": section.get("checked_decisions"),
            "failures": section.get("failures"),
            "warnings": section.get("warnings"),
        }

    all_p0_pass = all(status == "PASS" for status in effective_p0.values())
    engineering_status = str(v1_audit.get("engineering_status") or "UNKNOWN")
    strategic = str(governance.get("strategic_validity") or "NOT_VALIDATED")

    return {
        "schema_version": "HBI_EFFECTIVE_RESEARCH_STATUS_V1",
        "generated_at_utc": current.astimezone(UTC).isoformat(),
        "system_version": governance.get("system_version"),
        "engineering_status": engineering_status,
        "operational_validity": governance.get("operational_validity"),
        "strategic_validity": strategic,
        "shadow_champion": governance.get("shadow_champion"),
        "market_baseline": governance.get("market_baseline"),
        "effective_p0": effective_p0,
        "all_p0_currently_pass": all_p0_pass,
        "p1": governance.get("p1") or {},
        "evidence": evidence,
        "learning_dataset": v1_audit.get("learning_dataset") or {},
        "challenger_forward_clocks": v1_audit.get("challenger_forward_clocks") or [],
        "execution_authority": False,
        "auto_promotion_enabled": False,
        "adaptive_switching_enabled": False,
        "manual_approval_required": True,
        "interpretation": (
            "This is automatically derived current evidence. P0 PASS means the "
            "latest stored-state audit passed; it does not validate betting edge. "
            "Strategic validity and promotion remain separately governed."
        ),
    }
