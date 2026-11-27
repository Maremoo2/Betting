"""Offline candidate tests; simulated rechecks never certify a real freeze."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from test_phase_a_contract import PHYSICAL, RUN, adapt, envelope_fixture, packet_fixture

from hbi.phase_a_contract import digest, stamp
from hbi.phase_a_finalizer import TestRechecks, evaluate_test_candidate

NOW = stamp("2026-11-25T08:15:00Z")


def evidence(packet, now=NOW):
    return TestRechecks(
        packet_sha256=digest(packet), latest_collector_run_id=RUN,
        roster_sha256=adapt(packet)["roster_sha256"],
        roster_checked_at=now, archive_checked_at=now, ledger_checked_at=now,
        completed_physical_race_ids=frozenset(),
    )


def run(packet, envelope, rechecks=None, now=NOW):
    return evaluate_test_candidate(
        packet, envelope, expected_packet_sha256=digest(packet),
        rechecks=evidence(packet, now) if rechecks is None else rechecks,
        reference_time=now,
    )


def test_threshold_and_authority_separation():
    p = packet_fixture()
    e = envelope_fixture(p)
    result = run(p, e)
    assert result["total_preview"] == 70
    assert result["classification_preview"] == "A_WATCH"
    assert result["execution_mode"] == "OFFLINE_REPLAY_ONLY"
    for key in ("sports_quality_verified", "live_rechecks_verified", "phase_a_completed",
                "production_freeze", "persist_authorized", "bet_authority"):
        assert result[key] is False
    assert "frozen_at" not in result
    assert run(p, e) == result
    assert result["draft_sha256"] == digest(e)


@pytest.mark.parametrize("scores", [
    [19, 15, 20, 8, 7],  # 69
    [14, 20, 30, 15, 10],  # data gate
    [25, 9, 30, 15, 10],  # shape gate
    [25, 20, 17, 15, 10],  # mispricing gate
    [25, 20, 30, 7, 10],  # liquidity gate
])
def test_total_and_component_gates(scores):
    p = packet_fixture()
    e = envelope_fixture(p)
    e["draft"]["champion_provisional"] = dict(
        zip(e["draft"]["champion_provisional"], scores)
    )
    assert run(p, e)["classification_preview"] == "BELOW_THRESHOLD"


@pytest.mark.parametrize("now", [
    stamp("2026-11-25T08:23:00.125Z"),  # cutoff is exclusive
    stamp("2026-11-25T08:23:00.126Z"),
    stamp("2026-11-25T18:01:00Z"),  # at scheduled start
    stamp("2026-11-25T08:02:59Z"),  # before packet reference
])
def test_time_rejections(now):
    p = packet_fixture()
    with pytest.raises(ValueError, match="PRESTART_OR_FRESHNESS"):
        run(p, envelope_fixture(p), now=now)


def test_subsecond_before_cutoff_is_not_rounded():
    p = packet_fixture()
    now = stamp("2026-11-25T08:23:00.124Z")
    assert run(p, envelope_fixture(p), now=now)["status"] == "TEST_CANDIDATE_VALIDATED"


@pytest.mark.parametrize("change", [
    {"latest_collector_run_id": "NEWER"},
    {"roster_sha256": "changed"},
    {"packet_sha256": "changed"},
    {"roster_checked_at": NOW - timedelta(seconds=30, microseconds=1)},
    {"archive_checked_at": NOW + timedelta(microseconds=1)},
    {"ledger_checked_at": NOW - timedelta(seconds=31)},
    {"completed_physical_race_ids": frozenset({PHYSICAL})},
    {"completed_physical_race_ids": None},
])
def test_changed_or_stale_recheck_blocks(change):
    p = packet_fixture()
    with pytest.raises(ValueError):
        run(p, envelope_fixture(p), rechecks=replace(evidence(p), **change))


def test_naive_clock_blocks():
    p = packet_fixture()
    with pytest.raises(ValueError, match="NAIVE_TEST_CLOCK"):
        run(p, envelope_fixture(p), rechecks=evidence(p), now=NOW.replace(tzinfo=None))


def test_live_diagnostic_packet_still_has_no_authority():
    p = packet_fixture()
    p["replay_only"] = False
    p["generated_at_utc"] = p["reference_utc"]
    p["diagnostic_status"] = "LIVE_LEDGER_SOURCE_DIAGNOSTIC"
    result = run(p, envelope_fixture(p))
    assert result["execution_mode"] == "OFFLINE_REPLAY_ONLY"
    assert result["production_freeze"] is False
    assert result["persist_authorized"] is False
