from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .fundamental import run_and_persist_fundamental
from .manifest import persist_run_manifest
from .provenance import record_decision_provenance
from .rikstoto_collector import RikstotoCollector
from .shadow import ShadowPolicy, run_win_shadow_decision
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"


@dataclass
class WatcherAudit:
    started_at_utc: str
    finished_at_utc: str | None = None
    status: str = "RUNNING"
    discovered: int = 0
    due_races: int = 0
    snapshots_inserted: int = 0
    fundamental_snapshots_inserted: int = 0
    fundamental_runs: int = 0
    fundamental_shadow_eligible: int = 0
    fundamental_failures: int = 0
    fetch_failures: int = 0
    shadow_bets_created: int = 0
    not_executable: int = 0
    passes: int = 0


def _store(path: str) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)
    return store


def _policy_from_env() -> ShadowPolicy:
    return ShadowPolicy(
        model_version=os.getenv(
            "HBI_SHADOW_MODEL_VERSION",
            "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL",
        ),
        fundamental_layer=os.getenv("HBI_SHADOW_FUNDAMENTAL_LAYER", "FUNDAMENTAL"),
        fundamental_weight=float(os.getenv("HBI_SHADOW_FUNDAMENTAL_WEIGHT", "1.0")),
        market_weight=float(os.getenv("HBI_SHADOW_MARKET_WEIGHT", "1.0")),
        material_conflict_threshold=float(
            os.getenv("HBI_SHADOW_CONFLICT_THRESHOLD", "20.0")
        ),
        minimum_edge=float(os.getenv("HBI_SHADOW_MIN_EDGE", "0.05")),
        safety_margin=float(os.getenv("HBI_SHADOW_SAFETY_MARGIN", "0.05")),
        single_win_stake_nok=float(os.getenv("HBI_SHADOW_WIN_STAKE_NOK", "25.0")),
        target_minutes_to_start=float(os.getenv("HBI_SHADOW_TARGET_MINUTES", "4.0")),
        max_win_bets_per_race=int(os.getenv("HBI_SHADOW_MAX_WIN_BETS_PER_RACE", "1")),
    )


