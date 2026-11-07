"""DATA-005 read-only historical form adapter; never a Champion/V2 feature switch.

Consumes *source-checked, explicitly status-labelled* historical PDF row data.
An archived race date is not evidence of source publication at model cutoff.
No model training, pricing, odds, betting decisions or horse-identity heuristics.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

VERSION = "DATA005_FORM_RESEARCH_ADAPTER_V1"


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("DATA005_REQUIRED_SOURCE_TIME_MISSING")
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError("DATA005_SOURCE_CLOCK_NOT_AWARE")
    return dt.astimezone(UTC)


def _sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(x in "0123456789abcdef" for x in value))


def form_candidate(
    *, race_id: str, horse_selection_id: str, horse_name: str,
    race_start_utc: str, model_cutoff_utc: str,
    source_original_pdf_sha256: str, source_observed_at_utc: str,
    source_published_at_utc: str | None,
    national_registration: str | None, independent_identity_attested: bool,
    original_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    if (not race_id.startswith("RIKSTOTO:")
            or not horse_selection_id.isdecimal() or not horse_name.strip()
            or not _sha(source_original_pdf_sha256)):
        raise ValueError("DATA005_PHYSICAL_RACE_SOURCE_OR_SELECTION_INVALID")
    cutoff, start, observed = (
        _utc(model_cutoff_utc), _utc(race_start_utc),
        _utc(source_observed_at_utc)
    )
    published = (_utc(source_published_at_utc)
                 if source_published_at_utc else None)
    if not cutoff < start:
        raise ValueError("DATA005_MODEL_CUTOFF_NOT_BEFORE_RACE")
    if not isinstance(original_entries, list):
        raise TypeError("DATA005_HISTORY_ROWS_MUST_BE_LIST")
    status = "PARTIAL"
    blockers = []
    if observed > cutoff or (published is not None and published > cutoff):
        status = "NOT_AVAILABLE_AT_PIT"
        blockers.append("HISTORICAL_SOURCE_OBSERVED_AFTER_FEATURE_CUTOFF")
    if not independent_identity_attested:
        blockers.append("INDEPENDENT_PERMANENT_HORSE_ID_UNATTESTED")
    if not national_registration:
        blockers.append("NATIONAL_REGISTRATION_MISSING")
    if published is None:
        blockers.append("HISTORICAL_PROVIDER_PUBLICATION_TIME_UNATTESTED")
    valid_dates = []
    seen = set()
    rows = []
    for row in original_entries:
        if not isinstance(row, dict):
            raise TypeError("DATA005_HISTORICAL_ROW_INVALID")
        if (row.get("horse") != horse_name
                or str(row.get("selection_id")) != horse_selection_id
                or row.get("original_sha256") != source_original_pdf_sha256):
            raise ValueError("DATA005_SOURCE_HORSE_IDENTITY_OR_SHA_MISMATCH")
        event_date = row.get("historical_date")
        try:
            dt = date.fromisoformat(event_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("DATA005_HISTORICAL_EVENT_DATE_INVALID") from exc
        if dt >= start.date():
            raise ValueError("DATA005_HISTORIC_EVENT_NOT_BEFORE_TARGET")
        key = (event_date, row.get("historical_track_code"),
               row.get("historical_race_number"))
        if key in seen:
            raise ValueError("DATA005_DUPLICATE_HISTORIC_START_ID")
        seen.add(key)
        valid_dates.append(dt)
        rows.append({
            "date":event_date,
            "track_code":row.get("historical_track_code"),
            "race_number_at_track":row.get("historical_race_number"),
            "placing_code":row.get("raw_placing_code"),
            "km_time_raw":row.get("raw_km_time_token"),
            "distance_m":row.get("historical_distance_m"),
            "gallop_marked":row.get("gallop_marked_in_time"),
            "disqualified_marked":row.get("disqualification_marked"),
            "driver_abbrev":row.get("driver_abbrev"),
            "start_method":"MISSING_NOT_ATTESTED",
            "start_post":"MISSING_OR_AMBIGUOUS",
            "official_historic_event_id":"MISSING_NOT_ATTESTED",
            "source_field_evidence_status":row.get(
                "source_field_evidence_status", "PDF_TEXT_LAYER_PARTIAL"
            ),
            "independent_official_result_verified":(
                row.get("independent_official_result_verified") is True
            ),
            "original_line_sha256":row.get("original_line_sha256"),
        })
    if valid_dates != sorted(valid_dates) or len(rows) != 5:
        blockers.append("NO_CHRONOLOGICALLY_COMPLETE_FIVE_SOURCE_ROWS")
    if any(not row["independent_official_result_verified"] for row in rows):
        blockers.append("NO_OFFICIAL_HISTORIC_RESULT_FOR_ALL_FIVE")
    if any(row["source_field_evidence_status"] != "MANUALLY_VERIFIED_ORIGINAL"
           for row in rows):
        blockers.append("ORIGINAL_PDF_COLUMNS_NOT_MANUALLY_CERTIFIED")
    if len(rows) < 5 or blockers:
        status = "NOT_AVAILABLE_AT_PIT" if status == "NOT_AVAILABLE_AT_PIT" else "PARTIAL"
    else:
        status = "READY_FOR_RESEARCH_BUT_NOT_MODEL_ENABLED"
    payload = {
        "schema":VERSION,
        "physical_race_id":race_id,"selection_id":horse_selection_id,
        "horse_name":horse_name,
        "source_original_sha256":source_original_pdf_sha256,
        "source_observed_at_utc":observed.isoformat(),
        "source_published_at_utc":published.isoformat() if published else None,
        "target_cutoff_utc":cutoff.isoformat(),
        "historical_rows":rows,
        "dated_rows":len(rows),"last_5_full_verified":(
            len(rows)==5 and not blockers
        ),
        "previous_10":"MISSING","previous_20":"MISSING",
        "opponent_historical_strength":"MISSING_UNVERIFIED_PREVIOUS_FIELDS",
        "status":status, "blockers":sorted(set(blockers)),
        "source_pit_certified":False,"model_feature_authority":False,
        "model_invocations":0,"bet_authority":False,
        "frozen_champion_unchanged":True,"challenger_v2_unchanged":True,
    }
    signature = json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()
    payload["research_record_sha256"] = hashlib.sha256(signature).hexdigest()
    return payload
