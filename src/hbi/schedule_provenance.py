"""DATA-005O additive, research-only schedule provenance for the existing HBI SQLite store.

Stores hashes of HTTP response bytes when available; NEVER stores raw response bodies,
never claims a completed PIT evidence chain, never authorizes models or wagers.
Not integrated into GitHub production without an explicit owner-approved PR.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ScheduleEvent:
    event_id: str
    race_id: str
    source_uri: str
    observed_at_utc: str
    source_schedule_raw: str
    normalized_start_utc: str
    source_grade: str
    source_body_sha256: str | None
    source_time_basis: str
    http_date: str | None
    http_etag: str | None
    http_last_modified: str | None
    before_declared_start: int

    def values(self) -> tuple:
        return tuple(getattr(self, k) for k in (
            "event_id", "race_id", "source_uri", "observed_at_utc",
            "source_schedule_raw", "normalized_start_utc", "source_grade",
            "source_body_sha256", "source_time_basis", "http_date",
            "http_etag", "http_last_modified", "before_declared_start",
        ))


def aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_OR_INVALID_TIME")
    return value.astimezone(UTC)


def make_event(*, race_id: str, source_uri: str, observed_at: datetime,
               source_schedule_raw: str, normalized_start: datetime,
               raw_body_sha256: str | None = None,
               http_date: str | None = None, http_etag: str | None = None,
               http_last_modified: str | None = None,
               completion_verified: bool = False) -> ScheduleEvent:
    """Build defensively labelled observation; no raw HTTP archive/independent notarization."""
    if not isinstance(race_id, str) or not re.fullmatch(r"RIKSTOTO:[A-Za-z0-9_-]+:[1-9][0-9]*", race_id):
        raise ValueError("INVALID_RACE_ID")
    u = urlsplit(source_uri)
    if (u.scheme != "https" or u.netloc != "www.rikstoto.no" or
            u.path != "/api/racedays/" or u.query or u.fragment or u.username or u.password):
        raise ValueError("INVALID_DISCOVERY_SOURCE_URI")
    if not isinstance(source_schedule_raw, str) or not source_schedule_raw.strip() or len(source_schedule_raw) > 100:
        raise ValueError("MISSING_RAW_SCHEDULE_TIME")
    obs, start = aware_utc(observed_at), aware_utc(normalized_start)
    # A provider display string must resolve to the same UTC instant as the
    # normalized schedule. Otherwise the immutable log would preserve a false
    # correlation, potentially hiding an earlier physical race.
    try:
        raw_clock = datetime.fromisoformat(source_schedule_raw)
    except ValueError as exc:
        raise ValueError("INVALID_SOURCE_SCHEDULE_CLOCK") from exc
    if raw_clock.tzinfo is None or raw_clock.utcoffset() is None:
        oslo = ZoneInfo("Europe/Oslo")
        candidate = raw_clock.replace(tzinfo=oslo)
        other = raw_clock.replace(tzinfo=oslo, fold=1)
        standard_roundtrip = (
            candidate.astimezone(UTC).astimezone(oslo).replace(tzinfo=None) == raw_clock
        )
        fold_roundtrip = (
            other.astimezone(UTC).astimezone(oslo).replace(tzinfo=None) == raw_clock
        )
        if not standard_roundtrip and not fold_roundtrip:
            raise ValueError("NONEXISTENT_LOCAL_SOURCE_CLOCK")
        if candidate.utcoffset() != other.utcoffset() and standard_roundtrip and fold_roundtrip:
            raise ValueError("AMBIGUOUS_LOCAL_SOURCE_CLOCK")
        raw_clock = candidate
    if raw_clock.astimezone(UTC) != start:
        raise ValueError("SOURCE_SCHEDULE_NORMALIZATION_MISMATCH")
    if raw_body_sha256 is not None and not re.fullmatch(r"[a-f0-9]{64}", raw_body_sha256):
        raise ValueError("INVALID_RAW_BODY_SHA256")
    if completion_verified and raw_body_sha256 is None:
        raise ValueError("COMPLETION_WITHOUT_BODY_HASH")
    if not completion_verified and raw_body_sha256 is not None:
        raise ValueError("UNVERIFIED_HASH_CANNOT_CLAIM_RAW_HTTP")
    for header in (http_date,http_etag,http_last_modified):
        if header is not None and (not isinstance(header,str) or len(header)>512 or "\r" in header or "\n" in header):
            raise ValueError("INVALID_HTTP_HEADER")
    details = {
        "race_id": race_id, "source_uri": source_uri, "observed_at_utc": obs.isoformat(),
        "source_schedule_raw": source_schedule_raw, "normalized_start_utc": start.isoformat(),
        "source_grade": "HASH_ONLY_NO_RAW_BYTES" if completion_verified else "PARSED_ONLY",
        "source_body_sha256": raw_body_sha256,
        "source_time_basis": "HTTP_RESPONSE_COMPLETED" if completion_verified else "CALLER_SUPPLIED_UNVERIFIED",
        "http_date": http_date if completion_verified else None,
        "http_etag": http_etag if completion_verified else None,
        "http_last_modified": http_last_modified if completion_verified else None,
        "before_declared_start": int(obs < start),
    }
    digest=hashlib.sha256(json.dumps(details,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return ScheduleEvent(event_id=digest,**details)


def append_observation(connection: sqlite3.Connection, event: ScheduleEvent) -> bool:
    """Caller owns the transaction. Make INSERT + race UPSERT atomic in the same connection."""
    fields=("event_id","race_id","source_uri","observed_at_utc","source_schedule_raw",
        "normalized_start_utc","source_grade","source_body_sha256","source_time_basis",
        "http_date","http_etag","http_last_modified","before_declared_start")
    sql=("INSERT OR IGNORE INTO race_schedule_observations ("+",".join(fields)+") VALUES ("+",".join("?" for _ in fields)+")")
    cursor=connection.execute(sql,event.values())
    if cursor.rowcount==0:
        original=connection.execute("SELECT "+",".join(fields)+" FROM race_schedule_observations WHERE event_id=?",(event.event_id,)).fetchone()
        if original is None or tuple(original)!=event.values():
            raise ValueError("EVENT_ID_COLLISION_OR_CONFLICT")
        return False
    return True


def schedule_research_status(connection: sqlite3.Connection,race_id: str)->dict:
    """This is only a supplemental RESEARCH gate, never a Betting V3.3.12 gate."""
    rows=connection.execute("SELECT normalized_start_utc,source_time_basis,source_grade "
        "FROM race_schedule_observations WHERE race_id=? ORDER BY observed_at_utc",(race_id,)).fetchall()
    if not rows:
        return {"status":"NO_SCHEDULE_EVIDENCE","versions":0,"distinct_clocks":0,"model_eligible":False}
    clocks={r[0] for r in rows}
    if len(clocks)>1:
        status="CLOCK_VERSION_CONFLICT_REVIEW"
    elif any(r[1]!="HTTP_RESPONSE_COMPLETED" for r in rows):
        status="UNVERIFIED_OBSERVATION_CLOCK"
    else:
        status="HASH_ONLY_SOURCE_REPLAY_NOT_PROVEN"
    return {"status":status,"versions":len(rows),"distinct_clocks":len(clocks),"model_eligible":False}
