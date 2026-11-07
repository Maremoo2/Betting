"""BENCHMARK-002 offline retrospective research. Requires NumPy; no runtime integration."""
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np

from hbi.evaluation import calibration_bins, log_loss, multiclass_brier

SCOPE = "RESEARCH_RETROSPECTIVE"
RIDGE = 0.03
VARIANTS = {"F0": (0,), "F1_5": (0, 1, 4), "F1_10": (0, 2, 4),
            "F1_EXP": (0, 3, 4), "FORM": (0, 1, 2, 3, 4),
            "FORM_CLASS_PROXY": (0, 1, 2, 3, 4, 5, 6),
            "CHALLENGER_V2": (0, 1, 2, 3, 4, 5, 6, 7, 8)}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source(path, expected):
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError(f"Source hash mismatch: {path.name}")
    return raw


def lines(raw):
    return map(json.loads, raw.splitlines())


def historical_day(value):
    day = date.fromisoformat(value)
    if not 2015 <= day.year <= 2024:
        raise ValueError("Outside retrospective scope")
    return day


def load_export(root):
    manifest = json.loads((root / "EXPORT_MANIFEST.json").read_bytes())["files"]
    for filename in ("events.jsonl", "targets.jsonl"):
        yield lines(source(root / filename, manifest[filename]["sha256"]))


def finite_time(row):
    value = row["race_time"]["value"]
    return value if value is not None and row["gallop_status"] is not True else None


def purse_proxy(workspace, row):
    path = (workspace / row["source_id"]).resolve()
    base = workspace / "Betting" / "research-local" / "archive-2015-2025" / "full" / "raw-results"
    if path.parent != base or len(path.stem) != 64 or path.suffix != ".json":
        raise ValueError("Outside source allowlist")
    raw = json.loads(source(path, row["source_hash"]))
    result = raw["body"]["result"]
    if result["startTime"][:10] != row["race_date"]:
        raise ValueError("Raw result date mismatch")
    prizes = [entry.get("prize") for entry in result["results"] if entry["place"] == 1]
    if len(prizes) == 1 and type(prizes[0]) in (int, float) and prizes[0] > 0:
        return math.log1p(prizes[0])
    return None


def feature(history, rating, day, n):
    prior = 1 / n
    wins = sum(row[1] for row in history)
    career = (wins + 6 * prior) / (len(history) + 6)
    clean = [(row[0], row[2]) for row in history if row[2] is not None]

    def recent(k):
        values = [row[2] for row in history[-k:] if row[2] is not None]
        return sum(values) / (len(values) + 3)

    weights = [2 ** (-(day - when).days / 90) for when, _ in clean]
    exp = sum(w * row[1] for w, row in zip(weights, clean)) / (3 + sum(weights))
    layoff = math.log1p((day - history[-1][0]).days) if history else 0
    class_rows = [(row[2], row[3]) for row in history[-10:] if row[3] is not None]
    level = sum(purse - 9 for _, purse in class_rows) / (3 + len(class_rows))
    interaction = sum(z * (purse - 9) for z, purse in class_rows if z is not None)
    faced = [row[4] for row in history[-10:]]
    return [math.log(career), recent(5), recent(10), exp, layoff,
            level, interaction / (3 + len(class_rows)), rating, sum(faced) / (3 + len(faced))]


def race_softmax(values):
    exp = np.exp(np.asarray(values) - max(values))
    return exp / exp.sum()


def admission(row):
    """Historical admission deliberately grants no model/PIT authority."""
    if not row["record_eligible"]:
        return "MISSING", row["exclusion_reasons"]
    if not row["availability_evidence"]:
        return "RETROSPECTIVE_ONLY", ["EXACT_VERSION_AVAILABILITY_MISSING"]
    return "PIT_UNPROVEN", ["TARGET_SPECIFIC_CERTIFICATION_REQUIRED"]


