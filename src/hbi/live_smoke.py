"""Read-only live acceptance: schemas alone never enable provider/country pairs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .fundamental import run_and_persist_fundamental
from .provider_capability import capability
from .rikstoto_collector import RikstotoCollector
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"


@dataclass
class SmokeReport:
    observed_at_utc: str
    races_discovered: int = 0
    probes: list[dict] = field(default_factory=list)
    verified_countries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    acceptance_scope: str = "NO_SE_TROT_PRODUCT_V1"
    required_countries: list[str] = field(default_factory=lambda: ["NO", "SE"])
    candidate_races_by_country: dict[str, int] = field(default_factory=dict)


def _store(path: str | Path) -> SQLiteStore:
    store = SQLiteStore(path)
    store.initialize(SCHEMA)
    store.apply_migrations(MIGRATIONS)
    return store


def run_live_smoke() -> SmokeReport:
    now = datetime.now(UTC)
    report = SmokeReport(observed_at_utc=now.isoformat())
    required = {part.strip().upper() for part in
                os.getenv("HBI_SMOKE_REQUIRED_COUNTRIES", "NO,SE").split(",") if part.strip()}
    # The product contract cannot accidentally drop one of its two countries.
    # DK/FR use the same unchanged gates in a separate diagnostic job.
    if required not in ({"NO", "SE"}, {"DK", "FR"}):
        raise ValueError("PROVIDER_SMOKE_SCOPE_MUST_BE_NO_SE_OR_DIAGNOSTIC_DK_FR")
    report.required_countries = sorted(required)
    if required == {"DK", "FR"}:
        report.acceptance_scope = "DK_FR_TROT_DIAGNOSTIC_V1"
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(Path(tmp) / "smoke.sqlite")
        collector = RikstotoCollector(store)
        races = collector.discover(now)
        report.races_discovered = len(races)
        meetings = {}
        for race in sorted(races, key=lambda r: r.start_time):
            if (race.start_time > now and race.country_code in required
                    and race.progress_status == "Future"
                    and collector._discipline(race.sport_type) == "trot"):
                meetings.setdefault(race.raceday_key, []).append(race)
                report.candidate_races_by_country[race.country_code] = (
                    report.candidate_races_by_country.get(race.country_code, 0) + 1)
        # Test each meeting before testing further races. Bounded requests, no polling loop.
        selected = [
            meeting[i] for i in range(3) for meeting in meetings.values() if len(meeting) > i
        ]
        for race in selected[:60]:
            pair = capability("atg", race.country_code, collector._discipline(race.sport_type))
            if race.country_code in report.verified_countries:
                continue
            collector.capability_probe = pair["status"] != "VERIFIED"
            collector.collect_fundamentals(
                raceday_key=race.raceday_key,
                race_number=race.race_number,
                race_id=race.race_id,
                observed_at=datetime.now(UTC),
            )
            evidence = dict(collector.last_capability)
            evidence.update(
                race_id=race.race_id, track=race.raceday_name, registry_status=pair["status"]
            )
            decision_time = datetime.now(UTC)
            run = run_and_persist_fundamental(store, race_id=race.race_id, created_at=decision_time)
            evidence["shadow_eligible"] = run.shadow_eligible
            if collector.capability_probe and run.shadow_eligible:
                report.errors.append(f"UNVERIFIED_PAIR_ESCAPED_GATE:{race.race_id}")
            if evidence["passed"] and not collector.capability_probe:
                if not run.shadow_eligible or run.history_coverage != 1:
                    report.errors.append(f"RUNTIME_GATE_MISMATCH:{race.race_id}")
                else:
                    report.verified_countries.append(race.country_code)
            elif run.shadow_eligible:
                report.errors.append(f"FAILED_FIELD_ESCAPED_GATE:{race.race_id}")
            report.probes.append(evidence)
        for country in sorted(required - set(report.verified_countries)):
            report.errors.append(f"NO_FULL_FIELD_LIVE_PASS:{country}")
        if len(report.verified_countries) < 2:
            report.errors.append("MULTI_COUNTRY_EVIDENCE_MISSING")
    return report


def main() -> None:
    payload = asdict(run_live_smoke())
    output = Path(os.getenv("HBI_LIVE_SMOKE_PATH", "live-smoke.json"))
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "probes"}, indent=2))
    for p in payload["probes"]:
        print(
            p["country"],
            p["track"],
            p["race_id"],
            p["passed"],
            f"{p['matched_complete_runners']}/{p['active_runners']}",
            p["reasons"],
        )
    if payload["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
