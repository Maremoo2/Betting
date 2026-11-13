"""Offline journal over a pinned DEV-009 denominator and archived CORE-003 freezes."""

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .benchmark003_framework import validate
from .evaluation import log_loss, multiclass_brier
from .prospective_outcome_scorecard import _field, _market, _official_winner, _probs, clock, digest


def checked(body, expected):
    if digest(body) != expected:
        raise ValueError("ORIGINAL_HASH_MISMATCH")
    return json.loads(body)


def score_row(source, model, archive):
    race = model["race"]
    rid = source["race_id"]
    active, blocks = _field(model)
    if blocks:
        return None, None, None, blocks
    as_of = clock(model["as_of_utc"])
    market = _market(active, as_of)
    vectors = {"champion": _probs(active, "champion_p_win"), "core004": _probs(active, "core004_p_win")}
    if market is not None:
        vectors["market"] = market
    reasons = [] if market is not None else [source.get("win_benchmark_blocker") or "NO_SAME_FREEZE_WIN"]
    if source.get("reasons"):
        return vectors, None, None, reasons + source["reasons"]
    bodies = {}
    start = clock(race["start_time_utc"])
    _, meeting, number = rid.split(":")
    for receipt in source["original_result_receipts"]:
        role = receipt["role"]
        paths = {
            "complete": f"/results/raceDays/{meeting}/{number}/completeresults",
            "raceday": f"/results/racedays/{meeting}/raceresults",
        }
        if (
            role not in paths or role in bodies
            or receipt["source_uri"] != f"https://www.rikstoto.no/api{paths[role]}"
            or receipt["http_status"] != 200 or receipt.get("error_kind") is not None
            or clock(receipt["observed_at_utc"]) is None or clock(receipt["observed_at_utc"]) <= start
        ):
            return vectors, None, None, reasons + ["OFFICIAL_RESULT_RECEIPT_INVALID"]
        name = f"official-{digest(rid.encode())[:16]}/{role}.raw.json"
        result = checked(archive.read(name), receipt["raw_sha256"])
        if result.get("success") is not True:
            return vectors, None, None, reasons + ["OFFICIAL_RESULT_RECEIPT_INVALID"]
        bodies[role] = result["result"]
    if set(bodies) != {"complete", "raceday"}:
        return vectors, None, None, reasons + ["OFFICIAL_RESULT_ORIGINAL_MISSING"]
    winner, reason = _official_winner(
        bodies["complete"], bodies["raceday"], active=active,
        race_no=race["race_no"], frozen_roster=model["runners"],
    )
    if reason:
        return vectors, None, None, reasons + [reason]
    if winner != source.get("winner_selection_id"):
        return vectors, None, None, reasons + ["OFFICIAL_WINNER_CONFLICT"]
    validate({
        "scope": "DECISION_TIME_OBSERVED" if market else "TERMINAL_RETROSPECTIVE",
        "active_field": [row["selection_id"] for row in active], "probabilities": vectors,
        "winner_selection_id": winner, "race_start_at": race["start_time_utc"],
        "decision_cutoff": source["benchmark_t4_cutoff_utc"],
        "model_calculated_at": model["as_of_utc"], "model_frozen_at": model["report_created_at_utc"],
        "market_observed_at": active[0].get("win_odds_observed_at_utc"),
    })
    scores = {name: {"log_loss": log_loss(p, winner), "multiclass_brier": multiclass_brier(p, winner)}
              for name, p in vectors.items()}
    return vectors, winner, scores, reasons


def load_model(source, originals, by_run):
    path = source.get("source_model_path")
    sha = source.get("source_model_original_sha256")
    if not path or not sha:
        raise ValueError("NO_VERIFIED_FROZEN_MODEL")
    eligible = [row for row in source.get("original_freeze_history", []) if row["eligible_pre_t4"]]
    if eligible:
        latest = max(eligible, key=lambda row: (
            clock(row["model_created_at_utc"]), row["model_sha256"], row["source_model_path"],
        ))
        if (latest["model_sha256"], latest["source_model_path"]) != (sha, path):
            raise ValueError("FROZEN_REFERENCE_SELECTION_MISMATCH")
    match = re.fullmatch(r"[^/]+/(\d+)/(race-\d+)/shadow\.json", path)
    if not match:
        raise ValueError("INVALID_FROZEN_MODEL_PATH")
    run, folder = match.groups()
    zip_path = originals / f"{by_run[run]}.zip"
    with ZipFile(zip_path) as archive:
        index = checked(archive.read("cohort-index.json"), source["source_cohort_index_sha256"])
        entries = [r for r in index["processed"] if r["race_id"] == source["race_id"]]
        if len(entries) != 1 or entries[0]["report_sha256"] != sha or entries[0]["directory"] != f"bet-mvp-shadow/{folder}":
            raise ValueError("FROZEN_COHORT_MEMBER_MISMATCH")
        model = checked(archive.read(f"{folder}/shadow.json"), sha)
    if model["race"]["race_id"] != source["race_id"]:
        raise ValueError("FROZEN_MODEL_RACE_ID_MISMATCH")
    return model


