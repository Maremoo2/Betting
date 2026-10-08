"""Bounded local before-start observer. No retrospective snapshot labels."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .capture import collect
from .extract import utc
from .transport import write_json


def checkpoint_status(start, observed, minutes, tolerance=60):
    seconds = (utc(start) - observed).total_seconds()
    target = minutes * 60
    if seconds > target:
        return "WAITING"
    if seconds <= 0 or target - seconds > tolerance:
        return "MISSED"
    return "DUE"


def watch(root, day, meeting, *, duration=3600, interval=30):
    if not 1 <= duration <= 86400 or not 5 <= interval <= 60:
        raise ValueError("Invalid bounded watch duration/interval")
    if utc(day + "T00:00:00").date() < datetime.now(UTC).date():
        raise ValueError("Watch requires a current or future date")
    root = Path(root)
    deadline = time.monotonic() + duration
    state_path = root / "watch-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    while time.monotonic() < deadline:
        collect(root, [day], refresh=True, meeting_key=meeting)
        # Every capture has acquisition provenance; labels refer to the last completed
        # observation, never merely the time the polling cycle began.
        for path in (root / "captures" / day).glob("*.json"):
            row = json.loads(path.read_text(encoding="utf-8"))
            observed = utc(row["observation_completed_at"])
            start = row["observed_race_metadata"]["startTime"]
            for minutes in (15, 5, 1):
                key = f"{row['race_id']}:{start}:T-{minutes}"
                status = checkpoint_status(start, observed, minutes)
                previous = state.get(key, {})
                if previous.get("status") == "CAPTURED" or status == "WAITING":
                    continue
                before = all(utc(s["fetched_at"]) < utc(start) for s in row["sources"])
                state[key] = {"status": "CAPTURED" if status == "DUE" and before else "MISSED",
                              "snapshot_id": row["snapshot_id"] if status == "DUE" and before else None,
                              "scheduled_start": start, "observed_at": observed.isoformat(),
                              "actual_start_verified": False}
        write_json(state_path, state)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    return state
