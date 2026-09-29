from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .providers.pmu import PmuClient
from .rikstoto_collector import RikstotoCollector
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"


def _normalize(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in ascii_value if ch.isalnum())


def _track_name(reunion: dict[str, object]) -> str:
    value = reunion.get("hippodrome")
    if isinstance(value, dict):
        return str(
            value.get("libelleCourt")
            or value.get("libelleLong")
            or value.get("libelle")
            or ""
        )
    return str(value or reunion.get("libelle") or "")


@dataclass
class PmuProbe:
    rikstoto_track: str
    rikstoto_race_number: int
    rikstoto_start_time_utc: str
    programme_ok: bool
    reunion_number: int | None = None
    pmu_track: str | None = None
    participant_count: int = 0
    participant_keys: list[str] = field(default_factory=list)
    performance_participant_count: int = 0
    performance_keys: list[str] = field(default_factory=list)
    history_item_keys: list[str] = field(default_factory=list)
    subject_history_participant_keys: list[str] = field(default_factory=list)
    participant_field_presence: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def run_probe() -> PmuProbe:
    now = datetime.now(UTC)
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteStore(Path(tmp) / "probe.sqlite")
        store.initialize(SCHEMA)
        if MIGRATIONS.exists():
            store.apply_migrations(MIGRATIONS)
        collector = RikstotoCollector(store)
        races = collector.discover(now)
        french = sorted(
            (
                race
                for race in races
                if race.country_code == "FR"
                and race.start_time > now
                and "V" in race.single_leg_products
            ),
            key=lambda race: race.start_time,
        )
        if not french:
            return PmuProbe(
                rikstoto_track="",
                rikstoto_race_number=0,
                rikstoto_start_time_utc="",
                programme_ok=False,
                errors=["NO_FUTURE_FRENCH_WIN_RACE"],
            )
        race = french[0]
        pmu = PmuClient()
        programme = pmu.programme(race.start_time.date())
        probe = PmuProbe(
            rikstoto_track=race.raceday_name or race.track_code,
            rikstoto_race_number=race.race_number,
            rikstoto_start_time_utc=race.start_time.isoformat(),
            programme_ok=programme.success,
        )
        if not programme.success:
            probe.errors.append(f"PROGRAMME_FETCH_FAILED:{programme.status_code}")
            return probe

        target = _normalize(probe.rikstoto_track)
        reunions = pmu.reunions(programme)
        matching = [
            reunion
            for reunion in reunions
            if _normalize(_track_name(reunion)) == target
            or target in _normalize(_track_name(reunion))
            or _normalize(_track_name(reunion)) in target
        ]
        if len(matching) != 1:
            probe.errors.append(
                "REUNION_MATCH_COUNT:"
                + str(len(matching))
                + ":"
                + ",".join(_track_name(item) for item in reunions)
            )
            return probe

        reunion = matching[0]
        try:
            reunion_number = int(reunion.get("numOfficiel"))
        except (TypeError, ValueError):
            probe.errors.append("MISSING_REUNION_NUMBER")
            return probe
        probe.reunion_number = reunion_number
        probe.pmu_track = _track_name(reunion)

        participants = pmu.participants(
            race.start_time.date(),
            reunion_number,
            race.race_number,
        )
        rows = pmu.participant_rows(participants)
        probe.participant_count = len(rows)
        if not rows:
            probe.errors.append(
                f"PARTICIPANTS_EMPTY:{participants.status_code}:{participants.error}"
            )
            return probe
        probe.participant_keys = sorted({key for row in rows for key in row})
        wanted = (
            "nom",
            "numPmu",
            "age",
            "sexe",
            "entraineur",
            "driver",
            "jockey",
            "nombreCourses",
            "nombreVictoires",
            "nombrePlaces",
            "nombrePlacesSecond",
            "nombrePlacesTroisieme",
            "gainsParticipant",
            "musique",
        )
        probe.participant_field_presence = {
            key: sum(row.get(key) is not None for row in rows)
            for key in wanted
        }

        performances = pmu.performances(
            race.start_time.date(),
            reunion_number,
            race.race_number,
        )
        perf_rows = pmu.performance_rows(performances)
        probe.performance_participant_count = len(perf_rows)
        if perf_rows:
            probe.performance_keys = sorted(
                {key for row in perf_rows for key in row}
            )
            history_items = [
                history
                for row in perf_rows
                for history in (row.get("coursesCourues") or [])
                if isinstance(history, dict)
            ]
            if history_items:
                probe.history_item_keys = sorted(
                    {key for history in history_items for key in history}
                )
                subject_rows = [
                    participant
                    for history in history_items
                    for participant in (history.get("participants") or [])
                    if isinstance(participant, dict) and participant.get("itsHim")
                ]
                if subject_rows:
                    probe.subject_history_participant_keys = sorted(
                        {key for row in subject_rows for key in row}
                    )
        else:
            probe.errors.append(
                f"PERFORMANCES_EMPTY:{performances.status_code}:{performances.error}"
            )
        return probe


def main() -> None:
    probe = run_probe()
    payload = asdict(probe)
    path = Path(os.getenv("HBI_PMU_PROBE_PATH", "pmu-live-probe.json"))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if probe.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
