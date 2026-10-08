"""Prospective, research-only PRE-WATCH V3 comparison. No wager or Champion writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from betting.v33 import POLICY, POLICY_HASH, normalize, verify_report

VERSION = "PREWATCH_V3_SHADOW_V1"
START = "2026-10-08T00:00:00+02:00"
CHECKPOINT = "2026-12-08T23:59:59+01:00"
TEMPERATURES = (0.8, 0.9, 1.0, 1.1, 1.2)
PENALTIES = (0.0, 0.1, 0.2, 0.35, 0.5)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def moment(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("all times must be timezone-aware")
    return dt.astimezone(timezone.utc)


def probabilities(values):
    if not isinstance(values, dict) or len(values) < 2:
        raise ValueError("full field with >=2 runners required")
    result = {str(k): float(v) for k, v in values.items()}
    if any(not math.isfinite(v) or v < 0 for v in result.values()):
        raise ValueError("invalid probability")
    total = sum(result.values())
    if total <= 0:
        raise ValueError("zero probability mass")
    return {k: v / total for k, v in result.items()}


def power(p, alpha):
    return probabilities({k: max(1e-12, v) ** alpha for k, v in p.items()})


def negative_col(win, col, gamma):
    """Never a wagering policy; renormalizes *all* runners."""
    if set(win) != set(col):
        raise ValueError("WIN/COL field mismatch")
    adjusted = {}
    for k, p in win.items():
        q = col[k]
        strong_negative = (q - p <= -POLICY["delta"] + 1e-12
                           and q / p <= POLICY["ratio_neg"] + 1e-12)
        adjusted[k] = p * math.exp(-gamma if strong_negative else 0)
    return probabilities(adjusted)


def score(p, winner):
    if winner not in p:
        raise ValueError("winner not in full field")
    return {"log_loss": -math.log(max(1e-15, p[winner])),
            "brier": sum((v - (1 if k == winner else 0)) ** 2 for k, v in p.items()),
            "top1": int(p[winner] == max(p.values()))}


def read_ledger(path):
    if not Path(path).exists():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if digest(row["payload"]) != row["sha256"]:
                raise ValueError("immutable ledger checksum mismatch")
            rows.append(row)
    return rows


def append(path, kind, key, payload):
    path = Path(path)
    record = {"kind": kind, "key": key, "payload": payload, "sha256": digest(payload)}
    for old in read_ledger(path):
        if (old["kind"], old["key"]) == (kind, key):
            if old["sha256"] == record["sha256"]:
                return record
            raise ValueError("frozen record cannot be overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(canonical(record) + "\n")
    return record


def validate_decision(entry):
    """Accept original, verifiable V3 report plus independently timestamped provider evidence.

    Missing/late evidence is recorded as ineligible, not backfilled from final prices.
    """
    report = entry["v3_report"]
    verify_report(report)
    race_id, field = str(report["race_id"]), list(map(str, report["active_field"]))
    start, decision = moment(report["race_start"]), moment(report["decision_time"])
    if start <= decision:
        raise ValueError("V3 decision at/after scheduled start")
    if moment(entry["recorded_at"]) < decision:
        raise ValueError("recorded_at predates V3 decision")
    if entry["race_id"] != race_id:
        raise ValueError("identity mismatch")
    if entry.get("product") not in report["decision_snapshot"].get("collective", {}):
        raise ValueError("selected product not in frozen V3 report")
    win = report["decision_snapshot"]["WIN"]
    pool = report["decision_snapshot"]["collective"][entry["product"]]
    evidence = entry.get("evidence", {})
    flags = []
    for name, snap in (("WIN", win), ("COL", pool)):
        item = evidence.get(name, {})
        if not item.get("source_uri") or not item.get("captured_at"):
            flags.append(name + "_MISSING_SOURCE_CAPTURE")
            continue
        observed = moment(snap["observed_at"])
        captured = moment(item["captured_at"])
        if observed > captured or captured > decision:
            flags.append(name + "_NOT_AVAILABLE_AT_DECISION")
        if (decision - captured).total_seconds() > POLICY["max_age_seconds"]:
            flags.append(name + "_STALE")
        if snap.get("provider_updated_at"):
            if moment(snap["provider_updated_at"]) > decision:
                flags.append(name + "_LATE_PROVIDER_UPDATE")
    if abs((moment(win["observed_at"]) - moment(pool["observed_at"])).total_seconds()) > POLICY["max_pool_skew_seconds"]:
        flags.append("POOL_SKEW")
    if set(win["odds"]) != set(field) or set(pool["shares"]) != set(field):
        flags.append("INCOMPLETE_FIELD")
    pwin = normalize(win["odds"], field, odds=True)
    pcol = normalize(pool["shares"], field)
    champ = entry.get("champion")
    if champ is not None:
        if set(champ["probabilities"]) != set(field):
            flags.append("CHAMPION_INCOMPLETE_FIELD")
        if not champ.get("model_version") or not champ.get("source_uri"):
            flags.append("CHAMPION_MISSING_PROVENANCE")
        if moment(champ["priced_at"]) > decision:
            flags.append("CHAMPION_NOT_FROZEN_BEFORE_DECISION")
    if moment(entry["recorded_at"]) >= start:
        flags.append("LOGGED_AFTER_SCHEDULED_START")
    # A scheduled start is NOT evidence of actual start time.
    return {
        "race_id": race_id, "product": entry["product"], "decision_at": decision.isoformat(),
        "scheduled_start": start.isoformat(), "recorded_at": moment(entry["recorded_at"]).isoformat(),
        "v3_decision_id": report["decision_id"], "v3_policy_hash": POLICY_HASH,
        "v3_selection_decisions": {k: report["runners"][k]["WIN"]["decision"] for k in field},
        "v3_allowed": report["allowed"], "p_win": pwin, "p_col": pcol,
        "win_odds_at_decision": win["odds"],
        "evidence": evidence, "champion": champ, "flags": sorted(set(flags)),
        "pit_eligible": not flags, "actual_start_verified": False,
        "execution": "SHADOW_ONLY", "version": VERSION,
    }


def fit(development, fitted_at, minimum=100):
    """Chronological development only. Prospective period starts strictly after fit."""
    fitted = moment(fitted_at)
    rows = sorted(development, key=lambda r: r["decision_at"])
    rows = [r for r in rows if r.get("pit_eligible") and r.get("winner") in r["p_win"]
            and moment(r["scheduled_start"]) < fitted
            and moment(r["outcome_at"]) <= fitted]
    if len({r["race_id"] for r in rows}) < minimum:
        raise ValueError("insufficient verified development races")
    unique = {}
    for r in rows:
        unique.setdefault(r["race_id"], r)
    rows = list(unique.values())
    if len(rows) < minimum:
        raise ValueError("insufficient unique development races")
    cutoff = max(1, int(len(rows) * 0.7))
    train, validate = rows[:cutoff], rows[cutoff:]
    def loss(data, alpha, gamma):
        return sum(score(negative_col(power(r["p_win"], alpha), r["p_col"], gamma),
                         r["winner"])["log_loss"] for r in data) / len(data)
    alpha = min(TEMPERATURES, key=lambda a: loss(train, a, 0))
    gamma = min(PENALTIES, key=lambda g: loss(validate, alpha, g))
    artifact = {
        "version": VERSION, "fitted_at": fitted.isoformat(), "forward_start": fitted.isoformat(),
        "train_n": len(train), "validation_n": len(validate),
        "development_sha256": digest(rows), "win_temperature": alpha,
        "negative_col_penalty": gamma, "policy_hash": POLICY_HASH,
        "selection": "chrono_70_30_train_WIN_then_validate_COL",
        "execution": "SHADOW_ONLY",
    }
    artifact["artifact_sha256"] = digest(artifact)
    return artifact


def validate_model(model):
    if model["artifact_sha256"] != digest({k: v for k, v in model.items() if k != "artifact_sha256"}):
        raise ValueError("model artifact changed after freeze")
    if model["policy_hash"] != POLICY_HASH or model["version"] != VERSION:
        raise ValueError("model version mismatch")


def report(ledger, model=None, start=START, end=CHECKPOINT):
    records = read_ledger(ledger)
    decisions = {r["key"]: r["payload"] for r in records if r["kind"] == "decision"}
    outcomes = {r["key"]: r["payload"] for r in records if r["kind"] == "outcome"}
    if model is not None:
        validate_model(model)
    evaluated = []
    rejection = {}
    for key, d in decisions.items():
        if not (moment(start) <= moment(d["decision_at"]) <= moment(end)):
            continue
        if d["flags"]:
            for flag in d["flags"]:
                rejection[flag] = rejection.get(flag, 0) + 1
        if not d["pit_eligible"] or key not in outcomes:
            continue
        o = outcomes[key]
        if o["winner"] not in d["p_win"] or moment(o["result_at"]) <= moment(d["scheduled_start"]):
            continue
        s = {"key": key, "race_id": d["race_id"], "product": d["product"],
             "winner": o["winner"], "v3_selections": d["v3_selection_decisions"],
             "win_raw": score(d["p_win"], o["winner"])}
        champ = d.get("champion")
        if champ:
            s["champion"] = score(probabilities(champ["probabilities"]), o["winner"])
        if model and moment(d["decision_at"]) > moment(model["forward_start"]):
            p_cal = power(d["p_win"], model["win_temperature"])
            s["win_calibrated"] = score(p_cal, o["winner"])
            s["negative_col"] = score(negative_col(p_cal, d["p_col"],
                                                 model["negative_col_penalty"]), o["winner"])
        evaluated.append(s)
    fields = ("win_raw", "win_calibrated", "negative_col", "champion")
    summary = {}
    for field in fields:
        subset = [e for e in evaluated if field in e]
        summary[field] = {"n_product_fields": len(subset),
                          "n_unique_races": len({e["race_id"] for e in subset}),
                          "mean_log_loss": (sum(e[field]["log_loss"] for e in subset) / len(subset)
                                            if subset else None),
                          "mean_brier": (sum(e[field]["brier"] for e in subset) / len(subset)
                                         if subset else None),
                          "top1_rate": (sum(e[field]["top1"] for e in subset) / len(subset)
                                         if subset else None)}
    paired = [e for e in evaluated if "win_calibrated" in e and "negative_col" in e]
    paired_delta = ([e["negative_col"]["log_loss"] - e["win_calibrated"]["log_loss"]
                     for e in paired])
    result = {"version": VERSION, "start": start, "end": end, "model": model,
              "n_decisions": sum(moment(start) <= moment(d["decision_at"]) <= moment(end)
                                 for d in decisions.values()),
              "n_outcomes": len(outcomes),
              "n_pit_eligible_decisions": sum(
                  moment(start) <= moment(d["decision_at"]) <= moment(end)
                  and d["pit_eligible"] for d in decisions.values()),
              "rejection_flags": rejection, "models": summary,
              "paired_col_minus_calibrated_win_log_loss": (
                  sum(paired_delta) / len(paired_delta) if paired_delta else None),
              "paired_n": len(paired),
              "v3_comparison": "V3 decisions retained; ROI not inferable without frozen bet rule and official dividends",
              "warning": "Scheduled-start evidence only; actual start unverified unless separately reconciled.",
              "promotion": "MANUAL_REVIEW_ONLY", "real_money_execution": False}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research-only PRE-WATCH V3 comparison")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("input")
    record.add_argument("--ledger", required=True)
    outcome = commands.add_parser("outcome")
    outcome.add_argument("input")
    outcome.add_argument("--ledger", required=True)
    fitting = commands.add_parser("fit")
    fitting.add_argument("development")
    fitting.add_argument("--fitted-at", required=True)
    fitting.add_argument("--output", required=True)
    fitting.add_argument("--min-races", type=int, default=100)
    review = commands.add_parser("compare")
    review.add_argument("--ledger", required=True)
    review.add_argument("--model")
    review.add_argument("--output", required=True)
    review.add_argument("--start", default=START)
    review.add_argument("--end", default=CHECKPOINT)
    args = parser.parse_args(argv)
    if args.command == "record":
        entry = json.loads(Path(args.input).read_text())
        d = validate_decision(entry)
        result = append(args.ledger, "decision", d["race_id"] + "|" + d["product"], d)
    elif args.command == "outcome":
        entry = json.loads(Path(args.input).read_text())
        if moment(entry["result_at"]) <= moment(entry["scheduled_start"]):
            raise ValueError("outcome cannot be before scheduled start")
        key = str(entry["race_id"]) + "|" + str(entry["product"])
        result = append(args.ledger, "outcome", key, entry)
    elif args.command == "fit":
        rows = [json.loads(line) for line in Path(args.development).read_text().splitlines()
                if line.strip()]
        result = fit(rows, args.fitted_at, args.min_races)
        path = Path(args.output)
        if path.exists():
            raise ValueError("frozen model artifact already exists")
        path.write_text(canonical(result) + "\n", encoding="utf-8")
    else:
        model = json.loads(Path(args.model).read_text()) if args.model else None
        result = report(args.ledger, model, args.start, args.end)
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
