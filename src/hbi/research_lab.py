"""Read-only research evaluation. No decision, stake or promotion authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result


def freeze(path, value):
    """Exclusive creation: never silently revise a registration or result."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def register(plan, registry, output):
    ids = {h["id"] for h in registry["hypotheses"]}
    if plan["hypothesis_id"] not in ids:
        raise ValueError("Unknown hypothesis")
    for key in ("experiment_id", "git_commit", "features", "model", "hyperparameters",
                "dataset_sha256", "primary_metrics", "exclusions", "slices"):
        if key not in plan:
            raise ValueError(f"Missing registration field: {key}")
    train = [timestamp(v) for v in plan["train_period"]]
    test = [timestamp(v) for v in plan["test_period"]]
    cutoff = timestamp(plan["data_cutoff"])
    if not (train[0] <= train[1] < test[0] <= test[1] <= cutoff):
        raise ValueError("Overlapping or invalid chronological split")
    role = plan["test_role"]
    bounds = registry["data_policy"].get(role)
    if role not in {"development", "internal_validation", "challenger_validation"}:
        raise ValueError("Lockbox/future access requires a separate exposure audit")
    if not bounds or test[0].year < bounds[0] or test[1].year > bounds[1]:
        raise ValueError("Test period outside registered data role")
    if train[0].year < 2015 or train[1].year > 2022:
        raise ValueError("Training is restricted to development years")
    artifact = {"schema_version": "HBI_EXPERIMENT_REGISTRATION_V1", "plan": plan,
                "plan_sha256": digest(plan), "registry_sha256": digest(registry),
                "registered_at": datetime.now().astimezone().isoformat(),
                "historical_not_prospective": True, "promotion_enabled": False}
    freeze(output, artifact)
    return artifact


def audit_race(race, plan):
    start = timestamp(race["start_at"])
    test = [timestamp(v) for v in plan["test_period"]]
    if not test[0] <= start <= test[1]:
        raise ValueError("Race outside test period")
    ids = race["active_runner_ids"]
    rows = race["runners"]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Invalid active roster")
    if len(rows) != len(ids) or {r["runner_id"] for r in rows} != set(ids):
        raise ValueError("FULL_FIELD_ONLY")
    if race.get("result_complete") is not True or race.get("winner_id") not in ids:
        raise ValueError("Missing verified single-winner result; dead heats excluded")
    if race.get("identity_verified") is not True or race.get("dead_heat", False):
        raise ValueError("Result identity/dead-heat gate")
    for row in rows:
        if row.get("identity_verified") is not True:
            raise ValueError("Runner identity unverified")
        for feature in plan["features"]:
            observation = row["features"][feature]
            if observation["value"] is None or not observation.get("source_sha256"):
                raise ValueError("Missing feature/provenance")
            if not (timestamp(observation["event_at"]) < start
                    and timestamp(observation["available_at"]) < start):
                raise ValueError("PIT violation")
        if timestamp(row["prediction_at"]) >= start:
            raise ValueError("Late prediction")
    for column in ("model_probability", "market_probability"):
        values = [r[column] for r in rows]
        if any(isinstance(v, bool) or not math.isfinite(v) or not 0 < v <= 1
               for v in values) or abs(sum(values) - 1) > 1e-6:
            raise ValueError(f"Invalid full-field distribution: {column}")
    if race.get("market_snapshot_type") != "PRE_RACE_VERIFIED":
        raise ValueError("Terminal historical market is not PIT evidence")
    if timestamp(race["market_available_at"]) >= start:
        raise ValueError("Late market")
    return rows


def metrics(races, column):
    losses, briers, bins = [], [], [[] for _ in range(10)]
    for race in races:
        for row in race["runners"]:
            p = row[column]
            y = int(row["runner_id"] == race["winner_id"])
            bins[min(int(p * 10), 9)].append((p, y))
        winner = next(r for r in race["runners"] if r["runner_id"] == race["winner_id"])
        losses.append(-math.log(winner[column]))
        briers.append(sum((r[column] - int(r["runner_id"] == race["winner_id"])) ** 2
                          for r in race["runners"]))
    return {"races": len(races), "log_loss": sum(losses) / len(losses) if losses else None,
            "brier": sum(briers) / len(briers) if briers else None,
            "calibration": [{"bin": i, "n": len(b),
                             "mean_probability": sum(p for p, _ in b) / len(b) if b else None,
                             "observed_rate": sum(y for _, y in b) / len(b) if b else None}
                            for i, b in enumerate(bins)]}


def evaluate(registration, dataset, output):
    plan = registration["plan"]
    if digest(plan) != registration["plan_sha256"]:
        raise ValueError("Registration checksum mismatch")
    if digest(dataset) != plan["dataset_sha256"]:
        raise ValueError("Dataset checksum mismatch")
    accepted, rejected, seen = [], [], set()
    for race in dataset:
        race_id = race["race_id"]
        if race_id in seen:
            raise ValueError("Duplicate race ID")
        seen.add(race_id)
        try:
            audit_race(race, plan)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            rejected.append({"race_id": race_id, "reason": str(error)})
        else:
            accepted.append(race)
    model = metrics(accepted, "model_probability")
    market = metrics(accepted, "market_probability")
    slices = {}
    for key in plan["slices"]:
        for value in sorted({str(r.get(key, "UNKNOWN")) for r in accepted}):
            group = [r for r in accepted if str(r.get(key, "UNKNOWN")) == value]
            slices[f"{key}={value}"] = {"model": metrics(group, "model_probability"),
                                       "market": metrics(group, "market_probability")}
    report = {"schema_version": "HBI_EXPERIMENT_RESULT_V1",
              "experiment_id": plan["experiment_id"], "registration_sha256": digest(registration),
              "dataset_sha256": digest(dataset), "accepted_race_ids": [r["race_id"] for r in accepted],
              "rejected": rejected, "model": model, "market": market, "slices": slices,
              "paired_log_loss_difference": (model["log_loss"] - market["log_loss"]
                                             if accepted else None),
              "economic_result": "NOT_ESTABLISHED_PRICE_AND_EXECUTION_AUDIT_REQUIRED",
              "promotion_enabled": False, "status": "EVALUATED" if accepted else "BLOCKED_NO_PIT_DATA"}
    freeze(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["register", "evaluate"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("research/registry.json"))
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if args.command == "register":
        register(data, json.loads(args.registry.read_text(encoding="utf-8")), args.output)
    else:
        if not args.dataset:
            parser.error("evaluate requires --dataset")
        evaluate(data, json.loads(args.dataset.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()

