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


CREATE TABLE IF NOT EXISTS provider_race_refs (
    provider TEXT NOT NULL,
    provider_raceday_key TEXT NOT NULL,
    race_number INTEGER NOT NULL,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    provider_track_code TEXT,
    provider_start_time_raw TEXT,
    discovered_at_utc TEXT NOT NULL,
    raw_json TEXT,
    PRIMARY KEY (provider, provider_raceday_key, race_number)
);

CREATE TABLE IF NOT EXISTS provider_market_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    product TEXT NOT NULL,
    selection_key TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    provider_updated_at_utc TEXT,
    odds_decimal REAL,
    min_odds REAL,
    max_odds REAL,
    pool_size REAL,
    source_uri TEXT NOT NULL,
    raw_json TEXT,
    UNIQUE(provider, race_id, product, selection_key, observed_at_utc)
);

CREATE TABLE IF NOT EXISTS provider_fetch_audit (
    fetch_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    success INTEGER NOT NULL,
    status_code INTEGER,
    latency_ms REAL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS shadow_tickets (
    ticket_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL,
    decision_time_utc TEXT NOT NULL,
    race_id TEXT REFERENCES races(race_id),
    provider TEXT NOT NULL,
    provider_raceday_key TEXT,
    product TEXT NOT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    selections_json TEXT NOT NULL,
    stake_nok REAL,
    row_price_nok REAL,
    number_of_rows INTEGER,
    available_price REAL,
    fair_odds REAL,
    estimated_edge REAL,
    expected_value REAL,
    model_version TEXT,
    source_snapshot_time_utc TEXT,
    target_minutes_to_start REAL,
    actual_minutes_to_start REAL,
    execution_latency_seconds REAL,
    reject_reason TEXT,
    settlement_source_uri TEXT,
    settled_at_utc TEXT,
    gross_return_nok REAL,
    net_pnl_nok REAL,
    closing_price REAL,
    clv REAL,
    result_json TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS shadow_daily_reports (
    report_date TEXT PRIMARY KEY,
    generated_at_utc TEXT NOT NULL,
    stake_nok REAL NOT NULL,
    gross_return_nok REAL NOT NULL,
    net_pnl_nok REAL NOT NULL,
    roi REAL,
    tickets INTEGER NOT NULL,
    settled_tickets INTEGER NOT NULL,
    winning_tickets INTEGER NOT NULL,
    positive_clv_tickets INTEGER NOT NULL,
    report_json TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS provider_payloads (
    payload_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    category TEXT NOT NULL,
    provider_raceday_key TEXT NOT NULL,
    race_number INTEGER,
    product TEXT,
    observed_at_utc TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(
        provider,
        category,
        provider_raceday_key,
        race_number,
        product,
        observed_at_utc
    )
);


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


CREATE TABLE IF NOT EXISTS system_run_manifests (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL,
    github_sha TEXT,
    github_run_id TEXT,
    model_version TEXT,
    governance_hash TEXT,
    critical_code_hash TEXT,
    db_schema_hash TEXT,
    policy_json TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_provenance (
    decision_run_id TEXT PRIMARY KEY REFERENCES shadow_decision_runs(decision_run_id),
    market_odds_json TEXT,
    combination_policy_json TEXT,
    decision_policy_json TEXT,
    code_sha TEXT,
    governance_hash TEXT,
    recorded_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS integrity_audits (
    audit_id TEXT PRIMARY KEY,
    audit_type TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    checked_rows INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    warnings INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL,
    github_sha TEXT
);

CREATE TABLE IF NOT EXISTS challenger_registry (
    challenger_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    registered_at_utc TEXT NOT NULL,
    discovery_cutoff_utc TEXT NOT NULL,
    forward_start_utc TEXT NOT NULL,
    minimum_forward_races INTEGER NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    UNIQUE(model_name, model_version)
);

CREATE TABLE IF NOT EXISTS challenger_forward_events (
    challenger_id TEXT NOT NULL REFERENCES challenger_registry(challenger_id),
    race_id TEXT NOT NULL REFERENCES races(race_id),
    race_start_utc TEXT NOT NULL,
    evaluation_created_at_utc TEXT NOT NULL,
    eligible INTEGER NOT NULL,
    reason TEXT,
    PRIMARY KEY (challenger_id, race_id)
);

CREATE TABLE IF NOT EXISTS counterfactual_runs (
    counterfactual_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    source_decision_run_id TEXT NOT NULL REFERENCES shadow_decision_runs(decision_run_id),
    created_at_utc TEXT NOT NULL,
    hypothesis_name TEXT NOT NULL,
    hypothesis_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    research_only INTEGER NOT NULL DEFAULT 1,
    execution_authority INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_decision_run_id, hypothesis_name)
);

CREATE INDEX IF NOT EXISTS idx_integrity_audits_type_time
ON integrity_audits (audit_type, generated_at_utc);

CREATE INDEX IF NOT EXISTS idx_challenger_forward_events_challenger
ON challenger_forward_events (challenger_id, eligible);

CREATE INDEX IF NOT EXISTS idx_system_run_manifests_type_time
ON system_run_manifests (run_type, started_at_utc);
