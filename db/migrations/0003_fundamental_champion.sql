CREATE TABLE IF NOT EXISTS runner_fundamental_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    feature_as_of_utc TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    horse_name TEXT,
    driver_or_jockey TEXT,
    trainer TEXT,
    post_position INTEGER,
    extra_distance_m INTEGER,
    total_earnings REAL,
    age INTEGER,
    sex TEXT,
    record_volt TEXT,
    record_auto TEXT,
    history_total_starts INTEGER,
    history_total_wins INTEGER,
    history_total_seconds INTEGER,
    history_total_thirds INTEGER,
    history_total_earnings REAL,
    current_year_starts INTEGER,
    current_year_wins INTEGER,
    current_year_seconds INTEGER,
    current_year_thirds INTEGER,
    current_year_earnings REAL,
    scratched INTEGER NOT NULL DEFAULT 0,
    data_quality TEXT NOT NULL,
    raw_json TEXT,
    UNIQUE(race_id, selection_id, observed_at_utc)
);

CREATE TABLE IF NOT EXISTS fundamental_model_runs (
    run_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    role TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    feature_as_of_utc TEXT NOT NULL,
    field_size INTEGER NOT NULL,
    active_runners INTEGER NOT NULL,
    known_history_runners INTEGER NOT NULL,
    history_coverage REAL NOT NULL,
    shadow_eligible INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    probabilities_json TEXT NOT NULL,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_fundamental_snapshots_race_time
ON runner_fundamental_snapshots (race_id, feature_as_of_utc);

CREATE INDEX IF NOT EXISTS idx_fundamental_runs_race_time
ON fundamental_model_runs (race_id, created_at_utc);
