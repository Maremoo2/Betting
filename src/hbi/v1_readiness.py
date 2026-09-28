from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .governance import load_governance, validate_governance

ROOT = Path(__file__).parents[2]
GOVERNANCE = ROOT / "docs" / "research_governance.json"

_REQUIRED_FILES = (
    "db/schema.sql",
    "db/migrations/0005_v1_control_learning_plane.sql",
    "src/hbi/research_integrity.py",
    "src/hbi/provider_integrity.py",
    "src/hbi/replay_validation.py",
    "src/hbi/settlement_integrity.py",
    "src/hbi/learning.py",
    "src/hbi/challenger.py",
    "src/hbi/promotion.py",
    "src/hbi/counterfactual.py",
    "src/hbi/manifest.py",
    "src/hbi/eligibility.py",
    "src/hbi/v1_audit.py",
    "docs/RESEARCH_GOVERNANCE.md",
    "docs/V1_ACCEPTANCE_CRITERIA.md",
    ".github/workflows/ci.yml",
    ".github/workflows/rikstoto-shadow-watcher.yml",
    ".github/workflows/nightly-shadow-settlement.yml",
    ".github/workflows/protected-strategy-files.yml",
    ".github/workflows/v1-system-audit.yml",
    ".github/CODEOWNERS",
)


@dataclass(frozen=True)
class V1Readiness:
    engineering_status: str
    strategic_status: str
    missing_files: tuple[str, ...]
    governance_errors: tuple[str, ...]
    governance_warnings: tuple[str, ...]
    evidence_pending: tuple[str, ...]

    @property
    def engineering_complete(self) -> bool:
        return self.engineering_status == "COMPLETE"


def assess_v1_readiness(
    *,
    root: Path = ROOT,
    governance: dict[str, Any] | None = None,
    latest_audit: dict[str, Any] | None = None,
) -> V1Readiness:
    policy = governance or load_governance(root / "docs" / "research_governance.json")
    validation = validate_governance(policy)
    missing = tuple(
        relative for relative in _REQUIRED_FILES if not (root / relative).exists()
    )

    engineering_status = (
        "COMPLETE" if not missing and validation.valid else "INCOMPLETE"
    )

    pending: list[str] = []
    if latest_audit is None:
        pending.append("no_real_state_v1_audit_supplied")
    else:
        for key in (
            "temporal_integrity",
            "provider_integrity",
            "runtime_replay_parity",
            "settlement_integrity",
        ):
            section = latest_audit.get(key)
            status = section.get("status") if isinstance(section, dict) else None
            if status not in {"PASS"}:
                pending.append(f"{key}:{status or 'MISSING'}")

    strategic_status = str(policy.get("strategic_validity") or "UNKNOWN")
    return V1Readiness(
        engineering_status=engineering_status,
        strategic_status=strategic_status,
        missing_files=missing,
        governance_errors=validation.errors,
        governance_warnings=validation.warnings,
        evidence_pending=tuple(pending),
    )


def render_readiness_json(readiness: V1Readiness) -> dict[str, object]:
    return {
        "schema_version": "HBI_V1_READINESS_V1",
        "engineering_status": readiness.engineering_status,
        "engineering_complete": readiness.engineering_complete,
        "strategic_status": readiness.strategic_status,
        "missing_files": list(readiness.missing_files),
        "governance_errors": list(readiness.governance_errors),
        "governance_warnings": list(readiness.governance_warnings),
        "evidence_pending": list(readiness.evidence_pending),
        "interpretation": (
            "Engineering COMPLETE means the V1 platform/control plane is built. "
            "Strategic validity remains governed separately by prospective evidence."
        ),
    }


def main() -> None:
    readiness = assess_v1_readiness()
    payload = render_readiness_json(readiness)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if not readiness.engineering_complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
