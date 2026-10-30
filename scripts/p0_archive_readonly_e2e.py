"""Read-only restored-state P0 forensic E2E. Never clears V1 gates or settles tickets."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

TOLERANCE = 1e-12
OFFICIAL_CATEGORIES = ("OFFICIAL_COMPLETE_RESULTS", "OFFICIAL_RACEDAY_RESULTS")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value: object) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def probabilities(raw: object) -> dict[str, float] | None:
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, dict) or len(parsed) < 2:
            return None
        values = {str(k): float(v) for k, v in parsed.items()}
        if any(not math.isfinite(v) or not 0 < v < 1 for v in values.values()):
            return None
        return values if abs(sum(values.values()) - 1) <= TOLERANCE else None
    except (TypeError, ValueError, OverflowError):
        return None


def odds_map(raw: object) -> dict[str, float] | None:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(value, dict) or len(value) < 2:
            return None
        parsed = {str(k): float(v) for k, v in value.items()}
        return parsed if all(math.isfinite(v) and v > 1 for v in parsed.values()) else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize(odds: dict[str, float]) -> dict[str, float]:
    inverse = {k: 1.0 / v for k, v in odds.items()}
    denominator = sum(inverse.values())
    return {k: value / denominator for k, value in inverse.items()}


def maps_match(a: dict[str, float], b: dict[str, float]) -> bool:
    return set(a) == set(b) and all(abs(a[k] - b[k]) <= TOLERANCE for k in a)


def exact_source(conn: sqlite3.Connection, row: sqlite3.Row, active: set[str]):
    entries = conn.execute(
        "SELECT selection_key,odds_decimal FROM provider_market_snapshots "
        "WHERE race_id=? AND product=? AND observed_at_utc=? ORDER BY selection_key",
        (row["race_id"], row["product"], row["source_market_observed_at_utc"]),
    ).fetchall()
    odds: dict[str, float] = {}
    unpriced: list[str] = []
    observed: set[str] = set()
    for entry in entries:
        key = str(entry["selection_key"])
        if key in observed or entry["odds_decimal"] is None:
            return None, []
        observed.add(key)
        try:
            price = float(entry["odds_decimal"])
        except (TypeError, ValueError, OverflowError):
            return None, []
        if not math.isfinite(price):
            return None, []
        if key in active and price > 1:
            odds[key] = price
        elif key not in active and price == -0.02:
            unpriced.append(key)
        else:
            return None, []
    return (odds, sorted(unpriced)) if set(odds) == active else (None, [])


def aware_later(later: object, earlier: object) -> bool:
    try:
        a = datetime.fromisoformat(str(later))
        b = datetime.fromisoformat(str(earlier))
        return a.utcoffset() is not None and b.utcoffset() is not None and a > b
    except (TypeError, ValueError):
        return False


def later_attached_cohort(conn: sqlite3.Connection, row: sqlite3.Row,
                          attached: dict[str, float]) -> str | None:
    cohorts = conn.execute(
        "SELECT observed_at_utc,selection_key,odds_decimal FROM provider_market_snapshots "
        "WHERE race_id=? AND product=? AND observed_at_utc>? "
        "ORDER BY observed_at_utc,selection_key",
        (row["race_id"], row["product"], row["source_market_observed_at_utc"]),
    )
    current_time: str | None = None
    group: dict[str, float] = {}
    invalid = False

    def matches() -> bool:
        return not invalid and set(group) == set(attached) and all(
            abs(group[k] - attached[k]) <= TOLERANCE for k in attached
        )

    for entry in cohorts:
        ts = str(entry["observed_at_utc"])
        if ts != current_time:
            if current_time is not None and matches() and aware_later(
                current_time, row["source_market_observed_at_utc"]
            ):
                return current_time
            current_time, group, invalid = ts, {}, False
        key = str(entry["selection_key"])
        try:
            price = float(entry["odds_decimal"])
        except (TypeError, ValueError, OverflowError):
            invalid = True
            continue
        if key in group or not math.isfinite(price):
            invalid = True
        elif key in attached and price > 1:
            group[key] = price
        elif key not in attached and price == -0.02:
            continue
        else:
            invalid = True
    return current_time if current_time and matches() and aware_later(
        current_time, row["source_market_observed_at_utc"]
    ) else None


def inspect(db_path: Path, audit_path: Path | None = None) -> dict[str, object]:
    before = file_hash(db_path)
    uri = "file:" + quote(str(db_path.resolve())) + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM shadow_decision_runs").fetchone()[0]
        data = conn.execute(
            "SELECT d.decision_run_id,d.race_id,d.product,d.source_market_observed_at_utc,"
            "d.market_probabilities_json,d.fundamental_probabilities_json,"
            "p.market_odds_json,p.recorded_at_utc FROM shadow_decision_runs d "
            "JOIN decision_provenance p ON d.decision_run_id=p.decision_run_id "
            "ORDER BY d.decision_run_id"
        ).fetchall()
        checked = 0
        exceptions = []
        for row in data:
            market = probabilities(row["market_probabilities_json"])
            fundamental = probabilities(row["fundamental_probabilities_json"])
            attached = odds_map(row["market_odds_json"])
            if market is None or fundamental is None or attached is None:
                continue
            if set(market) != set(fundamental) or set(market) != set(attached):
                continue
            checked += 1
            if maps_match(market, normalize(attached)):
                continue
            original, excluded = exact_source(conn, row, set(market))
            original_matches = original is not None and maps_match(market, normalize(original))
            later = later_attached_cohort(conn, row, attached)
            late_timestamp = aware_later(
                row["recorded_at_utc"], row["source_market_observed_at_utc"]
            )
            supported = bool(original_matches and later and late_timestamp)
            exceptions.append({
                "decision_run_id": row["decision_run_id"],
                "race_id": row["race_id"],
                "classification": (
                    "EXACT_SOURCE_AND_LATE_ATTACHMENT_CORROBORATED"
                    if supported else "UNRECONCILED"
                ),
                "original_source_market_matches_frozen": bool(original_matches),
                "later_attached_cohort_at_utc": later,
                "provenance_recorded_strictly_later": late_timestamp,
                "excluded_inactive_unpriced_keys": excluded,
                "max_attached_market_probability_delta": max(
                    abs(normalize(attached)[k] - market[k]) for k in market
                ),
                "frozen_market_sha256": fingerprint(market),
                "original_market_sha256": fingerprint(original) if original else None,
                "attached_odds_sha256": fingerprint(attached),
            })
        unresolved = sum(item["classification"] == "UNRECONCILED" for item in exceptions)
        open_tickets = []
        for ticket in conn.execute(
            "SELECT ticket_id,race_id,provider_raceday_key,status,selections_json,"
            "stake_nok,settled_at_utc,net_pnl_nok FROM shadow_tickets "
            "WHERE status='SHADOW_BET' ORDER BY ticket_id"
        ):
            winner = conn.execute(
                "SELECT winner_selection_id FROM outcomes WHERE race_id=?",
                (ticket["race_id"],),
            ).fetchone()
            categories = conn.execute(
                "SELECT category, COUNT(*) AS n FROM provider_payloads "
                "WHERE provider_raceday_key=? AND category IN (?,?) GROUP BY category",
                (ticket["provider_raceday_key"], *OFFICIAL_CATEGORIES),
            ).fetchall()
            open_tickets.append({
                "ticket_id": ticket["ticket_id"],
                "race_id": ticket["race_id"],
                "status": ticket["status"],
                "selections_json": ticket["selections_json"],
                "paper_stake_nok": ticket["stake_nok"],
                "stored_winner": winner["winner_selection_id"] if winner else None,
                "archived_official_result_payloads": sum(x["n"] for x in categories),
                "recorded_settlement": ticket["settled_at_utc"],
                "recorded_pnl": ticket["net_pnl_nok"],
                "settlement_authority": False,
            })
    after = file_hash(db_path)
    if before != after:
        raise RuntimeError("Archived SQLite changed during read-only review")
    audit_reference = None
    if audit_path is not None:
        external = json.loads(audit_path.read_text(encoding="utf-8"))
        replay = external["runtime_replay_parity"]
        mismatches = {str(x["decision_run_id"]) for x in replay["mismatches"]}
        observed = {str(x["decision_run_id"]) for x in exceptions}
        audit_reference = {
            "audit_json_sha256": file_hash(audit_path),
            "audited_decisions": replay["checked_decisions"],
            "audited_skipped": replay["skipped_decisions"],
            "audit_status": replay["status"],
            "audit_mismatch_ids_match_state": mismatches == observed,
            "audit_total_decisions": replay["checked_decisions"] + replay["skipped_decisions"],
            "state_decision_count": total,
            "exact_same_decision_denominator": (
                total == replay["checked_decisions"] + replay["skipped_decisions"]
            ),
            "warning": "Audit and Watcher artifacts are not one identical pinned state "
                       "unless the decision denominators and provenance match.",
        }
    report: dict[str, object] = {
        "schema": "P0_ARCHIVE_READONLY_E2E_V1",
        "authority": "RESEARCH_EVIDENCE_ONLY_NO_AUDIT_OVERRIDE",
        "p0_status": "BLOCKED",
        "source_database_sha256": before,
        "source_database_unchanged": True,
        "total_decisions": total,
        "checked_market_replays": checked,
        "skipped_decisions": total - checked,
        "market_replay_mismatches": len(exceptions),
        "original_source_and_late_provenance_confirmed": len(exceptions) - unresolved,
        "unreconciled_market_replays": unresolved,
        "exceptions": exceptions,
        "open_shadow_tickets": open_tickets,
        "audit_reference": audit_reference,
        "real_money_authority": False,
        "model_promotion_authority": False,
    }
    report["report_sha256"] = fingerprint(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--audit-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None and args.output.resolve() in {
        args.db.resolve(),
        *( [args.audit_json.resolve()] if args.audit_json is not None else [] ),
    }:
        parser.error("Output must not overwrite input database or source audit")
    result = inspect(args.db, args.audit_json)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
