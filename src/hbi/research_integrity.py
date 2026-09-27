from __future__ import annotations

from datetime import datetime

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
