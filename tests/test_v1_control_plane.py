import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hbi.challenger import forward_clock, record_forward_event, register_challenger
from hbi.eligibility import evaluate_win_eligibility
from hbi.governance import load_governance, validate_governance
from hbi.manifest import build_run_manifest
from hbi.promotion import PromotionMetrics, assess_challenger_for_manual_review
from hbi.research_integrity import future_mutation_invariance, run_research_integrity_check
from hbi.storage import SQLiteStore
from hbi.v1_audit import run_v1_audit

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
GOVERNANCE = ROOT / "docs" / "research_governance.json"


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    return store


def _race(store, race_id="r1", start="2026-09-27T18:00:00+00:00"):
    store.upsert_race(
        {
            "race_id": race_id,
            "race_date": "2026-09-27",
            "country": "SE",
            "track": "Mantorp",
            "race_no": 1,
            "start_time_utc": start,
            "discipline": "trot",
            "distance_m": 2140,
            "start_method": "auto",
            "race_class": None,
            "created_at_utc": "2026-09-27T08:00:00+00:00",
        }
    )


def test_governance_is_machine_readable_and_safe():
    governance = load_governance(GOVERNANCE)
    result = validate_governance(governance)
    assert result.valid
    assert governance["auto_promotion_enabled"] is False
    assert governance["adaptive_switching_enabled"] is False
    assert governance["real_money_execution"] is False
    assert governance["manual_approval_required"] is True


def test_future_mutation_invariance_passes():
    report = future_mutation_invariance()
    assert report["status"] == "PASS"
    assert report["baseline"] == report["replay_after_future_mutation"]
    assert report["future_row_rejected"] is True


def test_temporal_integrity_catches_future_feature(tmp_path):
    store = _store(tmp_path)
    _race(store)
    created = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    with store.connect() as connection:
        connection.execute(
            "INSERT INTO predictions "
            "(prediction_id,race_id,selection_id,created_at_utc,model_name,"
            "model_version,layer,probability,feature_as_of_utc,frozen) "
            "VALUES (?,?,?,?,?,?,?,?,?,1)",
            (
                "bad",
                "r1",
                "1",
                created.isoformat(),
                "bad",
                "bad",
                "FUNDAMENTAL",
                0.5,
                (created + timedelta(minutes=1)).isoformat(),
            ),
        )
    report = run_research_integrity_check(store)
    assert report["status"] == "FAIL"
    assert any(
        item["reason"] == "feature_after_prediction"
        for item in report["database"]["problems"]
    )


def test_eligibility_gate_blocks_post_decision_market():
    decision = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    result = evaluate_win_eligibility(
        decision_time=decision,
        race_start_time=decision + timedelta(minutes=4),
        market_observed_at=decision + timedelta(seconds=1),
        fundamental_shadow_eligible=True,
        fundamental_selections={"1", "2"},
        market_selections={"1", "2"},
    )
    assert not result.allowed
    assert "MARKET_AFTER_DECISION" in result.reasons


def test_run_manifest_contains_reproducibility_hashes():
    started = datetime(2026, 9, 27, 17, 55, tzinfo=UTC)
    manifest = build_run_manifest(
        run_type="TEST",
        started_at=started,
        finished_at=started + timedelta(seconds=2),
        status="OK",
        model_version="FUNDAMENTAL_CHAMPION_V1_1",
        policy={"minimum_edge": 0.05},
        metadata={"race_id": "r1"},
        run_id="test-manifest",
    )
    assert len(str(manifest["critical_code_hash"])) == 64
    assert len(str(manifest["db_schema_hash"])) == 64
    assert len(str(manifest["governance_hash"])) == 64


def test_challenger_has_its_own_forward_clock(tmp_path):
    store = _store(tmp_path)
    _race(store)
    registered = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    challenger_id = register_challenger(
        store,
        model_name="test_model",
        model_version="CHALLENGER_V2",
        registered_at=registered,
        discovery_cutoff=registered,
        minimum_forward_races=2,
    )
    record_forward_event(
        store,
        challenger_id=challenger_id,
        race_id="r1",
        race_start=datetime(2026, 9, 27, 18, 0, tzinfo=UTC),
        evaluation_created_at=datetime(2026, 9, 27, 19, 0, tzinfo=UTC),
        eligible=True,
    )
    clock = forward_clock(store, challenger_id)
    assert clock.eligible_races == 1
    assert clock.status == "COLLECTING"


def test_promotion_never_bypasses_governance():
    governance = load_governance(GOVERNANCE)
    assessment = assess_challenger_for_manual_review(
        governance=governance,
        metrics=PromotionMetrics(
            forward_races=1000,
            champion_log_loss=1.0,
            challenger_log_loss=0.8,
            market_log_loss=0.9,
            champion_brier=0.5,
            challenger_brier=0.3,
            market_brier=0.4,
            replicated_across_required_slices=True,
        ),
    )
    assert assessment.status == "DO_NOT_PROMOTE"
    assert assessment.recommendation_only
    assert assessment.manual_approval_required
    assert not assessment.execution_authority


def test_empty_database_v1_audit_is_engineering_pass_with_evidence_pending(tmp_path):
    store = _store(tmp_path)
    report = run_v1_audit(
        store,
        now=datetime(2026, 9, 28, 0, 30, tzinfo=UTC),
    )
    assert report["engineering_status"] == "PASS_WITH_EVIDENCE_PENDING"
    assert report["temporal_integrity"]["status"] == "PASS"
    assert report["runtime_replay_parity"]["status"] == "NO_EVIDENCE"
