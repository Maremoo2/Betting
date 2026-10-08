from hbi.research_status import build_effective_research_status


def test_effective_research_status_uses_live_audit_not_static_p0_labels():
    governance = {
        "system_version": "HBI_V1",
        "operational_validity": "SHADOW_OPERATIONAL",
        "strategic_validity": "NOT_VALIDATED",
        "shadow_champion": "FUNDAMENTAL_CHAMPION_V1_1",
        "market_baseline": "RIKSTOTO_WIN_NORMALIZED",
        "p0": {
            "temporal_integrity": "ENGINEERING_PASS_EVIDENCE_ACCUMULATING",
            "provider_integrity": "SHADOW_VALIDATING",
            "runtime_replay_parity": "ENGINEERING_PASS_EVIDENCE_ACCUMULATING",
            "settlement_integrity": "ENGINEERING_PASS_EVIDENCE_ACCUMULATING",
        },
        "p1": {"statistical_validation": "BLOCKED_BY_FORWARD_EVIDENCE"},
    }
    audit = {
        "engineering_status": "PASS",
        "temporal_integrity": {"status": "PASS", "checked_rows": 327},
        "provider_integrity": {"status": "PASS", "checked_decisions": 9},
        "runtime_replay_parity": {"status": "PASS", "checked_decisions": 3},
        "settlement_integrity": {"status": "PASS", "checked_rows": 7},
        "learning_dataset": {"rows": 9},
        "challenger_forward_clocks": [],
    }

    status = build_effective_research_status(
        governance=governance,
        v1_audit=audit,
    )

    assert status["all_p0_currently_pass"] is True
    assert set(status["effective_p0"].values()) == {"PASS"}
    assert status["strategic_validity"] == "NOT_VALIDATED"
    assert status["execution_authority"] is False
    assert status["auto_promotion_enabled"] is False


def test_effective_research_status_surfaces_missing_evidence():
    governance = {
        "system_version": "HBI_V1",
        "operational_validity": "SHADOW_OPERATIONAL",
        "strategic_validity": "NOT_VALIDATED",
        "shadow_champion": "FUNDAMENTAL_CHAMPION_V1_1",
        "market_baseline": "RIKSTOTO_WIN_NORMALIZED",
        "p1": {},
    }
    audit = {
        "engineering_status": "PASS_WITH_EVIDENCE_PENDING",
        "temporal_integrity": {"status": "PASS"},
        "provider_integrity": {"status": "NO_EVIDENCE"},
        "runtime_replay_parity": {"status": "NO_EVIDENCE"},
        "settlement_integrity": {"status": "PASS"},
    }

    status = build_effective_research_status(
        governance=governance,
        v1_audit=audit,
    )

    assert status["all_p0_currently_pass"] is False
    assert status["effective_p0"]["provider_integrity"] == "NO_EVIDENCE"
    assert status["effective_p0"]["runtime_replay_parity"] == "NO_EVIDENCE"
