from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .fundamental import run_and_persist_fundamental
from .rikstoto_collector import RikstotoCollector
from .providers.rikstoto import RikstotoClient
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"


@dataclass
class LiveSmokeResult:
    observed_at_utc: str
    settings_ok: bool = False
    racedays_ok: bool = False
    races_discovered: int = 0
    selected_race_id: str | None = None
    selected_raceday_key: str | None = None
    selected_race_number: int | None = None
    selected_track: str | None = None
    selected_start_time_utc: str | None = None
    fundamental_endpoint_ok: bool = False
    fundamental_snapshots: int = 0
    fundamental_model_status: str | None = None
    fundamental_shadow_eligible: bool | None = None
    fundamental_history_coverage: float | None = None
    fundamental_probabilities: dict[str, float] | None = None
    win_market_supported: bool = False
    win_market_rows: int = 0
    provider_fetch_failures: int = 0
    error: str | None = None


def _store(path: str | Path) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)
    return store


def run_live_smoke() -> LiveSmokeResult:
    now = datetime.now(UTC)
    result = LiveSmokeResult(observed_at_utc=now.isoformat())
    client = RikstotoClient(timeout=20.0)

    settings = client.settings_urls()
    result.settings_ok = settings.success
    if not settings.success:
        result.error = f"settings endpoint failed: {settings.status_code} {settings.error}"
        return result

    racedays = client.racedays()
    result.racedays_ok = racedays.success
    if not racedays.success:
        result.error = f"racedays endpoint failed: {racedays.status_code} {racedays.error}"
        return result

    races = client.discover_races(racedays)
    result.races_discovered = len(races)
    if not races:
        result.error = "racedays endpoint returned no races"
        return result

    future = sorted(
        (race for race in races if race.start_time > now),
        key=lambda race: race.start_time,
    )
    ordered = future or sorted(races, key=lambda race: race.start_time, reverse=True)
    selected = next(
        (race for race in ordered if "V" in race.single_leg_products),
        ordered[0],
    )

    result.selected_race_id = selected.race_id
    result.selected_raceday_key = selected.raceday_key
    result.selected_race_number = selected.race_number
    result.selected_track = selected.raceday_name or selected.track_code
    result.selected_start_time_utc = selected.start_time.isoformat()
    result.win_market_supported = "V" in selected.single_leg_products

    with tempfile.TemporaryDirectory() as tmp:
        store = _store(Path(tmp) / "live-smoke.sqlite")
        collector = RikstotoCollector(store, client)
        collector.discover(now)

        fundamental_inserted, fundamental_ok, _ = collector.collect_fundamentals(
            raceday_key=selected.raceday_key,
            race_number=selected.race_number,
            race_id=selected.race_id,
            observed_at=now,
            products=[
                *selected.single_leg_products,
                *selected.pools,
            ],
        )
        result.fundamental_endpoint_ok = fundamental_ok
        result.fundamental_snapshots = fundamental_inserted

        if fundamental_ok:
            run = run_and_persist_fundamental(
                store,
                race_id=selected.race_id,
                created_at=now,
            )
            result.fundamental_model_status = run.status
            result.fundamental_shadow_eligible = run.shadow_eligible
            result.fundamental_history_coverage = run.history_coverage
            result.fundamental_probabilities = run.probabilities

        if result.win_market_supported:
            inserted, failures = collector.collect_market(
                raceday_key=selected.raceday_key,
                race_number=selected.race_number,
                race_id=selected.race_id,
                observed_at=now,
                products={"V"},
            )
            result.win_market_rows = inserted
            result.provider_fetch_failures += failures

        result.provider_fetch_failures += sum(
            1
            for row in store.fetch_table("provider_fetch_audit")
            if not bool(row["success"])
        )

    if not result.fundamental_endpoint_ok:
        result.error = "no usable Rikstoto base-program fundamentals for selected race"
    return result


def main() -> None:
    output_path = Path(os.getenv("HBI_LIVE_SMOKE_PATH", "live-smoke.json"))
    result = run_live_smoke()
    payload = asdict(result)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if not result.settings_ok or not result.racedays_ok or not result.fundamental_endpoint_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
