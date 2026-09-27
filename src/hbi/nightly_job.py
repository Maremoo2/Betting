from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .nightly import build_daily_report, settle_open_shadow_tickets
from .providers.rikstoto import RikstotoClient
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"
OSLO = ZoneInfo("Europe/Oslo")


def main() -> None:
    db_path = os.getenv("HBI_DB_PATH", "data/hbi.sqlite")
    output = Path(os.getenv("HBI_NIGHTLY_REPORT_PATH", "nightly-report.json"))
    store = SQLiteStore(db_path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)

    settlement = settle_open_shadow_tickets(store, client=RikstotoClient())
    report_date = datetime.now(UTC).astimezone(OSLO).date() - timedelta(days=1)
    report = build_daily_report(store, report_date)
    payload = {
        "settlement": {
            "attempted": settlement.attempted,
            "settled": settlement.settled,
            "pending": settlement.pending,
            "failed_fetches": settlement.failed_fetches,
        },
        "report": report,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    store.checkpoint()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
