from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from .benchmark import closing_line_value
from .providers.rikstoto import RikstotoClient
from .storage import SQLiteStore

OSLO = ZoneInfo("Europe/Oslo")
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SettlementSummary:
    attempted: int
    settled: int
    pending: int
    failed_fetches: int


def _final_odds(
    result: dict[str, object],
    *,
    product_key: str,
    race_number: int,
    selection: str,
) -> float | None:
    final_odds = result.get("finalOdds")
    if not isinstance(final_odds, dict):
        return None
    by_product = final_odds.get(product_key)
    if not isinstance(by_product, dict):
        return None
    by_race = by_product.get(str(race_number))
    if not isinstance(by_race, dict):
        return None
    entry = by_race.get(str(selection))
    if not isinstance(entry, dict):
        return None
    value = entry.get("odds")
    return None if value is None else float(value)


def _finish_map(complete: dict[str, object]) -> dict[str, int]:
    rows = complete.get("results")
    if not isinstance(rows, list):
        return {}
    output: dict[str, int] = {}
    seen_start_numbers: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        start = item.get("startNumber")
        if start is None:
            continue
        key = str(start)
        # A runner may appear only once in one race's official complete result.
        # The old dict assignment silently overwrote contradictory duplicates,
        # potentially turning unverifiable source data into a settled loss.
        if key in seen_start_numbers:
            return {}
        seen_start_numbers.add(key)
        place = item.get("place")
        if place is None:
            continue
        try:
            output[key] = int(place)
        except (TypeError, ValueError):
            continue
    return output


