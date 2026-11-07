"""Summarize frozen retrospective test rows. No pricing or settlement simulation."""
import argparse
import csv
import json
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
    ci = np.quantile(replicates, [0.025, 0.975], axis=0)
    p = (1 + np.sum(abs(replicates[:, 0] - delta[0]) >= abs(delta[0]))) / (1 + len(draws))
    return {"races": int(n.sum()), "weeks": len(n), "delta_ll": float(delta[0]),
            "ll_lo": float(ci[0, 0]), "ll_hi": float(ci[1, 0]), "delta_brier": float(delta[1]),
            "brier_lo": float(ci[0, 1]), "brier_hi": float(ci[1, 1]), "bootstrap_p": float(p)}


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
    ids = set()
    for row in rows:
        assert row["scope"] == "RESEARCH_RETROSPECTIVE" and row["race_id"] not in ids
        ids.add(row["race_id"])
        expected = set(row["probabilities"]["M0"])
        for p in row["probabilities"].values():
            assert set(p) == expected and all(0 < v <= 1 for v in p.values())
            assert abs(sum(p.values()) - 1) < 1e-9
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
    for i, row in enumerate(sorted(ablation, key=lambda r: r["bootstrap_p"])):
        previous = min(1, max(previous, (len(ablation) - i) * row["bootstrap_p"]))
        row["holm_p"] = previous
    with (path / "ABLATION_RESULTS.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ablation[0]))
        writer.writeheader()
        writer.writerows(ablation)
        writer.writerows({"feature": key, "status": "NOT_TESTABLE"} for key in UNMEASURED)
    with (path / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump({"ranking": ranking, "favorite": {m: favorite(rows, m) for m in
                   ("CHALLENGER_V2", "V2_MARKET_COMBO", "CALIBRATED_MARKET")},
                   "economic": "ECONOMIC_TEST_NOT_QUALIFIED"}, stream, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    summarize(parser.parse_args().run)
