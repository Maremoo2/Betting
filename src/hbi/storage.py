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
                if migration_id == "0006_international_full_field_enrichment.sql":
                    existing_columns = {
                        row[1]
                        for row in connection.execute(
                            "PRAGMA table_info(runner_fundamental_snapshots)"
                        )
                    }
                    additions = {
                        "enrichment_provider": "TEXT",
                        "identity_match_method": "TEXT",
                        "identity_match_confidence": "REAL",
                        "full_field_history_complete": "INTEGER NOT NULL DEFAULT 0",
                    }
                    for column, declaration in additions.items():
                        if column not in existing_columns:
                            connection.execute(
                                f"ALTER TABLE runner_fundamental_snapshots "
                                f"ADD COLUMN {column} {declaration}"
                            )
                else:
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

    def upsert_provider_race_ref(
        self,
        *,
        provider: str,
        provider_raceday_key: str,
        race_number: int,
        race_id: str,
        provider_track_code: str | None,
        provider_start_time_raw: str | None,
        discovered_at: datetime,
        raw: dict[str, object] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO provider_race_refs "
                "(provider,provider_raceday_key,race_number,race_id,provider_track_code,"
                "provider_start_time_raw,discovered_at_utc,raw_json) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(provider,provider_raceday_key,race_number) DO UPDATE SET "
                "race_id=excluded.race_id,provider_track_code=excluded.provider_track_code,"
                "provider_start_time_raw=excluded.provider_start_time_raw,"
                "discovered_at_utc=excluded.discovered_at_utc,raw_json=excluded.raw_json",
                (
                    provider,
                    provider_raceday_key,
                    race_number,
                    race_id,
                    provider_track_code,
                    provider_start_time_raw,
                    discovered_at.isoformat(),
                    None if raw is None else json.dumps(raw, ensure_ascii=False),
                ),
            )

    def provider_races_between(self, start: datetime, end: datetime) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT p.*, r.start_time_utc, r.track, r.country, r.discipline "
                "FROM provider_race_refs p JOIN races r ON r.race_id=p.race_id "
                "WHERE r.start_time_utc>=? AND r.start_time_utc<? ORDER BY r.start_time_utc",
                (start.isoformat(), end.isoformat()),
            )
            return [dict(row) for row in rows]

    def insert_provider_market_snapshot(
        self,
        *,
        snapshot_id: str,
        provider: str,
        race_id: str,
        product: str,
        selection_key: str,
        observed_at: datetime,
        provider_updated_at: datetime | None,
        source_uri: str,
        odds_decimal: float | None = None,
        min_odds: float | None = None,
        max_odds: float | None = None,
        pool_size: float | None = None,
        raw: dict[str, object] | None = None,
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO provider_market_snapshots "
                "(snapshot_id,provider,race_id,product,selection_key,observed_at_utc,"
                "provider_updated_at_utc,odds_decimal,min_odds,max_odds,pool_size,source_uri,"
                "raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot_id,
                    provider,
                    race_id,
                    product,
                    selection_key,
                    observed_at.isoformat(),
                    None if provider_updated_at is None else provider_updated_at.isoformat(),
                    odds_decimal,
                    min_odds,
                    max_odds,
                    pool_size,
                    source_uri,
                    None if raw is None else json.dumps(raw, ensure_ascii=False),
                ),
            )
            return cursor.rowcount == 1

    def latest_provider_market(
        self,
        race_id: str,
        product: str,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            observed = connection.execute(
                "SELECT MAX(observed_at_utc) FROM provider_market_snapshots "
                "WHERE race_id=? AND product=?",
                (race_id, product),
            ).fetchone()[0]
            if observed is None:
                return []
            rows = connection.execute(
                "SELECT * FROM provider_market_snapshots "
                "WHERE race_id=? AND product=? AND observed_at_utc=? "
                "ORDER BY selection_key",
                (race_id, product, observed),
            )
            return [dict(row) for row in rows]

    def insert_provider_payload(
        self,
        *,
        payload_id: str,
        provider: str,
        category: str,
        provider_raceday_key: str,
        observed_at: datetime,
        source_uri: str,
        payload: dict[str, object] | list[object],
        race_number: int | None = None,
        product: str | None = None,
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO provider_payloads "
                "(payload_id,provider,category,provider_raceday_key,race_number,product,"
                "observed_at_utc,source_uri,payload_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    payload_id,
                    provider,
                    category,
                    provider_raceday_key,
                    race_number,
                    product,
                    observed_at.isoformat(),
                    source_uri,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            return cursor.rowcount == 1

    def record_provider_fetch(
        self,
        *,
        fetch_id: str,
        provider: str,
        endpoint: str,
        fetched_at: datetime,
        success: bool,
        status_code: int | None,
        latency_ms: float,
        error_message: str | None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO provider_fetch_audit "
                "(fetch_id,provider,endpoint,fetched_at_utc,success,status_code,latency_ms,"
                "error_message) VALUES (?,?,?,?,?,?,?,?)",
                (
                    fetch_id,
                    provider,
                    endpoint,
                    fetched_at.isoformat(),
                    int(success),
                    status_code,
                    latency_ms,
                    error_message,
                ),
            )

    def insert_runner_fundamental_snapshot(
        self,
        snapshot: dict[str, object],
    ) -> bool:
        columns = (
            "snapshot_id", "race_id", "selection_id", "observed_at_utc",
            "feature_as_of_utc", "source_uri", "horse_name", "driver_or_jockey",
            "trainer", "post_position", "extra_distance_m", "total_earnings", "age",
            "sex", "record_volt", "record_auto", "history_total_starts",
            "history_total_wins", "history_total_seconds", "history_total_thirds",
            "history_total_earnings", "current_year_starts", "current_year_wins",
            "current_year_seconds", "current_year_thirds", "current_year_earnings",
            "scratched", "data_quality", "enrichment_provider",
            "identity_match_method", "identity_match_confidence",
            "full_field_history_complete", "raw_json",
        )
        values = [snapshot.get(column) for column in columns]
        with self.connect() as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO runner_fundamental_snapshots "
                f"({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            return cursor.rowcount == 1

    def latest_runner_fundamentals(
        self,
        race_id: str,
        *,
        before: datetime | None = None,
    ) -> list[dict[str, object]]:
        query = "SELECT * FROM runner_fundamental_snapshots WHERE race_id=?"
        params: list[object] = [race_id]
        if before is not None:
            query += " AND feature_as_of_utc<=?"
            params.append(before.isoformat())
        query += " ORDER BY selection_id, feature_as_of_utc DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params)
            output: dict[str, dict[str, object]] = {}
            for row in rows:
                selection = str(row["selection_id"])
                if selection not in output:
                    output[selection] = dict(row)
            return list(output.values())

    def insert_fundamental_model_run(self, run: dict[str, object]) -> bool:
        columns = (
            "run_id", "race_id", "model_name", "model_version", "role",
            "feature_set_version", "created_at_utc", "feature_as_of_utc", "field_size",
            "active_runners", "known_history_runners", "history_coverage",
            "shadow_eligible", "status", "reason", "probabilities_json",
            "metadata_json",
        )
        values = [run.get(column) for column in columns]
        with self.connect() as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO fundamental_model_runs "
                f"({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            return cursor.rowcount == 1

    def latest_fundamental_model_run(
        self,
        race_id: str,
        *,
        before: datetime | None = None,
    ) -> dict[str, object] | None:
        query = "SELECT * FROM fundamental_model_runs WHERE race_id=?"
        params: list[object] = [race_id]
        if before is not None:
            query += " AND created_at_utc<=?"
            params.append(before.isoformat())
        query += " ORDER BY created_at_utc DESC LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
            return None if row is None else dict(row)

    def upsert_model_version(
        self,
        *,
        model_name: str,
        version: str,
        role: str,
        training_cutoff_utc: str,
        feature_set_version: str,
        calibration_version: str,
        created_at: datetime,
        notes: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO model_versions "
                "(model_name,version,role,training_cutoff_utc,feature_set_version,"
                "calibration_version,created_at_utc,notes) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(model_name,version) DO UPDATE SET "
                "role=excluded.role,training_cutoff_utc=excluded.training_cutoff_utc,"
                "feature_set_version=excluded.feature_set_version,"
                "calibration_version=excluded.calibration_version,notes=excluded.notes",
                (
                    model_name,
                    version,
                    role,
                    training_cutoff_utc,
                    feature_set_version,
                    calibration_version,
                    created_at.isoformat(),
                    notes,
                ),
            )

    def latest_predictions(
        self,
        race_id: str,
        *,
        layer: str,
        before: datetime | None = None,
    ) -> dict[str, float]:
        where = "race_id=? AND layer=?"
        params: list[object] = [race_id, layer]
        if before is not None:
            where += " AND created_at_utc<=?"
            params.append(before.isoformat())
        with self.connect() as connection:
            latest = connection.execute(
                f"SELECT MAX(created_at_utc) FROM predictions WHERE {where}",
                params,
            ).fetchone()[0]
            if latest is None:
                return {}
            rows = connection.execute(
                "SELECT selection_id, probability FROM predictions "
                "WHERE race_id=? AND layer=? AND created_at_utc=? "
                "ORDER BY selection_id",
                (race_id, layer, latest),
            )
            return {
                str(row["selection_id"]): float(row["probability"])
                for row in rows
            }

    def get_shadow_decision_run(
        self,
        decision_run_id: str,
    ) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_decision_runs WHERE decision_run_id=?",
                (decision_run_id,),
            ).fetchone()
            return None if row is None else dict(row)

    def insert_shadow_decision_run(self, run: dict[str, object]) -> bool:
        columns = (
            "decision_run_id", "race_id", "provider_raceday_key", "product",
            "created_at_utc", "race_start_time_utc", "decision_status", "reason",
            "shadow_model_version", "fundamental_model_version",
            "source_market_observed_at_utc", "target_minutes_to_start",
            "actual_minutes_to_start", "execution_latency_seconds", "field_size",
            "fundamental_probabilities_json", "market_probabilities_json",
            "combined_probabilities_json", "model_market_conflict_score", "ticket_count",
        )
        values = [run.get(column) for column in columns]
        with self.connect() as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO shadow_decision_runs ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            return cursor.rowcount == 1

    def upsert_race_research_evaluation(self, evaluation: dict[str, object]) -> None:
        columns = (
            "race_id", "shadow_model_version", "fundamental_model_version",
            "decision_time_utc", "outcome_settled_at_utc", "winner_selection_id",
            "field_size", "fundamental_log_loss", "market_log_loss",
            "combined_log_loss", "fundamental_brier", "market_brier",
            "combined_brier", "model_market_conflict_score",
            "source_market_observed_at_utc", "created_at_utc",
        )
        values = [evaluation.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO race_research_evaluations ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(race_id,shadow_model_version) DO UPDATE SET "
                "fundamental_model_version=excluded.fundamental_model_version,"
                "decision_time_utc=excluded.decision_time_utc,"
                "outcome_settled_at_utc=excluded.outcome_settled_at_utc,"
                "winner_selection_id=excluded.winner_selection_id,"
                "field_size=excluded.field_size,"
                "fundamental_log_loss=excluded.fundamental_log_loss,"
                "market_log_loss=excluded.market_log_loss,"
                "combined_log_loss=excluded.combined_log_loss,"
                "fundamental_brier=excluded.fundamental_brier,"
                "market_brier=excluded.market_brier,"
                "combined_brier=excluded.combined_brier,"
                "model_market_conflict_score=excluded.model_market_conflict_score,"
                "source_market_observed_at_utc=excluded.source_market_observed_at_utc,"
                "created_at_utc=excluded.created_at_utc",
                values,
            )

    def upsert_research_daily_report(self, report: dict[str, object]) -> None:
        columns = (
            "report_date", "generated_at_utc", "schema_version", "data_health_json",
            "evaluation_json", "trend_json", "markdown_report",
        )
        values = [report.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO research_daily_reports ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(report_date) DO UPDATE SET "
                "generated_at_utc=excluded.generated_at_utc,"
                "schema_version=excluded.schema_version,"
                "data_health_json=excluded.data_health_json,"
                "evaluation_json=excluded.evaluation_json,"
                "trend_json=excluded.trend_json,"
                "markdown_report=excluded.markdown_report",
                values,
            )

    def upsert_decision_provenance(self, record: dict[str, object]) -> None:
        columns = (
            "decision_run_id", "market_odds_json", "combination_policy_json",
            "decision_policy_json", "code_sha", "governance_hash", "recorded_at_utc",
        )
        values = [record.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO decision_provenance ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(decision_run_id) DO UPDATE SET "
                "market_odds_json=excluded.market_odds_json,"
                "combination_policy_json=excluded.combination_policy_json,"
                "decision_policy_json=excluded.decision_policy_json,"
                "code_sha=excluded.code_sha,"
                "governance_hash=excluded.governance_hash,"
                "recorded_at_utc=excluded.recorded_at_utc",
                values,
            )

    def upsert_system_run_manifest(self, manifest: dict[str, object]) -> None:
        columns = (
            "run_id", "run_type", "started_at_utc", "finished_at_utc", "status",
            "github_sha", "github_run_id", "model_version", "governance_hash",
            "critical_code_hash", "db_schema_hash", "policy_json", "metadata_json",
        )
        values = [manifest.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO system_run_manifests ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(run_id) DO UPDATE SET "
                "finished_at_utc=excluded.finished_at_utc,status=excluded.status,"
                "github_sha=excluded.github_sha,github_run_id=excluded.github_run_id,"
                "model_version=excluded.model_version,"
                "governance_hash=excluded.governance_hash,"
                "critical_code_hash=excluded.critical_code_hash,"
                "db_schema_hash=excluded.db_schema_hash,"
                "policy_json=excluded.policy_json,metadata_json=excluded.metadata_json",
                values,
            )

    def insert_integrity_audit(self, audit: dict[str, object]) -> bool:
        columns = (
            "audit_id", "audit_type", "generated_at_utc", "status", "checked_rows",
            "failures", "warnings", "report_json", "github_sha",
        )
        values = [audit.get(column) for column in columns]
        with self.connect() as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO integrity_audits ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            return cursor.rowcount == 1

    def upsert_challenger(self, record: dict[str, object]) -> None:
        columns = (
            "challenger_id", "model_name", "model_version", "registered_at_utc",
            "discovery_cutoff_utc", "forward_start_utc", "minimum_forward_races",
            "status", "notes",
        )
        values = [record.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO challenger_registry ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(challenger_id) DO UPDATE SET "
                "model_name=excluded.model_name,model_version=excluded.model_version,"
                "discovery_cutoff_utc=excluded.discovery_cutoff_utc,"
                "forward_start_utc=excluded.forward_start_utc,"
                "minimum_forward_races=excluded.minimum_forward_races,"
                "status=excluded.status,notes=excluded.notes",
                values,
            )

    def upsert_challenger_forward_event(self, record: dict[str, object]) -> None:
        columns = (
            "challenger_id", "race_id", "race_start_utc",
            "evaluation_created_at_utc", "eligible", "reason",
        )
        values = [record.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO challenger_forward_events ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(challenger_id,race_id) DO UPDATE SET "
                "race_start_utc=excluded.race_start_utc,"
                "evaluation_created_at_utc=excluded.evaluation_created_at_utc,"
                "eligible=excluded.eligible,reason=excluded.reason",
                values,
            )

    def upsert_counterfactual_run(self, record: dict[str, object]) -> None:
        columns = (
            "counterfactual_id", "race_id", "source_decision_run_id",
            "created_at_utc", "hypothesis_name", "hypothesis_json", "result_json",
            "research_only", "execution_authority",
        )
        values = [record.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO counterfactual_runs ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(source_decision_run_id,hypothesis_name) DO UPDATE SET "
                "created_at_utc=excluded.created_at_utc,"
                "hypothesis_json=excluded.hypothesis_json,"
                "result_json=excluded.result_json,"
                "research_only=excluded.research_only,"
                "execution_authority=excluded.execution_authority",
                values,
            )

    def create_shadow_ticket(self, ticket: dict[str, object]) -> bool:
        columns = (
            "ticket_id", "dedupe_key", "created_at_utc", "decision_time_utc", "race_id",
            "provider", "provider_raceday_key", "product", "decision", "status",
            "selections_json", "stake_nok", "row_price_nok", "number_of_rows",
            "available_price", "fair_odds", "estimated_edge", "expected_value",
            "model_version", "source_snapshot_time_utc", "target_minutes_to_start",
            "actual_minutes_to_start", "execution_latency_seconds", "reject_reason",
            "notes",
        )
        values = [ticket.get(column) for column in columns]
        with self.connect() as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO shadow_tickets ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            return cursor.rowcount == 1

    def settle_shadow_ticket(
        self,
        *,
        ticket_id: str,
        settled_at: datetime,
        gross_return_nok: float,
        net_pnl_nok: float,
        settlement_source_uri: str,
        result: dict[str, object],
        closing_price: float | None = None,
        clv: float | None = None,
        status: str = "SETTLED",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE shadow_tickets SET status=?,settlement_source_uri=?,settled_at_utc=?,"
                "gross_return_nok=?,net_pnl_nok=?,closing_price=?,clv=?,result_json=? "
                "WHERE ticket_id=?",
                (
                    status,
                    settlement_source_uri,
                    settled_at.isoformat(),
                    gross_return_nok,
                    net_pnl_nok,
                    closing_price,
                    clv,
                    json.dumps(result, ensure_ascii=False),
                    ticket_id,
                ),
            )

    def open_shadow_tickets(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shadow_tickets WHERE status IN "
                "('SHADOW_BET','PENDING_SETTLEMENT') ORDER BY decision_time_utc"
            )
            return [dict(row) for row in rows]

    def shadow_tickets_between(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shadow_tickets "
                "WHERE decision_time_utc>=? AND decision_time_utc<? "
                "ORDER BY decision_time_utc",
                (start.isoformat(), end.isoformat()),
            )
            return [dict(row) for row in rows]

    def upsert_shadow_daily_report(self, report: dict[str, object]) -> None:
        columns = (
            "report_date", "generated_at_utc", "stake_nok", "gross_return_nok",
            "net_pnl_nok", "roi", "tickets", "settled_tickets", "winning_tickets",
            "positive_clv_tickets", "report_json",
        )
        values = [report.get(column) for column in columns]
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO shadow_daily_reports ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(report_date) DO UPDATE SET "
                "generated_at_utc=excluded.generated_at_utc,"
                "stake_nok=excluded.stake_nok,gross_return_nok=excluded.gross_return_nok,"
                "net_pnl_nok=excluded.net_pnl_nok,roi=excluded.roi,tickets=excluded.tickets,"
                "settled_tickets=excluded.settled_tickets,"
                "winning_tickets=excluded.winning_tickets,"
                "positive_clv_tickets=excluded.positive_clv_tickets,"
                "report_json=excluded.report_json",
                values,
            )

    def checkpoint(self) -> None:
        """Flush WAL pages into the main database before artifact persistence."""
        with self.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

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
            "prewatch_events", "outcomes", "provider_race_refs",
            "provider_market_snapshots", "provider_fetch_audit", "shadow_tickets",
            "shadow_daily_reports", "provider_payloads",
            "runner_fundamental_snapshots", "fundamental_model_runs",
            "shadow_decision_runs", "race_research_evaluations",
            "research_daily_reports", "decision_provenance",
            "system_run_manifests", "integrity_audits", "challenger_registry",
            "challenger_forward_events", "counterfactual_runs",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]

    def count(self, table: str) -> int:
        allowed = {
            "races", "runners", "evidence", "market_snapshots", "predictions",
            "race_diagnostics", "model_versions", "decisions", "review_flags",
            "prewatch_events", "outcomes", "schema_migrations", "provider_race_refs",
            "provider_market_snapshots", "provider_fetch_audit", "shadow_tickets",
            "shadow_daily_reports", "provider_payloads",
            "runner_fundamental_snapshots", "fundamental_model_runs",
            "shadow_decision_runs", "race_research_evaluations",
            "research_daily_reports", "decision_provenance",
            "system_run_manifests", "integrity_audits", "challenger_registry",
            "challenger_forward_events", "counterfactual_runs",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        with self.connect() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
