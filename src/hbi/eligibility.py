from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EligibilityResult:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_win_eligibility(
    *,
    decision_time: datetime,
    race_start_time: datetime,
    market_observed_at: datetime | None,
    fundamental_shadow_eligible: bool,
    fundamental_selections: set[str],
    market_selections: set[str],
) -> EligibilityResult:
    """Fail-closed integrity gate before the value layer.

    This gate does not decide whether a price is attractive and does not change
    model probabilities. It only checks whether the frozen inputs are eligible
    to reach the value/decision layer.
    """
    reasons: list[str] = []
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        reasons.append("DECISION_TIME_NOT_TIMEZONE_AWARE")
    if race_start_time.tzinfo is None or race_start_time.utcoffset() is None:
        reasons.append("RACE_START_NOT_TIMEZONE_AWARE")
    if decision_time >= race_start_time:
        reasons.append("RACE_ALREADY_STARTED")
    if market_observed_at is None:
        reasons.append("NO_MARKET_TIMESTAMP")
    elif market_observed_at > decision_time:
        reasons.append("MARKET_AFTER_DECISION")
    if not fundamental_shadow_eligible:
        reasons.append("FUNDAMENTAL_NOT_SHADOW_ELIGIBLE")
    if not fundamental_selections:
        reasons.append("NO_FUNDAMENTAL_FIELD")
    if not market_selections:
        reasons.append("NO_MARKET_FIELD")
    if fundamental_selections != market_selections:
        reasons.append("INCOMPLETE_FULL_FIELD_ALIGNMENT")
    return EligibilityResult(allowed=not reasons, reasons=tuple(reasons))
