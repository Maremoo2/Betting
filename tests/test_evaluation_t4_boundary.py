"""Synthetic source-shaped fields: evaluation cannot admit a late model freeze."""
from datetime import UTC, datetime, timedelta

import pytest
from test_challenger_v2_validation import score

from hbi.prospective_outcome_scorecard import _field
from hbi.shadow import ShadowPolicy

START = datetime(2026, 11, 7, 14, tzinfo=UTC)
CUTOFF = START - timedelta(minutes=ShadowPolicy().target_minutes_to_start)


@pytest.mark.parametrize("seconds,allowed", [(-1, True), (0, False), (1, False), (180, False)])
def test_v2_archived_after_t4_cannot_enter_prospective_scores(seconds, allowed):
    result = score(artifact=(CUTOFF + timedelta(seconds=seconds)).isoformat())
    if allowed:
        assert result["status"] == "PROSPECTIVE_SHADOW_EVALUABLE_NOT_BET"
    else:
        assert result == {"status": "NOT_AVAILABLE",
                          "reason": "MODEL_NOT_INDEPENDENTLY_ARCHIVED_BEFORE_T4"}
        assert "log_loss" not in result and "multiclass_brier" not in result


@pytest.mark.parametrize("seconds,allowed", [(-1, True), (0, False), (1, False)])
def test_champion_core004_full_field_freeze_has_same_strict_cutoff(seconds, allowed):
    freeze = CUTOFF + timedelta(seconds=seconds)
    model = {"race": {"start_time_utc": START.isoformat()},
             "report_created_at_utc": freeze.isoformat(),
             "as_of_utc": (CUTOFF - timedelta(minutes=1)).isoformat(),
             "run_kind": "PROSPECTIVE_ATTEMPT", "bet_authority": False,
             "model_status": "MODEL_READY", "source_archive_is_immutable_read_only": True,
             "field_size": 2, "active_runners": 2,
             "runners": [{"selection_id": str(n), "start_number": n, "scratched": False,
                          "champion_p_win": .5, "core004_p_win": .5} for n in (1, 2)]}
    _, blocks = _field(model)
    assert ("FROZEN_MODEL_MISSED_T4_OR_INVALID_CLOCK" not in blocks) == allowed
