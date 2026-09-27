from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .manifest import persist_run_manifest
from .nightly import build_daily_report, settle_open_shadow_tickets
from .observatory import build_research_observatory
from .providers.rikstoto import RikstotoClient
from .storage import SQLiteStore
from .v1_audit import run_v1_audit

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"
OSLO = ZoneInfo("Europe/Oslo")


def main() -> None:
    started_at = datetime.now(UTC)
    db_path = os.getenv("HBI_DB_PATH", "data/hbi.sqlite")
    output = Path(os.getenv("HBI_NIGHTLY_REPORT_PATH", "nightly-report.json"))
    observatory_json = Path(
        os.getenv("HBI_OBSERVATORY_JSON_PATH", "research-observatory.json")
    )
    observatory_md = Path(
        os.getenv("HBI_OBSERVATORY_MD_PATH", "research-observatory.md")
    )
    store = SQLiteStore(db_path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)

    client = RikstotoClient()
    settlement = settle_open_shadow_tickets(store, client=client)
    report_date = datetime.now(UTC).astimezone(OSLO).date() - timedelta(days=1)
    report = build_daily_report(store, report_date)
    observatory = build_research_observatory(
        store,
        report_date,
        client=client,
    )
    v1_output_dir = Path(os.getenv("HBI_V1_AUDIT_DIR", "research-v1"))
    v1_audit = run_v1_audit(
        store,
        output_dir=v1_output_dir,
        now=datetime.now(UTC),
    )
    payload = {
        "settlement": {
            "attempted": settlement.attempted,
            "settled": settlement.settled,
            "pending": settlement.pending,
            "failed_fetches": settlement.failed_fetches,
        },
        "report": report,
        "research_observatory": {
            "report_date": observatory["report_date"],
            "schema_version": observatory["schema_version"],
            "race_evaluations_materialized": observatory[
                "race_evaluations_materialized"
            ],
            "outcome_collection": observatory["outcome_collection"],
        },
        "v1_system_audit": {
            "engineering_status": v1_audit["engineering_status"],
            "temporal_integrity": v1_audit["temporal_integrity"]["status"],
            "provider_integrity": v1_audit["provider_integrity"]["status"],
            "runtime_replay_parity": v1_audit["runtime_replay_parity"]["status"],
            "settlement_integrity": v1_audit["settlement_integrity"]["status"],
            "learning_rows": v1_audit["learning_dataset"]["rows"],
        },
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    observatory_json.write_text(
        json.dumps(observatory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    observatory_md.write_text(
        str(observatory["markdown"]),
        encoding="utf-8",
    )
    persist_run_manifest(
        store,
        run_type="NIGHTLY_SETTLEMENT_RESEARCH",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        status=str(v1_audit["engineering_status"]),
        model_version="FUNDAMENTAL_CHAMPION_V1_1",
        metadata={
            "report_date": report_date.isoformat(),
            "settlement_attempted": settlement.attempted,
            "settlement_settled": settlement.settled,
            "learning_rows": v1_audit["learning_dataset"]["rows"],
        },
    )
    store.checkpoint()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
