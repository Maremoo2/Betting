"""Read-only October Pre-Watch funnel/near-threshold ledger audit.

The exported Google Sheet is a *dashboard*, not canonical racing truth.
This audit describes stored observations only and never revises frozen
V3.3.12 scores, probability snapshots or betting eligibility.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = {
    "PreWatchFunnel": (
        "race_id", "race_date", "screening_status_formula", "total_formula",
        "data_25", "shape_20", "mispricing_30", "liquidity_15", "today_fit_10",
        "source_backed_hypothesis", "uncertainty_and_missing",
        "liquidity_source_and_proxy", "candidate_horse_no_name",
    ),
    "PreWatchPreflight": (
        "race_id", "observed_at_utc", "scheduled_start_oslo",
        "win_market_scope", "win_pool_amount", "win_pool_asof", "operational_gate",
    ),
    "MarketSnapshots": (
        "race_id", "snapshot_id", "market_type", "observed_at",
        "scheduled_start_at", "is_prestart", "full_field_same_timestamp",
    ),
    "FrozenDecisions": ("race_id", "decision_id", "status", "hard_gates_pass"),
    "ProbabilitySnapshots": ("race_id", "snapshot_id", "frozen_at_iso", "p_win"),
    "RunLog": ("run_id", "run_time_iso", "identified_races"),
}
OPTIONAL_COLUMNS = {
    "RaceInventory": ("race_id", "assessment_status"),
    "PreWatchSelectionAudit": ("race_id", "selection_id", "selection_decision"),
}
FROZEN_A_WATCH_MIN = Decimal(70)
FROZEN_MISPRICING_MIN = Decimal(18)
FROZEN_LIQUIDITY_MIN = Decimal(8)


def _decimal(value: Any) -> Decimal | None:
    value = str(value if value is not None else "").strip()
    if not value or value.startswith("#"):
        return None
    try:
        number = Decimal(value)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def _clock(value: str) -> datetime | None:
    try:
        instant = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return instant.astimezone(timezone.utc) if instant.tzinfo else None


def _race_date(race_id: str) -> date | None:
    parts = race_id.split("|")
    if len(parts) != 3 or not parts[1].strip() or not parts[2].strip():
        return None
    try:
        return date.fromisoformat(parts[0])
    except ValueError:
        return None


def _status(row: dict[str, str]) -> str:
    value = row.get("screening_status_formula", "").strip()
    if value.startswith("#REF!") or value.startswith("#"):
        return "FORMULA_ERROR"
    return value or "UNKNOWN_STATUS"


def read_exported_tabs(directory: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, str]]:
    """Exact CSV headers; intentionally skip blank spacer rows in Sheets exports."""
    tabs: dict[str, list[dict[str, str]]] = {}
    hashes: dict[str, str] = {}
    for name, columns in {**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}.items():
        path = directory / f"{name}.csv"
        if not path.is_file():
            if name in REQUIRED_COLUMNS:
                raise ValueError(f"Missing required read-only export: {name}.csv")
            tabs[name] = []
            continue
        source = path.read_bytes()
        hashes[name] = hashlib.sha256(source).hexdigest()
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError(f"Invalid/duplicate CSV headers: {name}")
            if not set(columns).issubset(reader.fieldnames):
                raise ValueError(f"Missing expected export columns: {name}")
            result = []
            for entry in reader:
                if None in entry:
                    raise ValueError(f"Extra unnamed CSV cells in {name}")
                if not any(str(v or "").strip() for v in entry.values()):
                    continue
                row = {key: str(value or "").strip() for key, value in entry.items()}
                if not row.get("race_id", row.get("run_id", "")):
                    raise ValueError(f"Nonblank row without source identity in {name}")
                result.append(row)
            tabs[name] = result
    return tabs, hashes


def _preflight_evidence(
    race_id: str, preflights: list[dict[str, str]]
) -> tuple[dict[str, Any], list[str]]:
    before = []
    after = []
    bad_clock = 0
    for row in preflights:
        observed = _clock(row.get("observed_at_utc", ""))
        scheduled = _clock(row.get("scheduled_start_oslo", ""))
        if observed is None or scheduled is None:
            bad_clock += 1
        elif observed < scheduled:
            before.append((observed, row))
        else:
            after.append(row)
    # No post-start observation can retrospectively validate a prestart score.
    latest = max(before, key=lambda item: item[0])[1] if before else None
    reported_scope = latest["win_market_scope"] if latest else ""
    amount = _decimal(latest["win_pool_amount"]) if latest else None
    pool_asof = _clock(latest["win_pool_asof"]) if latest else None
    observed = _clock(latest["observed_at_utc"]) if latest else None
    scheduled = _clock(latest["scheduled_start_oslo"]) if latest else None
    # These labels are navigation observations, never independent proof
    # of actual WIN liquidity or Phase B approval.
    individual = reported_scope in {"CURRENT_STANDALONE_WIN", "CURRENT_INDIVIDUAL_WIN"}
    contemporaneous = (
        individual and amount is not None and amount > 0 and pool_asof is not None
        and scheduled is not None and observed is not None
        and pool_asof.date() == scheduled.date()
        and pool_asof <= observed < scheduled
    )
    reasons = []
    if not before:
        reasons.append("NO_TIMESTAMP_VERIFIED_PRESTART_PREFLIGHT")
    if bad_clock:
        reasons.append("PREFLIGHT_INVALID_OR_MISSING_TIMESTAMP")
    if after:
        reasons.append("POSTSTART_PREFLIGHT_EXCLUDED_FROM_PRIOR_DECISION")
    if not contemporaneous:
        reasons.append("CURRENT_STANDALONE_WIN_POOL_NOT_ESTABLISHED")
    return {
        "prestart_preflight_observations": len(before),
        "poststart_preflight_observations_excluded": len(after),
        "unparseable_preflight_timestamps": bad_clock,
        "latest_prestart_operational_gate": latest["operational_gate"] if latest else None,
        "win_pool_evidence_class": (
            "SELF_REPORTED_CURRENT_WIN_POOL_UNCORROBORATED"
            if contemporaneous else "UNKNOWN_OR_PROXY_NOT_MEASURED"
        ),
        "same_race_live_WIN_source_independently_confirmed": False,
    }, reasons


def _market_evidence(
    snapshots: list[dict[str, str]]
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in snapshots:
        grouped[item["snapshot_id"]].append(item)
    win_groups = 0
    declared_complete = 0
    stale_or_poststart = 0
    for group in grouped.values():
        if not all(item["market_type"] == "WIN" for item in group):
            continue
        win_groups += 1
        clocks = [(_clock(x["observed_at"]), _clock(x["scheduled_start_at"])) for x in group]
        valid_prestart = all(
            observed is not None and start is not None and observed < start
            and x["is_prestart"].upper() == "YES"
            for x, (observed, start) in zip(group, clocks, strict=True)
        )
        if not valid_prestart:
            stale_or_poststart += 1
        if valid_prestart and all(
            x["full_field_same_timestamp"].upper() == "YES" for x in group
        ):
            declared_complete += 1
    return {
        "market_snapshot_groups": len(grouped),
        "WIN_snapshot_groups": win_groups,
        "prestart_full_field_WIN_self_declared_groups": declared_complete,
        "WIN_snapshot_groups_stale_or_poststart": stale_or_poststart,
        "WIN_snapshot_independently_validated_for_BET": False,
    }


def audit_october(
    tabs: dict[str, list[dict[str, str]]],
    *, start: date = date(2026, 10, 12),
    end: date = date(2026, 10, 27),
    file_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Exactly one status per canonical funnel race, with diagnostic source joins."""
    if start > end:
        raise ValueError("Start date after end date")
    for name in REQUIRED_COLUMNS:
        if name not in tabs:
            raise ValueError(f"Missing mandatory source tab {name}")
    candidates: dict[str, dict[str, str]] = {}
    invalid_id = []
    for row in tabs["PreWatchFunnel"]:
        race_id = row.get("race_id", "")
        when = _race_date(race_id)
        if when is None:
            invalid_id.append(race_id)
            continue
        if when < start or when > end:
            continue
        if race_id in candidates:
            raise ValueError(f"Repeated primary frozen race key: {race_id}")
        candidates[race_id] = row
    if invalid_id:
        raise ValueError(f"Invalid primary race identities: {invalid_id[:5]}")

    by_tab: dict[str, dict[str, list[dict[str, str]]]] = {}
    for name in (
        "PreWatchPreflight", "MarketSnapshots", "FrozenDecisions",
        "ProbabilitySnapshots", "RaceInventory", "PreWatchSelectionAudit",
    ):
        mapping: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in tabs.get(name, []):
            if row.get("race_id"):
                mapping[row["race_id"]].append(row)
        by_tab[name] = mapping

    all_rows = []
    near_rows = []
    totals = Counter()
    scores = Counter()
    quality_flags = Counter()
    candidate_dates = set()
    for race_id, frozen in sorted(candidates.items()):
        race_day = _race_date(race_id)
        assert race_day is not None
        candidate_dates.add(race_day.isoformat())
        status = _status(frozen)
        totals[status] += 1
        value = _decimal(frozen.get("total_formula", ""))
        scored = status == "SCREENED_BELOW_THRESHOLD" and value is not None
        if scored:
            scores["scored_below_threshold"] += 1
            if value >= FROZEN_A_WATCH_MIN:
                quality_flags["CONTRADICTORY_BELOW_THRESHOLD_TOTAL"] += 1
        if status == "FORMULA_ERROR":
            quality_flags["FORMULA_ERROR_EXCLUDED_FROM_SCORED"] += 1
        if status == "SCREENED_BELOW_THRESHOLD" and value is None:
            quality_flags["SCORED_STATUS_WITHOUT_NUMERIC_SCORE"] += 1
        if status == "PARTIAL" and value is not None:
            quality_flags["PARTIAL_WITH_NUMERIC_SCORE_NOT_REINTERPRETED"] += 1

        mispricing = _decimal(frozen.get("mispricing_30", ""))
        liquidity = _decimal(frozen.get("liquidity_15", ""))
        if scored and mispricing is not None and mispricing < FROZEN_MISPRICING_MIN:
            scores["mispricing_component_below_18"] += 1
        if scored and liquidity is not None and liquidity < FROZEN_LIQUIDITY_MIN:
            scores["liquidity_component_below_8"] += 1

        preflight, blockers = _preflight_evidence(
            race_id, by_tab["PreWatchPreflight"].get(race_id, [])
        )
        market = _market_evidence(by_tab["MarketSnapshots"].get(race_id, []))
        probabilities = by_tab["ProbabilitySnapshots"].get(race_id, [])
        decisions = by_tab["FrozenDecisions"].get(race_id, [])
        selection = by_tab["PreWatchSelectionAudit"].get(race_id, [])
        inventory = by_tab["RaceInventory"].get(race_id, [])

        if not probabilities:
            blockers.append("NO_FROZEN_PROBABILITY_SNAPSHOT_IN_EXPORTED_LEDGER")
        if not market["prestart_full_field_WIN_self_declared_groups"]:
            blockers.append("NO_SAME_TIME_PRESTART_FULL_FIELD_WIN_SNAPSHOT_IN_EXPORT")
        if not decisions:
            blockers.append("NO_FROZEN_DECISION_IN_EXPORTED_LEDGER")
        elif not any(d["status"] in {"BET", "WATCH", "PASS"} for d in decisions):
            blockers.append("FROZEN_DECISION_NOT_EVALUABLE")
        if any(d["status"] == "BET" for d in decisions):
            quality_flags["RECORDED_BET_REQUIRES_INDEPENDENT_HARDGATE_AUDIT"] += 1

        if status == "SCREENED_BELOW_THRESHOLD" and value is not None:
            if FROZEN_A_WATCH_MIN > value:
                scores["scored_total_below_70"] += 1
            if Decimal(65) <= value <= Decimal(69):
                scores["near_65_to_69"] += 1

        record = {
            "race_id": race_id,
            "race_date": race_day.isoformat(),
            "prewatch_recorded_status": status,
            "frozen_total_score_display": str(value) if value is not None else None,
            "mispricing_30_display": str(mispricing) if mispricing is not None else None,
            "liquidity_15_display": str(liquidity) if liquidity is not None else None,
            "below_mispricing_component_gate": (
                mispricing < FROZEN_MISPRICING_MIN if scored and mispricing is not None
                else None
            ),
            "below_liquidity_component_gate": (
                liquidity < FROZEN_LIQUIDITY_MIN if scored and liquidity is not None
                else None
            ),
            "provisional_candidate": frozen.get("candidate_horse_no_name", ""),
            "candidate_hypothesis_present_not_edge_proof": bool(
                frozen.get("source_backed_hypothesis", "")
            ),
            "liquidity_source_note": frozen.get("liquidity_source_and_proxy", ""),
            "unresolved_evidence_note": frozen.get("uncertainty_and_missing", ""),
            **preflight,
            **market,
            "probability_rows_exact_join": len(probabilities),
            "frozen_decision_rows_exact_join": len(decisions),
            "manual_selection_audit_rows_exact_join": len(selection),
            "race_inventory_rows_exact_join": len(inventory),
            "diagnostic_blockers": sorted(set(blockers)),
            "independent_probability_approved_by_this_audit": False,
            "live_BET_eligible_by_this_audit": False,
        }
        all_rows.append(record)
        if scored and Decimal(65) <= value <= Decimal(69):
            near_rows.append(record)

    # A run log describes *attempts*, not one-to-one race identities.
    # Never sum the run's "identified_races" as unique actual races.
    raw_runs = tabs["RunLog"]
    run_ids = [r.get("run_id", "") for r in raw_runs]
    coverage = [
        d.isoformat() for n in range((end - start).days + 1)
        if (d := start + timedelta(days=n)).isoformat() not in candidate_dates
    ]
    return {
        "schema_version": "PREWATCH_OCTOBER_FUNNEL_READONLY_V1",
        "status": "DIAGNOSTIC_ONLY_NO_SCORE_MUTATION",
        "date_window_inclusive": [start.isoformat(), end.isoformat()],
        "file_sha256_by_sheet": file_hashes or {},
        "unique_frozen_funnel_races": len(candidates),
        "source_rows_by_tab": {
            name: len(rows) for name, rows in sorted(tabs.items())
        },
        "funnel_terminal_status_counts": dict(sorted(totals.items())),
        "scored_component_counts": dict(sorted(scores.items())),
        "quality_anomalies": dict(sorted(quality_flags.items())),
        "days_without_funnel_rows_not_proven_no_races": coverage,
        "runlog_rows_not_unique_race_count": len(raw_runs),
        "runlog_distinct_ids": len(set(run_ids)),
        "near_threshold_65_69": sorted(
            near_rows, key=lambda row: (-Decimal(row["frozen_total_score_display"]), row["race_id"])
        ),
        "per_race_reconciliation": all_rows,
        "frozen_thresholds_unchanged": {
            "A_WATCH": 70, "mispricing": 18, "liquidity": 8
        },
        "actual_WATCH_BET_not_authorized_by_report": True,
        "canonical_snapshots_mutated": False,
        "BET_BLOCKED": True,
        "interpretation_limits": [
            "Source spreadsheet is a dashboard, not the canonical database.",
            "Missing same-day WIN pool evidence does not mean measured low liquidity.",
            "Missing independent price evidence does not prove no real mispricing.",
            "A frozen score is neither p(win) nor estimated expected value.",
            "A-WATCH score alone never authorizes Phase B, BET or a wager.",
            "Repeated RunLog, preflight or market rows are not distinct race decisions.",
            "Missing funnel rows for a date do not establish no races occurred.",
            "Manual chat candidates are not retroactively frozen model decisions.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--from-date", type=date.fromisoformat, default=date(2026, 10, 12))
    parser.add_argument("--through-date", type=date.fromisoformat, default=date(2026, 10, 27))
    args = parser.parse_args()
    if args.output.resolve() == args.export_dir.resolve():
        raise ValueError("Output must not overwrite source export directory")
    tabs, hashes = read_exported_tabs(args.export_dir)
    report = audit_october(
        tabs, start=args.from_date, end=args.through_date, file_hashes=hashes
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    summary = {key: value for key, value in report.items()
               if key not in ("per_race_reconciliation", "near_threshold_65_69")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
