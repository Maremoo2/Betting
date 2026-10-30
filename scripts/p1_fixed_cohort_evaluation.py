"""Fixed-cohort, paired probability scoring for future P1 research only.

The cohort must be declared before observing outcomes. This tool verifies
internal consistency but cannot independently attest GitHub publication times,
original provider history, or the truth of supplied signature/boolean claims.
It never approves Champion, wagers, staking, expected value or real money.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from hbi.prospective_eval_gate import validate_cohort


def digest_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _aware(value: object) -> datetime:
    dt = datetime.fromisoformat(str(value))
    if dt.utcoffset() is None:
        raise ValueError("All timestamps must be timezone aware")
    return dt


def _scores(p: dict, winner: str) -> tuple[float, float]:
    if winner not in p:
        raise ValueError("Winner absent from exact frozen full field")
    win = float(p[winner])
    if not 0 < win <= 1:
        raise ValueError("Invalid winning probability")
    # Standard multiclass Brier: sum (p_i - 1{win=i})^2.
    return -math.log(win), math.fsum(
        (float(value) - (1.0 if key == winner else 0.0)) ** 2
        for key, value in p.items()
    )


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def evaluate(manifest: dict, records: list[dict], *, protocol_bytes: bytes) -> dict:
    expected = manifest.get("declared_race_ids")
    if not isinstance(expected, list) or not expected or not all(
        isinstance(x, str) and x.strip() for x in expected
    ):
        raise ValueError("Manifest needs nonempty explicit declared_race_ids")
    if len(set(expected)) != len(expected):
        raise ValueError("Duplicate race in frozen denominator")
    registered = _aware(manifest["protocol_registered_at_utc"])
    protocol_sha = digest_bytes(protocol_bytes)
    if protocol_sha != manifest.get("protocol_sha256"):
        raise ValueError("Protocol bytes differ from declared SHA-256")
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("Records must be a list of mappings")
    by_id = {r.get("race_id"): r for r in records}
    if len(by_id) != len(records):
        raise ValueError("Duplicate physical race row")
    missing = sorted(set(expected) - set(by_id))
    unexpected = sorted(set(by_id) - set(expected))
    if not all(isinstance(k, str) for k in by_id):
        raise ValueError("Every row must specify race_id")
    report: dict = {
        "schema": "P1_FIXED_PROSPECTIVE_PAIRED_EVALUATION_V1",
        "authority": "CLAIMS_ONLY_NOT_EXTERNALLY_ATTESTED",
        "protocol_sha256": protocol_sha,
        "manifest_sha256": digest_bytes(json.dumps(
            manifest, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")),
        "records_sha256": digest_bytes(json.dumps(
            records, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")),
        "declared_total": len(expected),
        "submitted_total": len(records),
        "missing_races": missing,
        "unexpected_races": unexpected,
        "metrics": None,
        "per_day": {},
        "status": "BLOCKED",
        "source_pit_independently_attested": False,
        "experiment_preregistration_independently_attested": False,
        "p1_validated": False,
        "model_promotion_authority": False,
        "betting_authority": False,
        "blockers": [],
    }
    errors = report["blockers"]
    if missing:
        errors.append("MISSING_DECLARED_RACES")
    if unexpected:
        errors.append("UNEXPECTED_UNPREREGISTERED_RACES")
    # A self-declared frozen record must not purport to have been
    # preregistered or frozen before the *manifest protocol* existed.
    # This is necessary, though not independently sufficient, evidence.
    for record in records:
        for field, reason in (
            ("race_start_utc", "PROTOCOL_REGISTERED_AFTER_RACE_START"),
            ("preregistered_at_utc", "RACE_PREREG_PRECEDES_PROTOCOL"),
            ("frozen_at_utc", "RACE_FREEZE_PRECEDES_PROTOCOL"),
        ):
            if field not in record:
                continue
            try:
                recorded = _aware(record[field])
            except (TypeError, ValueError):
                errors.append("INVALID_DECLARED_RACE_TIME")
                continue
            if recorded <= registered:
                errors.append(reason)
    if errors:
        report["status"] = "BLOCKED_COHORT_INTEGRITY"
        return report
    if not records:
        report["status"] = "NO_EVIDENCE"
        return report
    claim_gate = validate_cohort(
        records, experiment_id=str(manifest["experiment_id"]),
        frozen_protocol_hash=protocol_sha,
    )
    blocked = [entry for entry in claim_gate["cases"] if entry["status"] == "BLOCKED"]
    if blocked:
        report["status"] = "BLOCKED_UNVERIFIED_PIT_OR_TIME"
        report["blockers"] = sorted({
            reason for entry in blocked for reason in entry["reasons"]
        })
        return report
    keyed = {name: {"log_loss": [], "brier": []}
             for name in ("candidate", "champion", "market")}
    per_day: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"candidate_minus_market_log_loss": [],
                 "candidate_minus_champion_log_loss": []}
    )
    for rid in expected:
        record = by_id[rid]
        winner = str(record["winner_selection_id"])
        current = {}
        for key in keyed:
            logloss, brier = _scores(record[f"{key}_probabilities"], winner)
            keyed[key]["log_loss"].append(logloss)
            keyed[key]["brier"].append(brier)
            current[key] = logloss
        race_day = _aware(record["race_start_utc"]).date().isoformat()
        per_day[race_day]["candidate_minus_market_log_loss"].append(
            current["candidate"] - current["market"]
        )
        per_day[race_day]["candidate_minus_champion_log_loss"].append(
            current["candidate"] - current["champion"]
        )
    dates = sorted(date.fromisoformat(x) for x in per_day)
    consecutive = len(dates) >= 30 and (
        dates[-1] - dates[0] == timedelta(days=len(dates) - 1)
    )
    values = {key: {metric: _mean(series) for metric, series in metrics.items()}
              for key, metrics in keyed.items()}
    values["candidate_minus_market_log_loss"] = (
        values["candidate"]["log_loss"] - values["market"]["log_loss"]
    )
    values["candidate_minus_champion_log_loss"] = (
        values["candidate"]["log_loss"] - values["champion"]["log_loss"]
    )
    report.update({
        "status": "EXPLORATORY_CLAIMS_ONLY_UNATTESTED",
        "metrics": values,
        "per_day": {key: {measure: _mean(vals) for measure, vals in row.items()}
                    for key, row in sorted(per_day.items())},
        "distinct_days": len(dates),
        "at_least_30_consecutive_days": consecutive,
        "blockers": ["EXTERNAL_PIT_PROOF_AND_PREREG_TIMESTAMP_UNVERIFIED"]
                    + ([] if consecutive else ["MINIMUM_PROSPECTIVE_DAYS_NOT_MET"]),
    })
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--protocol", required=True, type=Path)
    p.add_argument("--records", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    source_paths = {x.resolve() for x in (a.manifest, a.protocol, a.records)}
    if a.output.resolve() in source_paths:
        p.error("Refusing to overwrite protocol, manifest or submitted records")
    data = evaluate(
        json.loads(a.manifest.read_text(encoding="utf-8")),
        json.loads(a.records.read_text(encoding="utf-8")),
        protocol_bytes=a.protocol.read_bytes(),
    )
    a.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps({"status": data["status"], "declared_total": data["declared_total"],
                      "p1_validated": False, "betting_authority": False}))


if __name__ == "__main__":
    main()
