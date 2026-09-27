from __future__ import annotations

from datetime import datetime
from typing import Any

from .storage import SQLiteStore


def _latest_run_by_race(
    runs: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    ordered = sorted(
        runs,
        key=lambda row: str(row.get("created_at_utc") or ""),
        reverse=True,
    )
    output: dict[str, dict[str, object]] = {}
    for row in ordered:
        output.setdefault(str(row["race_id"]), row)
    return output


def build_learning_rows(store: SQLiteStore) -> list[dict[str, Any]]:
    """Build one deterministic research row per frozen shadow decision.

    Missing numeric evidence remains None. It is never converted to zero.
    """
    races = {str(row["race_id"]): row for row in store.fetch_table("races")}
    evaluations = {
        (str(row["race_id"]), str(row["shadow_model_version"])): row
        for row in store.fetch_table("race_research_evaluations")
    }
    outcomes = {
        str(row["race_id"]): row for row in store.fetch_table("outcomes")
    }
    fundamentals = _latest_run_by_race(
        store.fetch_table("fundamental_model_runs")
    )
    provenance = {
        str(row["decision_run_id"]): row
        for row in store.fetch_table("decision_provenance")
    }

    tickets_by_race: dict[str, list[dict[str, object]]] = {}
    for ticket in store.fetch_table("shadow_tickets"):
        tickets_by_race.setdefault(str(ticket.get("race_id") or ""), []).append(ticket)

    rows: list[dict[str, Any]] = []
    for decision in store.fetch_table("shadow_decision_runs"):
        race_id = str(decision["race_id"])
        race = races.get(race_id, {})
        evaluation = evaluations.get(
            (race_id, str(decision["shadow_model_version"])),
            {},
        )
        fundamental = fundamentals.get(race_id, {})
        outcome = outcomes.get(race_id, {})
        provenance_row = provenance.get(str(decision["decision_run_id"]), {})
        tickets = [
            ticket
            for ticket in tickets_by_race.get(race_id, [])
            if str(ticket.get("model_version") or "")
            == str(decision["shadow_model_version"])
            and str(ticket.get("status") or "") != "NOT_EXECUTABLE"
        ]
        settled = [ticket for ticket in tickets if ticket.get("status") == "SETTLED"]

        stake = sum(float(ticket.get("stake_nok") or 0) for ticket in settled)
        pnl = sum(float(ticket.get("net_pnl_nok") or 0) for ticket in settled)
        clv_values = [
            float(ticket["clv"])
            for ticket in settled
            if ticket.get("clv") is not None
        ]

        known_history = fundamental.get("history_coverage")
        source_complete = bool(
            decision.get("fundamental_probabilities_json")
            and decision.get("market_probabilities_json")
        )
        provenance_complete = bool(
            provenance_row.get("combination_policy_json")
            and provenance_row.get("decision_policy_json")
        )
        if source_complete and provenance_complete:
            quality = "OK"
        elif source_complete or provenance_complete:
            quality = "PARTIAL"
        else:
            quality = "UNKNOWN"

        rows.append(
            {
                "decision_run_id": decision["decision_run_id"],
                "race_id": race_id,
                "race_time_utc": race.get("start_time_utc"),
                "country": race.get("country"),
                "track": race.get("track"),
                "race_no": race.get("race_no"),
                "discipline": race.get("discipline"),
                "distance_m": race.get("distance_m"),
                "start_method": race.get("start_method"),
                "field_size": decision.get("field_size"),
                "decision_time_utc": decision.get("created_at_utc"),
                "target_minutes_to_start": decision.get("target_minutes_to_start"),
                "actual_minutes_to_start": decision.get("actual_minutes_to_start"),
                "execution_latency_seconds": decision.get("execution_latency_seconds"),
                "decision_status": decision.get("decision_status"),
                "decision_reason": decision.get("reason"),
                "shadow_model_version": decision.get("shadow_model_version"),
                "fundamental_model_version": decision.get("fundamental_model_version"),
                "history_coverage": (
                    None if known_history is None else float(known_history)
                ),
                "shadow_eligible": (
                    None
                    if fundamental.get("shadow_eligible") is None
                    else bool(fundamental.get("shadow_eligible"))
                ),
                "winner_selection_id": outcome.get("winner_selection_id"),
                "fundamental_log_loss": evaluation.get("fundamental_log_loss"),
                "market_log_loss": evaluation.get("market_log_loss"),
                "combined_log_loss": evaluation.get("combined_log_loss"),
                "fundamental_brier": evaluation.get("fundamental_brier"),
                "market_brier": evaluation.get("market_brier"),
                "combined_brier": evaluation.get("combined_brier"),
                "model_market_conflict_score": decision.get(
                    "model_market_conflict_score"
                ),
                "settled_ticket_count": len(settled),
                "settled_stake_nok": stake if settled else None,
                "net_pnl_nok": pnl if settled else None,
                "roi": None if not settled or stake <= 0 else pnl / stake,
                "mean_clv": (
                    None if not clv_values else sum(clv_values) / len(clv_values)
                ),
                "data_quality_status": quality,
                "research_only": True,
                "execution_authority": False,
            }
        )

    rows.sort(
        key=lambda row: (
            str(row.get("race_time_utc") or ""),
            str(row.get("race_id") or ""),
            str(row.get("decision_run_id") or ""),
        )
    )
    return rows


def learning_dataset_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    evaluated = [
        row for row in rows if row.get("combined_log_loss") is not None
    ]
    settled = [row for row in rows if row.get("settled_ticket_count")]
    countries: dict[str, int] = {}
    for row in rows:
        country = str(row.get("country") or "UNKNOWN")
        countries[country] = countries.get(country, 0) + 1
    return {
        "rows": len(rows),
        "evaluated_rows": len(evaluated),
        "settled_rows": len(settled),
        "countries": countries,
        "data_quality": {
            status: sum(row.get("data_quality_status") == status for row in rows)
            for status in ("OK", "PARTIAL", "UNKNOWN")
        },
    }