def build_ledger(originals: Path, scorecard: Path, index_sha: str) -> dict:
    with ZipFile(scorecard) as archive:
        doc = checked(archive.read("index.json"), index_sha)
        if doc.get("schema") != "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1" or doc.get("bet_authority") is not False:
            raise ValueError("UNSUPPORTED_SCORECARD")
        rows = doc["records"]
        ids = [r["race_id"] for r in rows]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_PHYSICAL_RACE")
        inventory = doc["cumulative_original_inventory"]
        by_run = {str(r["source_run_id"]): r["artifact_id"]
                  for r in inventory["selected_artifacts"] if r["kind"] == "model"}
        records = []
        for source in sorted(rows, key=lambda r: r["race_id"]):
            model = {}
            vectors = winner = scores = None
            reasons = list(source.get("reasons", []))
            try:
                model = load_model(source, originals, by_run)
                vectors, winner, scores, blocks = score_row(source, model, archive)
                reasons.extend(blocks)
            except (BadZipFile, KeyError, OSError, TypeError, ValueError) as exc:
                reasons.insert(0, str(exc) if isinstance(exc, ValueError) else "ORIGINAL_MEMBER_UNAVAILABLE")
            race = model.get("race", {})
            runners = model.get("runners") or []
            status = "BLOCKED_SOURCE"
            if scores:
                status = "TRIPLE_EVALUABLE" if "market" in scores else "MODEL_PAIR_ONLY"
            records.append({
                "race_id": source["race_id"], "date": race.get("race_date"), "track": race.get("track"),
                "start_utc": race.get("start_time_utc") or source.get("race_start_utc"),
                "registered": len(runners) if runners else None,
                "active": sum(r.get("scratched") is False for r in runners) if runners else None,
                "scratched": sum(r.get("scratched") is True for r in runners) if runners else None,
                "full_field": bool(model and not _field(model)[1]),
                "history_status": "NOT_INDEPENDENTLY_ATTESTED", "identity_status": "UNATTESTED",
                "scratch_status": "NOT_INDEPENDENTLY_ATTESTED",
                "source_freeze": {k: source.get(k) for k in (
                    "source_model_original_sha256", "source_cohort_index_sha256", "source_model_path",
                    "original_freeze_history", "benchmark_freeze_selection_rule", "model_created_at_utc",
                    "model_as_of_utc", "benchmark_t4_cutoff_utc",
                )},
                "model_code_sha": model.get("git_sha_of_current_workspace"),
                "model_versions": model.get("model_versions"),
                "source_database_sha256": model.get("source_database_sha256"),
                "model_status": model.get("model_status"),
                "probabilities": vectors, "win_raw_sha256": None,
                "win_prices": {r["selection_id"]: r["win_odds"] for r in runners if r.get("scratched") is False}
                if vectors and "market" in vectors else None,
                "win_observed_at": next((r.get("win_odds_observed_at_utc") for r in runners
                                         if r.get("scratched") is False), None) if vectors and "market" in vectors else None,
                "winner_selection_id": winner, "result_receipts": source["original_result_receipts"],
                "scores": scores, "pit_status": "NOT_CERTIFIED", "evaluation_status": status,
                "primary_stop_reason": reasons[0] if reasons else None, "blockers": sorted(set(reasons)),
            })
    metrics = {}
    for name, models in (("pair", ("champion", "core004")), ("triple", ("champion", "core004", "market"))):
        group = [r["scores"] for r in records if r["scores"] and all(m in r["scores"] for m in models)]
        metrics[name] = {"races": len(group), "scores": {
            m: {k: math.fsum(r[m][k] for r in group) / len(group) for k in ("log_loss", "multiclass_brier")}
            for m in models
        } if group else None}
    return {
        "schema": "HBI_RESEARCH_LEDGER_V1", "source_index_sha256": index_sha,
        "scope": "ARCHIVED_RESEARCH_ONLY",
        "observed": len(records), "upstream_counts": doc["counts"], "metrics": metrics,
        "complete_prediction_fields": sum(r["full_field"] for r in records),
        "pit_certified": 0,
        "missing_originals": inventory["missing_originals"],
        "status_counts": dict(Counter(r["evaluation_status"] for r in records)),
        "primary_stop_counts": dict(Counter(
            r["primary_stop_reason"] for r in records if r["primary_stop_reason"]
        )),
        "blocker_counts": dict(Counter(b for r in records for b in r["blockers"])),
        "bet_authority": False, "records": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("originals", "scorecard", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--index-sha", required=True)
    args = parser.parse_args()
    result = build_ledger(args.originals, args.scorecard, args.index_sha)
    body = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(body)
    print(digest(body))


if __name__ == "__main__":
    main()
