"""Read-only forensic replay of frozen decisions against exact provider snapshots.

Research-only diagnostics. Never updates the database, audits or BET gates.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from hashlib import sha256
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from .decision import DecisionPolicy
from .engine import CombinationPolicy, evaluate_race

TOLERANCE = 1e-12


def _loads_map(value: object) -> dict[str, float] | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict) or not payload:
            return None
        parsed = {str(k): float(v) for k, v in payload.items()}
        return parsed if all(math.isfinite(v) for v in parsed.values()) else None
    except (TypeError, ValueError):
        return None


def _replay_matches(row: sqlite3.Row, odds: dict[str, float]) -> bool:
    fundamental = _loads_map(row["fundamental_probabilities_json"])
    combined = _loads_map(row["combined_probabilities_json"])
    if (not fundamental or not combined or set(fundamental) != set(odds)
            or set(combined) != set(fundamental)):
        return False
    try:
        combo = json.loads(str(row["combination_policy_json"]))
        decision = json.loads(str(row["decision_policy_json"]))
        result = evaluate_race(
            fundamental_probabilities=fundamental,
            market_decimal_odds=odds,
            executable_prices=odds,
            combination_policy=CombinationPolicy(
                fundamental_weight=float(combo["fundamental_weight"]),
                market_weight=float(combo["market_weight"]),
                material_conflict_threshold=float(combo["material_conflict_threshold"]),
            ),
            decision_policy=DecisionPolicy(
                minimum_edge=float(decision["minimum_edge"]),
                safety_margin=float(decision["safety_margin"]),
            ),
        )
    except (TypeError, ValueError, KeyError, OverflowError):
        return False
    return (
        all(abs(result.combined_probabilities[k] - combined[k]) <= TOLERANCE
            for k in fundamental)
        and (row["model_market_conflict_score"] is None
             or abs(result.model_market_conflict_score -
                    float(row["model_market_conflict_score"])) <= TOLERANCE)
    )



def _exact_active_market(entries: list[sqlite3.Row], active: set[str]) -> tuple[dict[str, float], list[str]]:
    """Exact frozen-active WIN odds; ignore only observed, unpriced -0.02 markers.

    A duplicate, missing active quote or priced off-field selection blocks
    reconstruction. This forensic routine never edits V1 parity or history.
    """
    if len(active) < 2:
        return {}, []
    result: dict[str, float] = {}
    excluded: list[str] = []
    seen: set[str] = set()
    for item in entries:
        key = str(item["selection_key"])
        if key in seen or item["odds_decimal"] is None:
            return {}, []
        seen.add(key)
        try:
            price = float(item["odds_decimal"])
        except (ValueError, TypeError, OverflowError):
            return {}, []
        if not math.isfinite(price):
            return {}, []
        if key in active and price > 1:
            result[key] = price
        elif key not in active and price == -0.02:
            excluded.append(key)
        else:
            return {}, []
    return (result, sorted(excluded)) if set(result) == active else ({}, [])



def _evidence_hash(value: object) -> str:
    """Stable hash for the interpreted model/source evidence, not an external attestation."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _database_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provenance_is_later(source_time: object, recorded_at: object) -> bool:
    """Do not classify late attachment from naive, malformed or nonlater timestamps."""
    try:
        source = datetime.fromisoformat(str(source_time))
        recorded = datetime.fromisoformat(str(recorded_at))
    except (ValueError, TypeError):
        return False
    if source.utcoffset() is None or recorded.utcoffset() is None:
        return False
    return recorded > source


