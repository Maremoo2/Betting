"""PREWATCH-004: source-pack contract regression (all unit inputs synthetic)."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hbi.cloud_run002_import import SourceRace
from hbi.ingestion import RaceCard
from hbi.prewatch004_pack import (
    DRAFT_SCHEMA,
    SCHEMA,
    _snapshot_diff,
    _write_once,
    build_race_pack,
    validate_phase_a_draft,
)

MID = "S1_NR_2026-11-23"
RID = f"RIKSTOTO:{MID}:1"
OBS = datetime(2026, 11, 23, 8, 52, tzinfo=UTC)
SHA = "a" * 64


def fixture():
    card = RaceCard(
        race={
            "race_id": RID, "race_date": "2026-11-23",
            "country": "SE", "track": "Romme", "race_no": 1,
            "start_time_utc": "2026-11-23T11:20:00+00:00",
            "distance_m": 2140, "start_method": "VOLT",
        },
        runners=(
            {"selection_id": "1", "horse_name": "Kvikke Åsa", "scratched": 0,
             "post_position": 1, "driver_or_jockey": "Driver A"},
            {"selection_id": "2", "horse_name": "Traver B", "scratched": 1,
             "post_position": 2, "driver_or_jockey": "Driver B"},
            {"selection_id": "3", "horse_name": "Debutant C", "scratched": 0,
             "post_position": 3, "driver_or_jockey": "Driver C"},
        ),
    )
    item = SourceRace(
        card=card, meeting_id=MID, race_no=1, received_at=OBS,
        source_uri="https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/" + MID,
        payload={
            "race_id": RID, "source_ready_snapshot": True,
            "archive_sha256": SHA, "manifest_sha256": SHA,
            "starts_original_sha256": SHA, "program_pdf_original_sha256": SHA,
            "structured_program_sha256": SHA,
        },
    )
    doc = {
        "race": {"meeting_id": MID, "race_number": 1},
        "entrants": [
            {"program_number": 1, "name": "Kvikke Åsa",
             "past_starts": [{"date": "2026-11-10", "raw_text": "10.11.26 | 2140 3g"}]},
            {"program_number": 2, "name": "Traver B", "past_starts": []},
            {"program_number": 3, "name": "Debutant C", "past_starts": []},
        ],
    }
    return {"run_id": "20261123T085111520347Z", "date_oslo": "2026-11-23"}, item, doc


def test_exact_roster_scratches_and_uncertain_history():
    rec, item, doc = fixture()
    out = build_race_pack(rec, item, doc)
    assert out["schema"] == SCHEMA
    assert out["listed_count"] == 3
    assert out["active_count"] == 2
    assert out["scratched_numbers"] == ["2"]
    assert [r["selection_id"] for r in out["runners"]] == ["1", "2", "3"]
    prior = out["runners"][0]["source_history"][0]
    assert prior["date_candidate"] == "2026-11-10"
    assert prior["result"] == "UNKNOWN"
    assert prior["gallop"] == "UNKNOWN"
    assert not prior["official_result_verified"]
    assert out["runners"][0]["conservative_form"]["source_history_rows"] == 1
    assert out["runners"][0]["conservative_form"]["verified_gallop_rate"] == "UNKNOWN"
    assert out["runners"][2]["conservative_form"]["last_5_verified_form"] == "UNKNOWN"
    assert out["source"]["official_driver_changes_verified_by_this_stage"] is False
    assert out["phase_a_status"] == "NOT_RUN"
    assert out["bet_authorized"] is False
    assert "win_odds" not in json.dumps(out).lower()


def test_does_not_treat_unverified_negative_history_as_no_gallop():
    rec, item, doc = fixture()
    doc["entrants"][0]["past_starts"][0]["raw_text"] = "1st in gallop? raw 2ga"
    out = build_race_pack(rec, item, doc)
    assert out["runners"][0]["source_history"][0]["gallop"] == "UNKNOWN"
    assert out["runners"][0]["conservative_form"]["officially_verified_result_rows"] == 0


@pytest.mark.parametrize("change", [
    "duplicate", "missing", "name", "race_id", "unverified",
])
def test_hard_fail_on_roster_or_source_conflict(change):
    rec, item, doc = fixture()
    if change == "duplicate":
        doc["entrants"].append(dict(doc["entrants"][0]))
    elif change == "missing":
        doc["entrants"].pop()
    elif change == "name":
        doc["entrants"][0]["name"] = "Other Horse"
    elif change == "race_id":
        doc["race"]["race_number"] = 9
    elif change == "unverified":
        item = replace(item, payload={**item.payload, "source_ready_snapshot": False})
    with pytest.raises(ValueError):
        build_race_pack(rec, item, doc)


def test_snapshot_diff_is_descriptive_and_monotonic():
    rec, item, doc = fixture()
    previous = build_race_pack(rec, item, doc)
    next_item = replace(
        item, received_at=datetime(2026, 11, 23, 9, 52, tzinfo=UTC),
        card=replace(item.card, runners=(
            item.card.runners[0],
            {**item.card.runners[1], "scratched": 0, "driver_or_jockey": "New Driver"},
            item.card.runners[2],
        )),
    )
    newer = build_race_pack(rec, next_item, doc, previous=previous)
    assert newer["snapshot_diff"]["status"] == "CHANGED"
    assert {d["field"] for d in newer["snapshot_diff"]["changes"]} == {
        "scratched", "driver",
    }
    with pytest.raises(ValueError, match="NONMONOTONIC"):
        _snapshot_diff(newer, previous)


def _draft(pack):
    return {
        "schema": DRAFT_SCHEMA, "status": "DRAFT",
        "race_id": pack["race_id"], "source_run_id": pack["source"]["run_id"],
        "runners": [
            {"selection_id": r["selection_id"], "assessment": "Observed raw form; uncertain",
             "strengths": "Potential pace", "weaknesses": "Unproven",
             "evidence": "PDF line source"}
            for r in pack["runners"] if not r["scratched"]
        ],
        "race_shape": "Possible pace from inside", "candidate": "#1 Kvikke Åsa",
        "counterargument": "Unverified pace", "uncertainty": "Raw history only",
        "champion_provisional": {
            "data_25": 10, "shape_20": 8, "mispricing_30": 6,
            "liquidity_15": 1, "today_fit_10": 4,
        },
        "champion_evidence": {
            "data_25": "Snapshot complete, semantic history unknown",
            "shape_20": "Potential inside pace from start positions",
            "mispricing_30": "Unconfirmed hypothesis from source-only evidence",
            "liquidity_15": "No observed pool; preliminary only",
            "today_fit_10": "Distance and start method observed",
        },
    }


def test_draft_requires_all_active_runners_and_keeps_draft_status():
    rec, item, doc = fixture()
    pack = build_race_pack(rec, item, doc)
    draft = _draft(pack)
    validate_phase_a_draft(draft, pack)
    bad = {**draft, "runners": draft["runners"][:1]}
    with pytest.raises(ValueError, match="FULL_FIELD"):
        validate_phase_a_draft(bad, pack)
    bad = {**draft, "runners": [*draft["runners"], draft["runners"][0]]}
    with pytest.raises(ValueError):
        validate_phase_a_draft(bad, pack)
    with pytest.raises(ValueError, match="STATUS"):
        validate_phase_a_draft({**draft, "status": "FULLY_ASSESSED"}, pack)
    with pytest.raises(ValueError, match="FORBIDDEN"):
        validate_phase_a_draft({**draft, "frozen_at": "2026-11-23T09:01:00Z"}, pack)
    with pytest.raises(ValueError, match="SCORE_EVIDENCE_MISSING"):
        validate_phase_a_draft({**draft, "champion_evidence": {}}, pack)
    with pytest.raises(ValueError, match="RUNNER_FORBIDDEN"):
        validate_phase_a_draft(
            {**draft, "runners": [
                {**draft["runners"][0], "win_odds": 2.0},
                draft["runners"][1],
            ]}, pack,
        )


def test_draft_rejects_market_and_invalid_champion_scores():
    rec, item, doc = fixture()
    pack = build_race_pack(rec, item, doc)
    draft = _draft(pack)
    with pytest.raises(ValueError, match="FORBIDDEN"):
        validate_phase_a_draft({**draft, "win_odds": 2.1}, pack)
    bad = {**draft, "champion_provisional": {**draft["champion_provisional"],
                                           "mispricing_30": 31}}
    with pytest.raises(ValueError, match="SCORE_BOUNDS"):
        validate_phase_a_draft(bad, pack)
    with pytest.raises(ValueError, match="SCORE_BOUNDS"):
        validate_phase_a_draft({**draft, "champion_provisional": {
            **draft["champion_provisional"], "data_25": True}}, pack)


def test_immutable_writes_exact_readback(tmp_path: Path):
    target = tmp_path / "a.json"
    _write_once(target, b"one")
    _write_once(target, b"one")
    with pytest.raises(ValueError, match="CONFLICT"):
        _write_once(target, b"two")
    assert target.read_bytes() == b"one"


def test_previous_pack_cannot_be_different_race():
    rec, item, doc = fixture()
    pack = build_race_pack(rec, item, doc)
    with pytest.raises(ValueError, match="IDENTITY"):
        _snapshot_diff({**pack, "race_id": "RIKSTOTO:OTHER:1"}, pack)
