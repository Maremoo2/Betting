from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean, median
from zoneinfo import ZoneInfo

from .evaluation import calibration_bins, log_loss, multiclass_brier
from .providers.rikstoto import RikstotoClient
from .storage import SQLiteStore

OSLO = ZoneInfo("Europe/Oslo")
SCHEMA_VERSION = "RESEARCH_OBSERVATORY_V1"


@dataclass(frozen=True)
class OutcomeCollection:
    attempted: int
    persisted: int
    already_present: int
    pending: int
    failed_fetches: int


def _day_bounds(report_date: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(report_date, time.min, tzinfo=OSLO)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def _in_window(value: object, start: datetime, end: datetime) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return False
    return start <= parsed < end


def _mean(values: list[float]) -> float | None:
    return None if not values else mean(values)


def _median(values: list[float]) -> float | None:
    return None if not values else median(values)


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _loads_distribution(raw: object) -> dict[str, float] | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    output: dict[str, float] = {}
    for key, value in payload.items():
        try:
            output[str(key)] = float(value)
        except (TypeError, ValueError):
            return None
    if not output:
        return None
    return output


def _winner_from_complete(result: dict[str, object]) -> str | None:
    rows = result.get("results")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            place = int(row.get("place"))
        except (TypeError, ValueError):
            continue
        if place == 1 and row.get("startNumber") is not None:
            return str(row["startNumber"])
    return None


def collect_decision_outcomes(
    store: SQLiteStore,
    report_date: date,
    *,
    client: RikstotoClient | None = None,
    settled_at: datetime | None = None,
) -> OutcomeCollection:
    """Persist official winners for all frozen decision runs on one Oslo racing day."""
    api = client or RikstotoClient()
    now = settled_at or datetime.now(UTC)
    start, end = _day_bounds(report_date)
    decision_runs = [
        row
        for row in store.fetch_table("shadow_decision_runs")
        if _in_window(row.get("race_start_time_utc"), start, end)
    ]
    outcomes = {
        str(row["race_id"]): row
        for row in store.fetch_table("outcomes")
    }

    unique: dict[str, dict[str, object]] = {}
    for row in decision_runs:
        unique.setdefault(str(row["race_id"]), row)

    attempted = persisted = already = pending = failed = 0
    for race_id, decision in unique.items():
        attempted += 1
        if race_id in outcomes:
            already += 1
            continue
        raceday = decision.get("provider_raceday_key")
        race = store.get_race(race_id)
        if not raceday or race is None:
            pending += 1
            continue
        fetch = api.complete_results(str(raceday), int(race["race_no"]))
        if not fetch.success:
            failed += 1
            pending += 1
            continue
        winner = _winner_from_complete(api.result_object(fetch))
        if winner is None:
            pending += 1
            continue
        store.settle_outcome(
            race_id=race_id,
            winner_selection_id=winner,
            settled_at=now,
        )
        persisted += 1

    return OutcomeCollection(
        attempted=attempted,
        persisted=persisted,
        already_present=already,
        pending=pending,
        failed_fetches=failed,
    )


def materialize_race_evaluations(
    store: SQLiteStore,
    report_date: date,
    *,
    created_at: datetime | None = None,
) -> int:
    """Score frozen decision-time distributions only after an official outcome exists."""
    now = created_at or datetime.now(UTC)
    start, end = _day_bounds(report_date)
    outcomes = {
        str(row["race_id"]): row
        for row in store.fetch_table("outcomes")
    }
    decision_runs = [
        row
        for row in store.fetch_table("shadow_decision_runs")
        if _in_window(row.get("race_start_time_utc"), start, end)
    ]

    written = 0
    for run in decision_runs:
        race_id = str(run["race_id"])
        outcome = outcomes.get(race_id)
        if outcome is None:
            continue
        winner = str(outcome["winner_selection_id"])
        fundamental = _loads_distribution(run.get("fundamental_probabilities_json"))
        market = _loads_distribution(run.get("market_probabilities_json"))
        combined = _loads_distribution(run.get("combined_probabilities_json"))

        def score(
            distribution: dict[str, float] | None,
        ) -> tuple[float | None, float | None]:
            if distribution is None or winner not in distribution:
                return None, None
            return (
                log_loss(distribution, winner),
                multiclass_brier(distribution, winner),
            )

        fundamental_log, fundamental_brier = score(fundamental)
        market_log, market_brier = score(market)
        combined_log, combined_brier = score(combined)
        field = fundamental or market or combined or {}

        store.upsert_race_research_evaluation(
            {
                "race_id": race_id,
                "shadow_model_version": run["shadow_model_version"],
                "fundamental_model_version": run.get("fundamental_model_version"),
                "decision_time_utc": run["created_at_utc"],
                "outcome_settled_at_utc": outcome["settled_at_utc"],
                "winner_selection_id": winner,
                "field_size": len(field),
                "fundamental_log_loss": fundamental_log,
                "market_log_loss": market_log,
                "combined_log_loss": combined_log,
                "fundamental_brier": fundamental_brier,
                "market_brier": market_brier,
                "combined_brier": combined_brier,
                "model_market_conflict_score": run.get(
                    "model_market_conflict_score"
                ),
                "source_market_observed_at_utc": run.get(
                    "source_market_observed_at_utc"
                ),
                "created_at_utc": now.isoformat(),
            }
        )
        written += 1
    return written


def _latest_fundamental_rows(
    rows: list[dict[str, object]],
    race_ids: set[str],
) -> dict[tuple[str, str], dict[str, object]]:
    selected = [
        row for row in rows if str(row.get("race_id")) in race_ids
    ]
    selected.sort(
        key=lambda row: str(row.get("feature_as_of_utc") or ""),
        reverse=True,
    )
    latest: dict[tuple[str, str], dict[str, object]] = {}
    for row in selected:
        key = (str(row["race_id"]), str(row["selection_id"]))
        latest.setdefault(key, row)
    return latest


def build_data_health(store: SQLiteStore, report_date: date) -> dict[str, object]:
    start, end = _day_bounds(report_date)
    races = [
        row
        for row in store.fetch_table("races")
        if _in_window(row.get("start_time_utc"), start, end)
    ]
    race_ids = {str(row["race_id"]) for row in races}
    countries: dict[str, int] = {}
    for race in races:
        country = str(race.get("country") or "UNKNOWN")
        countries[country] = countries.get(country, 0) + 1

    fundamentals = _latest_fundamental_rows(
        store.fetch_table("runner_fundamental_snapshots"),
        race_ids,
    )
    fundamental_races = {race_id for race_id, _ in fundamentals}
    active_rows = [
        row for row in fundamentals.values() if not bool(row.get("scratched"))
    ]
    known_history = [
        row
        for row in active_rows
        if row.get("history_total_starts") is not None
        and row.get("history_total_wins") is not None
    ]
    atg_history = [
        row
        for row in active_rows
        if str(row.get("data_quality") or "") == "KNOWN_HISTORY_ATG"
    ]

    market_rows = [
        row
        for row in store.fetch_table("provider_market_snapshots")
        if str(row.get("race_id")) in race_ids and row.get("product") == "V"
    ]
    market_races = {str(row["race_id"]) for row in market_rows}

    model_runs = [
        row
        for row in store.fetch_table("fundamental_model_runs")
        if str(row.get("race_id")) in race_ids
    ]
    latest_model_runs: dict[str, dict[str, object]] = {}
    for row in sorted(
        model_runs,
        key=lambda item: str(item.get("created_at_utc") or ""),
        reverse=True,
    ):
        latest_model_runs.setdefault(str(row["race_id"]), row)
    history_coverages = [
        float(row["history_coverage"])
        for row in latest_model_runs.values()
        if row.get("history_coverage") is not None
    ]

    fetches = [
        row
        for row in store.fetch_table("provider_fetch_audit")
        if _in_window(row.get("fetched_at_utc"), start, end)
    ]
    fetch_failures = [row for row in fetches if not bool(row.get("success"))]
    failures_by_provider: dict[str, int] = {}
    for row in fetch_failures:
        provider = str(row.get("provider") or "UNKNOWN")
        failures_by_provider[provider] = failures_by_provider.get(provider, 0) + 1

    decision_runs = [
        row
        for row in store.fetch_table("shadow_decision_runs")
        if _in_window(row.get("race_start_time_utc"), start, end)
    ]
    status_counts: dict[str, int] = {}
    latencies: list[float] = []
    actual_minutes: list[float] = []
    for row in decision_runs:
        status = str(row.get("decision_status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        if row.get("execution_latency_seconds") is not None:
            latencies.append(float(row["execution_latency_seconds"]))
        if row.get("actual_minutes_to_start") is not None:
            actual_minutes.append(float(row["actual_minutes_to_start"]))

    tickets = [
        row
        for row in store.fetch_table("shadow_tickets")
        if _in_window(row.get("decision_time_utc"), start, end)
    ]
    executable_tickets = [
        row for row in tickets if row.get("status") != "NOT_EXECUTABLE"
    ]
    settled_tickets = [
        row for row in executable_tickets if row.get("status") == "SETTLED"
    ]

    return {
        "report_date": report_date.isoformat(),
        "races": len(races),
        "races_by_country": countries,
        "races_with_starts": len(fundamental_races),
        "starts_race_coverage": (
            None if not races else len(fundamental_races) / len(races)
        ),
        "races_with_v_odds": len(market_races),
        "v_odds_race_coverage": (
            None if not races else len(market_races) / len(races)
        ),
        "fundamental_model_runs": len(latest_model_runs),
        "shadow_eligible_fundamental_runs": sum(
            bool(row.get("shadow_eligible"))
            for row in latest_model_runs.values()
        ),
        "mean_history_coverage": _mean(history_coverages),
        "active_runner_rows": len(active_rows),
        "known_history_runner_rows": len(known_history),
        "known_history_runner_coverage": (
            None if not active_rows else len(known_history) / len(active_rows)
        ),
        "atg_history_runner_rows": len(atg_history),
        "atg_runner_coverage": (
            None if not active_rows else len(atg_history) / len(active_rows)
        ),
        "provider_fetches": len(fetches),
        "provider_fetch_failures": len(fetch_failures),
        "provider_fetch_failure_rate": (
            None if not fetches else len(fetch_failures) / len(fetches)
        ),
        "provider_fetch_failures_by_provider": failures_by_provider,
        "decision_runs": len(decision_runs),
        "decision_status_counts": status_counts,
        "t4_latency_seconds_mean": _mean(latencies),
        "t4_latency_seconds_median": _median(latencies),
        "t4_latency_seconds_p95": _p95(latencies),
        "actual_minutes_to_start_mean": _mean(actual_minutes),
        "shadow_tickets": len(executable_tickets),
        "settled_shadow_tickets": len(settled_tickets),
        "settlement_rate": (
            None
            if not executable_tickets
            else len(settled_tickets) / len(executable_tickets)
        ),
        "not_executable_ticket_rows": sum(
            row.get("status") == "NOT_EXECUTABLE" for row in tickets
        ),
    }


def _aggregate_metric(
    rows: list[dict[str, object]],
    key: str,
) -> float | None:
    values = [
        float(row[key]) for row in rows if row.get(key) is not None
    ]
    return _mean(values)


def build_evaluation_summary(
    store: SQLiteStore,
    report_date: date,
) -> dict[str, object]:
    start, end = _day_bounds(report_date)
    races = {
        str(row["race_id"]): row
        for row in store.fetch_table("races")
        if _in_window(row.get("start_time_utc"), start, end)
    }
    race_ids = set(races)
    evaluations = [
        row
        for row in store.fetch_table("race_research_evaluations")
        if str(row.get("race_id")) in race_ids
    ]
    decision_runs = [
        row
        for row in store.fetch_table("shadow_decision_runs")
        if str(row.get("race_id")) in race_ids
    ]
    outcomes = {
        str(row["race_id"]): str(row["winner_selection_id"])
        for row in store.fetch_table("outcomes")
        if str(row.get("race_id")) in race_ids
    }

    calibration: dict[str, list[dict[str, float | int]]] = {}
    for layer, column in (
        ("fundamental", "fundamental_probabilities_json"),
        ("market", "market_probabilities_json"),
        ("combined", "combined_probabilities_json"),
    ):
        observations: list[tuple[float, bool]] = []
        for run in decision_runs:
            winner = outcomes.get(str(run["race_id"]))
            distribution = _loads_distribution(run.get(column))
            if winner is None or distribution is None or winner not in distribution:
                continue
            observations.extend(
                (probability, selection == winner)
                for selection, probability in distribution.items()
            )
        calibration[layer] = (
            calibration_bins(observations, width=0.10)
            if observations
            else []
        )

    tickets = [
        row
        for row in store.fetch_table("shadow_tickets")
        if _in_window(row.get("decision_time_utc"), start, end)
        and row.get("status") != "NOT_EXECUTABLE"
    ]
    settled = [row for row in tickets if row.get("status") == "SETTLED"]
    settled_stake = sum(float(row.get("stake_nok") or 0) for row in settled)
    net_pnl = sum(float(row.get("net_pnl_nok") or 0) for row in settled)
    clvs = [
        float(row["clv"]) for row in settled if row.get("clv") is not None
    ]

    fundamental_log = _aggregate_metric(evaluations, "fundamental_log_loss")
    market_log = _aggregate_metric(evaluations, "market_log_loss")
    combined_log = _aggregate_metric(evaluations, "combined_log_loss")
    fundamental_brier = _aggregate_metric(evaluations, "fundamental_brier")
    market_brier = _aggregate_metric(evaluations, "market_brier")
    combined_brier = _aggregate_metric(evaluations, "combined_brier")

    return {
        "report_date": report_date.isoformat(),
        "race_evaluations_n": len(evaluations),
        "outcomes_n": len(outcomes),
        "fundamental_log_loss": fundamental_log,
        "market_log_loss": market_log,
        "combined_log_loss": combined_log,
        "combined_minus_market_log_loss": (
            None
            if combined_log is None or market_log is None
            else combined_log - market_log
        ),
        "fundamental_brier": fundamental_brier,
        "market_brier": market_brier,
        "combined_brier": combined_brier,
        "combined_minus_market_brier": (
            None
            if combined_brier is None or market_brier is None
            else combined_brier - market_brier
        ),
        "mean_model_market_conflict": _aggregate_metric(
            evaluations,
            "model_market_conflict_score",
        ),
        "calibration": calibration,
        "settled_shadow_bets_n": len(settled),
        "settled_stake_nok": settled_stake,
        "net_pnl_nok": net_pnl,
        "roi": None if settled_stake <= 0 else net_pnl / settled_stake,
        "mean_clv": _mean(clvs),
        "positive_clv_rate": (
            None
            if not clvs
            else sum(value > 0 for value in clvs) / len(clvs)
        ),
    }


def build_trend_summary(store: SQLiteStore) -> dict[str, object]:
    evaluations = store.fetch_table("race_research_evaluations")
    by_model: dict[str, list[dict[str, object]]] = {}
    for row in evaluations:
        model = str(row.get("fundamental_model_version") or "UNKNOWN")
        by_model.setdefault(model, []).append(row)

    model_summary: dict[str, dict[str, object]] = {}
    for model, rows in sorted(by_model.items()):
        model_summary[model] = {
            "n": len(rows),
            "fundamental_log_loss": _aggregate_metric(rows, "fundamental_log_loss"),
            "market_log_loss": _aggregate_metric(rows, "market_log_loss"),
            "combined_log_loss": _aggregate_metric(rows, "combined_log_loss"),
            "fundamental_brier": _aggregate_metric(rows, "fundamental_brier"),
            "market_brier": _aggregate_metric(rows, "market_brier"),
            "combined_brier": _aggregate_metric(rows, "combined_brier"),
            "mean_conflict": _aggregate_metric(
                rows,
                "model_market_conflict_score",
            ),
        }

    daily_reports = sorted(
        store.fetch_table("research_daily_reports"),
        key=lambda row: str(row.get("report_date") or ""),
    )[-14:]
    recent: list[dict[str, object]] = []
    for row in daily_reports:
        try:
            health = json.loads(str(row["data_health_json"]))
            evaluation = json.loads(str(row["evaluation_json"]))
        except (json.JSONDecodeError, KeyError):
            continue
        recent.append(
            {
                "report_date": row["report_date"],
                "races": health.get("races"),
                "decision_runs": health.get("decision_runs"),
                "shadow_eligible_runs": health.get(
                    "shadow_eligible_fundamental_runs"
                ),
                "evaluations_n": evaluation.get("race_evaluations_n"),
                "combined_log_loss": evaluation.get("combined_log_loss"),
                "market_log_loss": evaluation.get("market_log_loss"),
                "roi": evaluation.get("roi"),
                "mean_clv": evaluation.get("mean_clv"),
            }
        )

    return {
        "all_evaluations_n": len(evaluations),
        "by_fundamental_model_version": model_summary,
        "recent_14_reports": recent,
    }


def _fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(
    report_date: date,
    health: dict[str, object],
    evaluation: dict[str, object],
    trend: dict[str, object],
    outcome_collection: OutcomeCollection,
) -> str:
    lines = [
        f"# HBI Research Observatory — {report_date.isoformat()}",
        "",
        "## Data health",
        "",
        f"- Races discovered: {health['races']}",
        f"- Races with starts: {health['races_with_starts']} "
        f"({_fmt(health['starts_race_coverage'])})",
        f"- Races with Vinner odds: {health['races_with_v_odds']} "
        f"({_fmt(health['v_odds_race_coverage'])})",
        f"- Mean history coverage: {_fmt(health['mean_history_coverage'])}",
        f"- ATG runner coverage: {_fmt(health['atg_runner_coverage'])}",
        f"- Provider fetch failures: {health['provider_fetch_failures']} / "
        f"{health['provider_fetches']}",
        f"- Frozen T-4 decision runs: {health['decision_runs']} "
        f"{health['decision_status_counts']}",
        f"- T-4 latency median / p95: "
        f"{_fmt(health['t4_latency_seconds_median'], 1)}s / "
        f"{_fmt(health['t4_latency_seconds_p95'], 1)}s",
        f"- Shadow settlement rate: {_fmt(health['settlement_rate'])}",
        "",
        "## Predictive evaluation",
        "",
        f"- Official outcomes available: {evaluation['outcomes_n']}",
        f"- Frozen race evaluations: {evaluation['race_evaluations_n']}",
        f"- Log loss — fundamental / market / combined: "
        f"{_fmt(evaluation['fundamental_log_loss'])} / "
        f"{_fmt(evaluation['market_log_loss'])} / "
        f"{_fmt(evaluation['combined_log_loss'])}",
        f"- Brier — fundamental / market / combined: "
        f"{_fmt(evaluation['fundamental_brier'])} / "
        f"{_fmt(evaluation['market_brier'])} / "
        f"{_fmt(evaluation['combined_brier'])}",
        f"- Combined minus market log loss: "
        f"{_fmt(evaluation['combined_minus_market_log_loss'])}",
        f"- Mean model-market conflict: "
        f"{_fmt(evaluation['mean_model_market_conflict'])}",
        "",
        "## Shadow economics",
        "",
        f"- Settled shadow bets: {evaluation['settled_shadow_bets_n']}",
        f"- Settled stake: {_fmt(evaluation['settled_stake_nok'], 2)} NOK",
        f"- Net P/L: {_fmt(evaluation['net_pnl_nok'], 2)} NOK",
        f"- ROI: {_fmt(evaluation['roi'])}",
        f"- Mean CLV: {_fmt(evaluation['mean_clv'])}",
        f"- Positive CLV rate: {_fmt(evaluation['positive_clv_rate'])}",
        "",
        "## Outcome collection",
        "",
        f"- Attempted / persisted / already present / pending / failed fetches: "
        f"{outcome_collection.attempted} / {outcome_collection.persisted} / "
        f"{outcome_collection.already_present} / {outcome_collection.pending} / "
        f"{outcome_collection.failed_fetches}",
        "",
        "## Research guardrail",
        "",
        "These metrics describe the frozen prospective shadow system. Small-N results "
        "are not evidence of a durable betting edge and do not change the frozen "
        "Shadow Champion automatically.",
        "",
        f"Cumulative evaluated races: {trend['all_evaluations_n']}",
    ]
    return "\n".join(lines) + "\n"


def build_research_observatory(
    store: SQLiteStore,
    report_date: date,
    *,
    client: RikstotoClient | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    now = generated_at or datetime.now(UTC)
    outcome_collection = collect_decision_outcomes(
        store,
        report_date,
        client=client,
        settled_at=now,
    )
    materialized = materialize_race_evaluations(
        store,
        report_date,
        created_at=now,
    )
    health = build_data_health(store, report_date)
    evaluation = build_evaluation_summary(store, report_date)
    trend = build_trend_summary(store)
    markdown = render_markdown(
        report_date,
        health,
        evaluation,
        trend,
        outcome_collection,
    )

    report = {
        "report_date": report_date.isoformat(),
        "generated_at_utc": now.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "outcome_collection": asdict(outcome_collection),
        "race_evaluations_materialized": materialized,
        "data_health": health,
        "evaluation": evaluation,
        "trend": trend,
        "markdown": markdown,
    }
    store.upsert_research_daily_report(
        {
            "report_date": report_date.isoformat(),
            "generated_at_utc": now.isoformat(),
            "schema_version": SCHEMA_VERSION,
            "data_health_json": json.dumps(health, sort_keys=True),
            "evaluation_json": json.dumps(evaluation, sort_keys=True),
            "trend_json": json.dumps(trend, sort_keys=True),
            "markdown_report": markdown,
        }
    )
    return report
