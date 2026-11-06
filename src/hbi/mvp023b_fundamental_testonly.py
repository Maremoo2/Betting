"""MVP-023B P1-D TEST_ONLY full-field L2 multinomial logit prototype.

NO authentic historical training; no promotion, no betting, no Benter fit.
Only a synthetic cohort with an exact TEST_ONLY marker can be passed here.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from .research_lab import digest, metrics

SCHEMA = "MVP023B_TEST_ONLY_SYNTHETIC_COHORT_V1"
REPORT = "MVP023B_TEST_ONLY_FUNDAMENTAL_PROTOTYPE_V1"
FEATURES = (
    "observed_win_rate",
    "observed_start_count",
    "days_since_latest_observed_start",
)
RID = re.compile(r"^RIKSTOTO:[A-Z0-9]+_NR_(20\d{2}-\d{2}-\d{2}):[1-9]\d*$")
FORBIDDEN = {"market", "odds", "closing_odds", "win_odds", "pwin", "pcol",
             "placing", "result", "label", "target_result", "future_result"}
TRAIN = range(2015, 2023)
VALIDATE = {2023, 2024}


def _validate_races(dataset: dict) -> tuple[list[dict], list[dict]]:
    if not isinstance(dataset, dict):
        raise TypeError("TEST_ONLY_DATASET_OBJECT_REQUIRED")
    if (
        dataset.get("schema") != SCHEMA
        or dataset.get("source_scope") != "TEST_ONLY_SYNTHETIC"
        or dataset.get("bet_authority") is not False
        or dataset.get("model_eligible") is not False
    ):
        raise ValueError("AUTHENTIC_MODEL_FIT_FORBIDDEN_SOURCE_NOT_TEST_ONLY")
    rows = dataset.get("races")
    if not isinstance(rows, list):
        raise TypeError("TEST_ONLY_RACE_LIST_REQUIRED")
    train, holdout, seen = [], [], set()
    for row in rows:
        if not isinstance(row, dict) or row.get("research_role") != "TEST_ONLY":
            raise ValueError("NON_SYNTHETIC_RACE_ENTRY_FORBIDDEN")
        rid = row.get("race_id")
        match = RID.fullmatch(str(rid))
        if match is None:
            raise ValueError("INVALID_PHYSICAL_RACE_ID")
        year = int(match.group(1)[:4])
        if year == 2025:
            raise ValueError("2025_CANDIDATE_LOCKBOX_UNOPENED")
        if year == 2026:
            raise ValueError("EXPOSED_2026_NOT_BLIND_OOS")
        if year not in TRAIN and year not in VALIDATE:
            raise ValueError("CHRONOLOGICAL_RESEARCH_ROLE_OUT_OF_SCOPE")
        if rid in seen:
            raise ValueError("DUPLICATE_OR_LEAKED_RACE_BETWEEN_PARTITIONS")
        seen.add(rid)
        if (
            row.get("result_complete") is not True
            or row.get("dead_heat") is not False
            or row.get("full_field_verified") is not True
            or row.get("model_eligible") is not False
        ):
            raise ValueError("FULL_FIELD_OR_OFFICIAL_SINGLE_WINNER_NOT_ADMITTED")
        active = row.get("active_runner_ids")
        field = row.get("runners")
        if not isinstance(active, list) or not isinstance(field, list) or len(active) < 2:
            raise ValueError("FULL_ACTIVE_FIELD_MISSING")
        ids = [h.get("runner_id") for h in field if isinstance(h, dict)]
        if len(ids) != len(field) or set(ids) != set(active) or len(ids) != len(set(ids)):
            raise ValueError("FULL_ACTIVE_FIELD_ROSTER_MISMATCH")
        if len(active) != len(set(active)) or row.get("winner_id") not in ids:
            raise ValueError("WINNER_OUTSIDE_ACTIVE_FIELD")
        for horse in field:
            if set(horse) != {"runner_id", "features"}:
                raise ValueError("UNREVIEWED_HORSE_RESULT_OR_MARKET_FIELD")
            data = horse["features"]
            if not isinstance(data, dict) or set(data) != set(FEATURES):
                raise ValueError("MISSING_OR_UNREVIEWED_FUNDAMENTAL_FEATURE")
            if FORBIDDEN & {key.lower() for key in data}:
                raise ValueError("MARKET_OR_RESULT_IN_FUNDAMENTAL_INPUT")
            if any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in data.values()):
                raise ValueError("MISSING_FUNDAMENTAL_VALUE_CANNOT_BECOME_ZERO")
        (train if year in TRAIN else holdout).append(row)
    if not train:
        raise ValueError("NO_REGISTERED_TEST_ONLY_2015_2022_DEVELOPMENT")
    if not holdout:
        raise ValueError("NO_REGISTERED_TEST_ONLY_2023_2024_VALIDATION")
    return sorted(train, key=lambda r: r["race_id"]), sorted(
        holdout, key=lambda r: r["race_id"],
    )


def _distribution(row: dict, weights: list[float]) -> dict[str, float]:
    logits = [sum(weights[i] * horse["features"][key]
                  for i, key in enumerate(FEATURES))
              for horse in row["runners"]]
    largest = max(logits)
    exponents = [math.exp(value - largest) for value in logits]
    total = sum(exponents)
    probabilities = [v / total for v in exponents]
    if any(not math.isfinite(p) or p <= 0 for p in probabilities):
        raise ValueError("INVALID_TEST_ONLY_SOFTMAX")
    return {r["runner_id"]: p for r, p in zip(
        row["runners"], probabilities, strict=True
    )}


def _replay_metrics(rows: list[dict], weights: list[float] | None) -> dict:
    scored = []
    for row in rows:
        probabilities = (
            _distribution(row, weights) if weights is not None
            else {h["runner_id"]: 1 / len(row["runners"]) for h in row["runners"]}
        )
        scored.append({
            "race_id": row["race_id"], "winner_id": row["winner_id"],
            "runners": [
                {"runner_id": h["runner_id"],
                 "model_probability": probabilities[h["runner_id"]]}
                for h in row["runners"]
            ],
        })
    return metrics(scored, "model_probability")


def fit_test_only(dataset: dict, *, epochs: int = 160,
                  learning_rate: float = 0.08, l2: float = 0.1) -> dict:
    train, evaluation = _validate_races(dataset)
    if (type(epochs) is not int or not 1 <= epochs <= 2000
            or type(learning_rate) not in (int, float)
            or not 0 < learning_rate <= 0.2
            or type(l2) not in (int, float) or not 0 <= l2 <= 5):
        raise ValueError("UNREGISTERED_REGULARIZATION_OR_FIT_HYPERPARAMETER")
    weights = [0.0] * len(FEATURES)
    # Deterministic, full-batch L2 regularized conditional multinomial logit.
    # Only TEST_ONLY synthetic labels participate in gradient fitting.
    for _ in range(epochs):
        gradient = [0.0] * len(FEATURES)
        for race in train:
            probabilities = _distribution(race, weights)
            for horse in race["runners"]:
                deviation = probabilities[horse["runner_id"]] - (
                    horse["runner_id"] == race["winner_id"]
                )
                for j, key in enumerate(FEATURES):
                    gradient[j] += deviation * horse["features"][key] / len(train)
        weights = [
            w - learning_rate * (gradient[j] + l2 * w)
            for j, w in enumerate(weights)
        ]
        if any(not math.isfinite(w) for w in weights):
            raise ValueError("NONFINITE_TEST_ONLY_COEFFICIENT")
    fit_spec = {
        "algorithm": "L2_CONDITIONAL_MULTINOMIAL_LOGIT_TEST_ONLY",
        "features": FEATURES, "epochs": epochs, "learning_rate": learning_rate,
        "l2": l2, "training_race_ids": [r["race_id"] for r in train],
        "model_weights": dict(zip(FEATURES, weights, strict=True)),
        "input_dataset_sha256": digest(dataset),
        "seed": "NOT_NEEDED_DETERMINISTIC_BATCH",
    }
    evaluations = {}
    for year in sorted(VALIDATE):
        selected = [r for r in evaluation if r["race_id"].split("_NR_")[1][:4] == str(year)]
        evaluations[str(year)] = {
            "role": ("INTERNAL_VALIDATION_2023" if year == 2023
                     else "CHALLENGER_VALIDATION_2024"),
            "fundamental_test_only": _replay_metrics(selected, weights),
            "uniform_test_only": _replay_metrics(selected, None),
            "normalized_win_market": None,
            "champion": None, "benter_combined": None,
        }
    return {
        "schema": REPORT, "evidence_scope": "TEST_ONLY_SYNTHETIC",
        "bet_authority": False, "production_pit_verified": False,
        "fitted_test_only_estimator": True, "fitted_authentic_model": False,
        "fundamental_fit_ready": False, "benter_fit_ready": False,
        "model_promotion": False, "economic_ev_ready": False,
        "2025_lockbox_opened": False,
        "model_specification": fit_spec,
        "model_artifact_sha256": digest(fit_spec),
        "validation": evaluations,
        "limitations": [
            "All labels and features are synthetic; no empirical performance claim.",
            "2023 and 2024 examples are not genuine untouched OOS racing observations.",
            "No authentic verified historic feature sources or independent horse identities admitted.",
            "No pre-race executable WIN odds, Benter weights, EV or production state mutation.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-only-synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = fit_test_only(json.loads(args.test_only_synthetic.read_bytes()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        file.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
