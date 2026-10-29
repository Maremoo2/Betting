"""DATA-005Q: read-only, fail-closed clock provenance assessment.

This is NOT a wagering or Shadow policy. It never writes database rows, modifies
frozen decisions, certifies original HTTP bytes, or asserts actual physical start.
Schedule observations come from the additive DATA-005P research journal.
An unversioned old race row is never treated as a contemporaneous schedule source.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from typing import Any

JOURNAL = 'race_schedule_observations'


def parse_utc(value: str | datetime) -> datetime:
    try:
        dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise ValueError('INVALID_TIMESTAMP') from exc
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class ClockReview:
    race_id: str
    decision_time_utc: str
    status: str
    blockers: tuple[str, ...]
    precutoff_observations: int
    precutoff_distinct_clocks: int
    observed_earliest_start_utc: str | None
    retrospective_new_observations: int
    retrospective_clock_changed: bool
    retrospective_published_clock_conflict: bool
    asof_clock_consistent: bool
    original_http_bytes_replayable: bool = False
    source_publication_attested: bool = False
    physical_off_time_attested: bool = False
    full_field_verified: bool = False
    model_eligible: bool = False
    bet_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output['blockers'] = list(self.blockers)
        output['mode'] = 'READ_ONLY_RESEARCH'
        return output


def _journal_present(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (JOURNAL,)).fetchone() is not None


def assess(
    conn: sqlite3.Connection,
    *,
    race_id: str,
    decision_time: datetime,
    retrospective_through: datetime | None = None,
    external_published_start: datetime | None = None,
) -> ClockReview:
    """Assess immutable journal as of a freeze, separately from hindsight.

    `external_published_start` is a later source's *published schedule*, not an
    attestation of actual departure. It only contributes retrospective warnings.
    Missing rows, hash-only evidence or unknown physical off-time can never pass
    complete PIT admission. Query is SELECT-only and does not trust races.start_time.
    """
    if not isinstance(race_id, str) or not race_id.startswith('RIKSTOTO:'):
        raise ValueError('INVALID_RACE_ID')
    cutoff = parse_utc(decision_time)
    review_through = parse_utc(retrospective_through) if retrospective_through is not None else cutoff
    if review_through < cutoff:
        raise ValueError('RETROSPECTIVE_BEFORE_CUTOFF')
    independent = parse_utc(external_published_start) if external_published_start is not None else None
    blockers: list[str] = []
    before: list[tuple[datetime, datetime, str, str, int]] = []
    after: list[tuple[datetime, datetime, str, str, int]] = []
    if not _journal_present(conn):
        blockers.append('JOURNAL_NOT_INSTALLED')
    else:
        records = conn.execute(
            'SELECT observed_at_utc,normalized_start_utc,source_grade,source_time_basis,before_declared_start '
            'FROM race_schedule_observations WHERE race_id=? ORDER BY observed_at_utc,event_id',
            (race_id,),
        ).fetchall()
        for item in records:
            observed, scheduled = parse_utc(item[0]), parse_utc(item[1])
            if item[2] not in ('HASH_ONLY_NO_RAW_BYTES', 'PARSED_ONLY') or item[3] not in (
                    'HTTP_RESPONSE_COMPLETED', 'CALLER_SUPPLIED_UNVERIFIED'):
                blockers.append('JOURNAL_SCHEMA_CONTRADICTION')
            if int(item[4]) != int(observed < scheduled):
                blockers.append('JOURNAL_TIME_FLAG_CONTRADICTION')
            row = (observed, scheduled, item[2], item[3], item[4])
            if observed <= cutoff:
                before.append(row)
            elif observed <= review_through:
                after.append(row)
    if not before:
        blockers.append('NO_OBSERVATION_BY_CUTOFF')
    unique = {entry[1] for entry in before}
    if len(unique) > 1:
        blockers.append('CLOCK_VERSION_CONFLICT_AT_CUTOFF')
    if before and any(entry[0] >= entry[1] for entry in before):
        blockers.append('OBSERVATION_AT_OR_AFTER_ITS_PUBLISHED_START')
    if unique and cutoff >= min(unique):
        blockers.append('DECISION_AT_OR_AFTER_PUBLISHED_START')
    if before and any(entry[2] == 'PARSED_ONLY' or entry[3] != 'HTTP_RESPONSE_COMPLETED' for entry in before):
        blockers.append('SOURCE_RESPONSE_COMPLETION_UNVERIFIED')
    if before:
        blockers.append('RAW_RESPONSE_NOT_REPLAYABLE')
        blockers.append('INDEPENDENT_SOURCE_PUBLICATION_UNATTESTED')
    later_clocks = {entry[1] for entry in after}
    retro_changed = bool(before and any(x not in unique for x in later_clocks))
    if retro_changed:
        blockers.append('RETROSPECTIVE_CLOCK_VERSION_CHANGE')
    retro_external = bool(independent is not None and unique and independent not in unique)
    if retro_external:
        blockers.append('EXTERNAL_PUBLISHED_CLOCK_CONFLICT')
        if cutoff >= independent:
            blockers.append('FROZEN_AFTER_EXTERNAL_PUBLISHED_START_REVIEW')
    # As-of diagnostics deliberately ignore later observations. Hindsight warnings
    # add a quarantine reason, never a new/fixed pre-race prediction.
    asof_consistent = bool(before and len(unique) == 1 and
        all(e[0] < e[1] for e in before) and cutoff < min(unique))
    hard_conflict = any(x in blockers for x in (
        'CLOCK_VERSION_CONFLICT_AT_CUTOFF', 'DECISION_AT_OR_AFTER_PUBLISHED_START',
        'OBSERVATION_AT_OR_AFTER_ITS_PUBLISHED_START',
        'RETROSPECTIVE_CLOCK_VERSION_CHANGE', 'EXTERNAL_PUBLISHED_CLOCK_CONFLICT',
        'JOURNAL_TIME_FLAG_CONTRADICTION', 'JOURNAL_SCHEMA_CONTRADICTION',
    ))
    if hard_conflict:
        status = 'CLOCK_CONFLICT_QUARANTINE'
    elif not before:
        status = 'MISSING_CLOCK_PROVENANCE'
    elif not asof_consistent:
        status = 'CLOCK_REVIEW_REQUIRED'
    else:
        status = 'CLOCK_CONSISTENT_RESEARCH_ONLY'
    return ClockReview(
        race_id=race_id,
        decision_time_utc=cutoff.isoformat(),
        status=status,
        blockers=tuple(sorted(set(blockers))),
        precutoff_observations=len(before),
        precutoff_distinct_clocks=len(unique),
        observed_earliest_start_utc=min(unique).isoformat() if unique else None,
        retrospective_new_observations=len(after),
        retrospective_clock_changed=retro_changed,
        retrospective_published_clock_conflict=retro_external,
        asof_clock_consistent=asof_consistent,
    )
