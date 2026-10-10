import json
from copy import deepcopy

import pytest

from betting.cli import main
from betting.v33 import (
    POLICY_HASH,
    allocate_stake,
    attach_closing,
    construct_multi_race,
    divergence,
    evaluate,
    normalize,
    reassess,
    review_coupon,
)


@pytest.fixture
def case():
    probs = {"1": {"p_low": .35, "p_mid": .4, "p_high": .45},
             "2": {"p_low": .55, "p_mid": .6, "p_high": .65}}
    return {
        "race_id": "race", "active_field": ["1", "2"],
        "identity_matches": {k: {"status": "EXACT", "confidence": 1, "provider_id": k}
                             for k in probs},
        "decision_time": "2026-10-07T12:56:00+00:00", "race_start": "2026-10-07T13:00:00+00:00",
        "fundamental": {"market_free": True, "model_version": "external-calibrated-interval-v1",
                        "observed_at": "2026-10-07T12:50:00+00:00",
                        "priced_at": "2026-10-07T12:55:00+00:00", "probabilities": probs},
        "cases": {
            "1": {
                "qualified": True, "reason": "Recent form and draw support a winning case",
                "minimum_price": 3,
                "field_review": {"status": "QUALIFIED",
                                 "checked_factors": ["FORM", "DRAW"],
                                 "source_refs": ["program-form-2026-10-07"],
                                 "market_free": True},
            },
            "2": {
                "qualified": False, "reason": "No independent form or race-shape support",
                "minimum_price": 2,
                "field_review": {"status": "CASE_PASS",
                                 "checked_factors": ["FORM", "RACE_SHAPE"],
                                 "source_refs": ["program-form-2026-10-07"],
                                 "market_free": True},
            },
        },
        "decision_snapshot": {
            "WIN": {"race_id": "race", "snapshot_id": "win-1",
                    "observed_at": "2026-10-07T12:55:50+00:00", "odds": {"1": 2.8, "2": 2}},
            "collective": {name: {"race_id": "race", "product": name, "snapshot_id": name,
                                  "observed_at": "2026-10-07T12:55:45+00:00",
                                  "shares": {"1": 60, "2": 40}} for name in ("V4", "V65")}},
        "place": {"market_free": True, "model_version": "separate-place-v1", "paid_places": 1,
                  "observed_at": "2026-10-07T12:50:00+00:00",
                  "priced_at": "2026-10-07T12:55:00+00:00", "probabilities": deepcopy(probs),
                  "cases": {
                      "1": {
                          "qualified": True, "reason": "Independent place case from recent form",
                          "minimum_price": 3,
                          "field_review": {"status": "QUALIFIED",
                                           "checked_factors": ["FORM", "DRAW"],
                                           "source_refs": ["program-form-2026-10-07"],
                                           "market_free": True},
                      },
                      "2": {
                          "qualified": False, "reason": "No independent place case from form",
                          "minimum_price": 2,
                          "field_review": {"status": "CASE_PASS",
                                           "checked_factors": ["FORM", "RACE_SHAPE"],
                                           "source_refs": ["program-form-2026-10-07"],
                                           "market_free": True},
                      },
                  },
                  "snapshot": {"race_id": "race", "snapshot_id": "place-1",
                               "observed_at": "2026-10-07T12:55:50+00:00",
                               "odds": {"1": 3.1, "2": 2}}},
        "batch": {"batch_id": "blind-001", "mode": "PROSPECTIVE_BLIND",
                  "registered_at": "2026-10-07T12:00:00+00:00", "policy_hash": POLICY_HASH},
    }


def test_full_field_market_normalization():
    assert normalize({"1": 4, "2": 2}, ["1", "2"], odds=True) == pytest.approx(
        {"1": 1/3, "2": 2/3})
    assert normalize({"1": 12.5, "2": 37.5}, ["1", "2"]) == {"1": .25, "2": .75}


