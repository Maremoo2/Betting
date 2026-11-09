import pytest

from hbi.benchmark003_framework import score


def race(day, rid):
    return {
        "race_id": rid, "race_date": day, "scope": "TERMINAL_RETROSPECTIVE",
        "active_field": ["1", "2"],
        "probabilities": {"A": {"1": .7, "2": .3}, "B": {"1": .5, "2": .5}},
        "winner_selection_id": "1",
        "race_start_at": day + "T20:00:00Z",
        "decision_cutoff": day + "T19:56:00Z",
    }


def test_paired_retrospective_scoring_and_block_uncertainty():
    result = score([
        race("2024-02-01", "R1"),
        race("2024-02-09", "R2"),
    ], "A", "B")
    assert result["delta_log_loss"] < 0
    assert result["independent_weeks"] == 2
    assert result["block_week_ci_95"] is not None
    assert result["economic_edge_claimed"] is False


def test_scope_never_silently_promoted_to_pit():
    row = race("2026-11-09", "R1")
    row["scope"] = "PIT_CERTIFIED"
    with pytest.raises(ValueError, match="PIT_CLAIM_WITHOUT_CERTIFICATE"):
        score([row], "A", "B")


def test_mixed_scopes_and_duplicate_races_block():
    a = race("2024-02-01", "R1")
    b = race("2024-02-09", "R2")
    b["scope"] = "DECISION_TIME_OBSERVED"
    b["market_observed_at"] = "2024-02-09T19:55:00Z"
    with pytest.raises(ValueError, match="MIXED_SCOPE"):
        score([a, b], "A", "B")
    with pytest.raises(ValueError, match="DUPLICATE_RACE"):
        score([a, a], "A", "B")


def test_field_and_future_win_veto():
    row = race("2024-02-01", "R1")
    row["probabilities"]["A"]["2"] = .4
    with pytest.raises(ValueError, match="INVALID_MODEL_FIELD"):
        score([row], "A", "B")
    row = race("2024-02-01", "R1")
    row["scope"] = "DECISION_TIME_OBSERVED"
    row["market_observed_at"] = "2024-02-01T19:58:00Z"
    with pytest.raises(ValueError, match="MARKET_AFTER_CUTOFF"):
        score([row], "A", "B")
