CREATE TABLE IF NOT EXISTS shadow_decision_runs (
    decision_run_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    provider_raceday_key TEXT,
    product TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    race_start_time_utc TEXT NOT NULL,
    decision_status TEXT NOT NULL,
    reason TEXT,
    shadow_model_version TEXT NOT NULL,
    fundamental_model_version TEXT,
    source_market_observed_at_utc TEXT,
    target_minutes_to_start REAL,
    actual_minutes_to_start REAL,
    execution_latency_seconds REAL,
    field_size INTEGER,
    fundamental_probabilities_json TEXT,
    market_probabilities_json TEXT,
    combined_probabilities_json TEXT,
    model_market_conflict_score REAL,
    ticket_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(race_id, product, shadow_model_version, target_minutes_to_start)
);

CREATE TABLE IF NOT EXISTS race_research_evaluations (
    race_id TEXT NOT NULL REFERENCES races(race_id),
    shadow_model_version TEXT NOT NULL,
    fundamental_model_version TEXT,
    decision_time_utc TEXT NOT NULL,
    outcome_settled_at_utc TEXT NOT NULL,
    winner_selection_id TEXT NOT NULL,
    field_size INTEGER NOT NULL,
    fundamental_log_loss REAL,
    market_log_loss REAL,
    combined_log_loss REAL,
    fundamental_brier REAL,
    market_brier REAL,
    combined_brier REAL,
    model_market_conflict_score REAL,
    source_market_observed_at_utc TEXT,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (race_id, shadow_model_version)
);

CREATE TABLE IF NOT EXISTS research_daily_reports (
    report_date TEXT PRIMARY KEY,
    generated_at_utc TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    data_health_json TEXT NOT NULL,
    evaluation_json TEXT NOT NULL,
    trend_json TEXT NOT NULL,
    markdown_report TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_decision_runs_created
ON shadow_decision_runs (created_at_utc);

CREATE INDEX IF NOT EXISTS idx_race_research_evaluations_created
ON race_research_evaluations (created_at_utc);
