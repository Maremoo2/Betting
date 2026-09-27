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
