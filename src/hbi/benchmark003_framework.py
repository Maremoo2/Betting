"""BENCHMARK-003 paired research evaluator. No pricing, fitting or BET.

Reuses the existing hbi.evaluation scoring/calibration functions. PIT labels
are treated as input assertions, never independently issued certificates.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from math import isfinite
import random
from typing import Any

from hbi.evaluation import calibration_bins, log_loss, multiclass_brier

SCOPES = {
    "TERMINAL_RETROSPECTIVE", "DECISION_TIME_OBSERVED",
    "PIT_CERTIFIED", "PROSPECTIVE_FROZEN",
}


def instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_MISSING")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("TIMESTAMP_NAIVE")
    return d


def validate(row: dict[str, Any]) -> dict[str, Any]:
    scope = row.get("scope")
    if scope not in SCOPES:
        raise ValueError("INVALID_EVIDENCE_SCOPE")
    ids = row.get("active_field")
    if not isinstance(ids, list) or len(ids) < 2 or len(set(ids)) != len(ids):
        raise ValueError("INVALID_ACTIVE_FIELD")
    probs = row.get("probabilities", {})
    if not isinstance(probs, dict) or not probs:
        raise ValueError("MISSING_PROBABILITIES")
    for name, p in probs.items():
        if (
            not isinstance(p, dict) or set(p) != set(ids)
            or any(
                type(v) not in (int, float) or not isfinite(v) or not 0 < v < 1
                for v in p.values()
            )
            or abs(sum(p.values()) - 1) > 1e-9
        ):
            raise ValueError("INVALID_MODEL_FIELD_" + str(name))
    if row.get("winner_selection_id") not in ids:
        raise ValueError("WINNER_NOT_IN_ACTIVE_FIELD")
    start = instant(row["race_start_at"])
    cutoff = instant(row["decision_cutoff"])
    if cutoff >= start:
        raise ValueError("CUTOFF_NOT_PRESTART")
    if scope in {"PIT_CERTIFIED", "PROSPECTIVE_FROZEN"}:
        if row.get("pit_evidence_status") != "PIT_CERTIFIED":
            raise ValueError("PIT_CLAIM_WITHOUT_CERTIFICATE")
        if any(not row.get(k) for k in ("source_hash", "snapshot_id", "model_version")):
            raise ValueError("SOURCE_PROVENANCE_INCOMPLETE")
        if (
            instant(row["market_observed_at"]) > cutoff
            or instant(row["model_frozen_at"]) > cutoff
        ):
            raise ValueError("DECISION_TIME_LOOKAHEAD")
    elif scope == "DECISION_TIME_OBSERVED":
        if instant(row["market_observed_at"]) > cutoff:
            raise ValueError("MARKET_AFTER_CUTOFF")
    return row


def score(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    if not rows:
        return {"status": "NOT_READY_FOR_PIT_RESULT", "races": 0}
    seen = set()
    scope = None
    samples = []
    points = defaultdict(list)
    favorite_points = defaultdict(list)
    for row in rows:
        validate(row)
        if scope is not None and row["scope"] != scope:
            raise ValueError("MIXED_SCOPE_NOT_ALLOWED")
        scope = row["scope"]
        key = row["race_id"]
        if key in seen:
            raise ValueError("DUPLICATE_RACE")
        seen.add(key)
        if left not in row["probabilities"] or right not in row["probabilities"]:
            raise ValueError("BASELINE_MISSING")
        p = row["probabilities"]
        w = row["winner_selection_id"]
        day = date.fromisoformat(row["race_date"])
        a = log_loss(p[left], w)
        b = log_loss(p[right], w)
        brier_a = multiclass_brier(p[left], w)
        brier_b = multiclass_brier(p[right], w)
        week = day.isocalendar()
        samples.append(((week.year, week.week), a - b, brier_a - brier_b))
        for name in (left, right):
            points[name].extend((v, k == w) for k, v in p[name].items())
            fav = max(row["active_field"], key=lambda k: (p[name][k], k))
            favorite_points[name].append((p[name][fav], fav == w))
    groups = defaultdict(lambda: [0., 0., 0])
    for key, ll, brier in samples:
        groups[key][0] += ll
        groups[key][1] += brier
        groups[key][2] += 1
    observed = sum(x for _, x, _ in samples) / len(samples)
    observed_brier = sum(x for _, _, x in samples) / len(samples)
    ci = None
    if len(groups) >= 2:
        rng = random.Random(20261109)
        keys = sorted(groups)
        draws = []
        for _ in range(2000):
            blocks = [groups[keys[rng.randrange(len(keys))]] for _ in keys]
            draws.append(sum(x[0] for x in blocks) / sum(x[2] for x in blocks))
        draws.sort()
        ci = [draws[49], draws[1949]]
    return {
        "status": (
            "UPSTREAM_PIT_CLAIM_NOT_INDEPENDENTLY_VERIFIED"
            if scope in {"PIT_CERTIFIED", "PROSPECTIVE_FROZEN"}
            else "PAIRED_RESEARCH_DIAGNOSTIC"
        ),
        "scope": scope, "races": len(rows), "independent_weeks": len(groups),
        "delta_log_loss": observed, "delta_multiclass_brier": observed_brier,
        "block_week_ci_95": ci,
        "calibration": {
            k: calibration_bins(v, width=.1) for k, v in points.items()
        },
        "favorite_calibration": {
            k: calibration_bins(v, width=.1) for k, v in favorite_points.items()
        },
        "economic_edge_claimed": False, "bet_authority": False,
    }
