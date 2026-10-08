"""User-frozen historical timing cohorts. Reads PRE only; no strategy tuning."""
from __future__ import annotations

from collections import Counter
from math import isclose
from pathlib import Path

from betting.v33 import POLICY_HASH, divergence

from .exports import csv_file, frozen_rows
from .extract import numeric, utc
from .transport import digest, write_json

TIMING_POLICY = {"version": "PRE_WINNER_TIMING_V1", "primary_max_seconds": 60,
                 "secondary_max_seconds": 300, "unknown": "FAIL_CLOSED",
                 "authority": "USER_CONFIRMED_2026-10-08", "prospective": False}
TIMING_POLICY_HASH = digest(TIMING_POLICY)


def cohort(skew):
    skew = numeric(skew)
    return ("PRIMARY" if skew <= TIMING_POLICY["primary_max_seconds"] else "SECONDARY"
            if skew <= TIMING_POLICY["secondary_max_seconds"] else "EXCLUDE_DIAGNOSTIC")


def analyze(rows):
    pools, products, signals, races, observations = Counter(), Counter(), Counter(), {}, []
    for row in rows:
        if row["policy_hash"] != POLICY_HASH:
            raise ValueError("frozen signal policy mismatch")
        field = set(row["active_field"])
        if set(row["pWIN"]) != field or not isclose(sum(row["pWIN"].values()), 1, abs_tol=1e-9):
            raise ValueError("invalid full-field WIN normalization")
        for pool_id, pool in row["collective"].items():
            if set(pool["pCOL"]) != field or not isclose(sum(pool["pCOL"].values()), 1, abs_tol=1e-9):
                raise ValueError("invalid full-field collective normalization")
            actual_skew = max(abs((utc(row["runners"][n]["win_updated_at"]) -
                                   utc(pool["updated_at"])).total_seconds()) for n in field)
            if not isclose(actual_skew, pool["win_skew_seconds"], abs_tol=1e-6):
                raise ValueError("stored timing skew mismatch")
            group = cohort(actual_skew)
            pools[group] += 1
            products[pool["product"]] += 1
            races.setdefault(row["race_id"], set()).add(group)
            for n in row["active_field"]:
                calculated = divergence(pool["pCOL"][n], row["pWIN"][n])
                signals[group + ":" + calculated["signal"]] += 1
                observations.append([row["race_id"], pool_id, pool["product"], pool["leg"], n,
                                     actual_skew, group, calculated["pWIN"], calculated["pCOL"],
                                     calculated["delta"], calculated["ratio"], calculated["signal"]])
    report = {"timing_policy": TIMING_POLICY, "timing_policy_hash": TIMING_POLICY_HASH,
              "signal_policy_hash": POLICY_HASH, "race_count": len(rows),
              "country_races": dict(Counter(row["country"] for row in rows)),
              "pool_count": sum(pools.values()), "pool_cohorts": dict(pools),
              "product_pools": dict(products), "signal_counts_by_cohort": dict(signals),
              "races_with_any_primary_pool": sum("PRIMARY" in groups for groups in races.values()),
              "races_with_all_pools_primary": sum(groups == {"PRIMARY"} for groups in races.values()),
              "runner_pool_observations": len(observations), "post_read": False,
              "prospective": False, "full_PRE_WINNER_v1_protocol": "NOT_CONFIGURED",
              "moderate_extreme_thresholds": "NOT_CONFIGURED", "performance_claims": False}
    return report, observations


def run(root):
    root = Path(root)
    rows, freeze = frozen_rows(root)
    destination = root / "integrity"
    destination.mkdir(exist_ok=True)
    policy_path = destination / "timing-policy.json"
    policy = {"policy": TIMING_POLICY, "hash": TIMING_POLICY_HASH, "pre_sha256": freeze["file_sha256"]}
    if policy_path.exists():
        from .job import read
        if read(policy_path) != policy:
            raise ValueError("immutable timing policy differs; use a new batch")
    else:
        # Persist the selected boundaries before calculating any signal counts.
        write_json(policy_path, policy)
    report, observations = analyze(rows)
    report["pre_sha256"] = freeze["file_sha256"]
    frozen_rows(root)
    write_json(destination / "report.json", report)
    csv_file(destination / "observations.csv", ["race_id", "pool_id", "product", "leg", "horse_no",
             "WIN_skew_seconds", "cohort", "pWIN", "pCOL", "delta", "R", "signal"], observations)
    lines = ["# PRE-WINNER timing integrity\n", "PRE-only historical diagnostic; no POST read.",
             "PRIMARY ≤60 s; SECONDARY >60–300 s; EXCLUDE/diagnostic >300 s.",
             "Timing policy SHA-256: " + TIMING_POLICY_HASH,
             "PRE SHA-256: " + freeze["file_sha256"],
             "\nFull M0–M6/MODERATE/EXTREME protocol remains NOT_CONFIGURED. No performance claims.\n"]
    lines += [f"- {key}: {value}" for key, value in report.items()
              if key not in {"timing_policy", "pre_sha256", "timing_policy_hash"}]
    (destination / "PRE-WINNER-integrity.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
