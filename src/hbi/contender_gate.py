"""V2.1 decision-completeness gate; never a probability or staking model."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from math import isclose, isfinite

from .domain import Decision


@dataclass(frozen=True)
class Contender:
    selection: str
    winner_odds: float | None = None
    system_share_percent: float | None = None
    sporting_signal: str | None = None
    market_discrepancy: str | None = None

    def triggers(self) -> list[str]:
        reasons = []
        if self.system_share_percent is not None:
            if not isfinite(self.system_share_percent) or not 0 <= self.system_share_percent <= 100:
                raise ValueError("system_share_percent must be in [0, 100]")
            if self.system_share_percent >= 8:
                reasons.append("SYSTEM_SHARE_GE_8_PERCENT")
        if self.winner_odds is not None:
            if not isfinite(self.winner_odds) or self.winner_odds <= 1:
                raise ValueError("winner_odds must be finite and > 1")
            if self.winner_odds <= 12:
                reasons.append("WINNER_LE_12")
        if self.sporting_signal and self.sporting_signal.strip():
            reasons.append("SPORTING_SIGNAL")
        if self.market_discrepancy and self.market_discrepancy.strip():
            reasons.append("MARKET_DISCREPANCY")
        # Missing market coverage must never silently exempt a horse from pricing.
        if self.winner_odds is None or self.system_share_percent is None:
            reasons.append("INCOMPLETE_SCREEN_PRICE_REQUIRED")
        return reasons


@dataclass(frozen=True)
class Pricing:
    p_win: float
    fair_odds: float
    minimum_odds: float
    decision: str
    priced_at: datetime


@dataclass(frozen=True)
class Quote:
    odds: float
    observed_at: datetime


@dataclass(frozen=True)
class GateReport:
    allowed: bool
    errors: tuple[str, ...]
    runners: tuple[dict, ...]
    winner_status: str

    def to_dict(self) -> dict:
        return {"gate_version": "V2.1", **asdict(self)}


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def review_contenders(
    *,
    contenders: Sequence[Contender],
    pricing: Mapping[str, Pricing],
    latest_quotes: Mapping[str, Quote],
    decision_time: datetime,
    race_start: datetime,
    ticket_selections: set[str] | None = None,
    omission_reasons: Mapping[str, str] | None = None,
    max_quote_age_seconds: float = 120,
    late_window_seconds: float = 300,
) -> GateReport:
    """Review one complete active field before Winner/one coupon leg is finalized.

    None means no multi-leg coupon is being reviewed; an empty set means an empty
    leg and still requires reasons for every omitted BET. Prices/signals only
    trigger review and never modify supplied probabilities. Invalid timing fails
    closed; a collapsed/stale/early BET becomes WATCH and cannot be executed.
    """
    if not _aware(decision_time) or not _aware(race_start):
        raise ValueError("timezone-aware decision and race start required")
    if not all(isfinite(v) and v > 0 for v in (max_quote_age_seconds, late_window_seconds)):
        raise ValueError("positive finite timing limits required")
    selections = {c.selection for c in contenders}
    if not contenders or len(selections) != len(contenders) or any(not s for s in selections):
        raise ValueError("unique nonempty active field required")
    if set(pricing) - selections or set(latest_quotes) - selections:
        raise ValueError("pricing/quotes contain selections outside the active field")
    if ticket_selections is not None and ticket_selections - selections:
        raise ValueError("coupon contains selections outside the active field")
    errors = []
    rows = []
    if decision_time >= race_start:
        errors.append("RACE_ALREADY_STARTED")
    for contender in contenders:
        selection = contender.selection
        triggers = contender.triggers()
        value = pricing.get(selection)
        row = {"selection": selection, "mandatory_price": bool(triggers),
               "triggers": triggers, "screen": asdict(contender), "pricing": None,
               "late_price_reason": None, "omission_reason": None}
        if value is None:
            if triggers:
                errors.append(f"UNPRICED_CONTENDER:{selection}")
            rows.append(row)
            continue
        valid = (
            all(isfinite(v) for v in (value.p_win, value.fair_odds, value.minimum_odds))
            and 0 < value.p_win <= 1
            and isclose(value.fair_odds, 1 / value.p_win, rel_tol=1e-6)
            and value.minimum_odds >= value.fair_odds
            and value.decision in {d.value for d in Decision}
            and _aware(value.priced_at) and value.priced_at <= decision_time
        )
        if not valid:
            errors.append(f"UNPRICED_CONTENDER:{selection}:INVALID_PRICING")
            rows.append(row)
            continue
        # Coupon consistency refers to the original value decision, even if the
        # final quote subsequently downgrades the Winner opportunity to WATCH.
        if (value.decision == Decision.BET and ticket_selections is not None
                and selection not in ticket_selections):
            reason = (omission_reasons or {}).get(selection, "").strip()
            row["omission_reason"] = reason or None
            row["consistency_alert"] = "BET_ABSENT_FROM_COUPON"
            if not reason:
                errors.append(f"BET_ABSENT_FROM_COUPON:{selection}:REASON_REQUIRED")
        original_decision = value.decision
        quote = latest_quotes.get(selection)
        row["latest_quote"] = None if quote is None else {
            "odds": quote.odds, "observed_at": quote.observed_at.isoformat()}
        if value.decision == Decision.BET:
            reason = None
            if quote is None or not _aware(quote.observed_at):
                reason = "NO_ACCEPTABLE_LATE_QUOTE"
            elif not isfinite(quote.odds) or quote.odds <= 1:
                reason = "INVALID_LATE_QUOTE"
            elif not 0 <= (decision_time - quote.observed_at).total_seconds() <= max_quote_age_seconds:
                reason = "STALE_OR_FUTURE_LATE_QUOTE"
            elif not 0 < (race_start - decision_time).total_seconds() <= late_window_seconds:
                reason = "OUTSIDE_LATE_PRICE_WINDOW"
            elif quote.odds < value.minimum_odds:
                reason = "PRICE_BELOW_MINIMUM"
            if reason:
                value = replace(value, decision=Decision.WATCH.value)
                row["late_price_reason"] = reason
        row["pricing"] = {**asdict(value), "priced_at": value.priced_at.isoformat(),
                          "original_decision": original_decision}
        rows.append(row)
    decisions = {r["pricing"]["decision"] for r in rows if r["pricing"]}
    status = "BLOCKED" if errors else (
        "BET" if Decision.BET in decisions else "WATCH" if Decision.WATCH in decisions else "PASS")
    return GateReport(not errors, tuple(errors), tuple(rows), status)
