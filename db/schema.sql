PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS races (
    race_id TEXT PRIMARY KEY,
    race_date TEXT NOT NULL,
    country TEXT NOT NULL,
    track TEXT NOT NULL,
    race_no INTEGER NOT NULL,
    start_time_utc TEXT NOT NULL,
    discipline TEXT NOT NULL,
    distance_m INTEGER,
    start_method TEXT,
    race_class TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runners (
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT NOT NULL,
    horse_name TEXT NOT NULL,
    post_position INTEGER,
    driver_or_jockey TEXT,
    trainer TEXT,
    scratched INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (race_id, selection_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT,
    claim_type TEXT NOT NULL,
    claim_value TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    source_published_at_utc TEXT NOT NULL,
    extracted_at_utc TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT NOT NULL,
    captured_at_utc TEXT NOT NULL,
    odds_decimal REAL NOT NULL,
    pool_size REAL,
    market_regime TEXT NOT NULL DEFAULT 'UNKNOWN',
    information_cutoff_phase TEXT NOT NULL DEFAULT 'UNKNOWN',
    source_uri TEXT,
    PRIMARY KEY (race_id, selection_id, captured_at_utc)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    layer TEXT NOT NULL,
    probability REAL NOT NULL CHECK(probability > 0 AND probability <= 1),
    feature_as_of_utc TEXT NOT NULL,
    frozen INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS race_diagnostics (
    race_id TEXT NOT NULL REFERENCES races(race_id),
    created_at_utc TEXT NOT NULL,
    model_version TEXT NOT NULL,
    race_difficulty_score REAL NOT NULL,
    race_stability_score REAL NOT NULL,
    reject_status TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (race_id, created_at_utc, model_version)
);

CREATE TABLE IF NOT EXISTS model_versions (
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    role TEXT NOT NULL,
    training_cutoff_utc TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (model_name, version)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT,
    decision_time_utc TEXT NOT NULL,
    decision TEXT NOT NULL,
    fundamental_p REAL,
    market_p REAL,
    combined_p REAL,
    fair_odds REAL,
    available_price REAL,
    minimum_price REAL,
    expected_close_price REAL,
    actual_close_price REAL,
    closing_line_value REAL,
    model_market_conflict_score REAL,
    race_difficulty_score REAL,
    reject_reason TEXT,
    stake_nok REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_flags (
    flag_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT,
    flag_type TEXT NOT NULL,
    note TEXT,
    source_uri TEXT NOT NULL,
    source_published_at_utc TEXT NOT NULL,
    captured_at_utc TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    resolved_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS prewatch_events (
    event_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT,
    captured_at_utc TEXT NOT NULL,
    action TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    probability_move_pp REAL,
    relative_odds_move_pct REAL,
    pool_growth_pct REAL,
    minutes_to_start REAL,
    policy_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    race_id TEXT PRIMARY KEY REFERENCES races(race_id),
    winner_selection_id TEXT NOT NULL,
    settled_at_utc TEXT NOT NULL,
    actual_close_price REAL,
    gross_return_nok REAL,
    net_pnl_nok REAL
);
