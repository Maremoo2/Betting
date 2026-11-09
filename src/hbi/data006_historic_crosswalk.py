"""DATA-006 strict retrospective DNT official result crosswalk. NO BET.

Official HTML was inspected retrospectively; unless original source bytes, SHA
and publication clocks exist, a correct race result does not prove PIT.
No cross-provider permanent ID is inferred from name or program number.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


def _at(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("DATA006_TIMESTAMP_REQUIRED")
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError("DATA006_TIMESTAMP_NOT_AWARE")
    return dt.astimezone(UTC)


def compare_historic_five(
    *, source_race_id: str, source_runner_selection: str,
    source_horse_name: str, source_ueln: str,
    source_pdf_sha256: str, source_observed_at_utc: str,
    target_start_utc: str, target_cutoff_utc: str,
    original_rows: list[dict[str, Any]],
    official_rows: list[dict[str, Any]],
    national_registry_independently_verified: bool = False,
) -> dict[str, Any]:
    """Exact five race-local source keys and status, never synthetic strength."""
    if (not source_race_id.startswith("RIKSTOTO:")
            or not source_runner_selection.isdecimal()
            or len(source_ueln) != 15 or not source_ueln.isdecimal()
            or not isinstance(source_pdf_sha256, str)
            or len(source_pdf_sha256) != 64
            or any(c not in "0123456789abcdef" for c in source_pdf_sha256)):
        raise ValueError("DATA006_ORIGINAL_RACE_ID_OR_REGISTRATION_INVALID")
    before, target, cutoff = (
        _at(source_observed_at_utc), _at(target_start_utc),
        _at(target_cutoff_utc)
    )
    if not before <= cutoff < target:
        raise ValueError("DATA006_PRESTART_FROZEN_SOURCE_CLOCK_INVALID")
    if len(original_rows) != 5 or len(official_rows) != 5:
        raise ValueError("DATA006_NEEDS_FIVE_SOURCE_AND_OFFICIAL_ROWS")
    original_index = {}
    for r in original_rows:
        if (r.get("horse_name") != source_horse_name
                or str(r.get("selection_id")) != source_runner_selection
                or r.get("ueln") != source_ueln
                or r.get("source_pdf_sha256") != source_pdf_sha256):
            raise ValueError("DATA006_ORIGINAL_HORSE_OR_SHA_MISMATCH")
        d = date.fromisoformat(r["date"])
        if d >= before.date():
            raise ValueError("DATA006_EVENT_NOT_PRE_SOURCE_OBSERVATION")
        key = (r["date"], r["track_code"], r["race_number"])
        if key in original_index:
            raise ValueError("DATA006_DUPLICATE_PRIOR_EVENT")
        original_index[key] = r
    if list(original_index) != sorted(original_index):
        raise ValueError("DATA006_PRIOR_EVENTS_NOT_CHRONOLOGICAL")
    official_index = {}
    for row in official_rows:
        if (row.get("horse_name") != source_horse_name
                or not row.get("official_result_url")
                or not str(row["official_result_url"]).startswith(
                    "https://old.travsport.no/Sport/Resultater/"
                )):
            raise ValueError("DATA006_OFFICIAL_HORSE_OR_SOURCE_MISMATCH")
        key = (row["date"], row["track_code"], row["race_number"])
        if key in official_index:
            raise ValueError("DATA006_DUPLICATE_OFFICIAL_EVENT")
        official_index[key] = row
    if set(official_index) != set(original_index):
        raise ValueError("DATA006_OFFICIAL_SOURCE_EVENT_MISMATCH")
    results = []
    for key, prior in original_index.items():
        official = official_index[key]
        if prior["start_number"] != official["start_number"]:
            raise ValueError("DATA006_HISTORIC_RACE_LOCAL_START_NO_CONFLICT")
        for field in ("distance_m", "placing_code", "km_time", "gallop", "disqualified"):
            if prior.get(field) != official.get(field):
                raise ValueError("DATA006_OFFICIAL_RESULT_FIELD_CONFLICT_" + field.upper())
        # URL is a source locator, not a provider-verified official race UUID.
        source_sha = official.get("official_original_sha256")
        source_sha_verified = (
            isinstance(source_sha, str) and len(source_sha) == 64
            and all(c in "0123456789abcdef" for c in source_sha)
            and official.get("official_original_sha_attested") is True
        )
        result_observed = official.get("official_observed_at_utc")
        original_received_pre_cutoff = (
            result_observed is not None and _at(result_observed) <= cutoff
        )
        published = official.get("official_published_at_utc")
        publication_proved = (
            published is not None and _at(published) <= cutoff
        )
        # Retrospective web row may confirm the result but never attest
        # the historical PIT state or individual permanent UELN.
        pit_certified = (
            source_sha_verified and original_received_pre_cutoff
            and publication_proved and national_registry_independently_verified
        )
        results.append({
            "date": key[0], "track_code": key[1], "race_number": key[2],
            "placing_code": official["placing_code"],
            "km_time": official.get("km_time"),
            "gallop": official.get("gallop"),
            "disqualified": official.get("disqualified"),
            "retrospective_official_result_match": True,
            "individual_ueln_in_official_event_result": False,
            "official_original_sha_attested": source_sha_verified,
            "source_pre_cutoff_observed": original_received_pre_cutoff,
            "publication_pre_cutoff_proved": publication_proved,
            "pit_certified": pit_certified,
            "model_feature_authority": False,
        })
    return {
        "schema": "DATA006_HISTORICAL_FIVE_SOURCE_RECONCILIATION_V1",
        "physical_target_race_id": source_race_id,
        "runner_selection_id": source_runner_selection,
        "ueln": source_ueln,
        "source_pdf_sha256": source_pdf_sha256,
        "source_observed_at_utc": before.isoformat(),
        "status": "VERIFIED_RETROSPECTIVE_OFFICIAL_ROWS_ONLY",
        "official_historic_rows_matched": len(results),
        "individual_register_verified": national_registry_independently_verified,
        "pit_certified": all(r["pit_certified"] for r in results),
        "feature_ready": False, "champion_unchanged": True,
        "challenger_shadow_only": True, "bet_authority": False,
        "rows": results,
    }
