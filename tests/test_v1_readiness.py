import json
from pathlib import Path

from hbi.governance import load_governance
from hbi.v1_readiness import assess_v1_readiness, render_readiness_json

ROOT = Path(__file__).parents[1]


def test_v1_engineering_contract_is_complete():
    governance = load_governance(ROOT / "docs" / "research_governance.json")
    readiness = assess_v1_readiness(root=ROOT, governance=governance)
    payload = render_readiness_json(readiness)

    assert readiness.engineering_complete
    assert readiness.engineering_status == "COMPLETE"
    assert readiness.missing_files == ()
    assert readiness.governance_errors == ()
    assert readiness.strategic_status == "NOT_VALIDATED"
    assert "no_real_state_v1_audit_supplied" in readiness.evidence_pending
    assert payload["engineering_complete"] is True


def test_v1_readiness_keeps_engineering_and_evidence_separate():
    governance = load_governance(ROOT / "docs" / "research_governance.json")
    fake_audit = {
        "temporal_integrity": {"status": "PASS"},
        "provider_integrity": {"status": "WARN"},
        "runtime_replay_parity": {"status": "NO_EVIDENCE"},
        "settlement_integrity": {"status": "PASS"},
    }
    readiness = assess_v1_readiness(
        root=ROOT,
        governance=governance,
        latest_audit=fake_audit,
    )

    assert readiness.engineering_complete
    assert "provider_integrity:WARN" in readiness.evidence_pending
    assert "runtime_replay_parity:NO_EVIDENCE" in readiness.evidence_pending
    assert readiness.strategic_status == "NOT_VALIDATED"
