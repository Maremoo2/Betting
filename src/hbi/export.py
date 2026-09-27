from __future__ import annotations

import csv
import json
from pathlib import Path

from .storage import SQLiteStore

DEFAULT_EXPORT_TABLES = (
    "races",
    "runners",
    "market_snapshots",
    "predictions",
    "race_diagnostics",
    "decisions",
    "review_flags",
    "prewatch_events",
    "outcomes",
    "provider_race_refs",
    "provider_market_snapshots",
    "provider_fetch_audit",
    "provider_payloads",
    "runner_fundamental_snapshots",
    "fundamental_model_runs",
    "shadow_tickets",
    "shadow_daily_reports",
)


def export_table_csv(store: SQLiteStore, table: str, output_path: str | Path) -> int:
    rows = store.fetch_table(table)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export_database_csv(
    store: SQLiteStore,
    output_dir: str | Path,
    tables: tuple[str, ...] = DEFAULT_EXPORT_TABLES,
) -> dict[str, int]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    return {
        table: export_table_csv(store, table, output / f"{table}.csv")
        for table in tables
    }


def export_database_json(
    store: SQLiteStore,
    output_path: str | Path,
    tables: tuple[str, ...] = DEFAULT_EXPORT_TABLES,
) -> None:
    payload = {table: store.fetch_table(table) for table in tables}
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
