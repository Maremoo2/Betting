"""Synthetic negative contracts, not real identities, calibration or betting evidence."""
import copy
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from hbi.benchmark002_summary import paired, validate_frozen_rows
from hbi.history_source_verification import inspect_dnt_race_kind

URI = "https://www.travsport.no/travbaner/klosterskogen-travbane/results/2026-11-07"
CUTOFF = datetime(2026, 11, 23, 18, 11, tzinfo=UTC)


def original(terms="Prøveløp", extra=""):
    body = (f'<div id="race-21" class="navigation">Ordinary</div>'
            f'<div id="race-21" class="m-b-2 js-tabbedContent-panel">'
            f'<h2>Løp 21</h2><div>{terms}</div><table><tr><td>Other</td></tr></table></div>'
            + extra).encode()
    return {"status": 200, "url": URI, "final_url": URI, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "observed_at": (CUTOFF - timedelta(seconds=1)).isoformat()}, body


def inspect(source):
    return inspect_dnt_race_kind(source, official_race_uri=URI + "#race-21", cutoff=CUTOFF)


def test_trial_terms_are_not_five_ordinary_starts_or_identity_attestation():
    result = inspect(original())
    assert result["kind"] == "QUALIFICATION"
    assert result["exclude_from_ordinary_last_five"]
    assert not result["model_eligible"] and not result["pit_certified"]
    ordinary = inspect(original("2140m Autostart"))
    assert ordinary["kind"] == "UNCLASSIFIED_REQUIRES_REVIEW"


@pytest.mark.parametrize("fault", ["hash", "source", "late", "naive", "duplicate", "conflict"])
def test_race_terms_require_correct_original_and_strict_cutoff(fault):
    source = original("Prøveløp Mønstringsløp" if fault == "conflict" else "Prøveløp",
                      '<div id="race-21" class="js-tabbedContent-panel">Prøveløp</div>'
                      if fault == "duplicate" else "")
    if fault == "hash": source[0]["sha256"] = "0" * 64
    if fault == "source": source[0]["url"] = URI + "other"
    if fault == "late": source[0]["observed_at"] = CUTOFF.isoformat()
    if fault == "naive": source[0]["observed_at"] = "2026-11-23T10:00:00"
    with pytest.raises(ValueError):
        inspect(source)


def row(day="2024-01-01"):
    return {"race_id": "r1", "scope": "RESEARCH_RETROSPECTIVE", "day": day,
            "winner": "1", "probabilities": {"M0": {"1": .5, "2": .5},
                                                "V2": {"1": .6, "2": .4}}}


@pytest.mark.parametrize("fault", ["duplicate", "field", "winner", "sum", "nan", "bool", "lockbox"])
def test_frozen_evaluation_never_scores_invalid_cohorts(fault):
    r = row("2025-01-01" if fault == "lockbox" else "2024-01-01")
    if fault == "field": r["probabilities"]["V2"].pop("2")
    if fault == "winner": r["winner"] = "3"
    if fault == "sum": r["probabilities"]["V2"]["2"] = .3
    if fault == "nan": r["probabilities"]["V2"]["2"] = float("nan")
    if fault == "bool": r["probabilities"]["V2"]["2"] = True
    with pytest.raises(ValueError):
        validate_frozen_rows([r, copy.deepcopy(r)] if fault == "duplicate" else [r])


def test_metric_bootstrap_is_not_a_calibrated_horse_probability_interval():
    rows = [row()]
    coverage = validate_frozen_rows(rows)
    assert coverage["full_fields_verified"] == 1
    assert coverage["external_active_roster_verified_by_this_check"] is False
    result = paired(rows, "V2", "M0")
    assert result["uncertainty_status"] == "INSUFFICIENT_INDEPENDENT_CLUSTERS"
    assert result["ll_lo"] is None and result["brier_hi"] is None
    assert result["pwin_intervals_calibrated"] is False
    assert result["bootstrap_p"] is None


def test_existing_fold_generator_keeps_train_calibration_and_test_disjoint(monkeypatch):
    from datetime import date

    from hbi import benchmark002_retrospective as benchmark

    rows = [{"day": date(year, 1, 1)} for year in range(2020, 2025)]
    calls = []
    monkeypatch.setattr(benchmark, "fit", lambda data, cols: calls.append(list(data)))
    for year, train, calibration, test, _ in benchmark.freeze_model_rows(rows):
        assert all(r["day"].year < year - 1 for r in train)
        assert all(r["day"].year == year - 1 for r in calibration)
        assert all(r["day"].year == year for r in test)
        assert {id(r) for r in train}.isdisjoint({id(r) for r in calibration + test})
    assert calls  # The fit call is a stub; no model was trained.
