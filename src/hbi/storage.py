from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .domain import MarketSnapshot
from .prewatch import MaterialChange


@dataclass
class SQLiteStore:
    """Persistent source-of-truth store for HBI.

    Google Sheets/Drive may mirror/export these records, but must not replace the
    canonical point-in-time database.
    """

    path: str | Path

    def connect(self) -> sqlite3.Connection:
        if str(self.path) != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        if str(self.path) != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self, schema_path: str | Path) -> None:
        schema = Path(schema_path).read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema)

    def apply_migrations(self, migrations_dir: str | Path) -> list[str]:
        """Apply *.sql files once, in filename order."""
        directory = Path(migrations_dir)
        applied: list[str] = []
        with self.connect() as connection:
            known = {
                row[0]
                for row in connection.execute(
                    "SELECT migration_id FROM schema_migrations"
                )
            }
            for path in sorted(directory.glob("*.sql")):
                migration_id = path.name
                if migration_id in known:
                    continue
                connection.executescript(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (migration_id,applied_at_utc) "
                    "VALUES (?,?)",
                    (migration_id, datetime.now().astimezone().isoformat()),
                )
                applied.append(migration_id)
        return applied

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

    def get_race(self, race_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM races WHERE race_id=?",
                (race_id,),
            ).fetchone()

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

    def latest_market_snapshot(
        self,
        race_id: str,
        selection_id: str,
        *,
        before: datetime | None = None,
    ) -> sqlite3.Row | None:
        query = (
            "SELECT * FROM market_snapshots WHERE race_id=? AND selection_id=?"
        )
        params: list[object] = [race_id, selection_id]
        if before is not None:
            query += " AND captured_at_utc < ?"
            params.append(before.isoformat())
        query += " ORDER BY captured_at_utc DESC LIMIT 1"
        with self.connect() as connection:
            return connection.execute(query, params).fetchone()

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
        if not 0 < probability <= 1:
            raise ValueError("probability must be in (0, 1]")
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

    def insert_prewatch_event(
        self,
        *,
        race_id: str,
        captured_at: datetime,
        change: MaterialChange,
        policy_version: str = "v1",
    ) -> str:
        event_id = str(uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO prewatch_events "
                "(event_id,race_id,selection_id,captured_at_utc,action,reasons_json,"
                "probability_move_pp,relative_odds_move_pct,pool_growth_pct,minutes_to_start,"
                "policy_version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    race_id,
                    change.selection_id,
                    captured_at.isoformat(),
                    change.action.value,
                    json.dumps(change.reasons),
                    change.probability_move_pp,
                    change.relative_odds_move_pct,
                    change.pool_growth_pct,
                    change.minutes_to_start,
                    policy_version,
                ),
            )
        return event_id

    def insert_review_flag(
        self,
        *,
        flag_id: str,
        race_id: str,
        flag_type: str,
        source_uri: str,
        source_published_at: datetime,
        captured_at: datetime,
        selection_id: str | None = None,
        note: str = "",
        confidence: float = 1.0,
    ) -> None:
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if source_published_at > captured_at:
            raise ValueError("source_published_at cannot be after captured_at")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO review_flags "
                "(flag_id,race_id,selection_id,flag_type,note,source_uri,"
                "source_published_at_utc,captured_at_utc,confidence) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    flag_id,
                    race_id,
                    selection_id,
                    flag_type,
                    note,
                    source_uri,
                    source_published_at.isoformat(),
                    captured_at.isoformat(),
                    confidence,
                ),
            )

    def insert_decision(self, decision: dict[str, object]) -> None:
        columns = (
            "decision_id", "race_id", "selection_id", "decision_time_utc", "decision",
            "fundamental_p", "market_p", "combined_p", "fair_odds", "available_price",
            "minimum_price", "expected_close_price", "actual_close_price", "closing_line_value",
            "model_market_conflict_score", "race_difficulty_score", "reject_reason", "stake_nok",
        )
        values = [decision.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO decisions ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )

    def settle_outcome(
        self,
        *,
        race_id: str,
        winner_selection_id: str,
        settled_at: datetime,
        actual_close_price: float | None = None,
        gross_return_nok: float | None = None,
        net_pnl_nok: float | None = None,
    ) -> None:
        """Idempotently persist settlement data without changing frozen predictions."""
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO outcomes "
                "(race_id,winner_selection_id,settled_at_utc,actual_close_price,"
                "gross_return_nok,net_pnl_nok) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(race_id) DO UPDATE SET "
                "winner_selection_id=excluded.winner_selection_id,"
                "settled_at_utc=excluded.settled_at_utc,"
                "actual_close_price=excluded.actual_close_price,"
                "gross_return_nok=excluded.gross_return_nok,"
                "net_pnl_nok=excluded.net_pnl_nok",
                (
                    race_id,
                    winner_selection_id,
                    settled_at.isoformat(),
                    actual_close_price,
                    gross_return_nok,
                    net_pnl_nok,
                ),
            )

    def fetch_market_snapshots(self, race_id: str, selection_id: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM market_snapshots WHERE race_id=? AND selection_id=? "
                    "ORDER BY captured_at_utc",
                    (race_id, selection_id),
                )
            )

    def fetch_table(self, table: str) -> list[dict[str, object]]:
        allowed = {
            "races", "runners", "evidence", "market_snapshots", "predictions",
            "race_diagnostics", "model_versions", "decisions", "review_flags",
            "prewatch_events", "outcomes",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]

    def count(self, table: str) -> int:
        allowed = {
            "races", "runners", "evidence", "market_snapshots", "predictions",
            "race_diagnostics", "model_versions", "decisions", "review_flags",
            "prewatch_events", "outcomes", "schema_migrations",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        with self.connect() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
