ALTER TABLE runner_fundamental_snapshots
ADD COLUMN enrichment_provider TEXT;

ALTER TABLE runner_fundamental_snapshots
ADD COLUMN identity_match_method TEXT;

ALTER TABLE runner_fundamental_snapshots
ADD COLUMN identity_match_confidence REAL;

ALTER TABLE runner_fundamental_snapshots
ADD COLUMN full_field_history_complete INTEGER NOT NULL DEFAULT 0;