def _confirmed_win_dividends(result: dict, race_number: int, winners: set[str]) -> bool:
    """A published winning dividend confirms the result without pricing losing horses."""
    try:
        entries = result["finalOdds"]["winOdds"][str(race_number)]
        return bool(winners) and all(
            entries[w]["payoutStatus"] == "Dividends"
            and math.isfinite(float(entries[w]["odds"]))
            and float(entries[w]["odds"]) > 0
            for w in winners
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _confirmed_disqualification(complete: dict, selection: str) -> bool:
    """Only the live-verified Dsk marker with positive participation odds is a loss.

    Plain finish zero and Str are ambiguous/scratch states, never inferred losses.
    """
    rows = complete.get("results")
    if not isinstance(rows, list):
        return False
    matches = [r for r in rows if isinstance(r, dict) and str(r.get("startNumber")) == selection]
    if len(matches) != 1:
        return False
    row = matches[0]
    try:
        price = float(row["odds"])
        return (row.get("place") == 0 and row.get("kmTime") == "Dsk"
                and math.isfinite(price) and price > 0)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def settle_open_shadow_tickets(
    store: SQLiteStore,
    *,
    client: RikstotoClient | None = None,
    settled_at: datetime | None = None,
    trace_hook: Callable[[dict[str, object]], None] | None = None,
) -> SettlementSummary:
    api = client or RikstotoClient()
    now = settled_at or datetime.now(UTC)
    open_tickets = store.open_shadow_tickets()
    result_cache: dict[str, tuple[dict[str, object], str]] = {}
    complete_cache: dict[tuple[str, int], tuple[dict[str, object], str]] = {}
    # Provenance metadata is separate from cached result payloads; the normal
    # settlement decisions and source lookup count remain unchanged.
    day_receipts: dict[str, dict[str, object]] = {}
    complete_receipts: dict[tuple[str, int], dict[str, object]] = {}
    settled = pending = failed = 0

    def receipt(fetch: object) -> dict[str, object]:
        completed = getattr(fetch, "response_completed_at", None)
        return {
            "source_url": getattr(fetch, "url", None) or "MISSING",
            "http_status": getattr(fetch, "status_code", None),
            "source_observed_at_utc": (
                completed.isoformat() if isinstance(completed, datetime) else "MISSING"
            ),
            "received_at_utc": (
                completed.isoformat() if isinstance(completed, datetime) else "MISSING"
            ),
            "source_published_at_utc": "MISSING",
            "source_body_sha256": getattr(fetch, "response_body_sha256", None) or "MISSING",
            "original_raw_body_reference": "MISSING",
            "source_error_type": (
                "MISSING" if getattr(fetch, "success", False)
                else str(getattr(fetch, "error", None) or "UNKNOWN_FETCH_ERROR").split(":")[0][:80]
            ),
        }

    for ticket in open_tickets:
        attempt_id = str(uuid4())
        attempt_started = datetime.now(UTC)
        trace_day: dict[str, object] | None = None
        trace_complete: dict[str, object] | None = None

        def emit(reason: str, *, after: str = "SHADOW_BET") -> None:
            """Explicit opt-in only. Tracer errors must NEVER change settlement."""
            if trace_hook is None:
                return
            try:
                selections = json.loads(str(ticket.get("selections_json")))  # noqa: B023
                selection = str(selections[0]) if isinstance(selections, list) and selections else "MISSING"
            except (TypeError, ValueError, IndexError):
                selection = "MISSING"
            event: dict[str, object] = {
                "schema": "PIT012_SETTLEMENT_ATTEMPT_V1",
                "attempt_id": attempt_id,  # noqa: B023
                "ticket_id": str(ticket.get("ticket_id") or "MISSING"),  # noqa: B023
                "race_id": str(ticket.get("race_id") or "MISSING"),  # noqa: B023
                "horse_id": selection,
                "horse_id_scope": "RACE_LOCAL_SELECTION_NOT_PERMANENT_ID",
                "job_run_id": os.getenv("GITHUB_RUN_ID") or "MISSING",
                "started_at_utc": attempt_started.isoformat(),  # noqa: B023
                "finished_at_utc": datetime.now(UTC).isoformat(),
                "settlement_code_sha": os.getenv("GITHUB_SHA") or "MISSING",
                "raceday_results": trace_day or {"status": "MISSING"},  # noqa: B023
                "complete_results": trace_complete or {"status": "MISSING"},  # noqa: B023
                "cached_outcome_is_original_official_proof": False,
                "eligibility": "ACCEPTED" if reason == "SETTLED" else "REJECTED",
                "decision_reason": reason,
                "ticket_status_before": str(ticket.get("status") or "MISSING"),  # noqa: B023
                "ticket_status_after": after,
                "bet_authority": False,
                "source_raw_body_retained_by_settlement": False,
            }
            try:
                trace_hook(event)
            except Exception as exc:  # noqa: BLE001
                # The sidecar never changes settlement. Log only the *type*,
                # not source content, tokens or other private details.
                LOGGER.warning("PIT012 trace unavailable: %s", type(exc).__name__)


        raceday = ticket.get("provider_raceday_key")
        race_id = ticket.get("race_id")
        if not raceday or not race_id:
            pending += 1
            emit("MISSING_RACE_REFERENCE")
            continue
        race = store.get_race(str(race_id))
        if race is None:
            pending += 1
            emit("RACE_NOT_FOUND")
            continue
        race_number = int(race["race_no"])

        if str(raceday) not in result_cache:
            fetched = api.raceday_results(str(raceday))
            day_receipts[str(raceday)] = receipt(fetched)
            if not fetched.success:
                failed += 1
                pending += 1
                trace_day = day_receipts[str(raceday)]
                emit("RACEDAY_RESULTS_FETCH_FAILED")
                continue
            result_cache[str(raceday)] = (api.result_object(fetched), fetched.url)
        trace_day = day_receipts.get(str(raceday))

        key = (str(raceday), race_number)
        if key not in complete_cache:
            fetched = api.complete_results(str(raceday), race_number)
            complete_receipts[key] = receipt(fetched)
            if not fetched.success:
                failed += 1
                pending += 1
                trace_complete = complete_receipts[key]
                emit("COMPLETE_RESULTS_FETCH_FAILED")
                continue
            complete_cache[key] = (api.result_object(fetched), fetched.url)
        trace_complete = complete_receipts.get(key)

        raceday_result, odds_url = result_cache[str(raceday)]
        complete, result_url = complete_cache[key]
        finishes = _finish_map(complete)
        selections = json.loads(str(ticket["selections_json"]))
        if not selections:
            pending += 1
            emit("SELECTION_MISSING")
            continue
        selection = str(selections[0])
        stake = float(ticket.get("stake_nok") or 0.0)
        product = str(ticket["product"])

        if product == "V":
            winners = {number for number, finish in finishes.items() if finish == 1}
            finish = finishes.get(selection)
            if (
                complete.get("isComplete") is not True
                or finish is None or (finish <= 0 and not _confirmed_disqualification(
                    complete, selection))
                or not _confirmed_win_dividends(raceday_result, race_number, winners)
            ):
                pending += 1
                if complete.get("isComplete") is not True:
                    emit("OFFICIAL_RESULT_INCOMPLETE")
                elif finish is None:
                    emit("HORSE_NOT_IN_COMPLETE_RESULT")
                elif finish <= 0 and not _confirmed_disqualification(complete, selection):
                    emit("RESULT_CODE_UNSUPPORTED")
                else:
                    emit("WINNING_DIVIDEND_MISSING_OR_UNCONFIRMED")
                continue
            price = _final_odds(
                raceday_result,
                product_key="winOdds",
                race_number=race_number,
                selection=selection,
            )
            won = finish == 1
            if won and price is None:
                pending += 1
                emit("WINNER_FINAL_PRICE_MISSING")
                continue
            gross = stake * price if won else 0.0
        elif product == "P":
            final_odds = raceday_result.get("finalOdds")
            place_by_race = (
                final_odds.get("placeOdds")
                if isinstance(final_odds, dict)
                else None
            )
            race_place_odds = (
                place_by_race.get(str(race_number))
                if isinstance(place_by_race, dict)
                else None
            )
            if not isinstance(race_place_odds, dict) or not finishes:
                pending += 1
                emit("PLACE_ODDS_OR_RESULTS_MISSING")
                continue
            price = _final_odds(
                raceday_result,
                product_key="placeOdds",
                race_number=race_number,
                selection=selection,
            )
            won = selection in race_place_odds and price is not None and price > 0
            gross = stake * price if won and price is not None else 0.0
        else:
            # Publicly observed result contracts used here expose reliable V/P
            # final odds. Other products stay pending until an official dividend
            # contract is verified.
            pending += 1
            emit("UNSUPPORTED_PRODUCT")
            continue

        close = price
        decision_price = ticket.get("available_price")
        clv = None
        if decision_price is not None and close is not None and close > 1:
            clv = closing_line_value(float(decision_price), float(close))
        net = gross - stake
        store.settle_shadow_ticket(
            ticket_id=str(ticket["ticket_id"]),
            settled_at=now,
            gross_return_nok=gross,
            net_pnl_nok=net,
            settlement_source_uri=f"{odds_url} | {result_url}",
            closing_price=close,
            clv=clv,
            result={
                "won": won,
                "finish": finishes.get(selection),
                "selection": selection,
                "product": product,
                "official_final_odds": close,
            },
        )
        settled += 1
        emit("SETTLED", after="SETTLED")

    return SettlementSummary(
        attempted=len(open_tickets),
        settled=settled,
        pending=pending,
        failed_fetches=failed,
    )


def build_daily_report(store: SQLiteStore, report_date: date) -> dict[str, object]:
    local_start = datetime.combine(report_date, time.min, tzinfo=OSLO)
    local_end = local_start + timedelta(days=1)
    tickets = store.shadow_tickets_between(
        local_start.astimezone(UTC),
        local_end.astimezone(UTC),
    )
    executable = [
        ticket
        for ticket in tickets
        if ticket.get("status") not in {"NOT_EXECUTABLE"}
    ]
    settled = [ticket for ticket in executable if ticket.get("status") == "SETTLED"]
    stake = sum(float(ticket.get("stake_nok") or 0) for ticket in executable)
    settled_stake = sum(float(ticket.get("stake_nok") or 0) for ticket in settled)
    gross = sum(float(ticket.get("gross_return_nok") or 0) for ticket in settled)
    net = sum(float(ticket.get("net_pnl_nok") or 0) for ticket in settled)
    wins = sum(float(ticket.get("gross_return_nok") or 0) > 0 for ticket in settled)
    positive_clv = sum(
        ticket.get("clv") is not None and float(ticket["clv"]) > 0
        for ticket in settled
    )
    roi = None if settled_stake <= 0 else net / settled_stake

    by_product: dict[str, dict[str, float | int]] = {}
    for ticket in executable:
        product = str(ticket["product"])
        bucket = by_product.setdefault(
            product,
            {"tickets": 0, "stake_nok": 0.0, "gross_return_nok": 0.0, "net_pnl_nok": 0.0},
        )
        bucket["tickets"] = int(bucket["tickets"]) + 1
        bucket["stake_nok"] = float(bucket["stake_nok"]) + float(ticket.get("stake_nok") or 0)
        bucket["gross_return_nok"] = float(bucket["gross_return_nok"]) + float(
            ticket.get("gross_return_nok") or 0
        )
        bucket["net_pnl_nok"] = float(bucket["net_pnl_nok"]) + float(
            ticket.get("net_pnl_nok") or 0
        )

    report = {
        "report_date": report_date.isoformat(),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "stake_nok": stake,
        "settled_stake_nok": settled_stake,
        "gross_return_nok": gross,
        "net_pnl_nok": net,
        "roi": roi,
        "tickets": len(executable),
        "settled_tickets": len(settled),
        "winning_tickets": wins,
        "positive_clv_tickets": positive_clv,
        "not_executable": len(tickets) - len(executable),
        "by_product": by_product,
    }
    store.upsert_shadow_daily_report(
        {
            **{key: report[key] for key in (
                "report_date",
                "generated_at_utc",
                "stake_nok",
                "gross_return_nok",
                "net_pnl_nok",
                "roi",
                "tickets",
                "settled_tickets",
                "winning_tickets",
                "positive_clv_tickets",
            )},
            "report_json": json.dumps(report, ensure_ascii=False),
        }
    )
    return report
