from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from .domain import ProbabilityEstimate
from .model_registry import ModelRole
from .point_in_time import PointInTimeRecord, validate_record
from .probability import normalize
from .storage import SQLiteStore


@dataclass(frozen=True)
class FundamentalChampionPolicy:
    """Pre-registered shadow Champion v1 policy.

    V1 deliberately uses one market-free signal only: a horse's pre-race historical
    win record from the provider program. It applies empirical-Bayes shrinkage toward
    the race's uniform prior and then normalizes across the active field.

    No odds, betting percentages, exchange data, tipster ranks, or post-race data are
    accepted by this model.
    """

    prior_starts: float = 6.0
    minimum_history_coverage: float = 0.80
    minimum_active_runners: int = 2

    def __post_init__(self) -> None:
        if self.prior_starts <= 0:
            raise ValueError("prior_starts must be > 0")
        if not 0 <= self.minimum_history_coverage <= 1:
            raise ValueError("minimum_history_coverage must be in [0, 1]")
        if self.minimum_active_runners < 2:
            raise ValueError("minimum_active_runners must be >= 2")


@dataclass(frozen=True)
class FundamentalRun:
    run_id: str
    race_id: str
    created_at: datetime
    feature_as_of: datetime
    probabilities: dict[str, float]
    field_size: int
    active_runners: int
    known_history_runners: int
    history_coverage: float
    shadow_eligible: bool
    status: str
    reason: str | None


class MarketFreeFundamentalChampionV1:
    MODEL_NAME = "rikstoto_market_free_empirical_win"
    VERSION = "FUNDAMENTAL_CHAMPION_V1"
    FEATURE_SET_VERSION = "RIKSTOTO_PROGRAM_CAREER_WIN_V1"
    CALIBRATION_VERSION = "UNVALIDATED_SHADOW_V1"
    ROLE = ModelRole.SHADOW_CHAMPION
    LAYER = "FUNDAMENTAL"

    def __init__(self, policy: FundamentalChampionPolicy | None = None):
        self.policy = policy or FundamentalChampionPolicy()

    @staticmethod
    def _history(row: dict[str, object]) -> tuple[int, int] | None:
        starts = row.get("history_total_starts")
        wins = row.get("history_total_wins")
        if starts is None or wins is None:
            return None
        try:
            starts_i = int(starts)
            wins_i = int(wins)
        except (TypeError, ValueError):
            return None
        if starts_i < 0 or wins_i < 0 or wins_i > starts_i:
            return None
        return starts_i, wins_i

    def estimate(
        self,
        *,
        race_id: str,
        rows: list[dict[str, object]],
        created_at: datetime,
    ) -> FundamentalRun:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        active = [row for row in rows if not bool(row.get("scratched"))]
        if len(active) < self.policy.minimum_active_runners:
            run_id = self._run_id(race_id, created_at, {})
            return FundamentalRun(
                run_id=run_id,
                race_id=race_id,
                created_at=created_at,
                feature_as_of=created_at,
                probabilities={},
                field_size=len(rows),
                active_runners=len(active),
                known_history_runners=0,
                history_coverage=0.0,
                shadow_eligible=False,
                status="NOT_EXECUTABLE",
                reason="INSUFFICIENT_ACTIVE_FIELD",
            )

        feature_times: list[datetime] = []
        for row in active:
            raw_time = row.get("feature_as_of_utc")
            if not isinstance(raw_time, str):
                raise ValueError("fundamental snapshot missing feature_as_of_utc")
            feature_time = datetime.fromisoformat(raw_time)
            validate_record(
                PointInTimeRecord(
                    name=f"fundamental:{race_id}:{row.get('selection_id')}",
                    feature_as_of=feature_time,
                    source_published_at=feature_time,
                    decision_time=created_at,
                )
            )
            feature_times.append(feature_time)

        feature_as_of = max(feature_times)
        prior = 1.0 / len(active)
        raw_strength: dict[str, float] = {}
        known = 0

        for row in active:
            selection = str(row["selection_id"])
            history = self._history(row)
            if history is None:
                strength = prior
            else:
                starts, wins = history
                known += 1
                strength = (
                    wins + self.policy.prior_starts * prior
                ) / (starts + self.policy.prior_starts)
            if not math.isfinite(strength) or strength <= 0:
                strength = prior
            raw_strength[selection] = strength

        probabilities = normalize(raw_strength)
        ProbabilityEstimate(
            race_id=race_id,
            model_version=self.VERSION,
            created_at=created_at,
            probabilities=probabilities,
        )
        coverage = known / len(active)
        eligible = coverage >= self.policy.minimum_history_coverage
        reason = None if eligible else "LOW_HISTORY_COVERAGE"
        status = "OK" if eligible else "CAUTION"
        run_id = self._run_id(race_id, created_at, probabilities)

        return FundamentalRun(
            run_id=run_id,
            race_id=race_id,
            created_at=created_at,
            feature_as_of=feature_as_of,
            probabilities=probabilities,
            field_size=len(rows),
            active_runners=len(active),
            known_history_runners=known,
            history_coverage=coverage,
            shadow_eligible=eligible,
            status=status,
            reason=reason,
        )

    @classmethod
    def _run_id(
        cls,
        race_id: str,
        created_at: datetime,
        probabilities: dict[str, float],
    ) -> str:
        payload = json.dumps(probabilities, sort_keys=True, separators=(",", ":"))
        return sha256(
            f"{race_id}|{cls.VERSION}|{created_at.isoformat()}|{payload}".encode()
        ).hexdigest()


