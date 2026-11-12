"""CLOUD-RUN-004: opt-in genuine fundamental enrichment of canonical Collector races.

Uses the EXISTING RikstotoCollector/ATG full-field resolver. Archived race/runner
rows remain immutable in this research path; live versions are feature snapshots,
not retroactive replacements. No inferred permanent horse IDs or betting.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Callable

from .fundamental import MarketFreeFundamentalChampionV1
from .rikstoto_collector import RikstotoCollector
from .storage import SQLiteStore

CATEGORY = "CLOUD_RUN004_FUNDAMENTAL_RESEARCH_RECEIPT_V1"
RACE_ID = re.compile(r"RIKSTOTO:([A-Z0-9_]+_\d{4}-\d{2}-\d{2}):([1-9]\d*)\Z")
NO_BET = ("PIT=BLOCKED", "NO_BET_AUTHORITY")


def _now(clock: Callable[[], datetime]) -> datetime:
    observed = clock()
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("ENRICHMENT_CLOCK_NAIVE")
    return observed.astimezone(UTC)


def _append_receipt(
    store: SQLiteStore, *, race_id: str, raceday_key: str,
    race_no: int, at: datetime, payload: dict[str, object],
) -> str:
    """Immutable research receipt with same-key/different-payload conflict detection."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    row = (
        digest, "cloud-run004", CATEGORY, raceday_key, race_no, "FUNDAMENTAL_RESEARCH",
        at.isoformat(), f"research://collector/{race_id}", canonical,
    )
    fields = ("payload_id", "provider", "category", "provider_raceday_key",
              "race_number", "product", "observed_at_utc", "source_uri", "payload_json")
    with store.connect() as db:
        same = db.execute(
            "SELECT * FROM provider_payloads WHERE payload_id=?", (digest,)
        ).fetchone()
        if same is None:
            try:
                db.execute(
                    f"INSERT INTO provider_payloads ({','.join(fields)}) "
                    f"VALUES ({','.join('?' for _ in fields)})", row,
                )
            except Exception as exc:
                raise ValueError("FUNDAMENTAL_RECEIPT_KEY_CONFLICT") from exc
        elif tuple(same[col] for col in fields) != row:
            raise ValueError("FUNDAMENTAL_RECEIPT_HASH_COLLISION_OR_MISMATCH")
        readback = db.execute(
            "SELECT * FROM provider_payloads WHERE payload_id=?", (digest,)
        ).fetchone()
        if readback is None or tuple(readback[col] for col in fields) != row:
            raise ValueError("FUNDAMENTAL_RECEIPT_SQLITE_READBACK_FAILED")
    return digest


