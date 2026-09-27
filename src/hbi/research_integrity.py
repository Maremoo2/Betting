from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from .fundamental import MarketFreeFundamentalChampionV1
from .point_in_time import PointInTimeViolation
from .storage import SQLiteStore


def check_temporal_order(store: SQLiteStore) -> dict[str, object]:
    problems: list[dict[str, object]] = []
    checked = 0
    for row in store.fetch_table("predictions"):
        checked += 1
        created = datetime.fromisoformat(str(row["created_at_utc"]))
        feature = datetime.fromisoformat(str(row["feature_as_of_utc"]))
        if feature > created:
            problems.append({"id": row["prediction_id"], "reason": "feature_after_prediction"})
    for row in store.fetch_table("fundamental_model_runs"):
        checked += 1
        created = datetime.fromisoformat(str(row["created_at_utc"]))
        feature = datetime.fromisoformat(str(row["feature_as_of_utc"]))
        if feature > created:
            problems.append({"id": row["run_id"], "reason": "feature_after_model_run"})

    for row in store.fetch_table("shadow_decision_runs"):
        checked += 1
        source = row.get("source_market_observed_at_utc")
        if not source:
            continue
        decision = datetime.fromisoformat(str(row["created_at_utc"]))
        observed = datetime.fromisoformat(str(source))
        if observed > decision:
            problems.append(
                {"id": row["decision_run_id"], "reason": "market_after_decision"}
            )

    for row in store.fetch_table("runner_fundamental_snapshots"):
        checked += 1
        observed = datetime.fromisoformat(str(row["observed_at_utc"]))
        feature = datetime.fromisoformat(str(row["feature_as_of_utc"]))
        if feature > observed:
            problems.append(
                {"id": row["snapshot_id"], "reason": "feature_after_observation"}
            )

    return {
        "status": "PASS" if not problems else "FAIL",
        "checked_rows": checked,
        "problems": problems,
    }



def _synthetic_row(
    selection_id: str,
    feature_time: datetime,
    starts: int,
    wins: int,
) -> dict[str, object]:
    return {
        "selection_id": selection_id,
        "feature_as_of_utc": feature_time.isoformat(),
        "history_total_starts": starts,
        "history_total_wins": wins,
        "scratched": 0,
    }


def _select_latest_as_of(
    rows: list[dict[str, object]],
    cutoff: datetime,
) -> list[dict[str, object]]:
    eligible = [
        row
        for row in rows
        if datetime.fromisoformat(str(row["feature_as_of_utc"])) <= cutoff
    ]
    eligible.sort(
        key=lambda row: (
            str(row["selection_id"]),
            str(row["feature_as_of_utc"]),
        ),
        reverse=True,
    )
    selected: dict[str, dict[str, object]] = {}
    for row in eligible:
        selected.setdefault(str(row["selection_id"]), row)
    return list(selected.values())


def future_mutation_invariance() -> dict[str, object]:
    decision = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
    pre = decision - timedelta(minutes=1)
    future = decision + timedelta(minutes=10)
    baseline_rows = [
        _synthetic_row("1", pre, 20, 8),
        _synthetic_row("2", pre, 20, 3),
        _synthetic_row("3", pre, 20, 1),
    ]
    mutated = [
        *baseline_rows,
        _synthetic_row("1", future, 100, 0),
        _synthetic_row("2", future, 100, 100),
        _synthetic_row("3", future, 100, 0),
    ]
    model = MarketFreeFundamentalChampionV1()
    baseline = model.estimate(
        race_id="SYNTHETIC_TEMPORAL_CHECK",
        rows=_select_latest_as_of(baseline_rows, decision),
        created_at=decision,
    ).probabilities
    replay = model.estimate(
        race_id="SYNTHETIC_TEMPORAL_CHECK",
        rows=_select_latest_as_of(mutated, decision),
        created_at=decision,
    ).probabilities

    future_rejected = False
    try:
        model.estimate(
            race_id="SYNTHETIC_TEMPORAL_CHECK",
            rows=[_synthetic_row("1", future, 100, 100), *baseline_rows[1:]],
            created_at=decision,
        )
    except PointInTimeViolation:
        future_rejected = True

    passed = baseline == replay and future_rejected
    return {
        "status": "PASS" if passed else "FAIL",
        "baseline": baseline,
        "replay_after_future_mutation": replay,
        "future_row_rejected": future_rejected,
    }


def run_research_integrity_check(store: SQLiteStore) -> dict[str, object]:
    database = check_temporal_order(store)
    mutation = future_mutation_invariance()
    status = (
        "PASS"
        if database["status"] == "PASS" and mutation["status"] == "PASS"
        else "FAIL"
    )
    generated_at = datetime.now(UTC)
    report = {
        "schema_version": "HBI_TEMPORAL_INTEGRITY_V1",
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "database": database,
        "future_mutation_invariance": mutation,
    }
    audit_id = sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    store.insert_integrity_audit(
        {
            "audit_id": audit_id,
            "audit_type": "TEMPORAL_INTEGRITY",
            "generated_at_utc": generated_at.isoformat(),
            "status": status,
            "checked_rows": int(database["checked_rows"]),
            "failures": len(database["problems"]) + int(mutation["status"] != "PASS"),
            "warnings": 0,
            "report_json": json.dumps(report, sort_keys=True),
            "github_sha": os.getenv("GITHUB_SHA"),
        }
    )
    return report
