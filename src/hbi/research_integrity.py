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
    return {"status": "PASS" if not problems else "FAIL", "checked_rows": checked, "problems": problems}
