from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from .storage import SQLiteStore


@dataclass(frozen=True)
class ForwardClock:
    challenger_id: str
    eligible_races: int
    minimum_races: int
    status: str
    forward_start_utc: str


def register_challenger(
    store: SQLiteStore,
    *,
    model_name: str,
    model_version: str,
    registered_at: datetime,
    discovery_cutoff: datetime,
    minimum_forward_races: int = 500,
    notes: str = "",
) -> str:
    if registered_at.tzinfo is None or registered_at.utcoffset() is None:
        raise ValueError("registered_at must be timezone-aware")
    if discovery_cutoff.tzinfo is None or discovery_cutoff.utcoffset() is None:
        raise ValueError("discovery_cutoff must be timezone-aware")
    if minimum_forward_races < 1:
        raise ValueError("minimum_forward_races must be >= 1")
    forward_start = max(registered_at, discovery_cutoff)
    challenger_id = sha256(
        f"{model_name}|{model_version}|{registered_at.isoformat()}".encode()
    ).hexdigest()
    store.upsert_challenger(
        {
            "challenger_id": challenger_id,
            "model_name": model_name,
            "model_version": model_version,
            "registered_at_utc": registered_at.astimezone(UTC).isoformat(),
            "discovery_cutoff_utc": discovery_cutoff.astimezone(UTC).isoformat(),
            "forward_start_utc": forward_start.astimezone(UTC).isoformat(),
            "minimum_forward_races": minimum_forward_races,
            "status": "COLLECTING",
            "notes": notes,
        }
    )
    return challenger_id


def record_forward_event(
    store: SQLiteStore,
    *,
    challenger_id: str,
    race_id: str,
    race_start: datetime,
    evaluation_created_at: datetime,
    eligible: bool,
    reason: str | None = None,
) -> None:
    store.upsert_challenger_forward_event(
        {
            "challenger_id": challenger_id,
            "race_id": race_id,
            "race_start_utc": race_start.astimezone(UTC).isoformat(),
            "evaluation_created_at_utc": evaluation_created_at.astimezone(UTC).isoformat(),
            "eligible": int(eligible),
            "reason": reason,
        }
    )


def forward_clock(store: SQLiteStore, challenger_id: str) -> ForwardClock:
    challengers = {
        str(row["challenger_id"]): row
        for row in store.fetch_table("challenger_registry")
    }
    challenger = challengers.get(challenger_id)
    if challenger is None:
        raise KeyError(f"unknown challenger {challenger_id}")
    events = [
        row
        for row in store.fetch_table("challenger_forward_events")
        if str(row["challenger_id"]) == challenger_id and bool(row["eligible"])
    ]
    n = len(events)
    minimum = int(challenger["minimum_forward_races"])
    status = "READY_FOR_MANUAL_REVIEW" if n >= minimum else "COLLECTING"
    if status != challenger.get("status"):
        store.upsert_challenger({**challenger, "status": status})
    return ForwardClock(
        challenger_id=challenger_id,
        eligible_races=n,
        minimum_races=minimum,
        status=status,
        forward_start_utc=str(challenger["forward_start_utc"]),
    )


def sync_forward_events_from_evaluations(
    store: SQLiteStore,
    challenger_id: str,
) -> ForwardClock:
    challengers = {
        str(row["challenger_id"]): row
        for row in store.fetch_table("challenger_registry")
    }
    challenger = challengers.get(challenger_id)
    if challenger is None:
        raise KeyError(f"unknown challenger {challenger_id}")
    version = str(challenger["model_version"])
    start = datetime.fromisoformat(str(challenger["forward_start_utc"]))
    races = {str(row["race_id"]): row for row in store.fetch_table("races")}

    for evaluation in store.fetch_table("race_research_evaluations"):
        if str(evaluation.get("fundamental_model_version") or "") != version:
            continue
        race = races.get(str(evaluation["race_id"]))
        if race is None:
            continue
        race_start = datetime.fromisoformat(str(race["start_time_utc"]))
        eligible = race_start >= start
        record_forward_event(
            store,
            challenger_id=challenger_id,
            race_id=str(evaluation["race_id"]),
            race_start=race_start,
            evaluation_created_at=datetime.fromisoformat(
                str(evaluation["created_at_utc"])
            ),
            eligible=eligible,
            reason=None if eligible else "PRE_FORWARD_CLOCK",
        )
    return forward_clock(store, challenger_id)
