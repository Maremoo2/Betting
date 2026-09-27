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
    UNIQUE(provider,category,provider_raceday_key,race_number,product,observed_at_utc)
);