def run_and_persist_fundamental(
    store: SQLiteStore,
    *,
    race_id: str,
    created_at: datetime,
    policy: FundamentalChampionPolicy | None = None,
) -> FundamentalRun:
    """Create one frozen market-free full-field estimate from latest PIT fundamentals."""
    model = MarketFreeFundamentalChampionV1(policy)
    rows = store.latest_runner_fundamentals(race_id, before=created_at)
    run = model.estimate(race_id=race_id, rows=rows, created_at=created_at)

    store.upsert_model_version(
        model_name=model.MODEL_NAME,
        version=model.VERSION,
        role=model.ROLE.value,
        training_cutoff_utc="NO_FITTED_COEFFICIENTS",
        feature_set_version=model.FEATURE_SET_VERSION,
        calibration_version=model.CALIBRATION_VERSION,
        created_at=created_at,
        notes=(
            "Shadow Champion v1. Market-free empirical-Bayes historical win-rate prior. "
            "No fitted coefficients; prospective validation required before promotion "
            "outside paper betting."
        ),
    )

    if run.probabilities:
        for selection_id, probability in run.probabilities.items():
            prediction_id = sha256(
                f"{run.run_id}|{selection_id}".encode()
            ).hexdigest()
            store.insert_prediction(
                prediction_id=prediction_id,
                race_id=race_id,
                selection_id=selection_id,
                created_at=created_at,
                model_name=model.MODEL_NAME,
                model_version=model.VERSION,
                layer=model.LAYER,
                probability=probability,
                feature_as_of=run.feature_as_of,
            )

    store.insert_fundamental_model_run(
        {
            "run_id": run.run_id,
            "race_id": race_id,
            "model_name": model.MODEL_NAME,
            "model_version": model.VERSION,
            "role": model.ROLE.value,
            "feature_set_version": model.FEATURE_SET_VERSION,
            "created_at_utc": created_at.isoformat(),
            "feature_as_of_utc": run.feature_as_of.isoformat(),
            "field_size": run.field_size,
            "active_runners": run.active_runners,
            "known_history_runners": run.known_history_runners,
            "history_coverage": run.history_coverage,
            "shadow_eligible": int(run.shadow_eligible),
            "status": run.status,
            "reason": run.reason,
            "probabilities_json": json.dumps(run.probabilities, sort_keys=True),
            "metadata_json": json.dumps(
                {
                    "prior_starts": model.policy.prior_starts,
                    "minimum_history_coverage": model.policy.minimum_history_coverage,
                    "market_features": [],
                    "unvalidated_shadow_champion": True,
                },
                sort_keys=True,
            ),
        }
    )
    return run
