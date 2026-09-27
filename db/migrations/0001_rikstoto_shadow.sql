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
