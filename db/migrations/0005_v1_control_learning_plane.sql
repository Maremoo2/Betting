CREATE TABLE IF NOT EXISTS system_run_manifests (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
