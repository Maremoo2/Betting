from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .fundamental import run_and_persist_fundamental
from .manifest import persist_run_manifest
from .provenance import record_decision_provenance
from .rikstoto_collector import RikstotoCollector
from .shadow import (
    ShadowPolicy,
    _decision_run_id,
    _persist_decision_run,
    run_win_shadow_decision,
)
from .storage import SQLiteStore
from .t4_evidence import classify_t4_receipt

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"
# Operational buffer only; T-4 cutoff itself is NEVER moved.
PRE_T4_REFRESH_LEAD = timedelta(seconds=60)


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
    # Additive evidence; never a substitute for private original WIN bytes.
    t4_attempts: list[dict[str, object]] = field(default_factory=list)


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


def _reject_missed_t4(
    store: SQLiteStore,
    *,
    race: dict[str, object],
    policy: ShadowPolicy,
    observed_now: datetime,
) -> bool:
    """Never promote a late watcher attempt to a qualified T-4 decision.

    Uses the existing immutable shadow decision row and existing NO BET reason.
    This does not change model probabilities, strategy thresholds or payouts.
    A previous immutable decision is never overwritten by a later run.
    """
    start = datetime.fromisoformat(str(race["start_time_utc"]))
    cutoff = start - timedelta(minutes=policy.target_minutes_to_start)
    if observed_now < cutoff:
        return False
    frozen_id = _decision_run_id(
        str(race["race_id"]), "V", policy.model_version,
        policy.target_minutes_to_start,
    )
    if store.get_shadow_decision_run(frozen_id) is None:
        _persist_decision_run(
            store,
            race_id=str(race["race_id"]),
            raceday_key=str(race["provider_raceday_key"]),
            race_start_at=start,
            decision_time=observed_now,
            policy=policy,
            status="NOT_EXECUTABLE",
            reason="T4_CUTOFF_MISSED",
        )
    return True


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
        # Do not wake AT T-4 and only then start network/model work. Plan
        # the final source refresh before the unchanged T-4 cutoff.
        wait_seconds = (target - PRE_T4_REFRESH_LEAD - live_now).total_seconds()
        if allow_sleep and now is None and 0 < wait_seconds <= 300:
            time.sleep(wait_seconds)
            live_now = datetime.now(UTC)

        # GitHub schedule lag, source latency and earlier races can all push
        # this attempt beyond T-4. Fail closed before a fresh source request.
        if _reject_missed_t4(store, race=race, policy=policy, observed_now=live_now):
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
        # Decisions must occur after provider responses, never at request start.
        if now is None:
            live_now = datetime.now(UTC)
        if _reject_missed_t4(store, race=race, policy=policy, observed_now=live_now):
            audit.not_executable += 1
            continue
        model_finished_at: datetime | None = None
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
            if now is None and hasattr(fundamental_run, "run_id"):
                model_finished_at = datetime.now(UTC)
        else:
            audit.fundamental_failures += 1

        # Recheck AFTER model evaluation/persistence. Its pre-calculation
        # timestamp cannot certify that the computation finished before T-4.
        if now is None:
            live_now = datetime.now(UTC)
        if _reject_missed_t4(store, race=race, policy=policy, observed_now=live_now):
            audit.not_executable += 1
            continue

        marks: dict[str, datetime] = {}

        result = run_win_shadow_decision(
            store,
            race_id=str(race["race_id"]),
            provider_raceday_key=str(race["provider_raceday_key"]),
            race_start_at=race_start,
            decision_time=live_now,
            policy=policy,
            # The synthetic clock-injected test path is never a real T-4
            # attestation. Live calls explicitly use the absolute deadline.
            t4_cutoff=target if now is None else None,
            milestone=marks.__setitem__,
        )
        # Read back the committed row before taking the independent clock.
        frozen_id = _decision_run_id(
            str(race["race_id"]), "V", policy.model_version,
            policy.target_minutes_to_start,
        )
        committed = store.get_shadow_decision_run(frozen_id)
        # Fake clock / mocked shadow calls cannot supply a real commit marker.
        verified_at = (
            datetime.now(UTC)
            if now is None and marks.get("DECISION_PERSISTED") is not None
            else None
        )
        source_receipts = getattr(collector, "source_receipts", {})
        bound_sources = {
            label: source_receipts.get((str(race["race_id"]), code), {})
            for label, code in (
                ("WIN", "V"), ("STARTS", "STARTS"), ("SCRATCHED", "SCRATCHED"),
            )
        }
        receipt = classify_t4_receipt(
            race_id=str(race["race_id"]),
            race_start_utc=race_start.isoformat(),
            target_minutes=policy.target_minutes_to_start,
            model_version=policy.model_version,
            decision_row=committed,
            sources=bound_sources,
            model_finished_at_utc=(
                None if model_finished_at is None
                else model_finished_at.isoformat()
            ),
            decision_calculated_at_utc=(
                None if marks.get("DECISION_CALCULATED") is None
                else marks["DECISION_CALCULATED"].isoformat()
            ),
            persist_started_at_utc=(
                None if marks.get("PERSIST_STARTED") is None
                else marks["PERSIST_STARTED"].isoformat()
            ),
            persist_confirmed_at_utc=(
                None if verified_at is None else verified_at.isoformat()
            ),
            github_sha=os.getenv("GITHUB_SHA"),
        )
        audit.t4_attempts.append(receipt)
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
        elif result.status in {"NOT_EXECUTABLE", "T4_PENDING_ATTESTATION"}:
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