def enrich_imported(
    store: SQLiteStore, imported: list[dict[str, object]], *,
    collector: RikstotoCollector | None = None,
    clock: Callable[[], datetime] | None = None,
    min_lead: timedelta = timedelta(minutes=4),
    max_live_races: int = 5,
) -> dict[str, object]:
    """Fetch live starts, scratches and ATG history only for future archived races."""
    clock = clock or (lambda: datetime.now(UTC))
    worker = collector or RikstotoCollector(store, clock=clock)
    if worker.store is not store:
        raise ValueError("ENRICHMENT_SQLITE_OWNER_MISMATCH")
    champion = MarketFreeFundamentalChampionV1()
    if not 1 <= max_live_races <= 30:
        raise ValueError("ENRICHMENT_BATCH_BOUND_INVALID")
    records: list[dict[str, object]] = []
    attempted = 0
    for source in imported:
        race_id = str(source.get("race_id"))
        race = store.get_race(race_id)
        match = RACE_ID.fullmatch(race_id)
        if race is None or match is None or race["race_no"] != int(match.group(2)):
            raise ValueError("ENRICHMENT_RACE_IDENTITY_MISMATCH")
        key, race_no_string = match.groups()
        number = int(race_no_string)
        start = datetime.fromisoformat(str(race["start_time_utc"]))
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("ENRICHMENT_SOURCE_START_CLOCK_INVALID")
        observed = _now(clock)
        record: dict[str, object] = {
            "race_id": race_id, "provider_raceday_key": key, "race_number": number,
            "status": "BLOCKED", "source_ready": source.get("source_ready") is True,
            "source_payload_id": source.get("payload_id"),
            "source_observed_at_utc": str(race["created_at_utc"]),
            "fetch_started_at_utc": None, "fetch_completed_at_utc": None,
            "live_fundamental_snapshot_rows": 0,
            "provisional_cross_provider_identity_matches": 0,
            "permanent_identity_attested": 0,
            "validated_history_rows": 0,
            "candidate_history_rows": 0,
            "full_field_evidence_passed": False,
            "independent_scratch_receipt_sha256": None,
            "source_receipts": {},
            "model_ready": False, "bet_ready": False, "pit_certified": False,
            "reasons": [],
        }
        reasons: list[str] = record["reasons"]  # type: ignore[assignment]
        if source.get("source_ready") is not True:
            reasons.append("ARCHIVED_SOURCE_REVISION_UNREVIEWED")
        elif observed + min_lead >= start:
            reasons.append("RACE_ALREADY_STARTED_OR_TOO_CLOSE_FOR_LIVE_ENRICHMENT")
        elif race["discipline"] != "trot" or race["country"] not in {"NO", "SE"}:
            reasons.append("OUTSIDE_APPROVED_NO_SE_TROT")
        elif attempted >= max_live_races:
            reasons.append("LIVE_RESEARCH_BATCH_LIMIT_DEFERRED")
        else:
            attempted += 1
            record["fetch_started_at_utc"] = observed.isoformat()
            worker.last_capability = None
            try:
                inserted, success, _ = worker.collect_fundamentals(
                    raceday_key=key, race_number=number, race_id=race_id,
                    observed_at=observed, persist_canonical_roster=False,
                )
            except (ValueError, TypeError, KeyError, OSError) as exc:
                # Fail closed, preserve other races; do not fabricate missing features.
                inserted = 0
                success = False
                reasons.append(f"LIVE_ENRICHMENT_EXCEPTION_{type(exc).__name__.upper()}")
            finished = _now(clock)
            record["fetch_completed_at_utc"] = finished.isoformat()
            record["live_fundamental_snapshot_rows"] = inserted
            evidence = worker.last_capability
            receipts = {
                category: value for (scope_race, category), value in worker.source_receipts.items()
                if scope_race == race_id
            }
            record["source_receipts"] = receipts
            scratch = receipts.get("SCRATCHED", {})
            record["independent_scratch_receipt_sha256"] = (
                scratch.get("body_sha256") if scratch.get("source_status") == "HTTP_SUCCESS"
                else None
            )
            if (not success or receipts.get("STARTS", {}).get("source_status") != "HTTP_SUCCESS"):
                reasons.append("LIVE_RIKSTOTO_STARTS_UNAVAILABLE")
            if record["independent_scratch_receipt_sha256"] is None:
                reasons.append("FRESH_SCRATCH_RESPONSE_NOT_VERIFIED")
            if finished >= start:
                reasons.append("LIVE_ENRICHMENT_FINISHED_AFTER_START")
            passed = isinstance(evidence, dict) and evidence.get("passed") is True
            record["full_field_evidence_passed"] = bool(passed)
            if not passed:
                for why in (evidence.get("reasons", []) if isinstance(evidence, dict) else []):
                    if isinstance(why, str):
                        reasons.append(f"EXISTING_FULL_FIELD_GATE_{why}")
                reasons.append("FULL_FIELD_COHORT_NOT_VERIFIED")
            else:
                identity_rows = evidence.get("runners", [])
                record["provisional_cross_provider_identity_matches"] = sum(
                    isinstance(row, dict) and row.get("schema_ok") is True
                    and row.get("match_method") == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
                    and row.get("provider_horse_id") is not None
                    for row in identity_rows
                )
            rows = store.latest_runner_fundamentals(race_id, before=finished)
            for row in rows:
                starts_wins = champion._history(row)
                if (not row.get("scratched") and starts_wins is not None
                        and row.get("data_quality") == "FULL_FIELD_HISTORY_ATG"
                        and row.get("full_field_history_complete") == 1
                        and datetime.fromisoformat(str(row["feature_as_of_utc"])) < start):
                    record["candidate_history_rows"] = int(record["candidate_history_rows"]) + 1
            # Provisional ATG name/number matching is not independent permanent
            # identity attestation or immutable original ATG source archive.
            if record["candidate_history_rows"]:
                reasons.append("ATG_HISTORY_ORIGINAL_BYTES_AND_IDENTITY_UNATTESTED")
            if record["provisional_cross_provider_identity_matches"]:
                reasons.append("CROSS_PROVIDER_MATCH_PROVISIONAL_NOT_PERMANENT_HORSE_ID")
            if not record["independent_scratch_receipt_sha256"]:
                reasons.append("INDEPENDENT_SCRATCH_STATE_MISSING")
            reasons.append("PERMANENT_HORSE_ID_UNATTESTED")
            reasons.append("ORIGINAL_LIVE_RESPONSES_NOT_ARCHIVED")
        record["reasons"] = sorted(set(reasons))
        record["status"] = "RESEARCH_ENRICHMENT_ATTEMPTED" if record["fetch_started_at_utc"] else "NOT_FETCHED"
        # Persist a diagnostic receipt for attempted live fetches, never a model
        # or PIT-qualified row. Skipped races remain in the run manifest.
        if record["fetch_started_at_utc"]:
            record["receipt_payload_id"] = _append_receipt(
                store, race_id=race_id, raceday_key=key, race_no=number,
                at=datetime.fromisoformat(str(record["fetch_completed_at_utc"])),
                payload=record,
            )
        records.append(record)
    return {
        "schema": "CLOUD_RUN004_LIVE_FUNDAMENTAL_ENRICHMENT_V1",
        "races_considered": len(records),
        "live_fetch_attempts": sum(r["fetch_started_at_utc"] is not None for r in records),
        "actual_live_fundamental_snapshots": sum(int(r["live_fundamental_snapshot_rows"]) for r in records),
        "provisional_cross_provider_identity_matches": sum(
            int(r["provisional_cross_provider_identity_matches"]) for r in records
        ),
        "permanent_horse_ids_attested": 0,
        "qualified_fundamental_history_rows": 0,
        "candidate_history_rows": sum(int(r["candidate_history_rows"]) for r in records),
        "full_field_evidence_races": sum(bool(r["full_field_evidence_passed"]) for r in records),
        "records": records,
        "bet_authorized": False, "pit_certified": False,
    }
