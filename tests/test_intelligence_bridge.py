from datetime import UTC, datetime
from pathlib import Path

from hbi.intelligence_bridge import ingest_intelligence_rows, validate_intelligence_row
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    store.upsert_race(
        {
            "race_id": "r1",
            "race_date": "2026-09-29",
            "country": "SE",
            "track": "Visby",
            "race_no": 4,
            "start_time_utc": "2026-09-29T18:00:00+00:00",
            "discipline": "trot",
            "distance_m": 2140,
            "start_method": "auto",
            "race_class": None,
            "created_at_utc": "2026-09-29T08:00:00+00:00",
        }
    )
    for selection in ("1", "2"):
        store.upsert_runner(
            {
                "race_id": "r1",
                "selection_id": selection,
                "horse_name": f"Horse {selection}",
                "post_position": int(selection),
                "driver_or_jockey": None,
                "trainer": None,
                "scratched": 0,
            }
        )
    store.upsert_provider_race_ref(
        provider="rikstoto",
        provider_raceday_key="VI_NR_2026-09-29",
        race_number=4,
        race_id="r1",
        provider_track_code="VI",
        provider_start_time_raw="2026-09-29T20:00:00",
        discovered_at=datetime(2026, 9, 29, 8, 0, tzinfo=UTC),
    )
    return store


def _valid_row():
    return {
        "inbox_id": "intel-inbox-1",
        "observed_at_utc": "2026-09-29T17:15:00+00:00",
        "provider": "rikstoto",
        "provider_raceday_key": "VI_NR_2026-09-29",
        "race_number": "4",
        "race_id": "",
        "selection_id": "1",
        "event_type": "EQUIPMENT_CHANGE",
        "claim_text": "Official source reports a material equipment change.",
        "source_uri": "https://example.test/race/4",
        "source_type": "OFFICIAL",
        "source_timestamp_utc": "2026-09-29T17:10:00+00:00",
        "source_time_basis": "PUBLISHED",
        "confidence": "0.95",
        "materiality": "HIGH",
        "evidence_status": "VERIFIED",
        "prewatch_score": "78",
        "policy_version": "V3.2-PW-1",
        "extractor": "chatgpt-prewatch",
        "notes_json": '{"why":"late equipment change"}',
    }


def test_valid_intelligence_is_resolved_and_research_only(tmp_path):
    store = _store(tmp_path)
    valid = validate_intelligence_row(store, _valid_row())

    assert valid.race_id == "r1"
    assert valid.selection_id == "1"
    assert valid.pit_eligible is True

    summary = ingest_intelligence_rows(
        store,
        [_valid_row()],
        source_sheet="HBI_EVIDENCE_INBOX",
        imported_at=datetime(2026, 9, 29, 17, 20, tzinfo=UTC),
    )

    assert summary.accepted == 1
    assert summary.pit_eligible == 1
    evidence = store.fetch_table("intelligence_evidence")
    assert len(evidence) == 1
    assert evidence[0]["research_only"] == 1
    assert evidence[0]["production_feature_eligible"] == 0
    assert evidence[0]["prewatch_score"] == 78.0


def test_bridge_is_idempotent_on_inbox_id(tmp_path):
    store = _store(tmp_path)
    first = ingest_intelligence_rows(
        store,
        [_valid_row()],
        source_sheet="HBI_EVIDENCE_INBOX",
    )
    second = ingest_intelligence_rows(
        store,
        [_valid_row()],
        source_sheet="HBI_EVIDENCE_INBOX",
    )

    assert first.accepted == 1
    assert second.accepted == 0
    assert second.duplicates == 1
    assert store.count("intelligence_evidence") == 1
    assert store.count("intelligence_bridge_imports") == 1


def test_bridge_rejects_canonical_market_or_decision_writes(tmp_path):
    store = _store(tmp_path)
    row = _valid_row()
    row["inbox_id"] = "bad-market"
    row["event_type"] = "MARKET_SNAPSHOT"

    summary = ingest_intelligence_rows(
        store,
        [row],
        source_sheet="HBI_EVIDENCE_INBOX",
    )

    assert summary.rejected == 1
    assert store.count("intelligence_evidence") == 0
    audit = store.fetch_table("intelligence_bridge_imports")[0]
    assert audit["status"] == "REJECTED"
    assert "CANONICAL_EVENT_FORBIDDEN" in audit["reason"]
    assert store.count("provider_market_snapshots") == 0
    assert store.count("predictions") == 0
    assert store.count("decisions") == 0


def test_bridge_rejects_unknown_runner_in_known_race(tmp_path):
    store = _store(tmp_path)
    row = _valid_row()
    row["inbox_id"] = "bad-runner"
    row["selection_id"] = "99"

    summary = ingest_intelligence_rows(
        store,
        [row],
        source_sheet="HBI_EVIDENCE_INBOX",
    )

    assert summary.rejected == 1
    assert "UNKNOWN_SELECTION_ID" in store.fetch_table(
        "intelligence_bridge_imports"
    )[0]["reason"]


def test_post_start_or_unknown_source_time_is_not_pit_eligible(tmp_path):
    store = _store(tmp_path)
    row = _valid_row()
    row["inbox_id"] = "post-start"
    row["observed_at_utc"] = "2026-09-29T18:01:00+00:00"

    summary = ingest_intelligence_rows(
        store,
        [row],
        source_sheet="HBI_EVIDENCE_INBOX",
    )

    assert summary.accepted == 1
    assert summary.pit_eligible == 0
    evidence = store.fetch_table("intelligence_evidence")[0]
    assert evidence["pit_eligible"] == 0
    assert evidence["production_feature_eligible"] == 0


def test_unverified_evidence_is_stored_but_not_pit_eligible(tmp_path):
    store = _store(tmp_path)
    row = _valid_row()
    row["inbox_id"] = "unverified"
    row["evidence_status"] = "UNVERIFIED"

    summary = ingest_intelligence_rows(
        store,
        [row],
        source_sheet="HBI_EVIDENCE_INBOX",
    )

    assert summary.accepted == 1
    assert summary.pit_eligible == 0
    assert store.fetch_table("intelligence_evidence")[0]["evidence_status"] == "UNVERIFIED"
