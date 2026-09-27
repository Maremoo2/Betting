from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .domain import MarketSnapshot


@dataclass
class SQLiteStore:
    """Persistent source-of-truth store for HBI.

    Google Sheets/Drive may mirror/export these records, but must not replace the
    canonical point-in-time database.
    """

    path: str | Path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self, schema_path: str | Path) -> None:
        schema = Path(schema_path).read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema)

    def upsert_race(self, race: dict[str, object]) -> None:
        columns = (
            "race_id", "race_date", "country", "track", "race_no", "start_time_utc",
            "discipline", "distance_m", "start_method", "race_class", "created_at_utc",
        )
        values = [race.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO races ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(race_id) DO UPDATE SET "
                "race_date=excluded.race_date,country=excluded.country,track=excluded.track,"
                "race_no=excluded.race_no,start_time_utc=excluded.start_time_utc,"
                "discipline=excluded.discipline,distance_m=excluded.distance_m,"
                "start_method=excluded.start_method,race_class=excluded.race_class",
                values,
            )

    def upsert_runner(self, runner: dict[str, object]) -> None:
        columns = (
            "race_id", "selection_id", "horse_name", "post_position", "driver_or_jockey",
            "trainer", "scratched",
        )
        values = [runner.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO runners ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(race_id,selection_id) DO UPDATE SET "
                "horse_name=excluded.horse_name,post_position=excluded.post_position,"
                "driver_or_jockey=excluded.driver_or_jockey,trainer=excluded.trainer,"
                "scratched=excluded.scratched",
                values,
            )

    def insert_market_snapshot(self, snapshot: MarketSnapshot, source_uri: str | None = None) -> bool:
        """Insert one immutable snapshot. Duplicate timestamped snapshots are idempotent."""
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO market_snapshots "
                "(race_id,selection_id,captured_at_utc,odds_decimal,pool_size,market_regime,"
                "information_cutoff_phase,source_uri) VALUES (?,?,?,?,?,?,?,?)",
                (
                    snapshot.race_id,
                    snapshot.selection_id,
                    snapshot.captured_at.isoformat(),
                    snapshot.odds_decimal,
                    snapshot.pool_size,
                    snapshot.market_regime,
                    snapshot.information_cutoff_phase,
                    source_uri,
                ),
            )
            return cursor.rowcount == 1

    def insert_prediction(
        self,
        *,
        prediction_id: str,
        race_id: str,
        selection_id: str,
        created_at: datetime,
        model_name: str,
        model_version: str,
        layer: str,
        probability: float,
        feature_as_of: datetime,
    ) -> None:
        """Insert a frozen prediction; an existing prediction_id may never be rewritten."""
        if feature_as_of > created_at:
            raise ValueError("feature_as_of cannot be after prediction creation time")
        with self.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO predictions "
                    "(prediction_id,race_id,selection_id,created_at_utc,model_name,model_version,"
                    "layer,probability,feature_as_of_utc,frozen) VALUES (?,?,?,?,?,?,?,?,?,1)",
                    (
                        prediction_id, race_id, selection_id, created_at.isoformat(), model_name,
                        model_version, layer, probability, feature_as_of.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"frozen prediction already exists: {prediction_id}") from exc

    def fetch_market_snapshots(self, race_id: str, selection_id: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM market_snapshots WHERE race_id=? AND selection_id=? "
                    "ORDER BY captured_at_utc",
                    (race_id, selection_id),
                )
            )

    def count(self, table: str) -> int:
        allowed = {
            "races", "runners", "evidence", "market_snapshots", "predictions",
            "race_diagnostics", "model_versions", "decisions", "review_flags",
            "prewatch_events", "outcomes",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        with self.connect() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
