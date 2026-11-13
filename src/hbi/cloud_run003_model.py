"""CLOUD-RUN-003 model admission over genuine archived Collector races.

The frozen market-free Champion is called ONLY when its existing full-field,
independent identity, historical cohort and pre-race requirements are met.
No guessed history, market shares, bet signals or retroactive PIT qualification.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from .fundamental import MarketFreeFundamentalChampionV1, run_and_persist_fundamental
from .horse_identity import ModelIdentityEvidence, resolve_model_identity
from .probability import fair_odds
from .provider_capability import full_field_gate
from .storage import SQLiteStore


@dataclass(frozen=True)
class IndependentScratchEvidence:
    """A verified independent adapter's original race roster and scratch state."""

    race_id: str
    roster: tuple[tuple[str, bool], ...]
    observed_at: datetime
    original_sha256: str
    original_uri: str
    original: bytes | None = None

    def is_usable(self, race_id: str, moment: datetime) -> bool:
        if self.race_id != race_id or any(type(flag) is not bool for _, flag in self.roster):
            return False
        doc = verified_original(
            "INDEPENDENT_SCRATCH", self.original_uri, self.original_sha256,
            self.observed_at, self.original, moment,
        )
        return doc == {
            "schema": "VERIFIED_INDEPENDENT_SCRATCH_V1",
            "race_id": race_id,
            "roster": [[selection, flag] for selection, flag in self.roster],
        }


def assess_and_run(
    store: SQLiteStore,
    imported: list[dict[str, object]],
    *,
    now: datetime | None = None,
    identity_evidence: tuple[ModelIdentityEvidence, ...] = (),
    scratch_evidence: tuple[IndependentScratchEvidence, ...] = (),
) -> dict[str, object]:
    """Run existing full-field model only for a fully admitted contemporaneous cohort."""
    moment = now or datetime.now(UTC)
    if moment.utcoffset() is None:
        raise ValueError("CLOUD_MODEL_CLOCK_NAIVE")
    moment = moment.astimezone(UTC)
    model = MarketFreeFundamentalChampionV1()
    records: list[dict[str, object]] = []
    reasons_all: Counter[str] = Counter()
    identity_by_entry: dict[tuple[str, str], list[ModelIdentityEvidence]] = {}
    for item in identity_evidence:
        key = (item.identity.race_id, item.identity.selection_id)
        identity_by_entry.setdefault(key, []).append(item)
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
        roster = {str(row["selection_id"]): bool(row["scratched"]) for row in runners}
        expected = {selection for selection, scratched in roster.items() if not scratched}
        snaps = store.latest_runner_fundamentals(race_id, before=moment)
        by_selection = {str(row["selection_id"]): row for row in snaps if not row["scratched"]}
        reasons: list[str] = []
        if source.get("source_ready") is not True:
            reasons.append("COLLECTOR_SOURCE_REVISION_OR_INCOMPLETE")
        if len(expected) < 2:
            reasons.append("ACTIVE_FIELD_INCOMPLETE")
        if moment >= start:
            reasons.append("MODEL_COMPUTATION_NOT_BEFORE_RACE_START")
        scratches = [item for item in scratch_evidence if item.is_usable(race_id, moment)]
        if not scratches:
            reasons.append("INDEPENDENT_SCRATCH_CORROBORATION_NOT_ATTESTED")
        elif any(len(item.roster) != len(roster) or dict(item.roster) != roster for item in scratches):
            reasons.append("INDEPENDENT_SCRATCH_ROSTER_CONFLICT")
        if set(by_selection) != expected:
            reasons.append("FULL_FIELD_FUNDAMENTAL_COHORT_MISSING")
        if any(
            str(row["selection_id"]) not in roster
            or roster[str(row["selection_id"])] != bool(row["scratched"])
            for row in snaps
        ):
            reasons.append("FUNDAMENTAL_ROSTER_OR_SCRATCH_CONFLICT")
        if any(selection not in by_selection for selection in expected):
            reasons.extend(("PERMANENT_HORSE_ID_UNATTESTED", "IDENTITY_UNRESOLVED"))
        gate = full_field_gate(store, race_id, snaps, moment)
        if gate is not None:
            reasons.append(gate)
        identities: list[str] = []
        atg_ids: list[int] = []
        verified_identity_sources: dict[str, list[dict[str, object]]] = {}
        for selection in sorted(expected):
            row = by_selection.get(selection)
            if row is None:
                continue
            try:
                raw = json.loads(row.get("raw_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            atg = raw.get("atg_market_free") if isinstance(raw, dict) else None
            proofs = tuple(identity_by_entry.get((race_id, selection), ()))
            horse_id, identity_reason = resolve_model_identity(race_id, selection, row, atg, proofs, moment)
            if identity_reason:
                reasons.extend(("PERMANENT_HORSE_ID_UNATTESTED", identity_reason))
            elif horse_id is not None:
                identities.append(horse_id)
                atg_ids.append(atg["horseId"])
                verified_identity_sources[selection] = [{
                    "horse_id": item.identity.horse_id,
                    "source": item.identity.source,
                    "source_version": item.identity.source_version,
                    "original_uri": item.original_uri,
                    "original_sha256": item.original_sha256,
                    "observed_at_utc": item.observed_at.astimezone(UTC).isoformat(),
                    "atg_horse_id": item.atg_horse_id,
                    "snapshot_id": item.snapshot_id,
                    "history_original_uri": item.history_original_uri,
                    "history_original_sha256": item.history_original_sha256,
                    "history_completed_at_utc": item.history_completed_at.astimezone(UTC).isoformat(),
                } for item in proofs]
            try:
                observed = datetime.fromisoformat(str(row["observed_at_utc"]))
                timely = observed.utcoffset() is not None and observed <= moment
            except (KeyError, ValueError):
                timely = False
            if not timely:
                reasons.append("FUNDAMENTAL_OBSERVATION_UNATTESTED_OR_LATE")
            totals = model._history(row)
            if (row.get("data_quality") != "FULL_FIELD_HISTORY_ATG"
                    or row.get("full_field_history_complete") != 1
                    or not isinstance(atg, dict)
                    or totals is None
                    or any(type(atg.get(key)) is not int for key in ("lifeStarts", "lifeWins"))
                    or (atg.get("lifeStarts"), atg.get("lifeWins")) != totals):
                reasons.append("VALIDATED_LIFETIME_WIN_HISTORY_MISSING")
        if len(set(identities)) != len(identities) or len(set(atg_ids)) != len(atg_ids):
            reasons.append("DUPLICATE_HORSE_IDENTITY_IN_ACTIVE_FIELD")
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
            "active_runners": len(expected),
            "validated_fundamental_rows": len(by_selection),
            "identity_sources": verified_identity_sources,
            "independent_scratch_sources": [{
                "original_uri": item.original_uri,
                "original_sha256": item.original_sha256,
                "observed_at_utc": item.observed_at.astimezone(UTC).isoformat(),
            } for item in scratches],
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
from .admission_originals import verified_original
