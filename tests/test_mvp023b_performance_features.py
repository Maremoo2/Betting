"""MVP-023B: authentic 2026 previous-start research and explicit TEST_ONLY attacks."""
# ruff: noqa: I001  # Real-source integration helpers use test-local import roots.
import copy
import json
from pathlib import Path

import pytest

from hbi.mvp023b_performance_features import (
    build_performance_features,
    main,
    replay_existing_no_2026_originals,
    run_authentic_research,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def genuine_prior():
    return replay_existing_no_2026_originals(ROOT)


def test_authentic_seven_no_historical_starts_replayed(genuine_prior):
    assert len(genuine_prior) == 7
    assert all(r["source"]["archive_sha256"] ==
               "96d6a3c4a344a61b3d42b8173fff1b02fa44a4c1a430902db559d684960f8eb9"
               for r in genuine_prior)
    assert all(r["horse_identity"].startswith("DNT_REGISTRATION:") for r in genuine_prior)
    assert all(r["historical_date"].startswith("2026-") for r in genuine_prior)
    assert all(r["identity_method"] ==
               "EXACT_OFFICIAL_HISTORICAL_RACE_AND_STABLE_HORSE_CHAIN"
               for r in genuine_prior)
    assert all(r["historical_asof_attested"] is False for r in genuine_prior)


def test_authentic_features_limited_observed_not_full_lifetime(genuine_prior):
    a = build_performance_features(genuine_prior, evidence_mode="SOURCE_REPLAYED_NO_2026")
    b = run_authentic_research(ROOT)
    assert a == b
    assert a["source_observations"] == 7
    assert a["historical_date_years"] == ["2026"]
    assert a["retrospective_qualified_horses"] >= 1
    assert a["historical_asof_verified_horses"] == a["model_eligible_races"] == 0
    assert a["2025_lockbox_opened"] is False
    assert a["bet_authority"] is False
    assert sum(r["prior_start_count"] for r in a["materialized"]) == 7
    assert all(r["features"]["observed_prior_starts"]["history_completeness"] == "UNKNOWN"
               for r in a["materialized"])
    for row in a["materialized"]:
        features = row["features"]
        for size in (3, 5, 10):
            observed = features[f"last_{size}_observed_results"]
            rate = features[f"last_{size}_observed_win_rate"]
            assert observed["denominator"] <= size
            assert rate["denominator"] <= observed["denominator"]
            assert rate["value"] is None or 0 <= rate["value"] <= 1
        assert features["driver"]["value"] is None
        assert features["trainer"]["value"] is None
        assert features["opponent_strength"]["value"] is None
        assert features["target_post_position_context"]["value"] is None
        assert row["pit_verified"] is False and row["model_eligible"] is False


def test_real_cli_write_once_and_repeatability(tmp_path):
    output = tmp_path / "research" / "2026-no-history.json"
    args = ["--root", str(ROOT), "--output", str(output)]
    assert main(args) == 0
    doc = json.loads(output.read_text())
    assert doc["schema"] == "MVP023B_HORSE_PERFORMANCE_RESEARCH_V1"
    assert doc["source_observations"] == 7
    assert doc == run_authentic_research(ROOT)
    with pytest.raises(FileExistsError):
        main(args)


@pytest.mark.parametrize("mutate,reason", [
    (lambda row: row.update(historical_date="2026-10-21"), "FUTURE_OR_SAME_DAY"),
    (lambda row: row.update(historical_date="2026-10-20"), "FUTURE_OR_SAME_DAY"),
    (lambda row: row.update(historical_date="2025-10-20"), "LOCKBOX"),
    (lambda row: row.update(horse_identity="TMP-HORSE-1"), "BLOCKED_IDENTITY"),
    (lambda row: row.update(horse_identity="NAME:Go Fast"), "BLOCKED_IDENTITY"),
    (lambda row: row.update(horse_identity="ATG_HORSE:12345"), "BLOCKED_IDENTITY"),
    (lambda row: row["values"].update(win_odds=99.0), "UNREVIEWED_MARKET"),
    (lambda row: row["values"].update(km_time=999), "KM_TIME_SEMANTICS"),
    (lambda row: row["values"].update(distance_m="2140"), "INVALID_HISTORY_DISTANCE"),
    (lambda row: row["values"].update(gallop_flag="maybe"), "AMBIGUOUS_EVENT_CODE"),
    (lambda row: row["values"].update(start_method="TROT"), "UNKNOWN_START_METHOD"),
    (lambda row: row["source"].update(member_sha256="A" * 64), "SOURCE_RECEIPT"),
    (lambda row: row["source"].update(url="http://example.com"), "SOURCE_RECEIPT"),
    (lambda row: row.update(historical_asof_attested=True), "SOURCE_RECEIPT"),
    (lambda row: row["values"].update(placing=1, disqualification_flag=True),
     "DISQUALIFICATION_AND_POSITIVE"),
])
def test_test_only_negative_leakage_and_semantics(genuine_prior, mutate, reason):
    rows = [copy.deepcopy(genuine_prior[0])]
    mutate(rows[0])
    with pytest.raises(ValueError, match=reason):
        build_performance_features(rows, evidence_mode="TEST_ONLY")


def test_test_only_duplicate_prior_and_identity_collision(genuine_prior):
    row = copy.deepcopy(genuine_prior[0])
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_HISTORICAL_START"):
        build_performance_features([row, copy.deepcopy(row)])
    other = copy.deepcopy(row)
    other["horse_identity"] = "DNT_REGISTRATION:578001020000001"
    other["historical_date"] = "2026-03-11"
    with pytest.raises(ValueError, match="CROSS_START_HORSE_IDENTITY_COLLISION"):
        build_performance_features([row, other])


def test_test_only_unknown_outcome_never_becomes_no_wins(genuine_prior):
    row = copy.deepcopy(genuine_prior[0])
    row["values"]["placing"] = "UNKNOWN"
    row["values"]["disqualification_flag"] = "NOT_REPORTED"
    rows = build_performance_features([row])
    assert rows["evidence_mode"] == "TEST_ONLY"
    first = rows["materialized"][0]["features"]
    assert first["observed_prior_starts"]["value"] == 1
    assert first["observed_win_rate"]["value"] is None
    assert first["observed_win_rate"]["denominator"] == 0
    assert first["observed_top3_rate"]["value"] is None
    assert first["observed_gallop_rate"]["value"] is None


def test_test_only_last_n_rates_use_available_qualifying_denominator(genuine_prior):
    base = copy.deepcopy(genuine_prior[0])
    series = []
    for idx, placing in enumerate((1, 5, "UNPLACED"), start=1):
        item = copy.deepcopy(base)
        item["historical_date"] = f"2026-01-{idx:02d}"
        item["values"]["placing"] = placing
        item["values"]["disqualification_flag"] = "NOT_REPORTED"
        series.append(item)
    report = build_performance_features(series)
    facts = report["materialized"][0]["features"]
    assert facts["observed_win_rate"]["value"] == pytest.approx(1 / 3)
    assert facts["observed_win_rate"]["denominator"] == 3
    assert facts["last_5_observed_win_rate"]["denominator"] == 3
    assert facts["last_5_observed_results"]["denominator"] == 3
    assert facts["observed_top3_rate"]["value"] == pytest.approx(1 / 3)