def run_watcher(
    *,
    db_path: str,
    now: datetime | None = None,
    allow_sleep: bool = True,
) -> WatcherAudit:
    current = now or datetime.now(UTC)
    audit = WatcherAudit(started_at_utc=current.isoformat())
    store = _store(db_path)
    collector = RikstotoCollector(store)
    policy = _policy_from_env()

    races = collector.discover(current)
    audit.discovered = len(races)
    due = collector.due_races(now=current, min_minutes=1.0, max_minutes=8.0)
    audit.due_races = len(due)

    # Capture an early snapshot first. This creates market-path history even when
    # GitHub starts late and the ideal T-4 decision cannot be hit exactly.
    for race in due:
        raw = json.loads(str(race.get("raw_json") or "{}"))
        single_products = set(raw.get("single_leg_products") or [])
        inserted, failures = collector.collect_market(
            raceday_key=str(race["provider_raceday_key"]),
            race_number=int(race["race_number"]),
            race_id=str(race["race_id"]),
            observed_at=current,
            products=single_products,
        )
        audit.snapshots_inserted += inserted
        audit.fetch_failures += failures
        pool_inserted, pool_failures = collector.collect_pool_context(
            raceday_key=str(race["provider_raceday_key"]),
            products=list(raw.get("pools") or []),
            observed_at=current,
        )
        audit.snapshots_inserted += pool_inserted
        audit.fetch_failures += pool_failures

        fundamental_inserted, fundamental_ok, _ = collector.collect_fundamentals(
            raceday_key=str(race["provider_raceday_key"]),
            race_number=int(race["race_number"]),
            race_id=str(race["race_id"]),
            observed_at=current,
            products=[
                *list(raw.get("single_leg_products") or []),
                *list(raw.get("pools") or []),
            ],
        )
        audit.fundamental_snapshots_inserted += fundamental_inserted
        if not fundamental_ok:
            audit.fundamental_failures += 1

    target_schedule: list[tuple[datetime, dict[str, object]]] = []
    for race in due:
        start = datetime.fromisoformat(str(race["start_time_utc"]))
        target = start - timedelta(minutes=policy.target_minutes_to_start)
        target_schedule.append((target, race))
    target_schedule.sort(key=lambda item: item[0])

    for target, race in target_schedule:
        race_start = datetime.fromisoformat(str(race["start_time_utc"]))
        live_now = datetime.now(UTC) if now is None else current
        wait_seconds = (target - live_now).total_seconds()
        if allow_sleep and now is None and 0 < wait_seconds <= 300:
            time.sleep(wait_seconds)
            live_now = datetime.now(UTC)

        # If started already, do not manufacture a pre-race decision.
        if live_now >= race_start:
            audit.not_executable += 1
            continue

        raw = json.loads(str(race.get("raw_json") or "{}"))
        single_products = set(raw.get("single_leg_products") or [])
        inserted, failures = collector.collect_market(
            raceday_key=str(race["provider_raceday_key"]),
            race_number=int(race["race_number"]),
            race_id=str(race["race_id"]),
            observed_at=live_now,
            products=single_products,
        )
        audit.snapshots_inserted += inserted
        audit.fetch_failures += failures
        pool_inserted, pool_failures = collector.collect_pool_context(
            raceday_key=str(race["provider_raceday_key"]),
            products=list(raw.get("pools") or []),
            observed_at=live_now,
        )
        audit.snapshots_inserted += pool_inserted
        audit.fetch_failures += pool_failures

        fundamental_inserted, fundamental_ok, _ = collector.collect_fundamentals(
            raceday_key=str(race["provider_raceday_key"]),
            race_number=int(race["race_number"]),
            race_id=str(race["race_id"]),
            observed_at=live_now,
            products=[
                *list(raw.get("single_leg_products") or []),
                *list(raw.get("pools") or []),
            ],
        )
        audit.fundamental_snapshots_inserted += fundamental_inserted
        if fundamental_ok:
            fundamental_run = run_and_persist_fundamental(
                store,
                race_id=str(race["race_id"]),
                created_at=live_now,
            )
            audit.fundamental_runs += 1
            audit.fundamental_shadow_eligible += int(
                fundamental_run.shadow_eligible
            )
        else:
            audit.fundamental_failures += 1

        result = run_win_shadow_decision(
            store,
            race_id=str(race["race_id"]),
            provider_raceday_key=str(race["provider_raceday_key"]),
            race_start_at=race_start,
            decision_time=live_now,
            policy=policy,
        )
        record_decision_provenance(
            store,
            race_id=str(race["race_id"]),
            shadow_model_version=policy.model_version,
            target_minutes_to_start=policy.target_minutes_to_start,
            policy=asdict(policy),
            recorded_at=live_now,
        )
        if result.status == "SHADOW_BET":
            audit.shadow_bets_created += result.created
        elif result.status == "NOT_EXECUTABLE":
            audit.not_executable += 1
        else:
            audit.passes += 1

    audit.status = "OK"
    finished = datetime.now(UTC)
    audit.finished_at_utc = finished.isoformat()
    persist_run_manifest(
        store,
        run_type="WATCHER",
        started_at=datetime.fromisoformat(audit.started_at_utc),
        finished_at=finished,
        status=audit.status,
        model_version=policy.model_version,
        policy=asdict(policy),
        metadata=asdict(audit),
    )
    store.checkpoint()
    return audit


def main() -> None:
    db_path = os.getenv("HBI_DB_PATH", "data/hbi.sqlite")
    audit_path = Path(os.getenv("HBI_WATCHER_AUDIT_PATH", "watcher-audit.json"))
    audit = run_watcher(db_path=db_path)
    audit_path.write_text(json.dumps(asdict(audit), indent=2), encoding="utf-8")
    print(json.dumps(asdict(audit), indent=2))


if __name__ == "__main__":
    main()
