-- RELEASE-005: immutable, never-settleable frozen research signals.
-- Research-only: no trigger, FK or API can promote these into shadow_tickets.
CREATE TABLE IF NOT EXISTS shadow_research_signals (
    signal_id TEXT PRIMARY KEY,
    decision_run_id TEXT NOT NULL,
    race_id TEXT NOT NULL REFERENCES races(race_id),
    selection_id TEXT NOT NULL,
    horse_id_scope TEXT NOT NULL DEFAULT 'RACE_LOCAL_SELECTION',
    shadow_model_name TEXT NOT NULL,
    shadow_model_version TEXT NOT NULL,
    fundamental_model_version TEXT,
    fundamental_probabilities_json TEXT NOT NULL,
    market_probabilities_json TEXT NOT NULL,
    combined_probabilities_json TEXT NOT NULL,
    observed_win_odds REAL NOT NULL CHECK(observed_win_odds > 1),
    p_win REAL NOT NULL CHECK(p_win > 0 AND p_win <= 1),
    fair_odds REAL NOT NULL CHECK(fair_odds >= 1),
    expected_value REAL NOT NULL,
    minimum_acceptable_odds REAL NOT NULL CHECK(minimum_acceptable_odds >= 1),
    signal_calculated_at_utc TEXT NOT NULL,
    record_requested_at_utc TEXT NOT NULL,
    source_observed_at_utc TEXT,
    source_uri TEXT,
    source_body_sha256 TEXT,
    source_receipts_json TEXT NOT NULL,
    rejected_candidates_json TEXT NOT NULL,
    contender_payload_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SIGNAL_RECORDED' CHECK(status='SIGNAL_RECORDED'),
    t4_attested INTEGER NOT NULL DEFAULT 0 CHECK(t4_attested=0),
    pit_certified INTEGER NOT NULL DEFAULT 0 CHECK(pit_certified=0),
    shadow_ticket_created INTEGER NOT NULL DEFAULT 0 CHECK(shadow_ticket_created=0),
    research_only INTEGER NOT NULL DEFAULT 1 CHECK(research_only=1),
    UNIQUE(decision_run_id,selection_id)
);
CREATE INDEX IF NOT EXISTS idx_shadow_research_signals_race
ON shadow_research_signals(race_id,shadow_model_version);
CREATE TRIGGER IF NOT EXISTS shadow_research_signals_immutable_update
BEFORE UPDATE ON shadow_research_signals
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SHADOW_RESEARCH_SIGNAL'); END;
CREATE TRIGGER IF NOT EXISTS shadow_research_signals_immutable_delete
BEFORE DELETE ON shadow_research_signals
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SHADOW_RESEARCH_SIGNAL'); END;