def test_frozen_thresholds_and_sensitivity():
    assert divergence(.25, .20)["signal"] == "STRONG_POS"
    assert divergence(.15, .20)["signal"] == "STRONG_NEG"
    assert divergence(.25, .20)["BORDERLINE"]
    assert divergence(.30, .20)["ROBUST_CORE"]
    assert divergence(.10, .20)["ROBUST_CORE"]
    assert divergence(.21, .20)["signal"] == "NEUTRAL"


def test_evidence_never_creates_bet_or_probability(case):
    case["hbi_evidence"] = [{"prewatch_score": 99, "market_rejection": True}]
    report = evaluate(case)
    row = report["runners"]["1"]
    assert row["DUAL_POOL_STRONG"] and row["COL_CONSENSUS"] == "POSITIVE"
    assert row["WIN"]["decision"] == "PRICE_PASS"
    assert row["WIN"]["p_mid"] == .4
    assert row["PLACE"]["decision"] == "BET"
    assert report["runners"]["2"]["WIN"]["decision"] == "CASE_PASS"
    assert report["allowed"]
    assert report["full_field_quality"]["screened_runners"] == len(case["active_field"])
    assert [item["selection"] for item in report["ranked_qualified_WIN"]] == ["1"]


def test_reentry_is_new_revision_and_case_pass_stays_closed(case):
    original = evaluate(case)
    saved = deepcopy(original)
    quote = {"race_id": "race", "snapshot_id": "win-2",
             "observed_at": "2026-10-07T12:57:00+00:00", "odds": {"1": 3.1, "2": 100}}
    revision = reassess(original, quote, "2026-10-07T12:57:10+00:00")
    assert revision["WIN"]["1"]["decision"] == "BET"
    assert revision["WIN"]["2"]["decision"] == "CASE_PASS"
    assert revision["reprice_coverage"] == {"active": 2, "checked": 2}
    assert revision["changes"]["1"]["price_crossed"]
    assert revision["changes"]["1"]["current_status"] == "BET"
    assert original == saved
    assert allocate_stake(revision["WIN"]["1"])["stake_nok"] == 25
    assert allocate_stake(revision["WIN"]["2"])["stake_nok"] == 0
    closed = attach_closing(original, quote)
    assert closed["decision_id"] == original["decision_id"]
    assert closed["runners"] == original["runners"]
    assert original["closing_snapshot"] is None


@pytest.mark.parametrize("mutation", [
    lambda c: c["fundamental"]["probabilities"].pop("2"),
    lambda c: c["fundamental"]["probabilities"]["1"].update(p_low=.5),
    lambda c: c["fundamental"].update(market_free=False),
    lambda c: c["fundamental"].update(priced_at="2026-10-07T13:00:00+00:00"),
    lambda c: c["identity_matches"]["1"].update(confidence=.99),
    lambda c: c["identity_matches"]["2"].update(provider_id="1"),
    lambda c: c["decision_snapshot"]["WIN"]["odds"].update({"2": float("nan")}),
    lambda c: c["decision_snapshot"]["WIN"].update(race_id="other"),
    lambda c: c["cases"]["1"].update(minimum_price=2),
    lambda c: c["cases"]["2"].pop("field_review"),
    lambda c: c["cases"]["1"]["field_review"].update(source_refs=[]),
    lambda c: c["cases"]["1"]["field_review"].update(checked_factors=["FORM"]),
    lambda c: c["cases"]["1"]["field_review"].update(market_free=False),
    lambda c: c["cases"]["2"]["field_review"].update(status="QUALIFIED"),
    lambda c: c["cases"]["2"].update(reason="not sure"),
    lambda c: c["place"]["cases"]["1"].pop("field_review"),
    lambda c: c["batch"].update(policy_hash="tuned"),
    lambda c: c["batch"].update(registered_at="2026-10-07T13:00:00+00:00"),
    lambda c: c["place"]["probabilities"]["1"].update(p_mid=.5),
])
def test_fail_closed_invalid_coverage_provenance_batch(case, mutation):
    mutation(case)
    with pytest.raises(ValueError):
        evaluate(case)


