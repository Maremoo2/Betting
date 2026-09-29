CREATE TABLE IF NOT EXISTS intelligence_evidence (
    intelligence_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT,
    provider TEXT,
    provider_raceday_key TEXT,
    race_number INTEGER,
    observed_at_utc TEXT NOT NULL,
    event_type TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_timestamp_utc TEXT,
    source_time_basis TEXT NOT NULL DEFAULT 'UNKNOWN',
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    materiality TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    prewatch_score REAL CHECK(prewatch_score IS NULL OR (prewatch_score BETWEEN 0 AND 100)),
    policy_version TEXT NOT NULL,
    extractor TEXT,
    pit_eligible INTEGER NOT NULL DEFAULT 0,
    research_only INTEGER NOT NULL DEFAULT 1,
    production_feature_eligible INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intelligence_bridge_imports (
    inbox_id TEXT PRIMARY KEY,
    imported_at_utc TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER,
    status TEXT NOT NULL,
    reason TEXT,
    intelligence_id TEXT,
    race_id TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_race_time
ON intelligence_evidence (race_id, observed_at_utc);

CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_type
ON intelligence_evidence (event_type, evidence_status);

CREATE INDEX IF NOT EXISTS idx_intelligence_bridge_status
ON intelligence_bridge_imports (status, imported_at_utc);
