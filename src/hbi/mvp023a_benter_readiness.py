"""MVP-023A Benter combination readiness gate; research-only and no weight fit.

Reuses research_lab.audit_race and probability.combine_probabilities unchanged.
It does not guess alpha/beta or admit unsigned historic source attestations.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .research_lab import audit_race, digest

SCHEMA = "MVP023A_BENTER_READINESS_V1"
SHA = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_FEATURES = {
    "market", "odds", "closing_odds", "win_odds", "winner", "result",
    "placing", "place", "payout", "dividend", "pwin", "pcol", "prize",
    "market_probability", "final_odds", "result_position",
}


def _clock(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(UTC) if dt.utcoffset() is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def inspect_benter_readiness(bundle: dict) -> dict:
    """Return prerequisite matrix, never a model or a production authorization."""
    if not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA:
        raise ValueError("BENTER_READINESS_SCHEMA_INVALID")
    plan = bundle.get("plan")
    races = bundle.get("races")
    model = bundle.get("fundamental_model")
    if not isinstance(plan, dict) or not isinstance(races, list) or not isinstance(model, dict):
        raise TypeError("BENTER_INPUT_CONTRACT_INVALID")
    if not isinstance(plan.get("features"), list) or not plan["features"]:
        raise ValueError("REGISTERED_FEATURE_LIST_MISSING")
    if FORBIDDEN_FEATURES.intersection({str(k).lower() for k in plan["features"]}):
        raise ValueError("MARKET_OR_OUTCOME_LEAKAGE_IN_FUNDAMENTAL_PLAN")
    training = model.get("training_race_ids")
    if not isinstance(training, list) or not training or any(not isinstance(r, str) for r in training):
        raise ValueError("FUNDAMENTAL_TRAINING_COHORT_NOT_DECLARED")
    if len(training) != len(set(training)):
        raise ValueError("DUPLICATE_TRAINING_RACE")
    for rid in training:
        match = re.fullmatch(r"RIKSTOTO:[A-Z0-9]+_NR_(\d{4})-\d{2}-\d{2}:[1-9]\d*", rid)
        if match is None or not 2015 <= int(match.group(1)) <= 2022:
            raise ValueError("TRAINING_OUTSIDE_FROZEN_DEVELOPMENT_YEARS")
    if any(not _sha(model.get(k)) for k in (
        "model_original_sha256", "training_dataset_sha256",
        "frozen_prediction_bundle_sha256",
    )):
        raise ValueError("FUNDAMENTAL_ORIGINAL_MODEL_HASH_NOT_DECLARED")
    if model.get("uses_market_features") is not False:
        raise ValueError("FUNDAMENTAL_MODEL_NOT_MARKET_INDEPENDENT")
    seen = set()
    records = []
    proposed_calibration = model.get("calibration_race_ids", [])
    if (not isinstance(proposed_calibration, list)
            or any(not isinstance(r, str) for r in proposed_calibration)
            or len(set(proposed_calibration)) != len(proposed_calibration)):
        raise ValueError("FUNDAMENTAL_MODEL_CALIBRATION_COHORT_INVALID")

    stats = Counter()
    for race in races:
        if not isinstance(race, dict) or not isinstance(race.get("race_id"), str):
            raise TypeError("RACE_READINESS_DOCUMENT_INVALID")
        rid = race["race_id"]
        if rid in seen:
            raise ValueError("DUPLICATE_EVALUATION_RACE")
        seen.add(rid)
        match = re.fullmatch(r"RIKSTOTO:[A-Z0-9]+_NR_(\d{4})-\d{2}-\d{2}:[1-9]\d*", rid)
        if match is None:
            raise ValueError("PHYSICAL_RACE_ID_INVALID")
        if int(match.group(1)) == 2025:
            # The potentially exposed 2025 lockbox is never admitted into this
            # prototype, even if a caller supplies result labels.
            raise ValueError("CANDIDATE_2025_LOCKBOX_NOT_AUTHORIZED")
        reasons = []
        if rid in training:
            reasons.append("FUNDAMENTAL_PREDICTION_NOT_OOS")
        if not 2023 <= int(match.group(1)) <= 2024 and int(match.group(1)) != 2026:
            reasons.append("EVALUATION_ROLE_NOT_REGISTERED")
        cutoff = _clock(race.get("start_at"))
        cutoff = cutoff - timedelta(minutes=4) if cutoff else None
        if cutoff is None:
            reasons.append("RACE_T4_CLOCK_UNKNOWN")
        try:
            audit_race(race, plan)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            reasons.append("RESEARCH_LAB_PIT_OR_FIELD:" + str(exc))
        original = race.get("source_receipts")
        if not isinstance(original, dict):
            reasons.append("MISSING_SOURCE_RECEIPTS")
            original = {}
        for kind in ("market", "official_result", "fundamental_freeze"):
            receipt = original.get(kind)
            if not isinstance(receipt, dict) or not _sha(receipt.get("sha256")):
                reasons.append(kind.upper() + "_ORIGINAL_SHA_NOT_ATTESTED")
                continue
            if kind != "official_result":
                observed = _clock(receipt.get("observed_at_utc"))
                published = _clock(receipt.get("published_at_utc"))
                if cutoff is None or observed is None or observed >= cutoff:
                    reasons.append(kind.upper() + "_NOT_OBSERVED_BEFORE_T4")
                if published is None or cutoff is None or published >= cutoff:
                    reasons.append(kind.upper() + "_SOURCE_PUBLICATION_TIME_NOT_PROVEN")
        if race.get("model_training_race_ids") != training:
            reasons.append("FUNDAMENTAL_MODEL_TRAINING_PROVENANCE_CONFLICT")
        if race.get("market_snapshot_type") != "PRE_RACE_VERIFIED":
            reasons.append("HISTORICAL_TERMINAL_MARKET_NOT_EXECUTABLE")
        if not _sha(race.get("frozen_fundamental_prediction_sha256")):
            reasons.append("PREDICTION_FREEZE_ORIGINAL_SHA_MISSING")
        if cutoff is not None:
            for runner in race.get("runners", []):
                if isinstance(runner, dict):
                    pred = _clock(runner.get("prediction_at"))
                    if pred is None or pred >= cutoff:
                        reasons.append("FUNDAMENTAL_PREDICTION_AFTER_T4")
                    for key in plan["features"]:
                        feature = runner.get("features", {}).get(key)
                        if isinstance(feature, dict) and not _sha(feature.get("source_sha256")):
                            reasons.append("HISTORICAL_FEATURE_SHA_NOT_ATTESTED")
            market = _clock(race.get("market_available_at"))
            if market is None or market >= cutoff:
                reasons.append("MARKET_PRICE_NOT_AVAILABLE_BY_T4")
        # Stated receipt fields alone do not independently verify raw bytes,
        # publication history or fit provenance. The next phase must replay
        # source originals before any actual fitting or OOS claim.
        reasons.append("IMMUTABLE_RAW_ORIGINAL_REPLAY_REQUIRED")
        unique_reasons = sorted(set(reasons))
        stats.update(unique_reasons)
        records.append({
            "race_id": rid,
            "structural_race_check_passed": unique_reasons == ["IMMUTABLE_RAW_ORIGINAL_REPLAY_REQUIRED"],
            "blockers": unique_reasons,
            "readiness": "NOT_READY",
            "bet_authority": False,
        })
    if set(proposed_calibration).intersection(seen):
        raise ValueError("FUNDAMENTAL_MODEL_CALIBRATED_ON_EVALUATION_RACES")
    if any(re.search(r"_NR_2025-", rid) for rid in proposed_calibration):
        raise ValueError("CANDIDATE_2025_LOCKBOX_CALIBRATION_NOT_AUTHORIZED")
    if not races:
        stats["NO_EVALUATION_RACES"] += 1
    proposed_weights = bundle.get("combination_weights")
    if proposed_weights is not None:
        stats["COMBINATION_WEIGHTS_NOT_PROVEN_INDEPENDENTLY_FITTED"] += 1
        if not isinstance(proposed_weights, dict):
            raise TypeError("COMBINATION_WEIGHTS_MALFORMED")
        weight_fit = proposed_weights.get("fit_race_ids")
        if not isinstance(weight_fit, list) or any(not isinstance(rid, str) for rid in weight_fit):
            stats["COMBINATION_FIT_COHORT_NOT_ATTESTED"] += 1
        else:
            if len(weight_fit) != len(set(weight_fit)):
                raise ValueError("DUPLICATE_COMBINATION_FIT_RACES")
            if set(weight_fit).intersection(seen):
                raise ValueError("COMBINATION_FIT_TUNED_ON_EVALUATION_RACES")
            if any(re.search(r"_NR_2025-", rid) for rid in weight_fit):
                raise ValueError("CANDIDATE_2025_LOCKBOX_COMBINATION_FIT_NOT_AUTHORIZED")
            if not weight_fit or any(
                re.fullmatch(r"RIKSTOTO:[A-Z0-9]+_NR_2023-\d{2}-\d{2}:[1-9]\d*", rid) is None
                for rid in weight_fit
            ):
                stats["COMBINATION_FIT_ROLE_NOT_VERIFIED"] += 1
    else:
        stats["UNFITTED_ALPHA_BETA_NOT_ESTIMATED"] += 1
    if bundle.get("lockbox_exposure_approved") is True:
        stats["LOCKBOX_EXPOSURE_NOT_REVIEWED_BY_INDEPENDENT_OWNER"] += 1
    return {
        "schema": SCHEMA, "research_only": True,
        "bet_authority": False, "promotion_enabled": False,
        "training_performed": False, "weight_estimation_performed": False,
        "existing_combination_engine": "hbi.probability.combine_probabilities",
        "fundamental_model_sha256": model["model_original_sha256"],
        "registered_plan_sha256": digest(plan),
        "races_checked": len(records),
        "per_race": records,
        "blocker_counts": dict(sorted(stats.items())),
        "fit_readiness": "NOT_READY",
        "fundamental_dataset_ready": False,
        "oos_fundamental_predictions_ready": False,
        "market_pre_race_authority_ready": False,
        "same_race_alignment_structure_ready": (
            bool(records) and all(r["structural_race_check_passed"] for r in records)
        ),
        "combination_fit_ready": False,
        "independent_validation_ready": False,
        "economic_ev_ready": False,
        "2025_lockbox_used_for_tuning": False,
        "notes": [
            "This is an input/protocol gate, not a probability model.",
            "Original source bytes, publication clocks and OOS provenance are not re-attested.",
            "Do not set alpha/beta or import terminal historical odds as executable.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = inspect_benter_readiness(json.loads(args.bundle.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
