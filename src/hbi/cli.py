from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from .export import export_database_csv, export_database_json
from .github_evidence_inbox import GitHubEvidenceInbox
from .intelligence_bridge import ingest_intelligence_rows
from .json_provider import load_market_snapshots, load_race_cards, load_results
from .pipeline import HBIPipeline
from .sheets_inbox import GoogleSheetsEvidenceInbox
from .sheets_mirror import GoogleSheetsMirror
from .storage import SQLiteStore

DEFAULT_SCHEMA = Path(__file__).parents[2] / "db" / "schema.sql"
DEFAULT_MIGRATIONS = Path(__file__).parents[2] / "db" / "migrations"


def _store(path: str, schema: str | None = None) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(schema or DEFAULT_SCHEMA)
    if DEFAULT_MIGRATIONS.exists():
        store.apply_migrations(DEFAULT_MIGRATIONS)
    return store


def cmd_init(args: argparse.Namespace) -> None:
    _store(args.db, args.schema)
    print(f"initialized {args.db}")


def cmd_import_races(args: argparse.Namespace) -> None:
    pipeline = HBIPipeline(_store(args.db, args.schema))
    cards = load_race_cards(args.file)
    for card in cards:
        pipeline.persist_race_card(card)
    print(f"imported {len(cards)} race cards")


def cmd_import_snapshots(args: argparse.Namespace) -> None:
    pipeline = HBIPipeline(_store(args.db, args.schema))
    snapshots = load_market_snapshots(args.file)
    start = datetime.fromisoformat(args.race_start) if args.race_start else None
    inserted = events = 0
    for snapshot in snapshots:
        result = pipeline.process_snapshot(
            snapshot,
            race_start_at=start,
            source_uri=args.source_uri,
        )
        inserted += int(result.inserted)
        events += int(result.event_id is not None)
    print(f"inserted {inserted} snapshots; created {events} pre-watch events")


def cmd_import_results(args: argparse.Namespace) -> None:
    pipeline = HBIPipeline(_store(args.db, args.schema))
    results = load_results(args.file)
    for result in results:
        pipeline.settle(result)
    print(f"settled {len(results)} races")


def cmd_export(args: argparse.Namespace) -> None:
    store = _store(args.db, args.schema)
    if args.format == "csv":
        counts = export_database_csv(store, args.output)
        print("exported " + ", ".join(f"{table}={count}" for table, count in counts.items()))
    else:
        export_database_json(store, args.output)
        print(f"exported database to {args.output}")


def cmd_ingest_github_evidence_inbox(args: argparse.Namespace) -> None:
    token = os.environ.get(args.token_env)
    if not token:
        raise RuntimeError(f"missing GitHub token environment variable: {args.token_env}")
    store = _store(args.db, args.schema)
    inbox = GitHubEvidenceInbox(
        repository=args.repository,
        issue_number=args.issue_number,
        token=token,
    )
    summary = ingest_intelligence_rows(
        store,
        inbox.read_rows(),
        source_sheet=f"github-issue:{args.issue_number}",
    )
    store.checkpoint()
    print(
        "github intelligence inbox "
        f"seen={summary.seen} accepted={summary.accepted} "
        f"rejected={summary.rejected} duplicates={summary.duplicates} "
        f"pit_eligible={summary.pit_eligible}"
    )


def cmd_ingest_evidence_inbox(args: argparse.Namespace) -> None:
    store = _store(args.db, args.schema)
    inbox = GoogleSheetsEvidenceInbox(
        spreadsheet_id=args.spreadsheet_id,
        credentials_path=args.credentials,
        worksheet_name=args.worksheet,
    )
    summary = ingest_intelligence_rows(
        store,
        inbox.read_rows(),
        source_sheet=args.worksheet,
    )
    store.checkpoint()
    print(
        "intelligence inbox "
        f"seen={summary.seen} accepted={summary.accepted} "
        f"rejected={summary.rejected} duplicates={summary.duplicates} "
        f"pit_eligible={summary.pit_eligible}"
    )


def cmd_sync_sheets(args: argparse.Namespace) -> None:
    store = _store(args.db, args.schema)
    mirror = GoogleSheetsMirror(
        spreadsheet_id=args.spreadsheet_id,
        credentials_path=args.credentials,
    )
    counts = mirror.mirror_default_tables(store)
    print("mirrored " + ", ".join(f"{table}={count}" for table, count in counts.items()))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hbi")
    parser.add_argument("--db", default="data/hbi.sqlite")
    parser.add_argument("--schema", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-db")
    init.set_defaults(func=cmd_init)

    races = sub.add_parser("import-races")
    races.add_argument("file")
    races.set_defaults(func=cmd_import_races)

    snapshots = sub.add_parser("import-snapshots")
    snapshots.add_argument("file")
    snapshots.add_argument("--race-start", default=None)
    snapshots.add_argument("--source-uri", default=None)
    snapshots.set_defaults(func=cmd_import_snapshots)

    results = sub.add_parser("import-results")
    results.add_argument("file")
    results.set_defaults(func=cmd_import_results)

    export = sub.add_parser("export")
    export.add_argument("output")
    export.add_argument("--format", choices=("csv", "json"), default="csv")
    export.set_defaults(func=cmd_export)

    github_evidence = sub.add_parser("ingest-github-evidence-inbox")
    github_evidence.add_argument("--repository", required=True)
    github_evidence.add_argument("--issue-number", required=True, type=int)
    github_evidence.add_argument("--token-env", default="GITHUB_TOKEN")
    github_evidence.set_defaults(func=cmd_ingest_github_evidence_inbox)

    evidence = sub.add_parser("ingest-evidence-inbox")
    evidence.add_argument("--spreadsheet-id", required=True)
    evidence.add_argument("--credentials", required=True)
    evidence.add_argument("--worksheet", default="HBI_EVIDENCE_INBOX")
    evidence.set_defaults(func=cmd_ingest_evidence_inbox)

    sheets = sub.add_parser("sync-sheets")
    sheets.add_argument("--spreadsheet-id", required=True)
    sheets.add_argument("--credentials", required=True)
    sheets.set_defaults(func=cmd_sync_sheets)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