def test_missing_place_stops_finalize(case):
    del case["place"]
    report = evaluate(case)
    assert not report["allowed"]
    assert report["runners"]["1"]["PLACE"]["decision"] == "BLOCKED"
    with pytest.raises(ValueError):
        review_coupon(report, ["1"], omissions={"2": "reason"})


def test_pool_skew_stale_and_partial_are_unknown(case):
    case["decision_snapshot"]["collective"]["V4"]["shares"].pop("2")
    case["decision_snapshot"]["collective"]["V65"]["observed_at"] = "2026-10-07T12:54:00+00:00"
    report = evaluate(case)
    assert len(report["unavailable_pools"]) == 2
    assert not report["runners"]["1"]["DUAL_POOL_STRONG"]
    assert report["runners"]["1"]["COL_CONSENSUS"] == "INSUFFICIENT"


def test_market_rejection_requests_explanation_without_veto(case):
    for pool in case["decision_snapshot"]["collective"].values():
        pool["shares"] = {"1": 20, "2": 80}
    case["decision_snapshot"]["WIN"]["odds"]["1"] = 3.1
    report = evaluate(case)
    assert report["runners"]["1"]["WIN"]["decision"] == "BET"
    assert not report["allowed"]
    case["cases"]["1"]["market_conflict_explanation"] = "independent form case retained"
    assert evaluate(case)["allowed"]


def test_bankers_and_multirace_require_cut_audit(case):
    report = evaluate(case)
    bad = review_coupon(report, ["1"], omissions={}, banker="1", banker_reason="best chance")
    assert not bad["allowed"]
    leg = review_coupon(report, ["1"], omissions={"2": "price/cost tradeoff"},
                        banker="1", banker_reason="full-field uncertainty considered")
    assert leg["allowed"] and leg["full_field_pricing"]["1"]["p_low"] == .35
    second = {**leg, "race_id": "race-2"}
    assert construct_multi_race(
        [leg, second], .5, max_paper_cost_nok=.5
    )["paper_cost_nok"] == .5
    with pytest.raises(ValueError, match="budget"):
        construct_multi_race([leg, second], .5)
    with pytest.raises(ValueError, match="budget"):
        construct_multi_race([leg, second], .5, max_paper_cost_nok=.49)
    with pytest.raises(ValueError):
        construct_multi_race([leg, leg], .5, max_paper_cost_nok=100)
    with pytest.raises(ValueError):
        construct_multi_race([bad], .5, max_paper_cost_nok=100)


def test_shadow_combination_never_changes_decisions(case):
    base = evaluate(case)
    case["shadow_weights"] = {"fundamental": .3, "WIN": .3, "collective": .4}
    case["batch"]["shadow_weights"] = deepcopy(case["shadow_weights"])
    blend = evaluate(case)
    assert sum(blend["shadow_combined"].values()) == pytest.approx(1)
    assert blend["runners"] == base["runners"]
    assert blend["execution"] == "SHADOW_ONLY" and not blend["champion_changed"]


def test_tampering_cannot_reopen_case(case):
    report = evaluate(case)
    report["runners"]["2"]["WIN"]["decision"] = "PRICE_PASS"
    with pytest.raises(ValueError, match="integrity"):
        review_coupon(report, ["1"], omissions={"2": "reason"})


def test_missing_quality_data_blocks_bet_and_coupon(case):
    case["cases"]["2"]["field_review"]["status"] = "DATA_MISSING"
    report = evaluate(case)
    assert not report["allowed"]
    assert report["full_field_quality"]["blocked_by_missing_data"]
    with pytest.raises(ValueError, match="incomplete"):
        review_coupon(report, ["1"], omissions={"2": "insufficient independent form"})


