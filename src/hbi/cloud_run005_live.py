"""LIVE-RACE-001: one-shot genuine Rikstoto NO/SE pre-race research.

Only the already implemented RikstotoCollector, provider full-field gate and
frozen Champion admission are used; no independent consumer betting authority.
No production schedule, new parser, constructed horse IDs, or fabricated odds.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .cloud_run003_model import assess_and_run
from .cloud_run005_identity import reconcile_identity_candidates
from .cloud_run005_originals import OriginalCapture, verify_all
from .providers.atg import AtgClient
from .providers.rikstoto import RikstotoClient
from .rikstoto_collector import RikstotoCollector
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
OSLO = ZoneInfo("Europe/Oslo")
KEYS = ("ST_NR_", "S2_NR_")


def run_day(
    *, db: Path, archive_root: Path, day: str | None = None,
    max_races: int = 20,
) -> dict[str, object]:
    now = datetime.now(UTC)
    wanted = day or now.astimezone(OSLO).date().isoformat()
    if wanted != now.astimezone(OSLO).date().isoformat():
        raise ValueError("LIVE_RACE_DATE_MUST_BE_TODAY")
    if max_races < 1 or max_races > 20:
        raise ValueError("LIVE_RACE_BOUNDED_FIELD_SIZE_INVALID")
    store = SQLiteStore(db)
    store.initialize(ROOT / "db/schema.sql")
    store.apply_migrations(ROOT / "db/migrations")
    discoverer = RikstotoCollector(store)
    actual_races = discoverer.discover(now=now)
    wanted_keys = {prefix + wanted for prefix in KEYS}
    found = [
        race for race in actual_races
        if race.raceday_key in wanted_keys and race.start_time.astimezone(UTC) >
        datetime.now(UTC) + timedelta(minutes=4)
    ]
    found.sort(key=lambda race: (race.start_time, race.raceday_key, race.race_number))
    records: list[dict[str, object]] = []
    source_records: list[dict[str, object]] = []
    for race in found[:max_races]:
        race_id = race.race_id
        observed = datetime.now(UTC)
        capture = OriginalCapture(store, archive_root, race_id)
        fetcher = RikstotoCollector(
            store, client=RikstotoClient(archive_hook=capture.capture),
            atg_client=AtgClient(archive_hook=capture.capture),
        )
        status: dict[str, object] = {
            "race_id": race_id, "track": race.raceday_name,
            "scheduled_start_utc": race.start_time.astimezone(UTC).isoformat(),
            "live_request_started_at_utc": observed.isoformat(),
            "run_status": "RESEARCH_ONLY",
            "source_ready": False, "model_ready": False,
            "bet_ready": False, "identity_candidates": 0,
            "identity_attested": 0, "full_field_evidence": False,
            "p_win": None, "fair_odds": None,
            "win_market_snapshot_count": 0,
            "win_market_fetch_failures": 0,
            "win_market_observed_at_utc": None,
            "win_market_source_sha256": None,
            "win_prices": [],
            "reasons": [],
        }
        try:
            count, fetched, _ = fetcher.collect_fundamentals(
                raceday_key=race.raceday_key,
                race_number=race.race_number,
                race_id=race_id,
                observed_at=observed,
                persist_canonical_roster=True,
            )
            status["live_fundamental_rows"] = count
            status["source_receipts"] = capture.receipts
            at = datetime.now(UTC)
            status["fetch_completed_at_utc"] = at.isoformat()
            statuses = {
                category: receipt for (scope, category), receipt
                in fetcher.source_receipts.items() if scope == race_id
            }
            starts_ok = (
                statuses.get("STARTS", {}).get("source_status") == "HTTP_SUCCESS"
                and any(r["source_type"] == "STARTS" for r in capture.receipts)
            )
            scratch_ok = (
                statuses.get("SCRATCHED", {}).get("source_status") == "HTTP_SUCCESS"
                and any(r["source_type"] == "SCRATCHED" for r in capture.receipts)
            )
            if not fetched or not starts_ok or not scratch_ok:
                status["reasons"].append("LIVE_FIELD_OR_SCRATCH_SOURCE_INCOMPLETE")
            if at + timedelta(minutes=4) >= race.start_time.astimezone(UTC):
                status["reasons"].append("LIVE_T4_CUTOFF_NOT_MET")
            if count < 2:
                status["reasons"].append("LIVE_FUNDAMENTAL_FIELD_MISSING")
            status["source_ready"] = (
                fetched and starts_ok and scratch_ok and count >= 2
                and at + timedelta(minutes=4) < race.start_time.astimezone(UTC)
            )
            original_atg = any(r["source_type"] == "ATG_RACE" for r in capture.receipts)
            if not original_atg:
                status["reasons"].append("ATG_RACE_ORIGINAL_UNAVAILABLE")
            identity = reconcile_identity_candidates(
                store, race_id, observed_at=at,
                original_receipts=tuple(capture.receipts),
            )
            status["identity_candidates"] = identity["candidate"]
            status["identity_unattested"] = identity["unattested"]
            status["identity_rejected"] = identity["rejected"]
            status["identity_attested"] = identity["permanent_attested"]
            status["full_field_evidence"] = bool(
                isinstance(fetcher.last_capability, dict)
                and fetcher.last_capability.get("passed") is True
            )
            status["source_originals_sha_verified"] = len(capture.receipts)
            # Read-only WIN research evidence is recorded independently of
            # eligibility. Prices alone cannot authorize EV or BET.
            market_started = datetime.now(UTC)
            market_worker = RikstotoCollector(store)
            market_count, market_failures = market_worker.collect_market(
                raceday_key=race.raceday_key,
                race_number=race.race_number, race_id=race_id,
                observed_at=market_started, products={"V"},
            )
            status["win_market_snapshot_count"] = market_count
            status["win_market_fetch_failures"] = market_failures
            status["win_market_observed_at_utc"] = market_started.isoformat()
            market_receipt = market_worker.source_receipts.get((race_id, "V"), {})
            status["win_market_source_sha256"] = market_receipt.get("body_sha256")
            if market_failures or market_receipt.get("source_status") != "HTTP_SUCCESS":
                status["reasons"].append("WIN_SOURCE_UNAVAILABLE")
            with store.connect() as connection:
                prices = [
                    dict(row) for row in connection.execute(
                        "SELECT selection_key,odds_decimal,provider_updated_at_utc "
                        "FROM provider_market_snapshots WHERE provider='rikstoto' "
                        "AND race_id=? AND product='V' AND observed_at_utc=? "
                        "ORDER BY CAST(selection_key AS INTEGER)",
                        (race_id, market_started.isoformat()),
                    )
                ]
            status["win_prices"] = prices
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            status["run_status"] = "SOURCE_OR_IDENTITY_BLOCKED"
            status["reasons"].append(f"LIVE_RACE_FAILURE_{type(exc).__name__.upper()}")
        status["reasons"] = sorted(set(status["reasons"]))
        records.append(status)
        source_records.append({
            "race_id": race_id, "source_ready": status["source_ready"],
            "status": status["run_status"], "payload_id": (
                status.get("source_receipts") or [{}]
            )[0].get("receipt_sha256"),
        })
    model = assess_and_run(store, source_records, now=datetime.now(UTC)) if records else {
        "evaluated_races": 0, "model_input_complete": 0, "p_win_computed": 0,
        "records": [], "model_reject_reasons": {"NO_LIVE_RACES_DISCOVERED": 1},
    }
    by_race = {entry["race_id"]: entry for entry in model["records"]}
    for record in records:
        projection = by_race.get(record["race_id"])
        if projection is not None:
            record["model_ready"] = projection["model_ready"]
            record["p_win"] = projection["p_win"]
            record["fair_odds"] = projection["fair_odds"]
            record["model_reasons"] = projection["reasons"]
            record["bet_ready"] = False
            record["win_ev_status"] = "NOT_APPLICABLE_NO_QUALIFIED_MODEL"
    archived = verify_all(archive_root) if any(r.get("source_receipts") for r in records) else {
        "status": "NO_ARCHIVED_LIVE_ORIGINALS", "receipts": 0,
        "unique_originals": 0, "pit_certified": False,
    }
    store.checkpoint()
    return {
        "schema": "LIVE_RACE_001_CLOUD_RUN005_RESEARCH_V1",
        "oslo_date": wanted, "run_started_at_utc": now.isoformat(),
        "run_finished_at_utc": datetime.now(UTC).isoformat(),
        "provider_discovered_total": len(actual_races),
        "remaining_eligible_selected": len(found),
        "attempted": len(records),
        "originals_readback": archived["receipts"],
        "original_archive_status": archived["status"],
        "identity_candidate_total": sum(int(r["identity_candidates"]) for r in records),
        "permanent_identity_attested": 0,
        "win_market_snapshots": sum(
            int(r["win_market_snapshot_count"]) for r in records
        ),
        "win_market_races_with_prices": sum(
            bool(r["win_prices"]) for r in records
        ),
        "model_ready": model["model_input_complete"],
        "p_win_computed": model["p_win_computed"],
        "model_reasons": model["model_reject_reasons"],
        "race_records": records,
        "retrospective_replay": False,
        "pit_certified": False, "bet_authorized": False, "auto_bet": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--originals", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--day", default=None)
    ap.add_argument("--max-races", type=int, default=20)
    args = ap.parse_args()
    report = run_day(
        db=args.db, archive_root=args.originals,
        day=args.day, max_races=args.max_races,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "schema": report["schema"], "oslo_date": report["oslo_date"],
        "remaining_eligible_selected": report["remaining_eligible_selected"],
        "attempted": report["attempted"], "originals_readback": report["originals_readback"],
        "identity_candidate_total": report["identity_candidate_total"],
        "win_market_snapshots": report["win_market_snapshots"],
        "win_market_races_with_prices": report["win_market_races_with_prices"],
        "permanent_identity_attested": 0,
        "model_ready": report["model_ready"], "p_win_computed": report["p_win_computed"],
        "bet_authorized": False,
    }, sort_keys=True))
    if report["originals_readback"] < 1:
        raise SystemExit("LIVE_RACE_NO_ORIGINAL_BYTES_ARCHIVED_FAIL_CLOSED")


if __name__ == "__main__":
    main()
