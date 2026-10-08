from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from .benchmark import closing_line_value
from .storage import SQLiteStore


def run_settlement_integrity(
    store: SQLiteStore,
    *,
    now: datetime | None = None,
    grace_hours: float = 24.0,
) -> dict[str, object]:
    current = now or datetime.now(UTC)
    outcomes = {
        str(row["race_id"]): str(row["winner_selection_id"])
        for row in store.fetch_table("outcomes")
    }
    decisions = store.fetch_table("shadow_decision_runs")
    tickets = store.fetch_table("shadow_tickets")
    race_starts = {
        str(row["race_id"]): datetime.fromisoformat(str(row["start_time_utc"]))
        for row in store.fetch_table("races")
    }

    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    checked = 0

    for row in decisions:
        start = datetime.fromisoformat(str(row["race_start_time_utc"]))
        if start + timedelta(hours=grace_hours) > current:
            continue
        checked += 1
        race_id = str(row["race_id"])
        if race_id not in outcomes:
            warnings.append(
                {
                    "race_id": race_id,
                    "reason": "official_outcome_missing_after_grace",
                }
            )

    for ticket in tickets:
        status = str(ticket.get("status") or "")
        race_id = str(ticket.get("race_id") or "")
        if status == "NOT_EXECUTABLE":
            checked += 1
            if float(ticket.get("stake_nok") or 0.0) != 0.0:
                failures.append(
                    {
                        "ticket_id": ticket["ticket_id"],
                        "reason": "not_executable_has_nonzero_stake",
                    }
                )
            continue

        if status != "SETTLED":
            if race_id in outcomes:
                race_start = race_starts.get(race_id)
                if (
                    race_start is not None
                    and race_start + timedelta(hours=grace_hours) <= current
                ):
                    failures.append(
                        {
                            "ticket_id": ticket["ticket_id"],
                            "reason": "official_outcome_exists_but_ticket_unsettled_after_grace",
                        }
                    )
                else:
                    warnings.append(
                        {
                            "ticket_id": ticket["ticket_id"],
                            "reason": "official_outcome_exists_but_ticket_pending_within_grace",
                        }
                    )
            continue

        checked += 1
        stake = float(ticket.get("stake_nok") or 0.0)
        gross = float(ticket.get("gross_return_nok") or 0.0)
        net = ticket.get("net_pnl_nok")
        if net is None or not math.isclose(
            float(net),
            gross - stake,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            failures.append(
                {
                    "ticket_id": ticket["ticket_id"],
                    "reason": "net_pnl_not_equal_gross_minus_stake",
                }
            )

        selections_raw = ticket.get("selections_json")
        try:
            selections = json.loads(str(selections_raw))
        except json.JSONDecodeError:
            selections = []
        product = str(ticket.get("product") or "")
        if product == "V" and race_id in outcomes and selections:
            won = str(selections[0]) == outcomes[race_id]
            if won != (gross > 0):
                failures.append(
                    {
                        "ticket_id": ticket["ticket_id"],
                        "reason": "winner_and_gross_return_disagree",
                    }
                )

        available = ticket.get("available_price")
        close = ticket.get("closing_price")
        stored_clv = ticket.get("clv")
        if available is not None and close is not None and stored_clv is not None:
            expected_clv = closing_line_value(float(available), float(close))
            if not math.isclose(
                float(stored_clv),
                expected_clv,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                failures.append(
                    {
                        "ticket_id": ticket["ticket_id"],
                        "reason": "clv_reconciliation_mismatch",
                    }
                )

    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    report = {
        "schema_version": "HBI_SETTLEMENT_INTEGRITY_V1",
        "generated_at_utc": current.isoformat(),
        "status": status,
        "checked_rows": checked,
        "failures": failures,
        "warnings": warnings,
        "grace_hours": grace_hours,
    }
    audit_id = sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    store.insert_integrity_audit(
        {
            "audit_id": audit_id,
            "audit_type": "SETTLEMENT_INTEGRITY",
            "generated_at_utc": current.isoformat(),
            "status": status,
            "checked_rows": checked,
            "failures": len(failures),
            "warnings": len(warnings),
            "report_json": json.dumps(report, sort_keys=True),
            "github_sha": os.getenv("GITHUB_SHA"),
        }
    )
    return report
