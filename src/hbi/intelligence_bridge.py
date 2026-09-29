from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Iterable

from .storage import SQLiteStore

BRIDGE_VERSION = "HBI_INTELLIGENCE_BRIDGE_V1"

ALLOWED_EVENT_TYPES = frozenset(
    {
        "TRAINER_COMMENT",
        "DRIVER_CHANGE_CONTEXT",
        "JOCKEY_CHANGE_CONTEXT",
        "SCRATCH_NOTICE_CONTEXT",
        "TRACK_CONDITION",
        "WEATHER_CHANGE",
        "EQUIPMENT_CHANGE",
        "TROUBLED_TRIP_EVIDENCE",
        "RACE_SHAPE_HYPOTHESIS",
        "LATE_NEWS",
        "INJURY_VET_NOTICE",
        "CLASS_CHANGE_CONTEXT",
        "DISTANCE_TRACK_FIT",
        "PREWATCH_DISCOVERY_SIGNAL",
        "OTHER_RESEARCH_EVIDENCE",
    }
)

FORBIDDEN_CANONICAL_EVENT_TYPES = frozenset(
    {
        "ODDS",
        "MARKET_SNAPSHOT",
        "CLOSING_PRICE",
        "RESULT",
        "WINNER",
        "START_FIELD",
        "RUNNER_HISTORY",
        "FUNDAMENTAL_PROBABILITY",
        "MARKET_PROBABILITY",
        "COMBINED_PROBABILITY",
        "PREDICTION",
        "BET_DECISION",
        "STAKE",
        "SETTLEMENT",
        "MODEL_PROMOTION",
    }
)

ALLOWED_SOURCE_TYPES = frozenset(
    {
        "OFFICIAL",
        "PROVIDER_OFFICIAL",
        "TRACK_OFFICIAL",
        "TRAINER_INTERVIEW",
        "PUBLIC_NEWS",
        "OTHER_PUBLIC",
        "UNKNOWN",
    }
)
ALLOWED_TIME_BASIS = frozenset({"PUBLISHED", "OBSERVED", "UNKNOWN"})
ALLOWED_MATERIALITY = frozenset({"LOW", "MEDIUM", "HIGH", "UNKNOWN"})
ALLOWED_EVIDENCE_STATUS = frozenset(
    {"VERIFIED", "CORROBORATED", "UNVERIFIED", "CONFLICTING"}
)


@dataclass(frozen=True)
class BridgeImportSummary:
    seen: int
    accepted: int
    rejected: int
    duplicates: int
    pit_eligible: int


@dataclass(frozen=True)
class ValidatedIntelligence:
    intelligence_id: str
    race_id: str
    selection_id: str | None
    provider: str | None
    provider_raceday_key: str | None
    race_number: int | None
    observed_at: datetime
    event_type: str
    claim_text: str
    source_uri: str
    source_type: str
    source_timestamp: datetime | None
    source_time_basis: str
    confidence: float
    materiality: str
    evidence_status: str
    prewatch_score: float | None
    policy_version: str
    extractor: str | None
    pit_eligible: bool
    raw: dict[str, object]


