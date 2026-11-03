"""MVP-014: probability mathematics only; synthetic fields are NOT V4X originals."""
import copy
import hashlib
import json

import pytest

from hbi.mvp014_multileg_probability import (
    independent_combination_probability,
    independent_system_coverage,
)


def _raw_model(race_id: str, *, first_p: float = 0.3):
    model = {
        "schema": "BET_MVP_001_FROZEN_SHADOW_V1",
        "run_kind": "PROSPECTIVE_ATTEMPT",
        "model_status": "MODEL_READY",
        "source_archive_is_immutable_read_only": True,
        "bet_authority": False,
        "as_of_utc": "2026-11-03T10:54:00+00:00",
        "report_created_at_utc": "2026-11-03T10:55:00+00:00",
        "race": {"race_id": race_id, "start_time_utc": "2026-11-03T11:00:00+00:00"},
        "field_size": 2, "active_runners": 2,
        "runners": [
            {"selection_id": "1", "start_number": 1, "scratched": False,
             "champion_p_win": first_p, "core004_p_win": 0.5},
            {"selection_id": "2", "start_number": 2, "scratched": False,
             "champion_p_win": 1 - first_p, "core004_p_win": 0.5},
        ],
    }
    return model


def _leg(race_id: str, selections: list[str], *, model: dict | None = None):
    original = model or _raw_model(race_id)
    raw = json.dumps(original, sort_keys=True).encode("utf-8")
    return {
        "original_model_bytes": raw,
        "original_model_sha256": hashlib.sha256(raw).hexdigest(),
        "selections": selections,
    }


def test_four_leg_system_and_single_combination_mathematics():
    legs = [
        _leg("RACE:1", ["1"]),
        _leg("RACE:2", ["1", "2"]),
        _leg("RACE:3", ["2"]),
        _leg("RACE:4", ["1", "2"]),
    ]
    result = independent_system_coverage(legs, expected_legs=4)
    assert result["unique_rows"] == 4
    assert result["physical_race_count"] == 4
    assert result["probability_all_winners_covered_if_independent"] == pytest.approx(.21)
    assert result["model_name"] == "champion"
    assert result["independence_assumption"] == "ASSUMED_NOT_VALIDATED"
    assert result["pit_certification_performed"] is False
    assert result["bet_authority"] is False and result["stake_nok"] is None
    assert result["ticket"] is None and result["system_ev"] is None
    assert result["estimated_payout"] is None and result["collective_combination_price"] is None
    with pytest.raises(ValueError, match="NOT_A_SINGLE_WINNER_COMBINATION"):
        independent_combination_probability(legs)
    single = independent_combination_probability(
        [_leg(f"RACE:{i}", ["1"]) for i in range(1, 5)],
        expected_legs=4,
    )
    assert single["unique_rows"] == 1
    assert single["probability_all_winners_covered_if_independent"] == pytest.approx(.3 ** 4)


@pytest.mark.parametrize("legs_count", [4, 7, 8])
def test_product_agnostic_four_seven_eight_leg_count(legs_count):
    legs = [_leg(f"RIKSTOTO:TEST:{i}", ["1", "2"]) for i in range(legs_count)]
    answer = independent_system_coverage(legs, expected_legs=legs_count, model_name="core004")
    assert answer["unique_rows"] == 2 ** legs_count
    assert answer["probability_all_winners_covered_if_independent"] == pytest.approx(1.0)
    assert answer["model_name"] == "core004"
    assert answer["pool_identity_verified"] is False
    assert all(len(x["source_model_sha256"]) == 64 for x in answer["legs"])


