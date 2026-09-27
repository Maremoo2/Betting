from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256

from .storage import SQLiteStore


def run_provider_integrity(store: SQLiteStore) -> dict[str, object]:
    race_refs = {
        str(row["race_id"]): row
        for row in store.fetch_table("provider_race_refs")
    }
    markets = store.fetch_table("provider_market_snapshots")
    market_keys = {
        (
            str(row["race_id"]),
            str(row["product"]),
            str(row["observed_at_utc"]),
        )
        for row in markets
    }
    fundamental_races = {
        str(row["race_id"])
        for row in store.fetch_table("runner_fundamental_snapshots")
    }
    decisions = store.fetch_table("shadow_decision_runs")
    fetches = store.fetch_table("provider_fetch_audit")

    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    checked = 0

    for decision in decisions:
        checked += 1
        race_id = str(decision["race_id"])
        if race_id not in race_refs:
            failures.append(
                {"race_id": race_id, "reason": "missing_provider_race_reference"}
            )
        source_time = decision.get("source_market_observed_at_utc")
        if source_time and (
            race_id,
            str(decision["product"]),
            str(source_time),
        ) not in market_keys:
            failures.append(
                {
                    "race_id": race_id,
                    "decision_run_id": decision["decision_run_id"],
                    "reason": "decision_market_snapshot_not_found_in_provider_store",
                }
            )
        if decision.get("fundamental_model_version") and race_id not in fundamental_races:
            failures.append(
                {
                    "race_id": race_id,
                    "decision_run_id": decision["decision_run_id"],
                    "reason": "fundamental_decision_without_fundamental_snapshot",
                }
            )

    failed_fetches = [row for row in fetches if not bool(row.get("success"))]
    by_provider: dict[str, int] = {}
    for row in failed_fetches:
        provider = str(row.get("provider") or "UNKNOWN")
        by_provider[provider] = by_provider.get(provider, 0) + 1
    if failed_fetches:
        warnings.append(
            {
                "reason": "provider_fetch_failures_observed",
                "count": len(failed_fetches),
                "by_provider": by_provider,
            }
        )

    status = (
        "FAIL"
        if failures
        else "WARN"
        if warnings
        else "PASS"
        if checked or fetches
        else "NO_EVIDENCE"
    )
    generated_at = datetime.now(UTC)
    report = {
        "schema_version": "HBI_PROVIDER_INTEGRITY_V1",
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "checked_decisions": checked,
        "provider_fetches": len(fetches),
        "provider_fetch_failures": len(failed_fetches),
        "failures": failures,
        "warnings": warnings,
    }
    audit_id = sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    store.insert_integrity_audit(
        {
            "audit_id": audit_id,
            "audit_type": "PROVIDER_INTEGRITY",
            "generated_at_utc": generated_at.isoformat(),
            "status": status,
            "checked_rows": checked,
            "failures": len(failures),
            "warnings": len(warnings),
            "report_json": json.dumps(report, sort_keys=True),
            "github_sha": os.getenv("GITHUB_SHA"),
        }
    )
    return report
