"""Synthetic Collector-contract fixtures: no live source or betting authority."""
from __future__ import annotations

import copy
import hashlib

import pytest

from hbi.phase_a_contract import DRAFT_ENVELOPE, adapt_ready_packet, digest, validate_envelope
from hbi.prewatch004_pack import DRAFT_SCHEMA, SCORE_BOUNDS

DAY = "2026-11-25"
RUN = "20261125T075221791585Z"
MID = "S2_NR_2026-11-25"
RID = f"RIKSTOTO:{MID}:1"
PHYSICAL = f"{DAY}|Solvalla|1"
SHA = "a" * 64


def packet_fixture():
    """Match Collector tests/test_prewatch_ready.py shape, not real observations."""
    roster_rows = [
        {"start_number": n, "horse_name": name, "is_scratched": n == 2,
         "driver_change_documented": n == 3, "effective_driver": "B" if n == 3 else "A",
         "original_official_driver": "A"}
        for n, name in [(1, "Kvikke Åsa"), (2, "Example Two"), (3, "Example Three")]
    ]
    entries = [
        {"program_number": r["start_number"], "name": r["horse_name"],
         "scratch_state": "SCRATCHED_AS_OF_SNAPSHOT" if r["is_scratched"]
         else "ACTIVE_AS_OF_SNAPSHOT",
         "past_starts": [] if r["is_scratched"] else [
             {"date": "2026-11-10", "raw_text": f"synthetic history {r['start_number']}"}]}
        for r in roster_rows
    ]
    receipts = [
        {"status": "SHA_VERIFIED_SOURCE_RECEIPT", "sha256": SHA,
         "url": "https://www.rikstoto.no" + url, "observed_utc": when}
        for url, when in [
            (f"/api/racedays/{MID}/starts", "2026-11-25T07:53:00.125Z"),
            (f"/api/game/program/{MID}/driverChanges", "2026-11-25T07:53:05Z"),
        ]
    ]
    meta = {
        "race_id": RID, "ledger_race_id": PHYSICAL,
        "scheduled_start_iso": "2026-11-25T19:01:00+01:00",
        "active_numbers": [1, 3], "scratch_numbers": [2], "history_rows": 2,
        "history_complete_five": False, "roster_age_seconds": 600,
        "latest_freeze_utc": "2026-11-25T08:23:00.125Z",
        "source_archive_release_id": 100, "meeting_release_id": 101,
        "meeting_release_tag": f"prewatch-src-{DAY}-{MID}-p1-{RUN}",
        "race_pack_sha256": SHA, "data_quality": "SOURCE_READY_AS_OF_CAPTURE",
    }
    source = {
        "schema": "prewatch_source_v1", "record_type": "PHASE_A_SOURCE_PROJECTION",
        "race_id": RID, "date_oslo": DAY, "source_run_id": RUN,
        "source_archive_tag": f"rikstoto-program-{DAY}-{RUN}",
        "phase_a_completed": False, "bet_authority": False, "source_receipts": [],
        "program": {"race": {"meeting_id": MID, "race_number": 1, "track": "Solvalla",
                             "scheduled_time_local": "19:01", "distance_m": 2140,
                             "start_method": "Autostart"}, "entrants": entries},
        "official_roster": {"status": "VERIFIED_AS_OF_SOURCE_CAPTURE",
                            "source_run_id": RUN, "first_blocker": None,
                            "starts_source": receipts[0], "driver_changes_source": receipts[1],
                            "runners": roster_rows,
                            "driver_changes": [{"start_number": 3, "new_driver": "B"}]},
    }
    return {
        "schema": "prewatch_ready_v1", "status": "SOURCE_READY", "date_oslo": DAY,
        "collector_run_id": RUN, "index_sha256": SHA, "replay_only": True,
        "reference_utc": "2026-11-25T08:03:00Z", "generated_at_utc": None,
        "min_analysis_window_seconds": 120, "queue": [copy.deepcopy(meta)], "blocked": [],
        "selected": {"metadata": meta, "source_pack": source},
        "ledger_exclusion": "NOT_CHECKED", "diagnostic_status": "REPLAY_ONLY",
        "phase_a_completed": False, "bet_authority": False,
        "operational_publication_allowed": False, "freeze_recheck_required": True,
    }


def envelope_fixture(packet):
    return {
        "schema": DRAFT_ENVELOPE, "packet_sha256": digest(packet),
        "sports_first": {"selection_id": "1", "horse_name": "Kvikke Åsa"},
        "mispricing_candidate": {
            "selection_id": "3", "horse_name": "Example Three",
            "hypothesis": "Synthetic scenario for testing only",
            "counterargument": "Synthetic opposing scenario",
        },
        "history_refs": {
            str(n): [hashlib.sha256(f"synthetic history {n}".encode()).hexdigest()]
            for n in (1, 3)
        },
        "draft": {
            "schema": DRAFT_SCHEMA, "status": "DRAFT",
            "race_id": RID, "source_run_id": RUN,
            "runners": [
                {"selection_id": str(n), "assessment": "Synthetic assessment",
                 "strengths": "Synthetic strength", "weaknesses": "Synthetic weakness",
                 "evidence": f"synthetic history {n}"} for n in (1, 3)
            ],
            "race_shape": "Synthetic shape", "candidate": "#3 Example Three",
            "counterargument": "Synthetic opposing scenario", "uncertainty": "Test only",
            "champion_provisional": dict(zip(SCORE_BOUNDS, [20, 15, 20, 8, 7])),
            "champion_evidence": {k: "Synthetic reason" for k in SCORE_BOUNDS},
        },
    }


