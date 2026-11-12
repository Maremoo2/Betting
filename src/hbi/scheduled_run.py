from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .cloud_run002_import import import_source
from .json_provider import load_market_snapshots, load_race_cards, load_results
from .manifest import persist_run_manifest
from .pipeline import HBIPipeline
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"
DEFAULT_MIGRATIONS = ROOT / "db" / "migrations"


@dataclass
class RunAudit:
    mode: str
    started_at: str
    finished_at: str | None = None
    status: str = "RUNNING"
    provider_status: str = "NO_PROVIDER_CONFIGURED"
    race_cards: int = 0
    snapshots_seen: int = 0
    snapshots_inserted: int = 0
    prewatch_events: int = 0
    results_settled: int = 0
    source_ready_races: int = 0
    model_ready_races: int = 0
    bet_ready_races: int = 0
    collector_report: dict[str, object] | None = None


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def run_once(*, db_path: str, mode: str) -> RunAudit:
    audit = RunAudit(mode=mode, started_at=datetime.now(UTC).isoformat())
    store = SQLiteStore(db_path)
    store.initialize(DEFAULT_SCHEMA)
    if DEFAULT_MIGRATIONS.exists():
        store.apply_migrations(DEFAULT_MIGRATIONS)
    pipeline = HBIPipeline(store)

    races_path = _optional_path("HBI_RACE_CARDS_JSON")
    snapshots_path = _optional_path("HBI_MARKET_SNAPSHOTS_JSON")
    results_path = _optional_path("HBI_RESULTS_JSON")

    archive_env = os.environ.get("HBI_COLLECTOR_ARCHIVE_ZIP")
    checksum_env = os.environ.get("HBI_COLLECTOR_ARCHIVE_SHA256")
    if bool(archive_env) != bool(checksum_env):
        raise ValueError("COLLECTOR_ARCHIVE_AND_CHECKSUM_REQUIRED_TOGETHER")
    collector_source = bool(archive_env)
    if collector_source:
        if not Path(archive_env).is_file() or not Path(checksum_env).is_file():
            raise ValueError("COLLECTOR_CONFIGURED_ORIGINAL_SOURCE_MISSING")
        result = import_source(
            store, Path(archive_env), Path(checksum_env),
            date_oslo=os.environ.get("HBI_COLLECTOR_DATE_OSLO") or None,
        )
        audit.provider_status = "COLLECTOR_VERIFIED_ARCHIVE_RESEARCH_ONLY"
        audit.race_cards = int(result["observed_races"])
        audit.source_ready_races = int(result["source_ready"])
        audit.model_ready_races = 0
        audit.bet_ready_races = 0
        audit.collector_report = result
    configured = any((races_path, snapshots_path, results_path)) or collector_source
    if not collector_source and configured:
        audit.provider_status = "CANONICAL_FILES"

    if races_path:
        cards = load_race_cards(races_path)
        for card in cards:
            pipeline.persist_race_card(card)
        audit.race_cards = len(cards)

    if snapshots_path:
        snapshots = load_market_snapshots(snapshots_path)
        audit.snapshots_seen = len(snapshots)
        for snapshot in snapshots:
            result = pipeline.process_snapshot(
                snapshot,
                source_uri=os.environ.get("HBI_MARKET_SOURCE_URI", "scheduled://canonical-file"),
            )
            audit.snapshots_inserted += int(result.inserted)
            audit.prewatch_events += int(result.event_id is not None)

    if results_path:
        results = load_results(results_path)
        for result in results:
            pipeline.settle(result)
        audit.results_settled = len(results)

    audit.status = "OK" if configured else "NOOP"
    finished = datetime.now(UTC)
    audit.finished_at = finished.isoformat()
    persist_run_manifest(
        store,
        run_type="PREWATCH_" + mode,
        started_at=datetime.fromisoformat(audit.started_at),
        finished_at=finished,
        status=audit.status,
        metadata=asdict(audit),
    )
    store.checkpoint()
    return audit


def main() -> None:
    db_path = os.environ.get("HBI_DB_PATH", "data/hbi.sqlite")
    mode = os.environ.get("HBI_RUN_MODE", "HOURLY_WATCH")
    audit_path = Path(os.environ.get("HBI_RUN_AUDIT_PATH", "run-audit.json"))

    audit = run_once(db_path=db_path, mode=mode)
    audit_path.write_text(json.dumps(asdict(audit), indent=2), encoding="utf-8")
    print(json.dumps(asdict(audit), indent=2))


if __name__ == "__main__":
    main()