def build_races(workspace, events, targets):
    fields = defaultdict(list)
    coverage = Counter()
    diagnostics = Counter()
    for row in events:
        year = historical_day(row["race_date"]).year
        status, reasons = admission(row)
        namespace = row["source_url"].split("/")[2] if row.get("source_url") else "UNKNOWN"
        coverage[(year, row["track"], row["country"] or "UNKNOWN", namespace, status)] += 1
        diagnostics.update(reasons)
        for key in ("published_at", "revised_at", "available_at", "availability_evidence",
                    "event_time_verified", "source_revision", "driver_id", "trainer_id"):
            if row.get(key):
                diagnostics["PRESENT_" + key] += 1
        if row.get("archived_at"):
            stamp = datetime.fromisoformat(row["archived_at"])
            if stamp.date() > historical_day(row["race_date"]):
                diagnostics["RECEIPT_DATE_AFTER_EVENT_DATE"] += 1
        if row["scratched"] is False:
            fields[row["race_id"]].append(row)

    histories, ratings = defaultdict(list), defaultdict(float)
    result = []
    purse_count = 0
    by_day = defaultdict(list)
    for target in targets:
        by_day[historical_day(target["day"])].append(target)

    for day, daily in sorted(by_day.items()):
        updates = []
        seen = set()
        for target in sorted(daily, key=lambda target: target["race_id"]):
            rid = target["race_id"]
            if rid in seen:
                raise ValueError("Duplicate target race")
            seen.add(rid)
            field = fields.get(rid, [])
            horses = [row["horse_id"] for row in field]
            selections = [row["start_number"] for row in field]
            if (len(horses) < 2 or len(set(horses)) != len(horses)
                    or len(set(selections)) != len(selections)
                    or set(horses) != set(target["horse_ids"])
                    or len(target["horse_ids"]) != len(horses)
                    or not all(row["record_eligible"] and row["horse_id"]
                               and row["race_date"] == day.isoformat()
                               and row["identity_status"] == "EXACT_SOURCE_NATIVE_REGISTRATION"
                               and row["result_version"] == row["source_body_hash"] for row in field)
                    or len({row["result_version"] for row in field}) != 1):
                diagnostics["FULL_FIELD_REJECTED"] += 1
                continue
            winners = [i for i, row in enumerate(field) if row["winner"]]
            if len(winners) != 1 or any(row["dead_heat"] for row in field):
                diagnostics["DEAD_HEAT_OR_WINNER_UNRESOLVED"] += 1
                continue
            winner = winners[0]
            values = [finite_time(row) for row in field]
            clean = [v for v in values if v is not None]
            mean = sum(clean) / len(clean) if clean else 0
            purse = purse_proxy(workspace, field[winner])
            purse_count += purse is not None
            pre_ratings = [ratings[horse] for horse in horses]
            expectation = race_softmax(pre_ratings)
            features = [feature(histories[horse], rating, day, len(horses))
                        for horse, rating in zip(horses, pre_ratings)]
            for i, horse in enumerate(horses):
                relative = max(-4, min(4, mean - values[i])) if values[i] is not None else None
                faced = (sum(pre_ratings) - pre_ratings[i]) / (len(horses) - 1)
                won = i == winner
                updates.append((horse, (day, won, relative, purse, faced), 0.15 * (won - expectation[i])))
            result.append({"id": rid, "day": day, "track": target["track"], "selections": selections,
                           "x": features, "winner": winner})
        # No outcome enters another race on the same day, including rating or class state.
        for horse, history, change in updates:
            histories[horse].append(history)
            ratings[horse] += change

    diagnostics["PRIOR_PURSE_PROXY_AVAILABLE_RACES"] = purse_count
    return result, coverage, diagnostics


def fit(fields, columns):
    lengths = [len(r["x"]) for r in fields]
    starts = np.r_[0, np.cumsum(lengths)[:-1]]
    x = np.concatenate([np.array(r["x"])[:, columns] for r in fields])
    scale = np.maximum(x.std(axis=0), 1e-6)
    x = x / scale
    winners = starts + [r["winner"] for r in fields]
    beta = np.zeros(len(columns))
    # L2-regularized race-wise likelihood. A global step bound from centered X.
    x -= np.repeat(np.add.reduceat(x, starts, axis=0) / np.array(lengths)[:, None], lengths, axis=0)
    step = 1 / (float(np.sum(x * x)) / len(fields) + RIDGE)
    for _ in range(240):
        logits = x @ beta
        exp = np.exp(logits - np.repeat(np.maximum.reduceat(logits, starts), lengths))
        p = exp / np.repeat(np.add.reduceat(exp, starts), lengths)
        p[winners] -= 1
        beta -= step * (x.T @ p / len(fields) + RIDGE * beta)
    return beta / scale


def predict(race, columns, beta):
    return race_softmax(np.array(race["x"])[:, columns] @ beta)


