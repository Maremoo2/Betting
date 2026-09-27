from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .fundamental import run_and_persist_fundamental
from .rikstoto_collector import RikstotoCollector
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"


@dataclass
class RaceProbe:
    country: str
    track: str
    race_id: str
    race_number: int
    start_time_utc: str
    starts_ok: bool
    fundamental_rows: int
    known_history_rows: int
    history_coverage: float
    model_status: str | None
    shadow_eligible: bool | None
    win_market_rows: int
    fetch_failures: int


@dataclass
class SmokeReport:
    observed_at_utc: str
    races_discovered: int = 0
    norway: RaceProbe | None = None
    sweden: RaceProbe | None = None
    errors: list[str] = field(default_factory=list)


def _store(path: str | Path) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)
    return store


def _pick(races, country: str, now: datetime):
    candidates = [
        race
        for race in races
        if race.country_code == country
        and race.sport_type == "T"
        and race.start_time > now
        and "V" in race.single_leg_products
    ]
    candidates.sort(key=lambda race: race.start_time)
    return candidates[0] if candidates else None


def _probe(collector: RikstotoCollector, race, now: datetime) -> RaceProbe:
    before_failures = sum(
        1
        for row in collector.store.fetch_table("provider_fetch_audit")
        if not bool(row["success"])
    )
    inserted, ok, _ = collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=race.race_number,
        race_id=race.race_id,
        observed_at=now,
    )
    rows = collector.store.latest_runner_fundamentals(race.race_id, before=now)
    known = sum(
        1
        for row in rows
        if row.get("history_total_starts") is not None
        and row.get("history_total_wins") is not None
        and not bool(row.get("scratched"))
    )
    active = sum(1 for row in rows if not bool(row.get("scratched")))
    coverage = 0.0 if active == 0 else known / active

    model_status = None
    shadow_eligible = None
    if ok and rows:
        run = run_and_persist_fundamental(
            collector.store,
            race_id=race.race_id,
            created_at=now,
        )
        model_status = run.status
        shadow_eligible = run.shadow_eligible

    market_rows, _ = collector.collect_market(
        raceday_key=race.raceday_key,
        race_number=race.race_number,
        race_id=race.race_id,
        observed_at=now,
        products={"V"},
    )
    after_failures = sum(
        1
        for row in collector.store.fetch_table("provider_fetch_audit")
        if not bool(row["success"])
    )

    return RaceProbe(
        country=race.country_code,
        track=race.raceday_name or race.track_code,
        race_id=race.race_id,
        race_number=race.race_number,
        start_time_utc=race.start_time.isoformat(),
        starts_ok=ok,
        fundamental_rows=inserted,
        known_history_rows=known,
        history_coverage=coverage,
        model_status=model_status,
        shadow_eligible=shadow_eligible,
        win_market_rows=market_rows,
        fetch_failures=after_failures - before_failures,
    )


def run_live_smoke() -> SmokeReport:
    now = datetime.now(UTC)
    report = SmokeReport(observed_at_utc=now.isoformat())

    with tempfile.TemporaryDirectory() as tmp:
        store = _store(Path(tmp) / "live-smoke.sqlite")
        collector = RikstotoCollector(store)
        races = collector.discover(now)
        report.races_discovered = len(races)

        norway = _pick(races, "NO", now)
        sweden = _pick(races, "SE", now)

        if norway is None:
            report.errors.append("NO_FUTURE_NORWEGIAN_WIN_RACE")
        else:
            report.norway = _probe(collector, norway, now)
            if not report.norway.starts_ok or report.norway.fundamental_rows < 2:
                report.errors.append("NORWAY_STARTS_FAILED")

        if sweden is None:
            report.errors.append("NO_FUTURE_SWEDISH_WIN_RACE")
        else:
            report.sweden = _probe(collector, sweden, now)
            if not report.sweden.starts_ok or report.sweden.fundamental_rows < 2:
                report.errors.append("SWEDEN_STARTS_FAILED")
            elif report.sweden.history_coverage < 0.80:
                report.errors.append("SWEDEN_ATG_HISTORY_COVERAGE_BELOW_80_PCT")

    return report


def main() -> None:
    report = run_live_smoke()
    payload = asdict(report)
    output = Path(os.getenv("HBI_LIVE_SMOKE_PATH", "live-smoke.json"))
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if report.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
