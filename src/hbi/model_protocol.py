"""Chronological dataset controls and strictly separate prediction scoring."""
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from .evaluation import calibration_bins, log_loss, multiclass_brier
from .model_dataset import candidate


def splits(protocol):
    if protocol["schema"] != "HBI_CHRONOLOGICAL_PROTOCOL_V1":
        raise ValueError("UNKNOWN_PROTOCOL")
    previous = None
    result = {}
    for name in ("train", "validation", "test"):
        start, end = map(date.fromisoformat, protocol[name])
        if start > end or (previous and start <= previous):
            raise ValueError("SPLITS_MUST_BE_CHRONOLOGICAL_AND_DISJOINT")
        result[name] = (start, end)
        previous = end
    return result


def score(predicted, winners):
    """Validated full-field scoring primitive; not a prediction generator."""
    if not predicted or set(predicted) != set(winners):
        raise ValueError("PREDICTION_COHORT_MISMATCH")
    loss, brier, uniform_loss, uniform_brier, calibration = [], [], [], [], []
    for race, (field, winner) in winners.items():
        probabilities = predicted[race]
        if (set(probabilities) != set(field) or len(field) < 2 or winner not in field
                or any(isinstance(p, bool) or not isinstance(p, (float, int))
                    or not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values())
                or not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-9, rel_tol=0)):
            raise ValueError("INVALID_FULL_FIELD_PROBABILITIES")
        loss.append(log_loss(probabilities, winner))
        brier.append(multiclass_brier(probabilities, winner))
        baseline = dict.fromkeys(field, 1 / len(field))
        uniform_loss.append(log_loss(baseline, winner))
        uniform_brier.append(multiclass_brier(baseline, winner))
        calibration.extend((p, horse == winner) for horse, p in probabilities.items())
    return {"races": len(loss), "log_loss": sum(loss) / len(loss),
        "brier_sum_per_race": sum(brier) / len(brier), "calibration": calibration_bins(calibration),
        "uniform_baseline": {"log_loss": sum(uniform_loss) / len(loss),
            "brier_sum_per_race": sum(uniform_brier) / len(brier)}}


def audit(directory, protocol_path):
    directory = Path(directory)
    raw = (directory / "dataset.jsonl").read_bytes()
    manifest = json.loads((directory / "model-readiness.json").read_text())
    if hashlib.sha256(raw).hexdigest() != manifest["dataset_sha256"]:
        raise ValueError("DATASET_HASH_MISMATCH")
    protocol_raw = Path(protocol_path).read_bytes()
    boundaries = splits(json.loads(protocol_raw))
    rows = [json.loads(line) for line in raw.splitlines()]
    if len({r["race_id"] for r in rows}) != len(rows):
        raise ValueError("DUPLICATE_RACE")
    observations = []
    for row in rows:
        day = date.fromisoformat(row["date"])
        partition = next((n for n, (start, end) in boundaries.items() if start <= day <= end), "EXCLUDED")
        view = candidate(row)
        observations.append({"race_id": row["race_id"], "country": row["country"],
            "partition": partition, "active_runners": len(view["inputs"]),
            "data_ready": view["data_ready"], "reasons": view["exclusion_reasons"]})
    return {"schema": "HBI_MODEL_AUDIT_V1", "dataset_sha256": manifest["dataset_sha256"],
        "dataset_id": manifest["dataset_id"], "protocol_sha256": hashlib.sha256(protocol_raw).hexdigest(),
        "races": len(rows), "data_ready": sum(x["data_ready"] for x in observations),
        "empty_partitions": [name for name in boundaries if not any(x["partition"] == name for x in observations)],
        "by_country": {country: {"races": sum(x["country"] == country for x in observations),
            "partitions": dict(Counter(x["partition"] for x in observations if x["country"] == country))}
            for country in ("NO", "SE")}, "observations": observations,
        "metrics": None, "evaluation_status": "NOT_RUN_NO_VALIDATED_MODEL_OR_PREDICTIONS",
        "training_performed": False, "model_admission": False,
        "limitations": ["HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "NO_EMPIRICAL_PREDICTION_CLAIM",
            "SCORING_PRIMITIVE_TESTED_ONLY; MODEL_ARTIFACT_PROVENANCE_GATE_REQUIRED_BEFORE_EMPIRICAL_EVALUATION"]}


def cli(args):
    try:
        report = audit(args.dataset_dir, args.protocol)
        with Path(args.output).open("x") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}, indent=2))
