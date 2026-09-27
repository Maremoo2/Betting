from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")


@dataclass(frozen=True)
class ScheduleDecision:
    should_run: bool
    mode: str
    local_time: datetime
    reason: str


def evaluate_schedule(now: datetime | None = None) -> ScheduleDecision:
    """Match the PRE-WATCH cadence in Europe/Oslo.

    09:00 local time is MORNING_DISCOVERY.
    10:00 through 21:00 local time are HOURLY_WATCH.
    Other hours are skipped. The timezone conversion handles DST.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    local = current.astimezone(OSLO)
    hour = local.hour
    if hour == 9:
        return ScheduleDecision(True, "MORNING_DISCOVERY", local, "09:00 Oslo discovery run")
    if 10 <= hour <= 21:
        return ScheduleDecision(True, "HOURLY_WATCH", local, "hourly Oslo watch window")
    return ScheduleDecision(False, "SKIP", local, "outside 09:00-21:59 Oslo window")


def github_output(decision: ScheduleDecision) -> str:
    """Return newline-separated key=value output for $GITHUB_OUTPUT."""
    return "
".join(
        (
            f"should_run={'true' if decision.should_run else 'false'}",
            f"mode={decision.mode}",
            f"local_time={decision.local_time.isoformat()}",
            f"reason={decision.reason}",
        )
    )
