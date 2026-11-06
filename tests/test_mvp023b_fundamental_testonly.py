"""TEST_ONLY L2 racewise multinomial prototype; no empirical horse-racing model."""
import copy
import json
import math

import pytest

from hbi.mvp023b_fundamental_testonly import _distribution, fit_test_only, main


def synthetic_race(year, suffix, winner="1", country="NO"):
    return {
        "race_id": f"RIKSTOTO:{'BJ' if country == 'NO' else 'S1'}_NR_{year}-05-06:{suffix}",
        "research_role": "TEST_ONLY",
        "active_runner_ids": ["1", "2", "3"],
        "result_complete": True, "dead_heat": False, "full_field_verified": True,
        "winner_id": winner, "model_eligible": False,
        "runners": [
            {"runner_id": str(i), "features": {
                "observed_win_rate": [0.3, 0.2, 0.1][i-1],
                "observed_start_count": [2, 3, 4][i-1],
                "days_since_latest_observed_start": [11, 10, 9][i-1],
            }}
            for i in (1, 2, 3)
        ],
    }


def sample():
    return {
        "schema": "MVP023B_TEST_ONLY_SYNTHETIC_COHORT_V1",
        "source_scope": "TEST_ONLY_SYNTHETIC",
        "bet_authority": False,
        "model_eligible": False,
        "races": [
            synthetic_race(2019, 1),
            synthetic_race(2020, 1, "2"),
            synthetic_race(2021, 1, "3"),
            synthetic_race(2022, 1),
            synthetic_race(2023, 1),
            synthetic_race(2024, 1, "2"),
        ],
    }


def test_test_only_model_full_field_normalization_and_determinism():
    a = fit_test_only(sample())
    b = fit_test_only(sample())
    assert a == b
    assert a["evidence_scope"] == "TEST_ONLY_SYNTHETIC"
    assert a["fitted_test_only_estimator"] is True
    assert a["fitted_authentic_model"] is a["fundamental_fit_ready"] is False
    assert a["model_promotion"] is a["benter_fit_ready"] is False
    assert a["2025_lockbox_opened"] is a["bet_authority"] is False
    assert len(a["model_artifact_sha256"]) == 64
    assert len(a["model_specification"]["training_race_ids"]) == 4
    assert all("_NR_20" in r for r in a["model_specification"]["training_race_ids"])
    for year in ("2023", "2024"):
        v = a["validation"][year]
        assert v["fundamental_test_only"]["races"] == 1
        assert v["uniform_test_only"]["races"] == 1
        assert v["fundamental_test_only"]["log_loss"] is not None
        assert v["fundamental_test_only"]["brier"] is not None
        assert v["normalized_win_market"] is v["benter_combined"] is None
    w = [a["model_specification"]["model_weights"][key] for key in (
        "observed_win_rate", "observed_start_count", "days_since_latest_observed_start")]
    p = _distribution(sample()["races"][-1], w)
    assert set(p) == {"1", "2", "3"}
    assert sum(p.values()) == pytest.approx(1.0)
    assert all(math.isfinite(v) and 0 < v < 1 for v in p.values())


@pytest.mark.parametrize("change,reason", [
    (lambda d: d.update(source_scope="REAL_ORIGINAL"), "AUTHENTIC_MODEL_FIT_FORBIDDEN"),
    (lambda d: d.update(model_eligible=True), "AUTHENTIC_MODEL_FIT_FORBIDDEN"),
    (lambda d: d["races"].append(synthetic_race(2025, 1)), "2025_CANDIDATE_LOCKBOX"),
    (lambda d: d["races"].append(synthetic_race(2026, 1)), "EXPOSED_2026"),
    (lambda d: d["races"].append(copy.deepcopy(d["races"][0])),
     "DUPLICATE_OR_LEAKED_RACE"),
    (lambda d: d["races"][0].update(dead_heat=True), "FULL_FIELD_OR_OFFICIAL"),
    (lambda d: d["races"][0].update(full_field_verified=False), "FULL_FIELD_OR_OFFICIAL"),
    (lambda d: d["races"][0].update(winner_id="99"), "WINNER_OUTSIDE"),
    (lambda d: d["races"][0]["active_runner_ids"].pop(), "FULL_ACTIVE_FIELD_ROSTER"),
    (lambda d: d["races"][0]["runners"][0].update(market_probability=0.4),
     "UNREVIEWED_HORSE_RESULT"),
    (lambda d: d["races"][0]["runners"][0]["features"].update(closing_odds=2.5),
     "MISSING_OR_UNREVIEWED_FUNDAMENTAL"),
    (lambda d: d["races"][0]["runners"][0]["features"].update(observed_win_rate=None),
     "MISSING_FUNDAMENTAL_VALUE"),
    (lambda d: d["races"][0]["runners"][0]["features"].update(observed_win_rate=float("nan")),
     "MISSING_FUNDAMENTAL_VALUE"),
    (lambda d: d["races"][0]["runners"][0]["features"].update(observed_win_rate=False),
     "MISSING_FUNDAMENTAL_VALUE"),
    (lambda d: d["races"].__setitem__(slice(None, 4), []),
     "NO_REGISTERED_TEST_ONLY_2015_2022"),
])
def test_test_only_negative_full_field_temporal_data_and_market_attacks(change, reason):
    doc = sample()
    change(doc)
    with pytest.raises(ValueError, match=reason):
        fit_test_only(doc)


def test_test_only_explicit_tuning_not_on_2023_or_2024():
    doc = sample()
    doc["races"] = [r for r in doc["races"] if r["race_id"].startswith(
        ("RIKSTOTO:BJ_NR_2023-", "RIKSTOTO:BJ_NR_2024-"))]
    with pytest.raises(ValueError, match="NO_REGISTERED_TEST_ONLY_2015_2022"):
        fit_test_only(doc)


def test_test_only_invalid_regularization_never_trains():
    with pytest.raises(ValueError, match="UNREGISTERED_REGULARIZATION"):
        fit_test_only(sample(), epochs=0)
    with pytest.raises(ValueError, match="UNREGISTERED_REGULARIZATION"):
        fit_test_only(sample(), l2=-1)


def test_test_only_cli_output_write_once(tmp_path):
    doc = tmp_path / "synthetic.json"
    doc.write_text(json.dumps(sample()))
    out = tmp_path / "candidate" / "test_only.json"
    args = ["--test-only-synthetic", str(doc), "--output", str(out)]
    assert main(args) == 0
    result = json.loads(out.read_text())
    assert result["schema"] == "MVP023B_TEST_ONLY_FUNDAMENTAL_PROTOTYPE_V1"
    assert result["fitted_authentic_model"] is False
    assert result["benter_fit_ready"] is False
    with pytest.raises(FileExistsError):
        main(args)
