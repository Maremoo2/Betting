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
    discipline: str
    track: str
    race_id: str
    race_number: int
    start_time_utc: str
    starts_ok: bool
    active_runners: int
    fundamental_rows: int
    enriched_runners: int
    full_field_history_complete: bool
    history_coverage: float
    identity_methods: dict[str, int]
    model_status: str | None
    shadow_eligible: bool | None
    win_market_rows: int
    fetch_failures: int


@dataclass
class SmokeReport:
    observed_at_utc: str
    races_discovered: int = 0
    countries_discovered: list[str] = field(default_factory=list)
    probes: list[RaceProbe] = field(default_factory=list)
    full_data_countries: list[str] = field(default_factory=list)
    field_only_countries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _store(path: str | Path) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)
    return store


def _pick_by_country(races, now: datetime):
    chosen = {}
    for race in sorted(races, key=lambda item: item.start_time):
        if (
            race.start_time <= now
            or "V" not in race.single_leg_products
            or not race.country_code
        ):
            continue
        chosen.setdefault(race.country_code, race)
    return list(chosen.values())


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
    active_rows = [row for row in rows if not bool(row.get("scratched"))]
    enriched = [
        row
        for row in active_rows
        if bool(row.get("full_field_history_complete"))
        and row.get("history_total_starts") is not None
        and row.get("history_total_wins") is not None
    ]
    coverage = 0.0 if not active_rows else len(enriched) / len(active_rows)
    full_complete = bool(active_rows) and len(enriched) == len(active_rows)
    methods: dict[str, int] = {}
    for row in active_rows:
        method = str(row.get("identity_match_method") or "NONE")
        methods[method] = methods.get(method, 0) + 1

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
        discipline="trot" if race.sport_type == "T" else "gallop",
        track=race.raceday_name or race.track_code,
        race_id=race.race_id,
        race_number=race.race_number,
        start_time_utc=race.start_time.isoformat(),
        starts_ok=ok,
        active_runners=len(active_rows),
        fundamental_rows=inserted,
        enriched_runners=len(enriched),
        full_field_history_complete=full_complete,
        history_coverage=coverage,
        identity_methods=methods,
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
        report.countries_discovered = sorted(
            {race.country_code for race in races if race.country_code}
        )

        selected = _pick_by_country(races, now)
        if not selected:
            report.errors.append("NO_FUTURE_WIN_RACES")
            return report

        for race in selected:
            probe = _probe(collector, race, now)
            report.probes.append(probe)
            if probe.full_field_history_complete and probe.shadow_eligible:
                report.full_data_countries.append(probe.country)
            else:
                report.field_only_countries.append(probe.country)

        report.full_data_countries = sorted(set(report.full_data_countries))
        report.field_only_countries = sorted(set(report.field_only_countries))

        if not report.full_data_countries:
            report.errors.append("NO_FULL_FIELD_ENRICHMENT_VERIFIED")
        if not any(probe.starts_ok and probe.win_market_rows > 0 for probe in report.probes):
            report.errors.append("NO_RIKSTOTO_FIELD_AND_WIN_MARKET_VERIFIED")

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
