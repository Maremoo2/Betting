"""Summarize frozen retrospective test rows. No pricing or settlement simulation."""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from hbi.evaluation import calibration_bins, log_loss, multiclass_brier

ABLATIONS = [
    ("F1_LAST_5", "F1_5", "F0"),
    ("F1_LAST_10", "F1_10", "F0"),
    ("F1_EXP_90D", "F1_EXP", "F0"),
    ("F1_ALL", "FORM", "F0"),
    ("F2_PRIOR_PURSE_PROXY", "FORM_CLASS_PROXY", "FORM"),
    ("F3_OPPONENT_RATING", "CHALLENGER_V2", "FORM_CLASS_PROXY"),
    ("MARKET_COMBINATION", "V2_MARKET_COMBO", "CALIBRATED_MARKET"),
    ("MARKET_COMBINATION_SAME_CALIBRATION", "V2_MARKET_COMBO", "CALIBRATED_WIN_FOLD"),
]
UNMEASURED = ("F2_EXPLICIT_CLASS", "F4_CURRENT_RACE_CONDITIONS", "F5_DRIVER_TRAINER_EQUIPMENT",
              "DIRECT_MEETINGS")


def validate_frozen_rows(rows):
    """Research scoring contract, never a PIT or untouched-holdout certificate."""
    if not rows:
        raise ValueError("FROZEN_COHORT_EMPTY")
    ids, model_names, runners = set(), set(rows[0]["probabilities"]), 0
    for row in rows:
        if row.get("scope") != "RESEARCH_RETROSPECTIVE" or row["race_id"] in ids:
            raise ValueError("FROZEN_COHORT_SCOPE_OR_DUPLICATE")
        ids.add(row["race_id"])
        if not 2015 <= date.fromisoformat(row["day"]).year <= 2024:
            raise ValueError("FROZEN_COHORT_OUTSIDE_RESEARCH_SCOPE")
        if set(row["probabilities"]) != model_names:
            raise ValueError("FROZEN_COHORT_MODEL_SET_CONFLICT")
        field = set(row["probabilities"]["M0"])
        if len(field) < 2 or row["winner"] not in field:
            raise ValueError("FROZEN_COHORT_FIELD_OR_WINNER_INVALID")
        for distribution in row["probabilities"].values():
            if (set(distribution) != field or any(type(v) not in (int, float)
                    or not math.isfinite(v) or not 0 < v <= 1 for v in distribution.values())
                    or not math.isclose(math.fsum(distribution.values()), 1, rel_tol=0, abs_tol=1e-9)):
                raise ValueError("FROZEN_COHORT_DISTRIBUTION_INVALID")
        runners += len(field)
    return {"physical_races": len(ids), "runner_observations": runners,
            "full_fields_verified": len(ids), "probability_sums_verified": True,
            "pit_certified_by_this_check": False,
            "holdout_status": "ALREADY_EXAMINED_RETROSPECTIVE_NOT_UNTOUCHED"}


def paired(rows, first, second):
    groups = defaultdict(list)
    for row in rows:
        p, win = row["probabilities"], row["winner"]
        groups[date.fromisoformat(row["day"]).isocalendar()[:2]].append([
            log_loss(p[first], win) - log_loss(p[second], win),
            multiclass_brier(p[first], win) - multiclass_brier(p[second], win),
        ])
    n = np.array([len(group) for group in groups.values()])
    totals = np.array([np.sum(group, axis=0) for group in groups.values()])
    delta = totals.sum(axis=0) / n.sum()
    draws = np.random.default_rng(20261107).integers(len(n), size=(4000, len(n)))
    replicates = totals[draws].sum(axis=1) / n[draws].sum(axis=1)[:, None]
    ci = np.quantile(replicates, [0.025, 0.975], axis=0) if len(n) >= 2 else None
    p = (1 + np.sum(abs(replicates[:, 0] - delta[0]) >= abs(delta[0]))) / (1 + len(draws))
    return {"races": int(n.sum()), "weeks": len(n), "delta_ll": float(delta[0]),
            "ll_lo": float(ci[0, 0]) if ci is not None else None, "ll_hi": float(ci[1, 0]) if ci is not None else None, "delta_brier": float(delta[1]),
            "brier_lo": float(ci[0, 1]) if ci is not None else None,
            "brier_hi": float(ci[1, 1]) if ci is not None else None, "bootstrap_p": float(p) if ci is not None else None,
            "uncertainty_scope": "WEEK_CLUSTER_METRIC_DIFFERENCE_NOT_HORSE_PWIN_INTERVAL",
            "uncertainty_status": "DESCRIPTIVE_ONLY" if ci is not None else "INSUFFICIENT_INDEPENDENT_CLUSTERS",
            "pwin_intervals_calibrated": False}


