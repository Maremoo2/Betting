"""CLOUD-RUN-003 model admission over genuine archived Collector races.

The frozen market-free Champion is called ONLY when its existing full-field,
independent identity, historical cohort and pre-race requirements are met.
No guessed history, market shares, bet signals or retroactive PIT qualification.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime

from .fundamental import MarketFreeFundamentalChampionV1, run_and_persist_fundamental
from .probability import fair_odds
from .provider_capability import full_field_gate
from .storage import SQLiteStore


def assess_and_run(
    store: SQLiteStore,
    imported: list[dict[str, object]],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Run existing full-field model only for a fully admitted contemporaneous cohort."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    model = MarketFreeFundamentalChampionV1()
    records: list[dict[str, object]] = []
    reasons_all: Counter[str] = Counter()
    for source in imported:
        race_id = str(source["race_id"])
        race = store.get_race(race_id)
        if race is None:
            raise ValueError("CLOUD_MODEL_CANONICAL_RACE_MISSING")
        start = datetime.fromisoformat(str(race["start_time_utc"]))
        with store.connect() as db:
            runners = [dict(r) for r in db.execute(
                "SELECT * FROM runners WHERE race_id=? ORDER BY selection_id", (race_id,)
            )]
        active = [r for r in runners if not r["scratched"]]
        expected = {str(row["selection_id"]) for row in active}
        snaps = store.latest_runner_fundamentals(race_id, before=moment)
        by_selection = {str(row["selection_id"]): row for row in snaps}
        reasons: list[str] = []
        if source.get("source_ready") is not True:
            reasons.append("COLLECTOR_SOURCE_REVISION_OR_INCOMPLETE")
        if len(active) < 2:
            reasons.append("ACTIVE_FIELD_INCOMPLETE")
        if moment >= start:
            reasons.append("MODEL_COMPUTATION_NOT_BEFORE_RACE_START")
        if set(by_selection) != expected:
            reasons.append("FULL_FIELD_FUNDAMENTAL_COHORT_MISSING")
        if any(selection not in by_selection for selection in expected):
            reasons.append("PERMANENT_HORSE_ID_UNATTESTED")
        gate = full_field_gate(store, race_id, snaps, moment)
        if gate is not None:
            reasons.append(gate)
        # Existing ATG match is a potential identity *lead*, not a permanent ID
        # attestation. Require explicit independent source confirmation in every
        # active fundamental snapshot, never start-number/name derivation.
        for selection in sorted(expected):
            row = by_selection.get(selection)
            if row is None:
                continue
            try:
                raw = json.loads(row.get("raw_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            identity = raw.get("permanent_horse_identity") if isinstance(raw, dict) else None
            if (not isinstance(identity, dict)
                    or identity.get("status") != "ATTESTED"
                    or not isinstance(identity.get("horse_id"), str)
                    or not identity["horse_id"].strip()
                    or not identity.get("source") or not identity.get("source_version")):
                reasons.append("PERMANENT_HORSE_ID_UNATTESTED")
            if (row.get("data_quality") != "FULL_FIELD_HISTORY_ATG"
                    or row.get("full_field_history_complete") != 1
                    or model._history(row) is None):
                reasons.append("VALIDATED_LIFETIME_WIN_HISTORY_MISSING")
        reasons = sorted(set(reasons))
        probabilities: dict[str, float] | None = None
        odds: dict[str, float] | None = None
        model_run_id: str | None = None
        if not reasons:
            run = run_and_persist_fundamental(store, race_id=race_id, created_at=moment)
            if (not run.shadow_eligible or set(run.probabilities) != expected
                    or not math.isclose(sum(run.probabilities.values()), 1.0, abs_tol=1e-9)):
                # Never claim model-ready when frozen model rejects.
                reasons.append(run.reason or "FROZEN_CHAMPION_REJECTED")
            else:
                probabilities = run.probabilities
                odds = {selection: fair_odds(p) for selection, p in probabilities.items()}
                model_run_id = run.run_id
        for reason in reasons:
            reasons_all[reason] += 1
        records.append({
            "race_id": race_id,
            "source_status": source.get("status"),
            "source_ready": source.get("source_ready") is True,
            "active_runners": len(active),
            "validated_fundamental_rows": len(by_selection),
            "model_ready": not reasons,
            "model_version": model.VERSION,
            "feature_set_version": model.FEATURE_SET_VERSION,
            "calibration_version": model.CALIBRATION_VERSION,
            "input_source_payload_id": source.get("payload_id"),
            "calculated_at_utc": moment.isoformat() if model_run_id else None,
            "model_run_id": model_run_id,
            "p_win": probabilities, "fair_odds": odds,
            "bet_ready": False,
            "pit_certified": False,
            "reasons": sorted(set(reasons)),
        })
    return {
        "schema": "CLOUD_RUN003_FROZEN_MODEL_ADMISSION_V1",
        "model_version": model.VERSION,
        "evaluated_races": len(records),
        "model_input_complete": sum(item["model_ready"] for item in records),
        "p_win_computed": sum(item["p_win"] is not None for item in records),
        "model_reject_reasons": dict(reasons_all),
        "records": records,
        "bet_ready": 0, "pit_certified": False, "bet_authorized": False,
    }
