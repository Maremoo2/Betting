from hbi.strategic_governance import (
    build_strategic_focus,
    validate_hypothesis,
)


PASS_P0 = {
    "temporal_integrity": "PASS",
    "provider_integrity": "PASS",
    "runtime_replay_parity": "PASS",
    "settlement_integrity": "PASS",
}


def test_hard_integrity_failure_beats_roadmap_progress():
    focus = build_strategic_focus(
        p0_statuses={**PASS_P0, "provider_integrity": "WARN", "settlement_integrity": "FAIL"},
        evaluated_rows=600,
    )
    assert focus.selected_chain_link == "settlement_integrity"
    assert "PASS" in focus.proximate_objective
    assert "real-money execution" in focus.defer
    assert focus.execution_authority is False


def test_first_proximate_objective_is_evidence_not_model_complexity():
    focus = build_strategic_focus(p0_statuses=PASS_P0, evaluated_rows=39)
    assert focus.selected_chain_link == "prospective_evidence"
    assert "100" in focus.proximate_objective
    assert "new Champion weights or probability formula" in focus.defer


def test_diagnostic_sample_does_not_become_validation_claim():
    focus = build_strategic_focus(p0_statuses=PASS_P0, evaluated_rows=250)
    assert focus.selected_chain_link == "prospective_validation"
    assert "500" in focus.proximate_objective
    assert "claiming durable profitability" in focus.defer


def test_existing_challenger_forward_clock_takes_priority():
    focus = build_strategic_focus(
        p0_statuses=PASS_P0,
        evaluated_rows=250,
        challenger_clocks=[
            {
                "challenger_id": "c1",
                "eligible_races": 120,
                "minimum_races": 500,
                "status": "COLLECTING",
            }
        ],
    )
    assert focus.selected_chain_link == "challenger_forward_evidence"
    assert "mid-sample Challenger redesign" in focus.defer


def test_after_serious_sample_choose_one_falsifiable_hypothesis():
    focus = build_strategic_focus(p0_statuses=PASS_P0, evaluated_rows=600)
    assert focus.selected_chain_link == "challenger_hypothesis"
    assert "one" in focus.proximate_objective.lower()
    assert "falsifier" in focus.empirical_test[0]


def test_hypothesis_gate_requires_create_destroy_fields_and_no_authority():
    valid = {
        "name": "recent_form_ablation",
        "diagnosis": "Champion may omit recent-form information not fully in market.",
        "mechanism": "Recent form may retain incremental signal after market probability.",
        "expected_observation": "Lower OOS log loss on preregistered slices.",
        "falsifier": "No incremental OOS improvement after market comparison.",
        "candidate_change": "Add PIT recent-form feature block to Challenger only.",
        "discovery_cutoff_utc": "2026-10-07T00:00:00+00:00",
        "oos_plan": "Own untouched chronological forward clock.",
        "confounders": ["odds band", "country", "field size"],
        "production_authority": False,
        "status": "CHALLENGER_ONLY",
    }
    assert validate_hypothesis(valid) == ()

    invalid = {**valid, "falsifier": "", "production_authority": True}
    errors = validate_hypothesis(invalid)
    assert "missing:falsifier" in errors
    assert "production_authority_must_be_false" in errors