def favorite(rows, model):
    points, triggered = [], []
    for row in rows:
        p, market = row["probabilities"][model], row["probabilities"]["M0"]
        fav = max(market, key=lambda k: (market[k], k))
        winner = row["winner"]
        points.append((p[fav], fav == winner))
        if market[fav] - p[fav] >= 0.15:
            rivals = {k: q for k, q in market.items() if k != fav}
            pick = max(rivals, key=lambda k: (p[k] / market[k], k))
            triggered.append({"race_id": row["race_id"], "model_fav": p[fav], "market_fav": market[fav],
                              "fav_won": fav == winner, "single_hit": pick == winner,
                              "dutching_hit": winner in rivals})
    return {"calibration": calibration_bins(points, width=0.1), "n": len(triggered),
            "single_hits": sum(r["single_hit"] for r in triggered),
            "dutching_hits": sum(r["dutching_hit"] for r in triggered),
            "triggers": triggered}


def summarize(path):
    rows = [json.loads(line) for line in (path / "predictions.jsonl").read_bytes().splitlines()]
    coverage = validate_frozen_rows(rows)
    ranking = {}
    for model in rows[0]["probabilities"]:
        bins = calibration_bins([(p, selection == row["winner"]) for row in rows
                                 for selection, p in row["probabilities"][model].items()], width=0.1)
        ranking[model] = {
            "log_loss": float(np.mean([log_loss(r["probabilities"][model], r["winner"]) for r in rows])),
            "brier": float(np.mean([multiclass_brier(r["probabilities"][model], r["winner"]) for r in rows])),
            "ece": sum(b["n"] * abs(b["mean_predicted"] - b["observed_rate"]) for b in bins)
            / sum(b["n"] for b in bins),
            "calibration": bins,
            "vs_calibrated_terminal_win": paired(rows, model, "CALIBRATED_MARKET"),
        }
    ablation = [{"feature": feature, "with": model, "without": reference,
                 "status": "RETROSPECTIVE_ONLY", **paired(rows, model, reference)}
                for feature, model, reference in ABLATIONS]
    previous = 0
    for i, row in enumerate(sorted(ablation, key=lambda r: r["bootstrap_p"] if r["bootstrap_p"] is not None else float("inf"))):
        if row["bootstrap_p"] is None:
            row["holm_p"] = None
            continue
        previous = min(1, max(previous, (len(ablation) - i) * row["bootstrap_p"]))
        row["holm_p"] = previous
    with (path / "ABLATION_RESULTS.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ablation[0]))
        writer.writeheader()
        writer.writerows(ablation)
        writer.writerows({"feature": key, "status": "NOT_TESTABLE"} for key in UNMEASURED)
    with (path / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump({"coverage": coverage, "market_time_status": "TERMINAL_RETROSPECTIVE_NOT_PRESTART",
                   "pwin_interval_status": "NOT_CALIBRATED_NOT_PRODUCED", "ranking": ranking, "favorite": {m: favorite(rows, m) for m in
                   ("CHALLENGER_V2", "V2_MARKET_COMBO", "CALIBRATED_MARKET")},
                   "economic": "ECONOMIC_TEST_NOT_QUALIFIED"}, stream, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    summarize(parser.parse_args().run)
