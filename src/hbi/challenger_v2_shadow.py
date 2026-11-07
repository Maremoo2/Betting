"""CHALLENGER_V2: separate, deliberately UNFITTED market-free SHADOW candidate.

NO odds, markets, tips, outcomes or future observations accepted. All runner
features must belong to one fully verified, pre-race source observation cohort.
This is not Champion V1.1, does not refit V3.3.12 and has zero BET authority.

First bounded implementation deliberately scores ONLY existing, verifiable
pre-race career and current-year aggregate records. Individual 5/10/20 races,
class, opponent strengths, post position and driver remain UNMODELLED until
independent historical PIT contracts exist. Coefficients are frozen illustrative
research choices, *not* historically estimated or validated.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

MODEL_VERSION = "CHALLENGER_V2_0_SHADOW_SEASON_RESIDUAL_UNFITTED"
FEATURE_VERSION = "ATG_ORIGINAL_LIFETIME_AND_CURRENT_YEAR_V1"
TRAINING_CUTOFF = "NOT_FITTED_OR_TUNED"
ROLE = "SHADOW_CHALLENGER"
MISSING_FACTORS = (
    "recent_5_starts", "recent_10_starts", "recent_20_starts",
    "time_weighted_recent_form", "historical_class", "opponent_prior_strength",
    "direct_meetings", "common_opponent", "distance_conditioned_results",
    "post_position_effect", "driver_trainer_changes", "gallop_risk",
    "verified_sectionals", "track_condition",
)


@dataclass(frozen=True)
class CandidatePolicy:
    career_prior_starts: float = 6.0
    season_prior_starts: float = 10.0
    season_residual_weight: float = 0.25
    season_residual_log_cap: float = 0.4
    require_provider_horse_id: bool = True

    def __post_init__(self) -> None:
        if (self.career_prior_starts <= 0 or self.season_prior_starts <= 0
                or not 0 <= self.season_residual_weight <= 1
                or self.season_residual_log_cap <= 0
                or not self.require_provider_horse_id):
            raise ValueError("SHADOW_CANDIDATE_POLICY_INVALID")


def _time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise TypeError("SOURCE_CLOCK_REQUIRED")
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("SOURCE_CLOCK_NOT_ISO8601") from exc
    if stamp.utcoffset() is None:
        raise ValueError("SOURCE_CLOCK_NOT_TIMEZONE_AWARE")
    return stamp.astimezone(UTC)


def _integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _blocked(
    race_id: str, asof: datetime, starts: list[dict], blockers: set[str],
) -> dict[str, Any]:
    return {
        "schema": "CHALLENGER_V2_SHADOW_ORIGINAL_REPORT_V1",
        "race_id": race_id, "as_of_utc": asof.isoformat(),
        "model_version": MODEL_VERSION, "feature_set_version": FEATURE_VERSION,
        "training_cutoff": TRAINING_CUTOFF,
        "calibration_status": "UNVALIDATED_NOT_FITTED",
        "bet_authority": False, "pit_certified": False,
        "status": "BLOCKED_SHADOW_NO_COMPLETE_FIELD",
        "blockers": sorted(blockers),
        "p_win_sum": None,
        "runners": [
            {"selection_id": str(row.get("selection_id")),
             "p_win_challenger": None,
             "reason": "NOT_APPLICABLE_SCRATCHED" if row.get("scratched")
                       else "FULL_FIELD_ADMISSION_BLOCKED"}
            for row in starts
        ],
    }


def estimate_shadow(
    *, race_id: str, start_at_utc: str, as_of_utc: str,
    runners: list[dict[str, Any]], policy: CandidatePolicy | None = None,
) -> dict[str, Any]:
    """No partial field probabilities or market-conditioned features ever."""
    config = policy or CandidatePolicy()
    start, asof = _time(start_at_utc), _time(as_of_utc)
    if not isinstance(race_id, str) or not race_id.startswith("RIKSTOTO:"):
        raise ValueError("PHYSICAL_RACE_ID_REQUIRED")
    if not isinstance(runners, list) or not runners:
        raise TypeError("RUNNER_COHORT_REQUIRED")
    blockers: set[str] = set()
    if not asof < start:
        blockers.add("PREDICTION_NOT_BEFORE_RACE")
    seen: set[str] = set()
    active: list[dict[str, Any]] = []
    source_times: set[str] = set()
    for row in runners:
        if (not isinstance(row, dict)
                or not isinstance(row.get("selection_id"), str)
                or not row["selection_id"].isdigit()
                or type(row.get("scratched")) is not bool):
            raise TypeError("RUNNER_IDENTITY_SCHEMA_INVALID")
        sel = row["selection_id"]
        if sel in seen:
            blockers.add("DUPLICATE_SELECTION_ID")
        seen.add(sel)
        if row["scratched"]:
            continue
        active.append(row)
        if config.require_provider_horse_id and not _integer(row.get("atg_horse_id")):
            blockers.add("PROVIDER_PERMANENT_HORSE_ID_MISSING")
        if not _sha(row.get("historical_source_sha256")):
            blockers.add("ORIGINAL_HISTORICAL_SOURCE_SHA_MISSING")
        try:
            source_clock = _time(row.get("historical_observed_at_utc"))
            if source_clock > asof or source_clock >= start:
                blockers.add("SOURCE_OBSERVED_AFTER_FEATURE_CUTOFF")
            source_times.add(source_clock.isoformat())
        except (TypeError, ValueError):
            blockers.add("HISTORICAL_SOURCE_CLOCK_INVALID")
        career_starts, career_wins = row.get("career_starts"), row.get("career_wins")
        season_starts, season_wins = row.get("season_starts"), row.get("season_wins")
        if (not all(_integer(x) for x in (
                    career_starts, career_wins, season_starts, season_wins))
                or career_wins > career_starts
                or season_wins > season_starts
                or season_starts > career_starts
                or season_wins > career_wins):
            blockers.add("SEASON_CAREER_COUNTS_MISSING_OR_IMPOSSIBLE")
        if row.get("independent_registration_attested") is not True:
            # The research candidate may be calculated with an ATG horse ID,
            # but independent national registration/PIT remains uncertified.
            blockers.add("INDEPENDENT_REGISTRATION_NOT_ATTESTED")
    if len(active) < 2:
        blockers.add("INSUFFICIENT_ACTIVE_RUNNERS")
    if len(source_times) > 1:
        # One source cohort can contain different completed race-original clock
        # times; all must still be strictly before the analysis cutoff.
        pass
    research_blocks = blockers - {"INDEPENDENT_REGISTRATION_NOT_ATTESTED"}
    if research_blocks:
        return _blocked(race_id, asof, runners, blockers)
    n = len(active)
    race_prior = 1.0 / n
    strengths: dict[str, float] = {}
    pure_career: dict[str, float] = {}
    diagnostics: dict[str, dict] = {}
    for row in active:
        sid = row["selection_id"]
        starts, wins = row["career_starts"], row["career_wins"]
        ys, yw = row["season_starts"], row["season_wins"]
        # This is intentionally identical to the already frozen Champion's
        # per-horse career baseline, but produced in a SEPARATE shadow module.
        career = (wins + config.career_prior_starts * race_prior) / (
            starts + config.career_prior_starts
        )
        # Career and season results overlap. Model the bounded SEASON RESIDUAL
        # instead of adding a second independent season win-rate predictor.
        season_shrunk = (yw + config.season_prior_starts * career) / (
            ys + config.season_prior_starts
        )
        residual = math.log(season_shrunk / career)
        residual = min(config.season_residual_log_cap,
                       max(-config.season_residual_log_cap, residual))
        evidence_weight = ys / (ys + config.season_prior_starts)
        multiplier = math.exp(
            config.season_residual_weight * evidence_weight * residual
        )
        pure_career[sid] = career
        strengths[sid] = career * multiplier
        diagnostics[sid] = {
            "career_eb_strength": career,
            "season_shrunk_win_rate": season_shrunk,
            "season_vs_career_residual_log_clipped": residual,
            "season_evidence_weight": evidence_weight,
            "bounded_shadow_multiplier": multiplier,
        }
    denom = math.fsum(strengths.values())
    if denom <= 0 or not math.isfinite(denom):
        raise ValueError("CHALLENGER_SHADOW_NORMALIZER_INVALID")
    p = {sid: v / denom for sid, v in strengths.items()}
    if not math.isclose(math.fsum(p.values()), 1.0, abs_tol=1e-9):
        raise ValueError("CHALLENGER_SHADOW_PROBABILITIES_NOT_NORMALIZED")
    rows = []
    for row in runners:
        sid = row["selection_id"]
        rows.append({
            "selection_id": sid, "scratched": row["scratched"],
            "atg_horse_id": row.get("atg_horse_id"),
            "history_source_sha256": row.get("historical_source_sha256"),
            "history_source_observed_at_utc": row.get("historical_observed_at_utc"),
            "career_starts": row.get("career_starts"),
            "career_wins": row.get("career_wins"),
            "season_starts": row.get("season_starts"),
            "season_wins": row.get("season_wins"),
            "p_win_challenger": p.get(sid),
            "fair_odds_challenger": 1.0 / p[sid] if sid in p else None,
            "research_diagnostics": diagnostics.get(sid),
            "last_5_10_20": "MISSING_NO_INDIVIDUAL_RESULT_ORIGINALS",
            "historical_opponent_strength": "MISSING_NO_PIT_PROVEN_PREVIOUS_FIELD",
            "pit_status": "NOT_CERTIFIED",
            "decision": "NOT_EXECUTABLE" if not row["scratched"] else "NOT_APPLICABLE",
        })
    signature = {
        "race_id":race_id,"start_at_utc":start.isoformat(),
        "as_of_utc":asof.isoformat(),"model":MODEL_VERSION,
        "feature_set":FEATURE_VERSION,"policy":asdict(config),
        "input": [
            {k: r.get(k) for k in (
                "selection_id","scratched","atg_horse_id",
                "historical_source_sha256","historical_observed_at_utc",
                "career_starts","career_wins","season_starts","season_wins")}
            for r in runners
        ],
    }
    model_run_sha = hashlib.sha256(
        json.dumps(signature,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    return {
        "schema":"CHALLENGER_V2_SHADOW_ORIGINAL_REPORT_V1",
        "race_id":race_id,"start_at_utc":start.isoformat(),
        "as_of_utc":asof.isoformat(),
        "model_version":MODEL_VERSION,"model_run_sha256":model_run_sha,
        "feature_set_version":FEATURE_VERSION,"training_cutoff":TRAINING_CUTOFF,
        "role":ROLE,"calibration_status":"UNVALIDATED_NOT_FITTED",
        "model_uses_market_features":False,"model_uses_result_features":False,
        "actual_champion_modified":False,"bet_authority":False,"pit_certified":False,
        "status":"MODEL_RESEARCH_ONLY_NO_PIT_OR_IDENTITY_AUTHORITY",
        "blockers":sorted(blockers | {"PIT_SOURCE_PUBLICATION_UNATTESTED",
                                   "UNVALIDATED_CHALLENGER_V2"}),
        "feature_coefficients_illustrative":asdict(config),
        "features_omitted":list(MISSING_FACTORS),
        "p_win_sum":math.fsum(p.values()),"runners":rows,
    }