def test_does_not_use_win_or_post_results_from_other_snapshots():
    models = [_raw_model("R1"), _raw_model("R2")]
    models[0]["runners"][0]["win_odds"] = 3.0
    models[0]["runners"][0]["win_odds_observed_at_utc"] = "2026-11-03T11:30:00+00:00"
    models[1]["frozen_outcome"] = {"winner": "1", "payout": 1000.0}
    result = independent_system_coverage([
        _leg("R1", ["1"], model=models[0]), _leg("R2", ["1"], model=models[1])
    ], expected_legs=2)
    assert result["probability_all_winners_covered_if_independent"] == pytest.approx(.09)
    assert result["system_ev"] is None and result["bet_authority"] is False


@pytest.mark.parametrize("field,error", [
    ("model_status", "FROZEN_MODEL_NOT_ELIGIBLE"),
    ("run_kind", "FROZEN_MODEL_NOT_ELIGIBLE"),
    ("bet_authority", "FROZEN_MODEL_NOT_ELIGIBLE"),
    ("source_archive_is_immutable_read_only", "FROZEN_MODEL_NOT_ELIGIBLE"),
    ("report_created_at_utc", "MODEL_FREEZE_AFTER_CONSERVATIVE_T4"),
    ("as_of_utc", "MODEL_FREEZE_AFTER_CONSERVATIVE_T4"),
    ("active_runners", "MODEL_ACTIVE_FULL_FIELD_INVALID"),
    ("field_size", "MODEL_FULL_FIELD_INVALID"),
])
def test_invalid_frozen_model_fails_closed(field, error):
    changed = _raw_model("R1")
    changes = {
        "model_status": "MODEL_PARTIAL", "run_kind": "ARCHIVED_REPLAY",
        "bet_authority": True, "source_archive_is_immutable_read_only": False,
        "report_created_at_utc": "2026-11-03T10:56:01+00:00",
        "as_of_utc": "2026-11-03T10:55:30+00:00",
        "active_runners": 1, "field_size": 3,
    }
    changed[field] = changes[field]
    with pytest.raises(ValueError, match=error):
        independent_system_coverage([
            _leg("R1", ["1"], model=changed), _leg("R2", ["1"])
        ], expected_legs=2)


def test_invalid_or_missing_active_probability_fails_closed():
    model = _raw_model("R1")
    model["runners"][0]["champion_p_win"] = None
    with pytest.raises(ValueError, match="MODEL_ACTIVE_PROBABILITIES_INVALID"):
        independent_system_coverage([
            _leg("R1", ["1"], model=model), _leg("R2", ["1"])
        ])


def test_duplicate_and_unknown_or_scratched_selections_refused():
    base = _leg("R1", ["1"])
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE_IN_LEGS"):
        independent_system_coverage([base, copy.deepcopy(base)])
    with pytest.raises(ValueError, match="UNKNOWN_SCRATCHED_OR_DUPLICATE_SELECTION"):
        independent_system_coverage([_leg("R1", ["1", "1"]), _leg("R2", ["1"])])
    with pytest.raises(ValueError, match="UNKNOWN_SCRATCHED_OR_DUPLICATE_SELECTION"):
        independent_system_coverage([_leg("R1", ["3"]), _leg("R2", ["1"])])


def test_invalid_sha_and_unsupported_model_refused():
    first = _leg("R1", ["1"])
    first["original_model_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="MODEL_ORIGINAL_BYTES_OR_SHA256_UNVERIFIED"):
        independent_system_coverage([first, _leg("R2", ["1"])])
    with pytest.raises(ValueError, match="UNKNOWN_FROZEN_PROBABILITY_MODEL"):
        independent_system_coverage([_leg("R1", ["1"]), _leg("R2", ["1"])], model_name="win")


def test_no_implicit_missing_or_repeated_legs():
    with pytest.raises(ValueError, match="INCOMPLETE_OR_INVALID_LEG_COUNT"):
        independent_system_coverage([_leg("R1", ["1"]), _leg("R2", ["1"])], expected_legs=4)
    with pytest.raises(ValueError, match="INCOMPLETE_OR_INVALID_LEG_COUNT"):
        independent_system_coverage([_leg("R1", ["1"])])
