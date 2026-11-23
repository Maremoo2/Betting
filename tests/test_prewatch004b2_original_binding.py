"""PREWATCH-004B2: TEST_ONLY synthetic numeric cases + genuine 2026 research replay.

No synthetic positive test is evidence of a real accepted PIT or permanent ID.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_prewatch004b_features import sample

from hbi import admission_originals
from hbi.historical_intelligence_v2 import SCHEMA as HISTORIC_SCHEMA
from hbi.horse_identity import AttestedHorseIdentity, ModelIdentityEvidence
from hbi.mvp023b_performance_features import run_authentic_research
from hbi.prewatch004b2_original_binding import (
    DAY_SCHEMA,
    PIT_UNPROVEN,
    aggregate_official_history,
    bind_target_horse,
    feature,
)
from hbi.prewatch004b_features import build_feature_context
from hbi.providers.atg import AtgClient

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
        "dynamic_horse_statistics_ignored": True,
        "provider_publication_attested": published is not None,
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
    assert a["features"]["last_3_complete_results"]["value"] == "UNKNOWN"
    assert a["features"]["last_5_complete_results"]["value"] == "UNKNOWN"
    # A caller boolean cannot attest a complete history index.
    with pytest.raises(ValueError, match="HISTORY_INDEX_ATTESTATION"):
        aggregate_official_history(
            rows, horse_id=12345, cutoff_utc=CUTOFF,
            history_index_complete=True,
        )


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
        a["provider_publication_attested"] = True
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


def test_invalid_upstream_historical_result_provenance_is_rejected():
    row = fake_original(10, placing=1, gallop=False)
    row["original_sha256"] = "unverified"
    with pytest.raises(ValueError, match="UNATTESTED_UPSTREAM"):
        aggregate_official_history([row], horse_id=12345, cutoff_utc=CUTOFF)
    row = fake_original(10, placing=1, gallop=False)
    row["dynamic_horse_statistics_ignored"] = False
    with pytest.raises(ValueError, match="UNATTESTED_UPSTREAM"):
        aggregate_official_history([row], horse_id=12345, cutoff_utc=CUTOFF)


def test_only_independent_registry_and_original_result_positive_path(monkeypatch):
    """TEST_ONLY: do NOT count this synthetic registration or outcome as real PIT."""
    pack, doc = sample()
    context = build_feature_context(pack, doc)
    captured = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    provider_race_id = "2026-11-23_1_1"
    current_uri = f"{AtgClient.GAME_API}/vinnare_{provider_race_id}"
    current = {
        "id": f"vinnare_{provider_race_id}",
        "races": [{
            "id": provider_race_id, "sport": "trot", "status": "upcoming",
            "startTime": pack["race"]["start_time_utc"],
            "starts": [
                {"number": i, "horse": {
                    "id": i, "age": 5, "sex": "mare",
                    "trainer": {"lastName": "Synthetic"},
                    "statistics": {
                        "life": {
                            "starts": 20,
                            "placement": {"1": i, "2": 0, "3": 0},
                            "earnings": 0,
                        },
                        "years": {"2026": {"starts": 0, "earnings": 0}},
                    },
                }}
                for i in (1, 2)
            ],
        }],
    }
    current_bytes = json.dumps(current, sort_keys=True).encode()
    current_hash = hashlib.sha256(current_bytes).hexdigest()
    reg_url = "https://registry.example/TEST_ONLY_PREWATCH004B2"
    registry = {
        "schema": "VERIFIED_REGISTRY_BINDING_V1",
        "race_id": pack["race_id"], "selection_id": "1",
        "horse_id": "TEST_ONLY_REGISTRATION:1",
        "source": "TEST_ONLY", "source_version": "1",
        "atg_horse_id": 1, "snapshot_id": "1",
        "history_original_sha256": current_hash,
        "atg_race_id": provider_race_id,
    }
    registry_bytes = json.dumps(registry, sort_keys=True).encode()
    registry_hash = hashlib.sha256(registry_bytes).hexdigest()
    pins = frozenset({
        ("REGISTRY_BINDING", reg_url, registry_hash, captured),
        ("ATG_HISTORY", current_uri, current_hash, captured),
    })
    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", pins)
    identity = ModelIdentityEvidence(
        AttestedHorseIdentity(
            pack["race_id"], "1", "TEST_ONLY_REGISTRATION:1", "TEST_ONLY", "1",
        ), captured, reg_url, registry_hash, 1, "1",
        current_uri, current_hash, captured, registry_bytes, current_bytes,
    )
    previous = {
        "id": "2026-11-10_1_1",
        "date": "2026-11-10", "number": 1,
        "track": {"id": 1, "name": "Test Track", "countryCode": "SE"},
        "sport": "trot", "status": "results",
        "startTime": "2026-11-10T11:00:00+00:00",
        "distance": 2140, "startMethod": "AUTO",
        "starts": [
            {"number": 1, "horse": {"id": 1, "name": "Kvikke Åsa"},
             "result": {"place": 1, "galloped": False, "disqualified": False}},
            {"number": 2, "horse": {"id": 2, "name": "Other Horse"},
             "result": {"place": 2, "galloped": True, "disqualified": False}},
        ],
    }
    previous_original = json.dumps({"races": [previous]}, sort_keys=True).encode()
    previous_source = {
        "original": previous_original,
        "sha256": hashlib.sha256(previous_original).hexdigest(),
        "atg_race_id": "2026-11-10_1_1",
        "source_uri": f"{AtgClient.GAME_API}/vinnare_2026-11-10_1_1",
        "observed_at_utc": "2026-11-22T12:00:00+00:00",
        "published_at_utc": None,
    }
    kwargs = {
        "selection_id": "1", "cutoff_utc": CUTOFF,
        "current_atg": {"horseId": 1, "lifeStarts": 20, "lifeWins": 1},
        "identity_row": {"source_uri": current_uri, "snapshot_id": "1"},
        "identities": (identity,),
        "historical_originals": (previous_source,),
    }
    good = bind_target_horse(pack, context, **kwargs)
    assert good["identity_status"] == "ATTESTED_ORIGINAL_BINDING"
    assert good["permanent_horse_identity"] == "TEST_ONLY_REGISTRATION:1"
    assert good["historical_results_verified"] == 1
    assert good["features"]["observed_win_rate"]["value"] == 1.0
    assert good["features"]["observed_gallop_rate"]["value"] == 0.0
    assert good["features"]["last_3_complete_results"]["value"] == "UNKNOWN"
    assert good["pit_status"] == PIT_UNPROVEN
    assert good["model_eligible"] is False and good["bet_authorized"] is False

    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", frozenset())
    absent = bind_target_horse(pack, context, **kwargs)
    assert absent["identity_status"] == "IDENTITY_UNRESOLVED"
    assert absent["historical_results_verified"] == 0

    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", pins)
    tampered = {**previous_source, "sha256": "0" * 64}
    with pytest.raises(ValueError, match="HISTORIC_RAW_SHA_MISMATCH"):
        bind_target_horse(pack, context, **{**kwargs, "historical_originals": (tampered,)})
    late = {**previous_source, "published_at_utc": "2026-11-23T09:31:00+00:00"}
    with pytest.raises(ValueError, match="PAST_RESULT_NOT_AVAILABLE"):
        bind_target_horse(pack, context, **{**kwargs, "historical_originals": (late,)})


def test_verified_positive_placing_cannot_coexist_with_dq_or_dnf():
    row = fake_original(10, placing=1, gallop=True, dq=True)
    with pytest.raises(ValueError, match="PLACED_RESULT_CONTRADICTS_DQ_OR_DNF"):
        aggregate_official_history([row], horse_id=12345, cutoff_utc=CUTOFF)
    row = fake_original(10, placing=1, gallop=False, dq=False)
    row["fields"]["not_finished"] = True
    with pytest.raises(ValueError, match="PLACED_RESULT_CONTRADICTS_DQ_OR_DNF"):
        aggregate_official_history([row], horse_id=12345, cutoff_utc=CUTOFF)
