"""Read-only production coverage report. Missing evidence is never a pass."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

COUNTRIES = ("SE", "DK", "NO", "FR")
OSLO = ZoneInfo("Europe/Oslo")


def _time(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value))
        return result if result.utcoffset() is not None else None
    except ValueError:
        return None


def build_operations_report(db_path, start: date, end: date, *, now=None):
    now = now or datetime.now(UTC)
    if now.utcoffset() is None or end < start:
        raise ValueError("aware current time and ordered dates required")
    # mode=ro prevents an absent download from becoming an empty 'healthy' database.
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        races = [dict(r) for r in connection.execute("SELECT * FROM races")]
        decisions = defaultdict(list)
        for row in connection.execute("SELECT * FROM shadow_decision_runs"):
            if (t := _time(row["created_at_utc"])) and t <= now:
                decisions[row["race_id"]].append(dict(row))
        evidence = defaultdict(list)
        for row in connection.execute(
            "SELECT rowid AS evidence_order, * FROM provider_payloads "
            "WHERE category='FULL_FIELD_ONLY_V1'"
        ):
            if (t := _time(row["observed_at_utc"])) and t <= now:
                evidence[row["provider_raceday_key"]].append(
                    (t, row["evidence_order"], row["payload_json"]))
        tickets = [dict(r) for r in connection.execute("SELECT * FROM shadow_tickets")]
        outcomes = {r["race_id"]: dict(r) for r in connection.execute("SELECT * FROM outcomes")}
    finally:
        connection.close()
    rows = []
    for race in races:
        race_start = _time(race["start_time_utc"])
        if not race_start or race["country"] not in COUNTRIES:
            continue
        day = race_start.astimezone(OSLO).date()
        if not start <= day <= end:
            continue
        rid = race["race_id"]
        runs = sorted(decisions[rid], key=lambda d: _time(d["created_at_utc"]))
        # Latest pre-decision evidence, not enrichment obtained after a decision.
        cutoff = _time(runs[0]["created_at_utc"]) if runs else min(now, race_start)
        candidates = sorted((t, order, raw) for t, order, raw in evidence[rid] if t <= cutoff)
        field = None
        if candidates:
            try:
                field = json.loads(candidates[-1][2])
                if not isinstance(field, dict):
                    field = None
            except ValueError:
                pass
        coverage = "UNKNOWN"
        reasons = []
        identities = []
        if field:
            coverage = "REJECTED"
            reasons = field.get("reasons", [])
            identities = [{k: r.get(k) for k in (
                "selection_id", "match_method", "match_confidence", "schema_ok", "reason")}
                for r in field.get("runners", [])]
            if field.get("passed") is True and not field.get("probe_only"):
                coverage = "FULL_FIELD_EVIDENCE_PASS"
        timing = []
        for run in runs:
            actual = (_time(run["race_start_time_utc"]) - _time(run["created_at_utc"])
                      ).total_seconds() / 60
            timing.append({"decision_run_id": run["decision_run_id"],
                           "status": run["decision_status"], "reason": run["reason"],
                           "actual_minutes_to_start": actual,
                           "t4_error_seconds": (4 - actual) * 60,
                           "within_t4_plus_minus_60_seconds": abs(4 - actual) <= 1,
                           "pre_race": actual > 0})
        rows.append({"race_id": rid, "day": day.isoformat(), "country": race["country"],
                     "track": race["track"], "discipline": race["discipline"],
                     "start_time_utc": race_start.isoformat(), "started": race_start <= now,
                     "coverage": coverage, "coverage_reasons": reasons,
                     "active_runners": field.get("active_runners") if field else None,
                     "complete_runners": field.get("matched_complete_runners") if field else None,
                     "identities": identities, "decisions": timing,
                     "missing_decision_after_start": race_start <= now and not runs,
                     "outcome_present": rid in outcomes})
    race_lookup = {r["race_id"]: r for r in races}
    backlog = []
    for ticket in tickets:
        if ticket["status"] in {"SETTLED", "NOT_EXECUTABLE"}:
            continue
        race = race_lookup.get(ticket["race_id"], {})
        race_start = _time(race.get("start_time_utc"))
        backlog.append({"ticket_id": ticket["ticket_id"], "race_id": ticket["race_id"],
                        "country": race.get("country"), "product": ticket["product"],
                        "selections_json": ticket["selections_json"],
                        "provider_raceday_key": ticket["provider_raceday_key"],
                        "race_number": race.get("race_no"), "status": ticket["status"],
                        "age_hours": (now - race_start).total_seconds() / 3600
                        if race_start else None,
                        "overdue_24h": bool(race_start and now >= race_start + timedelta(hours=24)),
                        "outcome_present": ticket["race_id"] in outcomes,
                        "official_winner": outcomes.get(ticket["race_id"], {}).get(
                            "winner_selection_id")})
    daily = []
    day = start
    while day <= end:
        for country in COUNTRIES:
            subset = [r for r in rows if r["day"] == day.isoformat() and r["country"] == country]
            timings = [d for r in subset for d in r["decisions"]]
            errors = [d["t4_error_seconds"] for d in timings]
            ids = {r["race_id"] for r in subset}
            day_tickets = [t for t in tickets if t["race_id"] in ids
                           and t["status"] != "NOT_EXECUTABLE"]
            daily.append({"day": day.isoformat(), "country": country,
                          "observation_status": "FUTURE" if day > now.astimezone(OSLO).date()
                          else "PARTIAL_DAY" if day == now.astimezone(OSLO).date()
                          else "OBSERVED" if subset else "NO_EVIDENCE",
                          "discovered": len(subset),
                          "started": sum(r["started"] for r in subset),
                          "coverage": dict(Counter(r["coverage"] for r in subset)),
                          "rejections": dict(Counter(reason for r in subset
                                                     for reason in r["coverage_reasons"])),
                          "decisions": len(timings),
                          "statuses": dict(Counter(d["status"] for d in timings)),
                          "missing_decision_after_start": sum(
                              r["missing_decision_after_start"] for r in subset),
                          "t4_within_60_seconds": sum(
                              d["within_t4_plus_minus_60_seconds"] for d in timings),
                          "t4_error_seconds_median": median(errors) if errors else None,
                          "post_start_decisions": sum(not d["pre_race"] for d in timings)})
            daily[-1].update({
                "official_outcomes": sum(r["outcome_present"] for r in subset),
                "tickets": len(day_tickets),
                "settled_tickets": sum(t["status"] == "SETTLED" for t in day_tickets),
                "overdue_tickets": sum(t["overdue_24h"] for t in backlog if t["race_id"] in ids),
            })
        day += timedelta(days=1)
    return {"schema_version": "HBI_OPERATIONS_V1", "generated_at": now.isoformat(),
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "period_elapsed": now.astimezone(OSLO).date() > end,
            "daily": daily, "races": rows, "open_settlement_backlog_all_dates": backlog,
            "interpretation": "Read-only production snapshot. Coverage pass is provider evidence, "
            "not model eligibility or a betting edge. Missing decisions include races outside "
            "the supported universe; see each race. T-4 +/-60s is a reporting band only. "
            "Future days and absent evidence are never certified complete."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_operations_report(args.db, args.start, args.end)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "races"}, indent=2))


if __name__ == "__main__":
    main()