def freeze_model_rows(races):
    for year in (2022, 2023, 2024):
        train = [r for r in races if r["day"].year < year - 1]
        calibration = [r for r in races if r["day"].year == year - 1]
        test = [r for r in races if r["day"].year == year]
        models = {key: fit(train, cols) for key, cols in VARIANTS.items()}
        yield year, train, calibration, test, models


def load_legacy(root, synthesis):
    for item in json.loads(synthesis.read_bytes()):
        year = item["year"]
        if year not in range(2018, 2025):
            raise ValueError("Outside legacy scope")
        if year < 2021:
            continue
        folder = Path(item["source"]["path"].replace(chr(92), "/")).parent.name
        path, = (root / folder).glob(f"*{year}*CUMULATIVE_FORWARD_LEDGER.jsonl")
        for row in lines(path.read_bytes()):
            if row["primary"]:
                yield row


def distributions(row, models, legacy):
    selections = row["selections"]
    winner = selections[row["winner"]]
    if legacy is None or legacy["winner"] != winner:
        return None
    probs = {m: legacy["models"][m]["probabilities"] for m in ("M0", "CALIBRATED_MARKET", "COMBINED")}
    if any(set(p) != set(selections) or any(v <= 0 for v in p.values()) for p in probs.values()):
        return None
    for model, beta in models.items():
        probs[model] = dict(zip(selections, predict(row, VARIANTS[model], beta)))
    probs["UNIFORM"] = dict.fromkeys(selections, 1 / len(selections))
    return {"race_id": row["id"], "day": row["day"].isoformat(), "track": row["track"],
            "winner": winner, "scope": SCOPE, "probabilities": probs}


def combo_inputs(rows):
    for r in rows:
        p = r["probabilities"]
        keys = list(p["M0"])
        yield {"x": [[math.log(p["M0"][k]), math.log(p["CHALLENGER_V2"][k])] for k in keys],
               "winner": keys.index(r["winner"])}


def evaluate(rows):
    scores, calibration = {}, {}
    for name in rows[0]["probabilities"]:
        ll, brier, points = [], [], []
        for row in rows:
            p, winner = row["probabilities"][name], row["winner"]
            ll.append(log_loss(p, winner))
            brier.append(multiclass_brier(p, winner))
            points.extend((v, k == winner) for k, v in p.items())
        scores[name] = {"log_loss": float(np.mean(ll)), "brier": float(np.mean(brier))}
        calibration[name] = calibration_bins(points)
    return scores, calibration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    root = workspace / "outputs"
    export = root / "HIST_FORM_001" / "EXPORT_RELEASE"
    events, targets = load_export(export)
    races, coverage, diagnostics = build_races(workspace, events, targets)
    legacy = {r["race_id"]: r for r in load_legacy(
        root, root / "HBI_POST_2024_RESEARCH_SYNTHESIS_V1" / "ORIGINAL_ANNUAL_RESULTS_UNCHANGED.json")}
    report = {"scope": SCOPE, "model_eligible": False, "bet_authority": False,
              "model_version": "BENCHMARK002_CHALLENGER_V2_RETRO_V1",
              "export_manifest_sha256": sha((export / "EXPORT_MANIFEST.json").read_bytes()),
              "coverage": [[*k, count] for k, count in sorted(coverage.items())],
              "diagnostics": diagnostics, "folds": []}
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "predictions.jsonl").open("x", encoding="utf-8") as stream:
        for year, train, cal, test, models in freeze_model_rows(races):
            paired_cal = [p for r in cal if (p := distributions(r, models, legacy.get(r["id"])))]
            paired = [p for r in test if (p := distributions(r, models, legacy.get(r["id"])))]
            beta = fit(list(combo_inputs(paired_cal)), (0, 1))
            for row, combo in zip(paired, combo_inputs(paired)):
                p = row["probabilities"]
                p["V2_MARKET_COMBO"] = dict(zip(p["M0"], predict(combo, (0, 1), beta)))
                stream.write(json.dumps(row, allow_nan=False) + "\n")
            scores, bins = evaluate(paired)
            report["folds"].append({"test_year": year, "train_n": len(train), "cal_n": len(paired_cal),
                                    "full_test_n": len(test), "n": len(paired), "scores": scores,
                                    "calibration": bins, "combo_beta": beta.tolist(),
                                    "coefficients": {k: v.tolist() for k, v in models.items()}})
    (args.output / "benchmark.json").write_text(json.dumps(report, indent=2, allow_nan=False),
                                                encoding="utf-8")


if __name__ == "__main__":
    main()
