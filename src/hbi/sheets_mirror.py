from __future__ import annotations

from dataclasses import dataclass

from .export import DEFAULT_EXPORT_TABLES
from .storage import SQLiteStore


@dataclass
class GoogleSheetsMirror:
    """Optional human-readable mirror of canonical HBI data.

    The SQLite/Postgres database remains source of truth. This adapter deliberately
    uses replace-style worksheet mirroring rather than allowing Sheets edits to
    mutate historical point-in-time records.
    """

    spreadsheet_id: str
    credentials_path: str

    def _spreadsheet(self):
        try:
            import gspread
        except ImportError as exc:
            raise RuntimeError(
                'Google Sheets support is optional. Install with pip install -e ".[sheets]"'
            ) from exc
        client = gspread.service_account(filename=self.credentials_path)
        return client.open_by_key(self.spreadsheet_id)

    def mirror_table(
        self,
        store: SQLiteStore,
        table: str,
        *,
        worksheet_name: str | None = None,
    ) -> int:
        rows = store.fetch_table(table)
        spreadsheet = self._spreadsheet()
        name = worksheet_name or table.upper()
        try:
            worksheet = spreadsheet.worksheet(name)
        except Exception:
            worksheet = spreadsheet.add_worksheet(title=name, rows=max(100, len(rows) + 10), cols=40)

        worksheet.clear()
        if not rows:
            worksheet.update([["NO DATA"]], "A1")
            return 0

        headers = list(rows[0])
        values = [headers] + [[row.get(header) for header in headers] for row in rows]
        worksheet.update(values, "A1")
        return len(rows)

    def mirror_default_tables(
        self,
        store: SQLiteStore,
        tables: tuple[str, ...] = DEFAULT_EXPORT_TABLES,
    ) -> dict[str, int]:
        return {table: self.mirror_table(store, table) for table in tables}
