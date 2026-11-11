-- Existing signals retain nullable identity and their original immutable payload.
ALTER TABLE shadow_research_signals ADD COLUMN horse_id TEXT;
ALTER TABLE shadow_research_signals ADD COLUMN horse_id_source TEXT;
ALTER TABLE shadow_research_signals ADD COLUMN horse_id_source_version TEXT;
ALTER TABLE shadow_research_signals ADD COLUMN horse_identity_status TEXT NOT NULL DEFAULT 'UNATTESTED'
    CHECK(horse_identity_status IN ('UNATTESTED','ATTESTED'));
ALTER TABLE shadow_research_signals ADD COLUMN horse_identity_reason TEXT DEFAULT 'PERMANENT_HORSE_ID_UNATTESTED'
    CHECK(
        (horse_identity_status = 'UNATTESTED' AND horse_id IS NULL
         AND horse_id_source IS NULL AND horse_id_source_version IS NULL
         AND horse_identity_reason IS NOT NULL AND length(trim(horse_identity_reason)) > 0)
        OR
        (horse_identity_status = 'ATTESTED'
         AND horse_id IS NOT NULL AND length(trim(horse_id)) > 0
         AND horse_id_source IS NOT NULL AND length(trim(horse_id_source)) > 0
         AND horse_id_source_version IS NOT NULL AND length(trim(horse_id_source_version)) > 0
         AND horse_identity_reason IS NULL)
    );
-- REPLACE can skip DELETE triggers if recursive_triggers is off.
CREATE TRIGGER IF NOT EXISTS shadow_research_signals_no_replacement
BEFORE INSERT ON shadow_research_signals
WHEN EXISTS (
    SELECT 1 FROM shadow_research_signals
    WHERE signal_id=NEW.signal_id
       OR (decision_run_id=NEW.decision_run_id AND selection_id=NEW.selection_id)
)
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SHADOW_RESEARCH_SIGNAL'); END;
