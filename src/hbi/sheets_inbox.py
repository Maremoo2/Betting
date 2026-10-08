from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoogleSheetsEvidenceInbox:
    """Read-only adapter for the ChatGPT intelligence staging worksheet.

    The worksheet is an append-only inbox. Rows become canonical research evidence
    only after validation and insertion into HBI's SQLite database.
    """

    spreadsheet_id: str
    credentials_path: str
    worksheet_name: str = "HBI_EVIDENCE_INBOX"

    def _worksheet(self):
        try:
            import gspread
        except ImportError as exc:
            raise RuntimeError(
                'Google Sheets support is optional. Install with pip install -e ".[sheets]"'
            ) from exc
        client = gspread.service_account(filename=self.credentials_path)
        spreadsheet = client.open_by_key(self.spreadsheet_id)
        return spreadsheet.worksheet(self.worksheet_name)

    def read_rows(self) -> list[dict[str, object]]:
        worksheet = self._worksheet()
        records = worksheet.get_all_records(
            default_blank="",
            numericise_ignore=["all"],
        )
        return [dict(record) for record in records]