def classify_legacy_replay(db_path: Path) -> dict[str, object]:
    """Reconstruct source evidence without correcting or reclassifying old rows."""
    database_sha256 = _database_hash(db_path)
    path = "file:" + quote(str(db_path.resolve())) + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(path, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(
            "SELECT COUNT(*) FROM shadow_decision_runs"
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT d.decision_run_id, d.race_id, d.product, "
            "d.source_market_observed_at_utc, d.fundamental_probabilities_json, "
            "d.combined_probabilities_json, d.model_market_conflict_score, "
            "p.market_odds_json, p.combination_policy_json, p.decision_policy_json, "
            "p.recorded_at_utc AS provenance_recorded_at_utc "
            "FROM shadow_decision_runs d JOIN decision_provenance p "
            "ON d.decision_run_id = p.decision_run_id "
            "WHERE d.fundamental_probabilities_json IS NOT NULL "
            "AND d.combined_probabilities_json IS NOT NULL "
            "ORDER BY d.decision_run_id"
        ).fetchall()
        checked = passed = reconstructed = unresolved = no_saved_odds = 0
        failures: list[dict[str, object]] = []
        for row in rows:
            saved_odds = _loads_map(row["market_odds_json"])
            if saved_odds is None:
                no_saved_odds += 1
                continue
            checked += 1
            if _replay_matches(row, saved_odds):
                passed += 1
                continue
            entries = connection.execute(
                "SELECT selection_key, odds_decimal FROM provider_market_snapshots "
                "WHERE race_id=? AND product=? AND observed_at_utc=? "
                "ORDER BY selection_key",
                (row["race_id"], row["product"],
                 row["source_market_observed_at_utc"]),
            ).fetchall()
            frozen = _loads_map(row["fundamental_probabilities_json"])
            source_odds, excluded_unpriced = _exact_active_market(
                entries, set(frozen) if frozen else set()
            )
            source_complete = bool(source_odds)
            source_replay_pass = (
                source_complete and _replay_matches(row, source_odds)
            )
            proven_later = _provenance_is_later(
                row["source_market_observed_at_utc"],
                row["provenance_recorded_at_utc"],
            )
            verified_legacy = bool(source_replay_pass and proven_later)
            reconstructed += int(verified_legacy)
            unresolved += int(not verified_legacy)
            frozen_hash = _evidence_hash({
                "decision_run_id": row["decision_run_id"],
                "race_id": row["race_id"],
                "product": row["product"],
                "source_time": row["source_market_observed_at_utc"],
                "fundamental": _loads_map(row["fundamental_probabilities_json"]),
                "combined": _loads_map(row["combined_probabilities_json"]),
                "conflict_score": row["model_market_conflict_score"],
            })
            source_hash = _evidence_hash({
                "race_id": row["race_id"], "product": row["product"],
                "observed_at": row["source_market_observed_at_utc"],
                "active_market_odds": source_odds,
                "excluded_unpriced": excluded_unpriced,
            }) if source_complete else None
            attached_hash = _evidence_hash({
                "recorded_at": row["provenance_recorded_at_utc"],
                "market_odds": saved_odds,
                "combination_policy": json.loads(str(row["combination_policy_json"])),
                "decision_policy": json.loads(str(row["decision_policy_json"])),
            })
            failures.append({
                "decision_run_id": row["decision_run_id"],
                "race_id": row["race_id"],
                "classification": (
                    "LEGACY_LATE_PROVENANCE_SOURCE_RECONSTRUCTED"
                    if verified_legacy else "UNRECONCILED"
                ),
                "decision_source_timestamp": row["source_market_observed_at_utc"],
                "provenance_recorded_at": row["provenance_recorded_at_utc"],
                "original_source_selection_count": len(source_odds),
                "saved_provenance_selection_count": len(saved_odds),
                "source_field_complete": source_complete,
                "original_source_replays_frozen": bool(source_replay_pass),
                "provenance_timestamp_strictly_later": proven_later,
                "frozen_inputs_sha256": frozen_hash,
                "exact_source_market_sha256": source_hash,
                "attached_provenance_sha256": attached_hash,
                "excluded_unpriced_nonactive_selections": excluded_unpriced,
                "original_source_differs_from_saved_provenance": (
                    source_odds != saved_odds
                ),
            })
    if _database_hash(db_path) != database_sha256:
        raise RuntimeError("Source database changed during read-only forensic inspection")
    return {
        "schema_version": "HBI_LEGACY_PROVENANCE_DIAGNOSTIC_V1",
        "source_database_sha256": database_sha256,
        "source_database_unchanged": True,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "DIAGNOSTIC_ONLY_NOT_PRODUCTION_CLEARANCE",
        "read_only": True,
        "model_modified": False,
        "existing_integrity_audit_overridden": False,
        "total_decisions": total,
        "provenance_eligible_checked": checked,
        "saved_provenance_replay_pass": passed,
        "legacy_source_reconstructed": reconstructed,
        "unreconciled": unresolved,
        "incomplete_provenance_skipped": total - checked,
        "exceptions": failures,
        "interpretation": (
            "Original-source replay explains historical provenance corruption "
            "but does not authorize overwriting frozen history or overriding "
            "the existing V1 FAIL/BET_BLOCKED decision."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only legacy replay evidence")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = classify_legacy_replay(args.db)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
