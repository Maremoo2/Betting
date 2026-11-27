"""CORE-STABILITY-006A offline Phase A classification/freeze-candidate validator.

No network, credentials, wall-clock override of a real freeze, or Ledger writes.
The caller supplies *test* observations. They are not live evidence. A future
authorized finalizer must acquire independent fresh evidence and a real clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from unicodedata import normalize

from .phase_a_contract import adapt_ready_packet, digest, require, validate_envelope
from .prewatch004_pack import SCORE_BOUNDS

# Existing V3.3.12 gates, not fitted thresholds or a probability model.
MINIMUM = {"data_25": 15, "shape_20": 10, "mispricing_30": 18, "liquidity_15": 8}
TOTAL_GATE = 70


@dataclass(frozen=True)
class TestRechecks:
    """Simulated, caller-provided observations; never a live certification."""

    __test__ = False
    packet_sha256: str
    latest_collector_run_id: str
    roster_sha256: str
    roster_checked_at: datetime
    archive_checked_at: datetime
    ledger_checked_at: datetime
    completed_physical_race_ids: frozenset[str]


def _utc(value: datetime) -> datetime:
    require(isinstance(value, datetime) and value.utcoffset() is not None,
            "006A_NAIVE_TEST_CLOCK")
    return value.astimezone(UTC)


def evaluate_test_candidate(
    packet: dict, envelope: dict, *, expected_packet_sha256: str,
    rechecks: TestRechecks, reference_time: datetime,
) -> dict[str, Any]:
    """Validate an offline candidate; never return a real freeze or A-WATCH signal.

    Replay reference_time is explicit so tests are deterministic. It must not
    be used as the production clock. All timestamps use unrounded comparisons.
    """
    require(isinstance(rechecks, TestRechecks), "006A_RECHECKS_MISSING")
    adapted = adapt_ready_packet(packet, expected_packet_sha256=expected_packet_sha256)
    validate_envelope(envelope, adapted)
    now = _utc(reference_time)
    require(adapted["reference"] <= now < adapted["deadline"]
            and now < adapted["start"]
            and timedelta(0) <= now - adapted["oldest_roster"] <= timedelta(minutes=30)
            and adapted["latest_roster"] <= now, "006A_PRESTART_OR_FRESHNESS_FAILED")
    require(rechecks.packet_sha256 == expected_packet_sha256
            and rechecks.latest_collector_run_id == adapted["source"]["run_id"]
            and rechecks.roster_sha256 == adapted["roster_sha256"],
            "006A_SOURCE_CHANGED")
    for checked in (rechecks.roster_checked_at, rechecks.archive_checked_at,
                    rechecks.ledger_checked_at):
        when = _utc(checked)
        require(adapted["reference"] <= when <= now
                and now - when <= timedelta(seconds=30), "006A_RECHECK_STALE_OR_FUTURE")
    require(isinstance(rechecks.completed_physical_race_ids, frozenset)
            and all(isinstance(x, str) and bool(x.strip())
                    for x in rechecks.completed_physical_race_ids),
            "006A_LEDGER_EVIDENCE_INVALID")
    completed = {normalize("NFC", race_id) for race_id in rechecks.completed_physical_race_ids}
    require(adapted["physical_race_id"] not in completed,
            "006A_ALREADY_COMPLETED")
    scores = envelope["draft"]["champion_provisional"]
    # Recompute; do not trust any model-supplied total or classification.
    require(set(scores) == set(SCORE_BOUNDS)
            and all(type(scores[k]) is int and 0 <= scores[k] <= cap
                    for k, cap in SCORE_BOUNDS.items()), "006A_SCORE_BOUNDS")
    total = sum(scores.values())
    gate = total >= TOTAL_GATE and all(scores[k] >= minimum for k, minimum in MINIMUM.items())
    return {
        "schema": "CORE_STABILITY_006A_TEST_CANDIDATE_V1",
        "status": "TEST_CANDIDATE_VALIDATED",
        "execution_mode": "OFFLINE_REPLAY_ONLY",
        "race_id": adapted["race_id"],
        "physical_race_id": adapted["physical_race_id"],
        "source_run_id": adapted["source"]["run_id"],
        "packet_sha256": expected_packet_sha256,
        "draft_sha256": digest(envelope),
        "evaluated_at_test_utc": now.isoformat(),
        "latest_freeze_utc": adapted["deadline"].isoformat(),
        "active_count": adapted["active_count"],
        "scores": dict(scores),
        "total_preview": total,
        "classification_preview": "A_WATCH" if gate else "BELOW_THRESHOLD",
        "sports_quality_verified": False,
        "live_rechecks_verified": False,
        "phase_a_completed": False,
        "production_freeze": False,
        "persist_authorized": False,
        "bet_authority": False,
    }