class BridgeValidationError(ValueError):
    pass


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: object, *, field: str, required: bool) -> datetime | None:
    text = _clean(value)
    if text is None:
        if required:
            raise BridgeValidationError(f"MISSING_{field.upper()}")
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BridgeValidationError(f"INVALID_{field.upper()}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BridgeValidationError(f"NAIVE_{field.upper()}")
    return parsed.astimezone(UTC)


def _parse_float(
    value: object,
    *,
    field: str,
    minimum: float,
    maximum: float,
    required: bool,
) -> float | None:
    text = _clean(value)
    if text is None:
        if required:
            raise BridgeValidationError(f"MISSING_{field.upper()}")
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise BridgeValidationError(f"INVALID_{field.upper()}") from exc
    if not minimum <= number <= maximum:
        raise BridgeValidationError(f"OUT_OF_RANGE_{field.upper()}")
    return number


def _parse_int(value: object, *, field: str) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise BridgeValidationError(f"INVALID_{field.upper()}") from exc


def _normalize_enum(
    value: object,
    *,
    field: str,
    allowed: frozenset[str],
    default: str | None = None,
) -> str:
    text = _clean(value)
    if text is None:
        if default is not None:
            return default
        raise BridgeValidationError(f"MISSING_{field.upper()}")
    normalized = text.upper()
    if normalized not in allowed:
        raise BridgeValidationError(f"UNSUPPORTED_{field.upper()}:{normalized}")
    return normalized


def _derive_intelligence_id(inbox_id: str) -> str:
    return "intel-" + hashlib.sha256(inbox_id.encode()).hexdigest()[:32]


def _resolve_race(store: SQLiteStore, row: dict[str, object]) -> tuple[str, str | None, str | None, int | None]:
    race_id = _clean(row.get("race_id"))
    provider = _clean(row.get("provider"))
    raceday_key = _clean(row.get("provider_raceday_key"))
    race_number = _parse_int(row.get("race_number"), field="race_number")

    if race_id is not None:
        if store.get_race(race_id) is None:
            raise BridgeValidationError("UNKNOWN_RACE_ID")
        return race_id, provider, raceday_key, race_number

    if provider is None or raceday_key is None or race_number is None:
        raise BridgeValidationError("RACE_ID_OR_PROVIDER_REFERENCE_REQUIRED")
    resolved = store.resolve_provider_race(
        provider=provider.lower(),
        provider_raceday_key=raceday_key,
        race_number=race_number,
    )
    if resolved is None:
        raise BridgeValidationError("UNRESOLVED_PROVIDER_RACE")
    return resolved, provider.lower(), raceday_key, race_number


def validate_intelligence_row(
    store: SQLiteStore,
    row: dict[str, object],
) -> ValidatedIntelligence:
    inbox_id = _clean(row.get("inbox_id"))
    if inbox_id is None:
        raise BridgeValidationError("MISSING_INBOX_ID")

    event_type = (_clean(row.get("event_type")) or "").upper()
    if event_type in FORBIDDEN_CANONICAL_EVENT_TYPES:
        raise BridgeValidationError(f"CANONICAL_EVENT_FORBIDDEN:{event_type}")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise BridgeValidationError(f"UNSUPPORTED_EVENT_TYPE:{event_type or 'EMPTY'}")

    race_id, provider, raceday_key, race_number = _resolve_race(store, row)
    race = store.get_race(race_id)
    if race is None:
        raise BridgeValidationError("UNKNOWN_RACE_ID")

    selection_id = _clean(row.get("selection_id"))
    if selection_id is not None and not store.runner_exists(race_id, selection_id):
        raise BridgeValidationError("UNKNOWN_SELECTION_ID")

    observed_at = _parse_datetime(
        row.get("observed_at_utc"),
        field="observed_at_utc",
        required=True,
    )
    assert observed_at is not None
    source_timestamp = _parse_datetime(
        row.get("source_timestamp_utc"),
        field="source_timestamp_utc",
        required=False,
    )
    race_start = _parse_datetime(
        race["start_time_utc"],
        field="race_start_time_utc",
        required=True,
    )
    assert race_start is not None

    source_type = _normalize_enum(
        row.get("source_type"),
        field="source_type",
        allowed=ALLOWED_SOURCE_TYPES,
        default="UNKNOWN",
    )
    source_time_basis = _normalize_enum(
        row.get("source_time_basis"),
        field="source_time_basis",
        allowed=ALLOWED_TIME_BASIS,
        default="UNKNOWN",
    )
    materiality = _normalize_enum(
        row.get("materiality"),
        field="materiality",
        allowed=ALLOWED_MATERIALITY,
        default="UNKNOWN",
    )
    evidence_status = _normalize_enum(
        row.get("evidence_status"),
        field="evidence_status",
        allowed=ALLOWED_EVIDENCE_STATUS,
        default="UNVERIFIED",
    )

    confidence = _parse_float(
        row.get("confidence"),
        field="confidence",
        minimum=0.0,
        maximum=1.0,
        required=True,
    )
    assert confidence is not None
    prewatch_score = _parse_float(
        row.get("prewatch_score"),
        field="prewatch_score",
        minimum=0.0,
        maximum=100.0,
        required=False,
    )

    claim_text = _clean(row.get("claim_text"))
    if claim_text is None:
        raise BridgeValidationError("MISSING_CLAIM_TEXT")
    source_uri = _clean(row.get("source_uri"))
    if source_uri is None:
        raise BridgeValidationError("MISSING_SOURCE_URI")
    if not source_uri.startswith(("https://", "http://")):
        raise BridgeValidationError("INVALID_SOURCE_URI")

    policy_version = _clean(row.get("policy_version")) or BRIDGE_VERSION
    extractor = _clean(row.get("extractor"))

    source_known_before_observation = (
        source_timestamp is not None and source_timestamp <= observed_at
    )
    pit_eligible = (
        observed_at < race_start
        and source_known_before_observation
        and source_time_basis in {"PUBLISHED", "OBSERVED"}
        and evidence_status in {"VERIFIED", "CORROBORATED"}
    )

    intelligence_id = _clean(row.get("intelligence_id")) or _derive_intelligence_id(inbox_id)

    return ValidatedIntelligence(
        intelligence_id=intelligence_id,
        race_id=race_id,
        selection_id=selection_id,
        provider=provider,
        provider_raceday_key=raceday_key,
        race_number=race_number,
        observed_at=observed_at,
        event_type=event_type,
        claim_text=claim_text,
        source_uri=source_uri,
        source_type=source_type,
        source_timestamp=source_timestamp,
        source_time_basis=source_time_basis,
        confidence=confidence,
        materiality=materiality,
        evidence_status=evidence_status,
        prewatch_score=prewatch_score,
        policy_version=policy_version,
        extractor=extractor,
        pit_eligible=pit_eligible,
        raw=row,
    )


def ingest_intelligence_rows(
    store: SQLiteStore,
    rows: Iterable[dict[str, object]],
    *,
    source_sheet: str,
    imported_at: datetime | None = None,
) -> BridgeImportSummary:
    now = (imported_at or datetime.now(UTC)).astimezone(UTC)
    seen = accepted = rejected = duplicates = pit_count = 0

    existing_ids = {
        str(row["inbox_id"]) for row in store.fetch_table("intelligence_bridge_imports")
    }

    for source_row, row in enumerate(rows, start=2):
        seen += 1
        raw_json = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        inbox_id = _clean(row.get("inbox_id"))
        if inbox_id is None:
            inbox_id = (
                "invalid-"
                + hashlib.sha256(f"{source_sheet}:{source_row}:{raw_json}".encode()).hexdigest()[:32]
            )

        if inbox_id in existing_ids:
            duplicates += 1
            continue

        try:
            valid = validate_intelligence_row(store, row)
        except BridgeValidationError as exc:
            store.record_intelligence_bridge_import(
                {
                    "inbox_id": inbox_id,
                    "imported_at_utc": now.isoformat(),
                    "source_sheet": source_sheet,
                    "source_row": source_row,
                    "status": "REJECTED",
                    "reason": str(exc),
                    "intelligence_id": None,
                    "race_id": _clean(row.get("race_id")),
                    "raw_json": raw_json,
                }
            )
            existing_ids.add(inbox_id)
            rejected += 1
            continue

        inserted = store.insert_intelligence_evidence(
            {
                "intelligence_id": valid.intelligence_id,
                "race_id": valid.race_id,
                "selection_id": valid.selection_id,
                "provider": valid.provider,
                "provider_raceday_key": valid.provider_raceday_key,
                "race_number": valid.race_number,
                "observed_at_utc": valid.observed_at.isoformat(),
                "event_type": valid.event_type,
                "claim_text": valid.claim_text,
                "source_uri": valid.source_uri,
                "source_type": valid.source_type,
                "source_timestamp_utc": (
                    None
                    if valid.source_timestamp is None
                    else valid.source_timestamp.isoformat()
                ),
                "source_time_basis": valid.source_time_basis,
                "confidence": valid.confidence,
                "materiality": valid.materiality,
                "evidence_status": valid.evidence_status,
                "prewatch_score": valid.prewatch_score,
                "policy_version": valid.policy_version,
                "extractor": valid.extractor,
                "pit_eligible": int(valid.pit_eligible),
                "research_only": 1,
                "production_feature_eligible": 0,
                "raw_json": raw_json,
                "created_at_utc": now.isoformat(),
            }
        )
        store.record_intelligence_bridge_import(
            {
                "inbox_id": inbox_id,
                "imported_at_utc": now.isoformat(),
                "source_sheet": source_sheet,
                "source_row": source_row,
                "status": "ACCEPTED" if inserted else "DUPLICATE_EVIDENCE",
                "reason": None if inserted else "INTELLIGENCE_ID_ALREADY_EXISTS",
                "intelligence_id": valid.intelligence_id,
                "race_id": valid.race_id,
                "raw_json": raw_json,
            }
        )
        existing_ids.add(inbox_id)
        if inserted:
            accepted += 1
            pit_count += int(valid.pit_eligible)
        else:
            duplicates += 1

    return BridgeImportSummary(
        seen=seen,
        accepted=accepted,
        rejected=rejected,
        duplicates=duplicates,
        pit_eligible=pit_count,
    )
