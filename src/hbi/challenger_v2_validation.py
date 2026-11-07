"""Read-only DEV009 validation plus hardgated, chronological Challenger scoring.

The archived DEV009 evidence is a *research benchmark*, not a V2 validation
dataset. V2 scores exist only after independently pre-archived V2 predictions
are joined to later official outcomes. This module must never refit or select
an improved coefficient based on outcomes.
"""
from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from statistics import mean

SCHEMA = "CHALLENGER_V2_PROSPECTIVE_VALIDATION_V1"


def _clock(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError("PROSPECTIVE_VALIDATION_CLOCK_INVALID")
    return dt.astimezone(UTC)


def _multiclass_brier(probs: dict[str,float], winner: str) -> float:
    return math.fsum(
        (prob-(1 if horse==winner else 0))**2
        for horse,prob in probs.items()
    )


def _qualified_distribution(report: dict) -> dict[str,float] | None:
    rows=report.get("runners")
    if not isinstance(rows,list) or len(rows)<2:
        return None
    active=[r for r in rows if isinstance(r,dict) and r.get("scratched") is False]
    if len(active)<2:
        return None
    p={}
    for row in active:
        key=row.get("selection_id")
        prob=row.get("p_win_challenger")
        if (not isinstance(key,str) or key in p
                or type(prob) not in (int,float) or not math.isfinite(prob)
                or not 0<prob<1):
            return None
        p[key]=float(prob)
    return p if math.isclose(math.fsum(p.values()),1,rel_tol=0,abs_tol=1e-9) else None


def score_existing_challenger(
    original_challenger: dict, *,
    model_original_artifact_created_at_utc: str,
    official_result: dict,
    result_observed_at_utc: str,
    validation_holdout_start_utc: str,
) -> dict:
    """Fail closed unless *both* model and official outcome original clocks pass.

    Caller must independently verify raw bytes SHA and source identities before
    invoking this pure function. A JSON claim alone is NOT source attestation.
    """
    if (original_challenger.get("schema") !=
            "CHALLENGER_V2_SHADOW_ORIGINAL_REPORT_V1"
            or original_challenger.get("bet_authority") is not False
            or original_challenger.get("calibration_status") != "UNVALIDATED_NOT_FITTED"
            or original_challenger.get("status") !=
            "MODEL_RESEARCH_ONLY_NO_PIT_OR_IDENTITY_AUTHORITY"):
        return {"status":"NOT_AVAILABLE","reason":"CHALLENGER_ORIGINAL_INELIGIBLE"}
    try:
        start=_clock(original_challenger["start_at_utc"])
        cutoff=_clock(original_challenger["as_of_utc"])
        persisted=_clock(model_original_artifact_created_at_utc)
        observed=_clock(result_observed_at_utc)
        holdout=_clock(validation_holdout_start_utc)
    except (KeyError, ValueError, TypeError):
        return {"status":"NOT_AVAILABLE","reason":"ORIGINAL_CLOCK_MISSING"}
    if not (holdout <= cutoff <= persisted < start < observed):
        return {
            "status":"NOT_AVAILABLE",
            "reason":"MODEL_NOT_INDEPENDENTLY_ARCHIVED_BEFORE_START_OR_NOT_HOLDOUT",
        }
    probs=_qualified_distribution(original_challenger)
    if not probs:
        return {"status":"NOT_AVAILABLE","reason":"NO_VALID_FROZEN_V2_FULL_FIELD"}
    if (official_result.get("source_verified_full_field") is not True
            or official_result.get("same_physical_race_id") !=
            original_challenger.get("race_id")):
        return {"status":"NOT_AVAILABLE","reason":"OFFICIAL_RESULT_NOT_INDEPENDENTLY_ATTESTED"}
    winner=official_result.get("winner_selection_id")
    if not isinstance(winner,str) or winner not in probs:
        return {"status":"NOT_AVAILABLE","reason":"OFFICIAL_WINNER_NOT_IN_FROZEN_FIELD"}
    return {
        "status":"PROSPECTIVE_SHADOW_EVALUABLE_NOT_BET",
        "winner_selection_id":winner,
        "winner_p":probs[winner],
        "log_loss":-math.log(probs[winner]),
        "multiclass_brier":_multiclass_brier(probs,winner),
        "bet_authority":False,"pit_certified":False,
        "not_claiming_calibration_or_improved_accuracy":True,
    }


def dev009_benchmark(index: dict, *, bootstrap_replicates: int=5000) -> dict:
    if (index.get("schema")!="DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
            or index.get("bet_authority") is not False
            or index.get("pit_certification_performed") is not False):
        raise ValueError("DEV009_SOURCE_INDEX_NOT_AUTHENTIC_RESEARCH_COHORT")
    paired=[]
    for r in index.get("records",[]):
        if r.get("status")!="EVALUABLE_RESEARCH_ONLY":
            continue
        scores=r.get("score")
        if not isinstance(scores,dict):
            continue
        keys=("champion_log_loss","market_log_loss",
              "champion_multiclass_brier","market_multiclass_brier")
        if all(type(scores.get(k)) in (int,float)
               and math.isfinite(float(scores[k])) for k in keys):
            paired.append((r["race_id"],scores))
    if len({r for r,_ in paired}) != len(paired):
        raise ValueError("DUPLICATE_PHYSICAL_RACE_HISTORICAL_BENCHMARK")
    result={
        "schema":SCHEMA,"source":"DEV009_ORIGINAL_RESEARCH_COHORT",
        "source_status":index.get("status"),
        "full_evaluable_research_races":index.get("counts",{}).get("paired_champion_core004"),
        "paired_champion_market_count":len(paired),
        "pit_certified_pair_count":0,
        "v2_independent_outcome_score_count":0,
        "v2_vs_champion":"NOT_ESTABLISHED",
        "v2_vs_market":"NOT_ESTABLISHED",
        "bet_authority":False,
        "do_not_fit_and_test_on_same_races":True,
        "calibration_original":index.get("calibration"),
        "source_recency_not_validation_of_challenger":True,
    }
    if not paired:
        return result
    def avg(metric: str) -> float:
        return mean(scores[metric] for _, scores in paired)
    diffs={}
    for metric in ("log_loss","multiclass_brier"):
        values=[
            x["champion_"+metric]-x["market_"+metric] for _,x in paired
        ]
        rng=random.Random(20261107)
        simulations=sorted(
            mean(values[rng.randrange(len(values))] for _ in values)
            for _ in range(bootstrap_replicates)
        ) if bootstrap_replicates>0 else []
        diffs[metric]={
            "champion_mean_paired":avg("champion_"+metric),
            "market_mean_paired":avg("market_"+metric),
            "champion_minus_market":mean(values),
            "bootstrap_95_percent_descriptive":(
                [simulations[max(0,int(.025*len(simulations))-1)],
                 simulations[min(len(simulations)-1,int(.975*len(simulations)))]]
                if simulations else None
            ),
            "champion_worse_than_market_races":sum(x>0 for x in values),
            "champion_better_than_market_races":sum(x<0 for x in values),
        }
    result["paired_differences"]=diffs
    result["selection_bias_warning"]=(
        "48 of 135 documented physical races; research-only no PIT, "
        "resampling races does not correct source-selection and calendar bias"
    )
    result["favorite_outsider_diagnostic"]=(
        "NO ROBUST CONCLUSION: high-p bins absent/sparse, "
        "and archived DEV009 source does not supply all normalized "
        "market/Champion individual-horse pairs for each segment"
    )
    return result
