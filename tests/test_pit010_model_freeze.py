"""PIT-010: negative pre-cutoff regressions, research-only synthetic fixtures."""
import pytest

from hbi.benchmark003_framework import score, validate


def row(scope="DECISION_TIME_OBSERVED"):
    return {
        "race_id": "SYNTHETIC_RACE_DO_NOT_SCORE",
        "race_date": "2026-11-09",
        "race_start_at": "2026-11-09T17:42:00+00:00",
        "decision_cutoff": "2026-11-09T17:38:00+00:00",
        "scope": scope,
        "active_field": ["1", "2"],
        "winner_selection_id": "2",
        "probabilities": {
            "SHADOW_TEST": {"1": 0.4, "2": 0.6},
            "WIN_TEST": {"1": 0.5, "2": 0.5},
        },
        "market_observed_at": "2026-11-09T17:37:04+00:00",
        "model_calculated_at": "2026-11-09T17:37:11+00:00",
        "model_frozen_at": "2026-11-09T17:37:11.184096+00:00",
        # These fields are claims from an untrusted test fixture, not
        # authentic identity/PIT evidence and never yield BET authority.
        "pit_evidence_status": "PIT_UNPROVEN",
    }


def test_valid_timing_remains_diagnostic_only():
    case = row()
    assert validate(case) is case
    answer = score([case], "SHADOW_TEST", "WIN_TEST")
    assert answer["status"] == "PAIRED_RESEARCH_DIAGNOSTIC"
    assert answer["bet_authority"] is False
    assert answer["economic_edge_claimed"] is False


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("model_calculated_at", "2026-11-09T17:38:00.000001+00:00",
         "MODEL_CALCULATED_AFTER_CUTOFF"),
        ("model_frozen_at", "2026-11-09T17:38:00.000001+00:00",
         "MODEL_FROZEN_AFTER_CUTOFF"),
        ("model_calculated_at", "2026-11-09T17:37:12+00:00",
         "MODEL_CALCULATED_AFTER_FROZEN"),
        ("market_observed_at", "2026-11-09T17:38:00.000001+00:00",
         "MARKET_AFTER_CUTOFF"),
    ],
)
def test_late_or_out_of_order_times_rejected(field, value, reason):
    case = row()
    case[field] = value
    with pytest.raises(ValueError, match=reason):
        validate(case)
    with pytest.raises(ValueError, match=reason):
        score([case], "SHADOW_TEST", "WIN_TEST")


@pytest.mark.parametrize(
    "missing,reason",
    [
        ("model_calculated_at", "MODEL_CALCULATED_TIMESTAMP_MISSING"),
        ("model_frozen_at", "MODEL_FROZEN_TIMESTAMP_MISSING"),
        ("market_observed_at", "MARKET_TIMESTAMP_MISSING"),
    ],
)
def test_missing_clock_is_not_prestart_authority(missing, reason):
    case = row()
    del case[missing]
    with pytest.raises(ValueError, match=reason):
        validate(case)


@pytest.mark.parametrize("field", [
    "model_calculated_at", "model_frozen_at", "market_observed_at",
])
def test_naive_clock_is_rejected(field):
    case = row()
    case[field] = "2026-11-09T17:37:11"
    with pytest.raises(ValueError, match="TIMESTAMP_NAIVE"):
        validate(case)


def test_exact_predeclared_cutoff_allowed_for_noncertified_diagnostics():
    case = row()
    case["model_calculated_at"] = "2026-11-09T17:38:00Z"
    case["model_frozen_at"] = "2026-11-09T17:38:00Z"
    validate(case)
    assert case["pit_evidence_status"] == "PIT_UNPROVEN"


def test_pit_label_cannot_be_promoted_from_an_unattested_fixture():
    case = row("PIT_CERTIFIED")
    with pytest.raises(ValueError, match="PIT_CLAIM_WITHOUT_CERTIFICATE"):
        validate(case)


def test_claimed_certified_scope_still_blocks_late_calculation():
    case = row("PROSPECTIVE_FROZEN")
    case.update({
        "pit_evidence_status": "PIT_CERTIFIED",
        "source_hash": "a" * 64, "snapshot_id": "SYNTHETIC",
        "model_version": "SYNTHETIC_NOT_CERTIFIED",
        "model_calculated_at": "2026-11-09T17:39:00Z",
    })
    with pytest.raises(ValueError, match="MODEL_CALCULATED_AFTER_CUTOFF"):
        validate(case)


def test_earlier_offset_is_compared_as_instant_not_string():
    case = row()
    case["model_calculated_at"] = "2026-11-09T18:37:11+01:00"
    case["model_frozen_at"] = "2026-11-09T18:37:11.184096+01:00"
    assert validate(case) is case
    case["model_frozen_at"] = "2026-11-09T18:39:00+01:00"
    with pytest.raises(ValueError, match="MODEL_FROZEN_AFTER_CUTOFF"):
        validate(case)
