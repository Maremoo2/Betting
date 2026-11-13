"""Synthetic admission contracts. Archived source acceptance is exercised separately."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps
from pathlib import Path

import pytest

from hbi import admission_originals
from hbi.cloud_run003_model import IndependentScratchEvidence, assess_and_run
from hbi.horse_identity import AttestedHorseIdentity, ModelIdentityEvidence
from hbi.provider_capability import CONTRACT
from hbi.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
RACE = "RIKSTOTO:S1_NR_2026-11-12:1"
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
CAPTURE = NOW - timedelta(minutes=1)
START = NOW + timedelta(minutes=5)
SOURCE = [{"race_id": RACE, "source_ready": True}]


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "isolated.sqlite")
    store.initialize(ROOT / "db/schema.sql")
    store.apply_migrations(ROOT / "db/migrations")
    with store.connect() as db:
        db.execute(
            "INSERT INTO races (race_id,race_date,country,track,race_no,start_time_utc,discipline,created_at_utc)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (RACE, "2026-11-12", "SE", "Örebro", 1, START.isoformat(), "trot", CAPTURE.isoformat()),
        )
        db.executemany("INSERT INTO runners (race_id,selection_id,horse_name,scratched) VALUES (?,?,?,?)", [
            (RACE, "1", "Same Name", 0), (RACE, "2", "Same Name", 0), (RACE, "3", "Scratched", 1),
        ])
        payload = {
            "provider": "atg", "country": "SE", "discipline": "trot", "passed": True,
            "observed_at_utc": CAPTURE.isoformat(), "race_start_utc": START.isoformat(),
            "active_selections": ["1", "2"],
        }
        db.execute(
            "INSERT INTO provider_payloads (payload_id,provider,category,provider_raceday_key,"
            "observed_at_utc,source_uri,payload_json) VALUES (?,?,?,?,?,?,?)",
            ("test-only", "ATG", CONTRACT, RACE, CAPTURE.isoformat(), "https://atg.se/test", dumps(payload)),
        )
    proofs = []
    pins = set()
    atg_uri = "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_test"
    history = dumps({"id": "test", "status": "upcoming", "starts": [
        {"number": i, "horse": {"id": i, "age": 5, "sex": "mare", "trainer": {"lastName": "Test"},
         "statistics": {"life": {"starts": 20, "placement": {"1": i, "2": 0, "3": 0}, "earnings": 0},
                        "years": {"2026": {"starts": 0, "earnings": 0}}}}}
        for i in (1, 2)
    ]}).encode()
    history_hash = sha256(history).hexdigest()
    pins.add(("ATG_HISTORY", atg_uri, history_hash, CAPTURE))
    for i in (1, 2, 3):
        selection = str(i)
        store.insert_runner_fundamental_snapshot({
            "snapshot_id": selection, "race_id": RACE, "selection_id": selection,
            "observed_at_utc": CAPTURE.isoformat(), "feature_as_of_utc": CAPTURE.isoformat(),
            "source_uri": atg_uri, "scratched": int(i == 3),
            "history_total_starts": 20, "history_total_wins": i,
            "data_quality": "FULL_FIELD_HISTORY_ATG", "full_field_history_complete": 1,
            "raw_json": dumps({
                "atg_market_free": {"horseId": i, "lifeStarts": 20, "lifeWins": i},
                "permanent_horse_identity": {"status": "ATTESTED", "horse_id": str(i),
                                             "source": "TEST_ONLY", "source_version": "1"},
            }),
        })
        if i != 3:
            registry = dumps({
                "schema": "VERIFIED_REGISTRY_BINDING_V1", "race_id": RACE, "selection_id": selection,
                "horse_id": f"TEST_REGISTRY:{i}", "source": "TEST_ONLY", "source_version": "1",
                "atg_horse_id": i, "snapshot_id": selection, "history_original_sha256": history_hash,
                "atg_race_id": "test",
            }).encode()
            registry_hash = sha256(registry).hexdigest()
            pins.add(("REGISTRY_BINDING", "https://registry.example/test", registry_hash, CAPTURE))
            proofs.append(ModelIdentityEvidence(
                AttestedHorseIdentity(RACE, selection, f"TEST_REGISTRY:{i}", "TEST_ONLY", "1"),
                CAPTURE, "https://registry.example/test", registry_hash, i, selection,
                atg_uri, history_hash, CAPTURE, registry, history,
            ))
    roster = (("1", False), ("2", False), ("3", True))
    scratch_original = dumps({"schema": "VERIFIED_INDEPENDENT_SCRATCH_V1", "race_id": RACE,
                              "roster": roster}).encode()
    scratches = IndependentScratchEvidence(
        RACE, roster, CAPTURE, sha256(scratch_original).hexdigest(),
        "https://registry.example/startlist", scratch_original,
    )
    pins.add(("INDEPENDENT_SCRATCH", scratches.original_uri, scratches.original_sha256, CAPTURE))
    monkeypatch.setattr(admission_originals, "_REVIEWED_RECEIPTS", frozenset(pins))
    return store, tuple(proofs), scratches


def test_complete_active_cohort_uses_frozen_champion(cohort):
    store, proofs, scratches = cohort
    result = assess_and_run(store, SOURCE, now=NOW, identity_evidence=proofs, scratch_evidence=(scratches,))
    record = result["records"][0]
    assert record["reasons"] == []
    assert result["p_win_computed"] == 1
    assert set(record["p_win"]) == {"1", "2"}
    assert sum(record["p_win"].values()) == pytest.approx(1)
    assert record["identity_sources"]["1"][0]["history_original_sha256"] == proofs[0].history_original_sha256
    assert not record["pit_certified"] and not record["bet_ready"]
    assert store.fetch_table("shadow_tickets") == []


@pytest.mark.parametrize(("fault", "reason"), [
    ("missing_identity", "IDENTITY_UNRESOLVED"),
    ("conflict", "HORSE_IDENTITY_SOURCE_CONFLICT"),
    ("duplicate", "REGISTRY_BINDING_MISMATCH"),
    ("wrong_history_horse", "HISTORY_HORSE_IDENTITY_MISMATCH"),
    ("late_history", "IDENTITY_UNRESOLVED"),
    ("missing_history", "VALIDATED_LIFETIME_WIN_HISTORY_MISSING"),
    ("missing_runner", "FULL_FIELD_FUNDAMENTAL_COHORT_MISSING"),
    ("changed_scratch", "INDEPENDENT_SCRATCH_CORROBORATION_NOT_ATTESTED"),
    ("same_source", "INDEPENDENT_SCRATCH_CORROBORATION_NOT_ATTESTED"),
])
def test_unqualified_evidence_remains_blocked(cohort, fault, reason):
    store, proofs, scratches = cohort
    match fault:
        case "missing_identity":
            proofs = ()
        case "conflict":
            proofs += (replace(proofs[0], identity=replace(proofs[0].identity, horse_id="CONFLICT")),)
        case "duplicate":
            proofs = (proofs[0], replace(proofs[1], identity=replace(
                proofs[1].identity, horse_id=proofs[0].identity.horse_id,
            )))
        case "wrong_history_horse":
            proofs = (replace(proofs[0], atg_horse_id=2), proofs[1])
        case "late_history":
            proofs = (replace(proofs[0], history_completed_at=START), proofs[1])
        case "missing_history":
            with store.connect() as db:
                db.execute("UPDATE runner_fundamental_snapshots SET history_total_wins=NULL WHERE snapshot_id='1'")
        case "missing_runner":
            with store.connect() as db:
                db.execute("DELETE FROM runner_fundamental_snapshots WHERE snapshot_id='1'")
        case "changed_scratch":
            scratches = replace(scratches, roster=(("1", False), ("2", True), ("3", True)))
        case "same_source":
            scratches = replace(scratches, original_uri="https://www.rikstoto.no/api/scratched")
    result = assess_and_run(store, SOURCE, now=NOW, identity_evidence=proofs, scratch_evidence=(scratches,))
    assert reason in result["records"][0]["reasons"]
    assert result["p_win_computed"] == 0
    assert store.fetch_table("predictions") == []


@pytest.mark.parametrize("role", ["registry", "history", "scratch"])
@pytest.mark.parametrize("fault", ["missing", "fabricated", "wrong_source", "wrong_hash", "shifted", "late"])
def test_originals_require_reviewed_source_bytes_and_capture_clock(cohort, role, fault):
    store, proofs, scratches = cohort
    item = scratches if role == "scratch" else proofs[0]
    original, uri, digest, stamp = (
        ("history_original", "history_original_uri", "history_original_sha256", "history_completed_at")
        if role == "history" else ("original", "original_uri", "original_sha256", "observed_at")
    )
    fabricated = b'{"status":"ATTESTED"}'
    changes = {
        "missing": {original: None},
        "fabricated": {original: fabricated, digest: sha256(fabricated).hexdigest()},
        "wrong_source": {uri: "https://unreviewed.example/source"},
        "wrong_hash": {digest: "0" * 64},
        "shifted": {stamp: CAPTURE + timedelta(seconds=1)},
        "late": {stamp: START},
    }[fault]
    item = replace(item, **changes)
    if role == "scratch":
        scratches = item
    else:
        proofs = (item, proofs[1])
    result = assess_and_run(store, SOURCE, now=NOW, identity_evidence=proofs, scratch_evidence=(scratches,))
    reason = "INDEPENDENT_SCRATCH_CORROBORATION_NOT_ATTESTED" if role == "scratch" else "IDENTITY_UNRESOLVED"
    assert reason in result["records"][0]["reasons"]
    assert result["p_win_computed"] == 0
    assert store.fetch_table("predictions") == []