def test_two_independent_winner_cases_can_both_qualify(case):
    # There is no arbitrary one-runner-per-race cap.
    case["cases"]["2"]["qualified"] = True
    case["cases"]["2"]["reason"] = "Separate form-supported winning case for runner two"
    case["cases"]["2"]["field_review"]["status"] = "QUALIFIED"
    case["cases"]["2"]["market_conflict_explanation"] = "Form case despite negative pools"
    case["decision_snapshot"]["WIN"]["odds"] = {"1": 3.1, "2": 2.5}
    report = evaluate(case)
    assert report["allowed"]
    assert all(report["runners"][key]["WIN"]["decision"] == "BET"
               for key in case["active_field"])
    assert len(report["ranked_qualified_WIN"]) == 2


def test_every_coupon_omission_requires_specific_reason(case):
    # Even a low-probability runner must have a documented budget/cut rationale.
    case["fundamental"]["probabilities"] = {
        "1": {"p_low": .85, "p_mid": .92, "p_high": .95},
        "2": {"p_low": .05, "p_mid": .08, "p_high": .15},
    }
    case["cases"]["2"]["minimum_price"] = 20
    case["place"]["probabilities"] = deepcopy(case["fundamental"]["probabilities"])
    case["place"]["cases"]["2"]["minimum_price"] = 20
    report = evaluate(case)
    blocked = review_coupon(report, ["1"], omissions={})
    assert not blocked["allowed"]
    assert "CUT_AUDIT_REQUIRED:2" in blocked["errors"]
    approved = review_coupon(
        report, ["1"],
        omissions={"2": "Unqualified, stronger included single mark within budget"}
    )
    assert approved["allowed"]
    assert approved["cut_audit"]["2"]["required"]


def test_full_field_rank_reversal_detected_before_outcome(case):
    case["cases"]["2"]["qualified"] = True
    case["cases"]["2"]["reason"] = "Independent form-supported winning case for runner two"
    case["cases"]["2"]["field_review"]["status"] = "QUALIFIED"
    case["cases"]["2"]["market_conflict_explanation"] = "Fundamental factors independent"
    case["cases"]["2"]["minimum_price"] = 2
    case["decision_snapshot"]["WIN"]["odds"] = {"1": 2.8, "2": 2}
    original = evaluate(case)
    quote = {"race_id": "race", "snapshot_id": "new-quote",
             "observed_at": "2026-10-07T12:57:00+00:00",
             "odds": {"1": 3.2, "2": 5.0}}
    revision = reassess(original, quote, "2026-10-07T12:57:10+00:00")
    assert revision["reprice_coverage"] == {"active": 2, "checked": 2}
    assert revision["ranked_qualified_WIN"][0]["selection"] == "2"
    assert revision["changes"]["2"]["rank_changed"]
    assert revision["WIN"]["2"]["decision"] == "BET"


def test_pool_alias_is_not_independent_evidence(case):
    case["decision_snapshot"]["collective"]["V65"]["product"] = "V4"
    report = evaluate(case)
    assert not report["runners"]["1"]["DUAL_POOL_STRONG"]


def test_late_quote_must_be_fresh_and_prestart(case):
    report = evaluate(case)
    snapshot = {"race_id": "race", "snapshot_id": "late",
                "observed_at": "2026-10-07T12:50:00+00:00", "odds": {"1": 100, "2": 100}}
    assert reassess(report, snapshot, "2026-10-07T12:58:00+00:00")["WIN"]["1"][
        "decision"] == "WATCH"
    with pytest.raises(ValueError):
        reassess(report, snapshot, "2026-10-07T13:00:00+00:00")


def test_cli_fails_closed_and_never_overwrites(tmp_path):
    source, batch, output = (tmp_path / name for name in ("input.json", "batch.json", "out.json"))
    source.write_text("{}")
    batch.write_text("{}")
    with pytest.raises(SystemExit) as failure:
        main(["review", str(source), "--batch", str(batch), "--output", str(output)])
    assert failure.value.code == 2
    assert json.loads(output.read_text())["allowed"] is False
    with pytest.raises(FileExistsError):
        main(["register-batch", "batch", "--output", str(output)])
