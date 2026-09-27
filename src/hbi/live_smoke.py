from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .fundamental import run_and_persist_fundamental
from .providers.rikstoto import RikstotoClient
from .rikstoto_collector import RikstotoCollector
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
    selected_country: str | None = None
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
    probes: list[dict[str, object]] = field(default_factory=list)
    failed_fetches: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None


def _store(path: str | Path) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)
    return store


def _race_priority(race, now: datetime) -> tuple[int, int, datetime]:
    country_rank = {"NO": 0, "SE": 1, "DK": 2}.get(race.country_code, 3)
    future_rank = 0 if race.start_time > now else 1
    return future_rank, country_rank, race.start_time


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

    candidates = sorted(
        (race for race in races if "V" in race.single_leg_products),
        key=lambda race: _race_priority(race, now),
    )
    if not candidates:
        candidates = sorted(races, key=lambda race: _race_priority(race, now))

    distinct = []
    seen_racedays: set[str] = set()
    for race in candidates:
        if race.raceday_key in seen_racedays:
            continue
        seen_racedays.add(race.raceday_key)
        distinct.append(race)
        if len(distinct) >= 8:
            break

    selected = distinct[0]
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(Path(tmp) / "live-smoke.sqlite")
        collector = RikstotoCollector(store, client)
        collector.discover(now)

        successful = None
        for race in distinct:
            inserted, ok, source = collector.collect_fundamentals(
                raceday_key=race.raceday_key,
                race_number=race.race_number,
                race_id=race.race_id,
                observed_at=now,
                products=[
                    *race.single_leg_products,
                    *race.pools,
                ],
            )
            result.probes.append(
                {
                    "race_id": race.race_id,
                    "country": race.country_code,
                    "track": race.raceday_name or race.track_code,
                    "race_number": race.race_number,
                    "start_time_utc": race.start_time.isoformat(),
                    "single_leg_products": list(race.single_leg_products),
                    "pools": list(race.pools),
                    "fundamental_ok": ok,
                    "fundamental_snapshots": inserted,
                    "source": source,
                }
            )
            if ok and inserted >= 2:
                successful = race
                break

        selected = successful or selected
        result.selected_race_id = selected.race_id
        result.selected_raceday_key = selected.raceday_key
        result.selected_race_number = selected.race_number
        result.selected_country = selected.country_code
        result.selected_track = selected.raceday_name or selected.track_code
        result.selected_start_time_utc = selected.start_time.isoformat()
        result.win_market_supported = "V" in selected.single_leg_products

        if successful is not None:
            result.fundamental_endpoint_ok = True
            rows = store.latest_runner_fundamentals(selected.race_id, before=now)
            result.fundamental_snapshots = len(rows)
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

        audits = store.fetch_table("provider_fetch_audit")
        failed = [row for row in audits if not bool(row["success"])]
        result.provider_fetch_failures = len(failed)
        result.failed_fetches = [
            {
                "endpoint": row["endpoint"],
                "status_code": row["status_code"],
                "error_message": row["error_message"],
            }
            for row in failed[-30:]
        ]

    if not result.fundamental_endpoint_ok:
        result.error = "no usable Rikstoto base-program fundamentals across smoke probes"
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
