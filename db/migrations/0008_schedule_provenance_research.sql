-- DATA-005O: additive HBI schedule provenance. No model/strategy authority.
-- Table intentionally has no FK to races: first observations must precede race UPSERT.
CREATE TABLE IF NOT EXISTS race_schedule_observations (
    event_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    source_schedule_raw TEXT NOT NULL,
    normalized_start_utc TEXT NOT NULL,
    source_grade TEXT NOT NULL CHECK(source_grade IN ('HASH_ONLY_NO_RAW_BYTES','PARSED_ONLY')),
    source_body_sha256 TEXT,
    source_time_basis TEXT NOT NULL CHECK(source_time_basis IN ('HTTP_RESPONSE_COMPLETED','CALLER_SUPPLIED_UNVERIFIED')),
    http_date TEXT,
    http_etag TEXT,
    http_last_modified TEXT,
    before_declared_start INTEGER NOT NULL CHECK(before_declared_start IN (0,1)),
    research_only INTEGER NOT NULL DEFAULT 1 CHECK(research_only=1),
    pit_verified INTEGER NOT NULL DEFAULT 0 CHECK(pit_verified=0),
    model_eligible INTEGER NOT NULL DEFAULT 0 CHECK(model_eligible=0),
    bet_authorized INTEGER NOT NULL DEFAULT 0 CHECK(bet_authorized=0),
    CHECK((source_grade='HASH_ONLY_NO_RAW_BYTES' AND length(source_body_sha256)=64
       AND source_time_basis='HTTP_RESPONSE_COMPLETED')
       OR (source_grade='PARSED_ONLY' AND source_body_sha256 IS NULL
       AND source_time_basis='CALLER_SUPPLIED_UNVERIFIED'))
);
CREATE INDEX IF NOT EXISTS idx_race_schedule_observations_race_observed
    ON race_schedule_observations(race_id,observed_at_utc);
CREATE TRIGGER IF NOT EXISTS race_schedule_observations_no_update
BEFORE UPDATE ON race_schedule_observations
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SCHEDULE_OBSERVATION'); END;
CREATE TRIGGER IF NOT EXISTS race_schedule_observations_no_delete
BEFORE DELETE ON race_schedule_observations
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SCHEDULE_OBSERVATION'); END;
