"""Narrow, offline adapter for the archived Bjerke M1 source feed.

This imports a crawler release-body archive, not the unavailable binary ZIP.
Start numbers remain race-local selection IDs; no provider horse ID is inferred.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo

BODY_SHA256 = "d866a4fde7afd4a0e5646c09e676ab624710702effb4a219f98948c1eefaa85b"
SOURCE_URI = (
    "https://api.github.com/repos/Maremoo2/rikstoto-program-collector/releases/418031241"
)
RACE_ID = "BJ_NR_2026-10-20|1"
# GitHub release metadata: creation, not a claimed publication (it is a draft).
RELEASE_CREATED_AT = "2026-10-20T05:20:26+00:00"


def archive_card(body: str) -> tuple[dict, dict]:
    """Require the exact archived bytes, complete source field and pre-start times."""
    actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if actual != BODY_SHA256:
        raise ValueError("ARCHIVE_SHA256_MISMATCH")
    section = body.split("### Race 1 | Bjerke\n", 1)[1].split("### Race 2 |", 1)[0]
    header = re.search(
        r"race_key=(.*?) \| start_local=(\d\d:\d\d) \| distance_m=(\d+)"
        r" \| start_method=(\w+)", section,
    )
    if not header or header[1] != RACE_ID:
        raise ValueError("RACE_IDENTITY_MISMATCH")
    start = datetime.fromisoformat("2026-10-20T" + header[2]).replace(
        tzinfo=ZoneInfo("Europe/Oslo")
    ).astimezone(ZoneInfo("UTC"))
    captured = re.search(r"captured_utc=(\S+)", section)[1]
    pdf_uri = re.search(r"pdf_source_url=(\S+)", section)[1]
    rows = re.findall(
        r"^#(\d+) (.*?) \| driver=(.*?) \| scratch=(\w+)"
        r" \| scratch_asof_utc=(\S+) \| historical_count=(\d+)$", section, re.MULTILINE,
    )
    expected = int(re.search(r"horse_count=(\d+)", section)[1])
    if expected != 12 or len(rows) != expected or len({r[0] for r in rows}) != expected:
        raise ValueError("INCOMPLETE_SOURCE_FIELD")
    for value in [captured, *[r[4] for r in rows]]:
        observed = datetime.fromisoformat(value)
        if observed.tzinfo is None or observed >= start:
            raise ValueError("POST_START_SOURCE")
    history_dates = re.findall(r"^  - (\d{4}-\d\d-\d\d) previous_race=", section, re.MULTILINE)
    if len(history_dates) != 60 or any(d >= "2026-10-20" for d in history_dates):
        raise ValueError("INVALID_PREVIOUS_START_EVIDENCE")
    if any(r[3] != "ACTIVE_AS_OF_SNAPSHOT" or int(r[5]) != 5 for r in rows):
        raise ValueError("UNSUPPORTED_SOURCE_STATUS")
    card = {"race": {
        "race_id": RACE_ID, "race_date": "2026-10-20", "country": "NO",
        "track": "Bjerke", "race_no": 1, "start_time_utc": start.isoformat(),
        "discipline": "trot", "distance_m": int(header[3]), "start_method": header[4],
        "created_at_utc": captured,
    }, "runners": [{
        "race_id": RACE_ID, "selection_id": r[0], "horse_name": r[1], "scratched": 0,
    } for r in rows]}
    provenance = {
        "source_uri": SOURCE_URI, "body_sha256": actual, "pdf_source_uri": pdf_uri,
        "release_created_at": RELEASE_CREATED_AT, "release_is_draft": True,
        "pdf_captured_at": captured, "scratch_asof_utc": rows[0][4],
        "collection_status": "CAPTURED_UNVERIFIED",
        "field_scope": "COMPLETE_AS_OF_ARCHIVED_SNAPSHOT_ONLY",
        "provider_identity_verified": False, "source_runner_count": expected,
        "previous_start_rows": len(history_dates), "raw_race_section": section,
        "missing": ["provider_horse_ids", "calibrated_probability_intervals",
                    "full_field_WIN", "FFQ-1_review", "independent_PLACE_model"],
    }
    return card, provenance


def review_input(card: dict) -> dict:
    """Preserve missing evidence so the existing V3.3 boundary rejects the replay."""
    return {
        "race_id": card["race"]["race_id"],
        "race_start": card["race"]["start_time_utc"],
        "decision_time": RELEASE_CREATED_AT,
        "active_field": [r["selection_id"] for r in card["runners"]],
        "identity_matches": {},
        "hbi_evidence": {"source_uri": SOURCE_URI, "retrospective_replay": True},
    }
