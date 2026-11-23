"""PREWATCH-004B2: TEST_ONLY synthetic numeric cases + genuine 2026 research replay.

No synthetic positive test is evidence of a real accepted PIT or permanent ID.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_prewatch004b_features import sample

from hbi.historical_intelligence_v2 import SCHEMA as HISTORIC_SCHEMA
from hbi.mvp023b_performance_features import run_authentic_research
from hbi.prewatch004b2_original_binding import (
    DAY_SCHEMA,
    PIT_UNPROVEN,
    aggregate_official_history,
    bind_target_horse,
    feature,
)
from hbi.prewatch004b_features import build_feature_context

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)
CUTOFF = NOW.isoformat()


def fake_original(i: int, *, placing: int | str, gallop: bool | str,
                  dq: bool | str = "MISSING", observed_delta: int = -1,
                  published_delta: int | None = None) -> dict:
    observed = NOW + timedelta(hours=observed_delta)
    published = (
        (NOW + timedelta(hours=published_delta)).isoformat()
        if published_delta is not None else None
    )
    return {
        "schema": HISTORIC_SCHEMA, "horse_id": 12345, "status": "VERIFIED",
        "source_uri": f"https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-{i:02d}_1_1",
        "source_observed_at_utc": observed.isoformat(),
        "source_published_at_utc": published,
        "original_sha256": "a" * 64,
        "pit_certified": False, "bet_authority": False,
        "fields": {
            "race_date": f"2026-11-{i:02d}", "placing": placing,
            "distance_m": 2140, "start_method": "AUTO",
            "gallop": gallop, "disqualified": dq,
        },
    }


def test_strict_unknown_vs_negative_denominator_and_incomplete_last5():
    rows = [
        fake_original(10, placing=1, gallop=True, dq=False),
        fake_original(11, placing=2, gallop="MISSING", dq="MISSING"),
        fake_original(12, placing="MISSING", gallop=False, dq=False),
    ]
    result = aggregate_official_history(rows, horse_id=12345, cutoff_utc=CUTOFF)
    facts = result["features"]
    assert result["verified_individual_originals"] == 3
    assert facts["observed_win_rate"]["value"] == 0.5
    assert facts["observed_win_rate"]["denominator"] == 2
    assert facts["observed_top3_rate"]["value"] == 1.0
    assert facts["observed_gallop_rate"]["value"] == 0.5
    assert facts["observed_gallop_rate"]["denominator"] == 2
    assert facts["observed_disqualified_rate"]["value"] == 0
    assert facts["observed_disqualified_rate"]["denominator"] == 2
    assert facts["last_3_complete_results"]["value"] == "UNKNOWN"
    assert facts["last_5_complete_results"]["value"] == "UNKNOWN"
    assert facts["observed_start_method_counts"]["value"] == {"AUTO": 3}
    assert result["pit_status"] == PIT_UNPROVEN
    assert not result["model_eligible"] and not result["bet_authorized"]


def test_complete_last3_only_with_explicit_attestation():
    rows = [fake_original(n, placing=n - 9, gallop=False) for n in (10, 11, 12, 13, 14)]
    a = aggregate_official_history(
        rows, horse_id=12345, cutoff_utc=CUTOFF,
        history_index_complete=False,
    )
    b = aggregate_official_history(
        rows, horse_id=12345, cutoff_utc=CUTOFF,
        history_index_complete=True,
    )
    assert a["features"]["last_3_complete_results"]["value"] == "UNKNOWN"
    assert b["features"]["last_3_complete_results"]["status"] == "VERIFIED"
    assert b["features"]["last_5_complete_results"]["denominator"] == 5
    assert b["features"]["last_10_complete_results"]["status"] == "UNKNOWN"
    assert b["model_eligible"] is False


@pytest.mark.parametrize("mutation, error", [
    ("wrong_horse", "IDENTITY_CONFLICT"),
    ("duplicate", "DUPLICATE_PRIOR_RACE"),
    ("post_observed", "POST_CUTOFF"),
    ("post_published", "POST_CUTOFF"),
    ("same_day", "FUTURE_OR_SAME_DAY"),
    ("granted_bet", "UNREVIEWED_PIT_OR_BET"),
    ("granted_pit", "UNREVIEWED_PIT_OR_BET"),
    ("no_source", "SOURCE_ID_REQUIRED"),
])
def test_untrusted_official_rows_fail_closed(mutation, error):
    a = fake_original(10, placing=1, gallop=False)
    rows = [a]
    if mutation == "wrong_horse":
        a["horse_id"] = 999
    elif mutation == "duplicate":
        rows.append(deepcopy(a))
    elif mutation == "post_observed":
        a["source_observed_at_utc"] = (NOW + timedelta(minutes=1)).isoformat()
    elif mutation == "post_published":
        a["source_published_at_utc"] = (NOW + timedelta(minutes=1)).isoformat()
    elif mutation == "same_day":
        a["fields"]["race_date"] = "2026-11-23"
    elif mutation == "granted_bet":
        a["bet_authority"] = True
    elif mutation == "granted_pit":
        a["pit_certified"] = True
    elif mutation == "no_source":
        a["source_uri"] = ""
    with pytest.raises(ValueError, match=error):
        aggregate_official_history(rows, horse_id=12345, cutoff_utc=CUTOFF)


def test_all_missing_flags_produce_unknown_not_zero():
    a = fake_original(10, placing="MISSING", gallop="MISSING")
    res = aggregate_official_history([a], horse_id=12345, cutoff_utc=CUTOFF)
    facts = res["features"]
    assert facts["observed_win_rate"]["status"] == "UNKNOWN"
    assert facts["observed_gallop_rate"]["denominator"] == 0
    assert facts["observed_gallop_rate"]["value"] == "UNKNOWN"


def test_no_registry_pin_or_actual_identity_yields_no_history_features():
    p0, doc = sample()
    context = build_feature_context(p0, doc)
    res = bind_target_horse(
        p0, context, selection_id="1",
        cutoff_utc=CUTOFF, identities=(),
    )
    assert res["identity_status"] == "IDENTITY_UNRESOLVED"
    assert res["historical_results_verified"] == 0
    assert res["features"] == {}
    assert res["pit_status"] == PIT_UNPROVEN
    assert res["model_eligible"] is False
    assert res["bet_authorized"] is False


def test_wrong_start_snapshot_cutoff_and_mismatched_context_rejected():
    p0, doc = sample()
    context = build_feature_context(p0, doc)
    with pytest.raises(ValueError, match="SOURCE_OR_CUTOFF"):
        bind_target_horse(p0, context, selection_id="1",
                          cutoff_utc="2026-11-23T11:20:00+00:00")
    modified = deepcopy(context)
    modified["source_race_pack_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="DRAFT_SOURCE_CONTEXT"):
        bind_target_horse(p0, modified, selection_id="1", cutoff_utc=CUTOFF)


def test_scratched_horse_no_history_and_no_bet():
    p0, doc = sample()
    context = build_feature_context(p0, doc)
    res = bind_target_horse(p0, context, selection_id="2", cutoff_utc=CUTOFF)
    assert res["identity_status"] == "SCRATCHED_EXCLUDED"
    assert res["bet_authorized"] is False


def test_real_seven_official_dnt_originals_replayed_only_as_retrospective():
    """Real repo originals: stable DNT chain, but NO pre-cutoff PIT or Nov23 join."""
    result = run_authentic_research(Path(__file__).resolve().parents[1])
    assert result["source_observations"] == 7
    assert result["historical_date_years"] == ["2026"]
    assert result["retrospective_qualified_horses"] >= 1
    assert all(
        r["horse_identity"].startswith("DNT_REGISTRATION:")
        and r["pit_verified"] is False and r["asof_verified"] is False
        and r["model_eligible"] is False
        for r in result["materialized"]
    )
    assert not result["bet_authority"]
    assert result["model_eligible_races"] == 0


def test_unknown_feature_cannot_be_made_a_verified_zero():
    with pytest.raises(ValueError):
        feature(0, status="SILENTLY_VERIFIED")
    assert feature()["value"] == "UNKNOWN"
    assert feature()["denominator"] == 0
    assert DAY_SCHEMA.endswith("COVERAGE_V1")