def adapt(packet):
    return adapt_ready_packet(packet, expected_packet_sha256=digest(packet))


def test_adapter_and_existing_validator():
    packet = packet_fixture()
    adapted = adapt(packet)
    assert adapted["active_count"] == 2
    assert adapted["scratch_numbers"] == [2]
    assert adapted["physical_race_id"] == PHYSICAL
    assert adapted["deadline"].microsecond == 125000
    validate_envelope(envelope_fixture(packet), adapted)


def test_reject_packet_tampering():
    packet = packet_fixture()
    sha = digest(packet)
    packet["blocked"].append({"code": "changed"})
    with pytest.raises(ValueError, match="PACKET_HASH"):
        adapt_ready_packet(packet, expected_packet_sha256=sha)


@pytest.mark.parametrize("case", [
    "bet", "production", "duplicate_queue", "market", "duplicate_runner",
    "scratch_conflict", "driver_conflict", "missing_history", "future_history",
    "future_receipt", "wrong_deadline", "identity", "bad_receipt", "bad_number",
])
def test_packet_fail_closed(case):
    p = packet_fixture()
    meta, source = p["selected"]["metadata"], p["selected"]["source_pack"]
    roster, entries = source["official_roster"], source["program"]["entrants"]
    if case == "bet":
        p["bet_authority"] = True
    elif case == "production":
        p["operational_publication_allowed"] = True
    elif case == "duplicate_queue":
        p["queue"].append(copy.deepcopy(meta))
    elif case == "market":
        source["program"]["win_odds"] = []
    elif case == "duplicate_runner":
        entries.append(copy.deepcopy(entries[0]))
    elif case == "scratch_conflict":
        entries[0]["scratch_state"] = "SCRATCHED_AS_OF_SNAPSHOT"
    elif case == "driver_conflict":
        roster["runners"][2]["effective_driver"] = "C"
    elif case == "missing_history":
        entries[0]["past_starts"] = []
    elif case == "future_history":
        entries[0]["past_starts"][0]["date"] = DAY
    elif case == "future_receipt":
        roster["starts_source"]["observed_utc"] = "2026-11-25T08:04:00Z"
    elif case == "wrong_deadline":
        meta["latest_freeze_utc"] = "2026-11-25T08:24:00Z"
        p["queue"][0] = copy.deepcopy(meta)
    elif case == "identity":
        source["race_id"] = "RIKSTOTO:OTHER:1"
    elif case == "bad_receipt":
        roster["starts_source"]["sha256"] = "bad"
    elif case == "bad_number":
        entries[0]["program_number"] = True
    with pytest.raises(ValueError):
        adapt(p)


@pytest.mark.parametrize("case", [
    "wrong_hash", "missing_runner", "duplicate_runner", "scratched_candidate",
    "candidate_name", "mismatched_candidate", "counterargument", "score_missing",
    "bool_score", "score_overflow", "extra_odds", "wrong_history_hash",
    "cross_runner_history", "missing_ref", "extra_total", "freeze_claim",
])
def test_draft_fail_closed(case):
    p = packet_fixture()
    e = envelope_fixture(p)
    d = e["draft"]
    if case == "wrong_hash":
        e["packet_sha256"] = SHA
    elif case == "missing_runner":
        d["runners"].pop()
    elif case == "duplicate_runner":
        d["runners"][1] = copy.deepcopy(d["runners"][0])
    elif case == "scratched_candidate":
        e["mispricing_candidate"].update(selection_id="2", horse_name="Example Two")
    elif case == "candidate_name":
        e["sports_first"]["horse_name"] = "Wrong"
    elif case == "mismatched_candidate":
        d["candidate"] = "#1 Kvikke Åsa"
    elif case == "counterargument":
        d["counterargument"] = "Mismatch"
    elif case == "score_missing":
        del d["champion_provisional"]
        del d["champion_evidence"]
    elif case == "bool_score":
        d["champion_provisional"]["data_25"] = True
    elif case == "score_overflow":
        d["champion_provisional"]["shape_20"] = 21
    elif case == "extra_odds":
        d["win_odds"] = 2.0
    elif case == "wrong_history_hash":
        e["history_refs"]["1"] = [SHA]
    elif case == "cross_runner_history":
        e["history_refs"]["1"] = e["history_refs"]["3"]
    elif case == "missing_ref":
        del e["history_refs"]["1"]
    elif case == "extra_total":
        d["total"] = 70
    elif case == "freeze_claim":
        d["frozen_at"] = "2026-11-25T08:15:00Z"
    with pytest.raises(ValueError):
        validate_envelope(e, adapt(p))
