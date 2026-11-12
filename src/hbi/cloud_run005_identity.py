"""CLOUD-RUN-005: original-source identity candidates, NOT permanent attestations.

Rikstoto registration number and ATG horse.id are different namespaces. The
existing exact full-field match only permits a candidate; registry identity
requires a separate trusted attestation adapter and original source evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from .collector_handoff import name_key
from .horse_identity import identity_fields
from .storage import SQLiteStore

CATEGORY = "CLOUD_RUN005_IDENTITY_CANDIDATE_V1"


def reconcile_identity_candidates(
    store: SQLiteStore, race_id: str, *, observed_at: datetime,
    original_receipts: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    """Retain independent source IDs with no fabricated cross-namespace equality."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("IDENTITY_COHORT_CLOCK_NAIVE")
    with store.connect() as db:
        race = db.execute("SELECT * FROM races WHERE race_id=?", (race_id,)).fetchone()
        base = [dict(r) for r in db.execute(
            "SELECT * FROM runners WHERE race_id=? ORDER BY selection_id", (race_id,)
        )]
    if race is None or not base:
        raise ValueError("IDENTITY_CANONICAL_FIELD_MISSING")
    rows = store.latest_runner_fundamentals(race_id, before=observed_at)
    snapshots = {str(r["selection_id"]): r for r in rows}
    original_providers = {r["provider"] for r in original_receipts}
    source_receipts = {r["source_type"]: r["receipt_sha256"] for r in original_receipts}
    candidates: list[dict[str, object]] = []
    names = Counter(name_key(str(r["horse_name"])) for r in base)
    reg_owners: dict[str, set[str]] = {}
    atg_owners: dict[str, set[str]] = {}
    for row in base:
        sid = str(row["selection_id"])
        feat = snapshots.get(sid)
        raw: dict = {}
        if feat is not None:
            try:
                parsed = json.loads(feat.get("raw_json") or "{}")
                if isinstance(parsed, dict):
                    raw = parsed
            except (ValueError, TypeError):
                pass
        rik = raw.get("rikstoto") if isinstance(raw.get("rikstoto"), dict) else {}
        atg = raw.get("atg_market_free") if isinstance(
            raw.get("atg_market_free"), dict
        ) else {}
        evidence = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
        reg = rik.get("horseRegistrationNumber")
        reg = reg.strip() if isinstance(reg, str) and reg.strip() else None
        stable_reg_candidate = bool(
            reg and not reg.upper().startswith(("TMP", "TEMP", "UNKNOWN"))
        )
        atg_id = atg.get("horseId")
        atg_id = str(atg_id).strip() if atg_id is not None else None
        if not atg_id:
            atg_id = None
        name_match = (
            name_key(str(row["horse_name"])) == name_key(str(rik.get("horseName") or ""))
            and names[name_key(str(row["horse_name"]))] == 1
        )
        exactly_matched = (
            feat is not None and name_match
            and evidence.get("selection_id") == sid
            and evidence.get("match_method") == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
            and evidence.get("match_confidence") == 1.0
            and evidence.get("schema_ok") is True
            and feat.get("data_quality") == "FULL_FIELD_HISTORY_ATG"
            and feat.get("full_field_history_complete") == 1
        )
        status = ("CANDIDATE" if (
            exactly_matched and stable_reg_candidate and atg_id
            and {"atg", "rikstoto"}.issubset(original_providers)
        ) else "UNATTESTED")
        blockers: list[str] = []
        if not stable_reg_candidate:
            blockers.append("REGISTRY_NUMBER_MISSING_OR_TEMPORARY")
        if not atg_id:
            blockers.append("ATG_HORSE_ID_MISSING")
        if not exactly_matched:
            blockers.append("INDEPENDENT_FULL_FIELD_NAME_AND_NUMBER_MATCH_MISSING")
        if "ATG_RACE" not in source_receipts or "STARTS" not in source_receipts:
            blockers.append("ORIGINAL_CROSS_PROVIDER_BODY_EVIDENCE_MISSING")
            status = "UNATTESTED"
        if status == "CANDIDATE":
            reg_owners.setdefault(reg, set()).add(sid)
            atg_owners.setdefault(atg_id, set()).add(sid)
        permanent = identity_fields(race_id, sid)  # No authority attestation supplied.
        candidates.append({
            "schema": CATEGORY, "race_id": race_id, "selection_id": sid,
            "rikstoto_registration_number": reg, "atg_horse_id": atg_id,
            "race_local_program_number": sid, "horse_name": str(row["horse_name"]),
            "identity_match_method": evidence.get("match_method"),
            "identity_source_versions": source_receipts,
            "proposed_status": status, "status": status,
            **permanent,
            "attestation_source": None, "attestation_version": None,
            "blockers": sorted(set(blockers)),
            "pit_certified": False, "bet_authorized": False,
        })
    for entry in candidates:
        sid = entry["selection_id"]
        reg = entry["rikstoto_registration_number"]
        atg = entry["atg_horse_id"]
        if entry["status"] == "CANDIDATE" and (
            len(reg_owners.get(reg, set())) != 1 or len(atg_owners.get(atg, set())) != 1
        ):
            entry["status"] = "REJECTED_CONFLICT"
            entry["blockers"].append("MULTIPLE_SELECTIONS_SHARE_PROVIDER_ID")
    at = observed_at.astimezone(UTC).isoformat()
    for entry in candidates:
        encoded = json.dumps(entry, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False)
        identity_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        fields = ("payload_id", "provider", "category", "provider_raceday_key",
                  "race_number", "product", "observed_at_utc", "source_uri", "payload_json")
        key = race_id[len("RIKSTOTO:"):].rsplit(":", 1)[0]
        values = (
            identity_id, "cloud-run005", CATEGORY, key, int(race["race_no"]),
            str(entry["selection_id"]), at, f"research://identity/{race_id}", encoded,
        )
        with store.connect() as db:
            prior = db.execute(
                "SELECT * FROM provider_payloads WHERE payload_id=?", (identity_id,)
            ).fetchone()
            if prior is None:
                db.execute(
                    f"INSERT INTO provider_payloads ({','.join(fields)}) "
                    f"VALUES ({','.join('?' for _ in fields)})", values
                )
            elif tuple(prior[f] for f in fields) != values:
                raise ValueError("IDENTITY_CANDIDATE_SQLITE_HASH_CONFLICT")
        entry["identity_payload_id"] = identity_id
    return {
        "race_id": race_id, "total": len(candidates),
        "candidate": sum(r["status"] == "CANDIDATE" for r in candidates),
        "rejected": sum(r["status"] == "REJECTED_CONFLICT" for r in candidates),
        "unattested": sum(r["status"] == "UNATTESTED" for r in candidates),
        "permanent_attested": 0,
        "records": candidates,
        "pit_certified": False, "bet_authorized": False,
    }
