"""Offline journal over a pinned DEV-009 denominator and archived CORE-003 freezes."""

import argparse
import json
import math
import re
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .benchmark003_framework import validate
from .evaluation import log_loss, multiclass_brier
from .mvp016_research_status import RACE_ID
from .prospective_outcome_scorecard import (
    MODEL,
    _field,
    _market,
    _official_winner,
    _probs,
    clock,
    digest,
)


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


class DirectoryOriginal:
    def __init__(self, path):
        self.path = path

    def read(self, name):
        path = self.path / name
        if path.is_symlink() or not path.resolve().is_relative_to(self.path.resolve()):
            raise ValueError("ORIGINAL_MEMBER_UNSAFE")
        return path.read_bytes()


@contextmanager
def open_original(path):
    if path.is_dir():
        yield DirectoryOriginal(path)
    else:
        with ZipFile(path) as archive:
            yield archive


def load_model(source, originals, by_run, *, extracted=False):
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
    original_path = originals / run if extracted else originals / f"{by_run[run]}.zip"
    with open_original(original_path) as archive:
        index = checked(archive.read("cohort-index.json"), source["source_cohort_index_sha256"])
        entries = [r for r in index["processed"] if r["race_id"] == source["race_id"]]
        if len(entries) != 1 or entries[0]["report_sha256"] != sha or entries[0]["directory"] != f"bet-mvp-shadow/{folder}":
            raise ValueError("FROZEN_COHORT_MEMBER_MISMATCH")
        model = checked(archive.read(f"{folder}/shadow.json"), sha)
    if model["race"]["race_id"] != source["race_id"]:
        raise ValueError("FROZEN_MODEL_RACE_ID_MISMATCH")
    return model


def build_ledger(originals: Path, scorecard: Path, index_sha: str) -> dict:
    with open_original(scorecard) as archive:
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
                model = load_model(source, originals, by_run, extracted=scorecard.is_dir())
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


def attach_current(ledger, source_report, cohort_dir, handoff_path):
    """Join this run's original observations without changing benchmark rows."""
    source_raw = source_report.read_bytes()
    source_sha = digest(source_raw)
    source = json.loads(source_raw)
    cohort_raw = (cohort_dir / "cohort-index.json").read_bytes()
    cohort = json.loads(cohort_raw)
    if (source.get("schema_version") != "CORE_003_SHADOW_PILOT_V1"
            or source.get("bet_count") != 0
            or cohort.get("schema") != "BET_MVP_002_FIXED_COHORT_INDEX_V1"
            or cohort.get("bet_authority") is not False or cohort.get("pit_certified") is not False
            or cohort.get("source_report_sha256") != source_sha):
        raise ValueError("CURRENT_SOURCE_CONTRACT_INVALID")
    current = cohort["original_cohort"]
    if (not isinstance(current, list)
            or any(not isinstance(rid, str) or not RACE_ID.fullmatch(rid) for rid in current)
            or len(set(current)) != len(current) or current != source["races_in_fixed_cohort"]):
        raise ValueError("CURRENT_SOURCE_COHORT_IDENTITY_MISMATCH")

    handoff_sha = cohort.get("collector_handoff_sha256")
    handoff = {}
    handoff_status = "MISSING"
    if handoff_sha and handoff_path.is_file():
        original = checked(handoff_path.read_bytes(), handoff_sha)
        rows = original["records"]
        handoff = {row["race_id"]: row for row in rows}
        if (original.get("source_report_sha256") != source_sha
                or original.get("bet_authority") is not False or original.get("pit_certified") is not False
                or rows != cohort.get("collector_handoff") or len(handoff) != len(rows)
                or not set(handoff) <= set(current)):
            raise ValueError("CURRENT_COLLECTOR_HANDOFF_CONFLICT")
        handoff_status = "VERIFIED"
    elif not handoff_sha and cohort.get("collector_handoff"):
        raise ValueError("CURRENT_COLLECTOR_HANDOFF_ORIGINAL_MISSING")

    members = {}
    for key in ("processed", "not_processed", "errors"):
        for row in cohort[key]:
            rid = row["race_id"]
            if rid in members or rid not in current:
                raise ValueError("CURRENT_COHORT_MEMBER_CONFLICT")
            members[rid] = (key, row)
    records = []
    for rid in sorted(current):
        kind, row = members.get(rid, (None, {}))
        model = None
        reason = row.get("reason") or "CURRENT_MODEL_DISPOSITION_MISSING"
        if kind == "processed":
            reason = "CURRENT_OFFICIAL_OUTCOME_NOT_VERIFIED"
            try:
                directory = row["directory"]
                if not re.fullmatch(r"bet-mvp-shadow/race-[0-9]{3,}", directory):
                    raise ValueError("CURRENT_MODEL_PATH_INVALID")
                model = checked(
                    DirectoryOriginal(cohort_dir).read(f"{directory.split('/')[-1]}/shadow.json"),
                    row["report_sha256"],
                )
                if (model.get("schema") != MODEL
                        or model["race"]["race_id"] != rid):
                    raise ValueError("CURRENT_MODEL_RACE_ID_MISMATCH")
            except (OSError, KeyError, TypeError, ValueError) as exc:
                model = None
                reason = str(exc) if isinstance(exc, ValueError) else "CURRENT_MODEL_ORIGINAL_UNAVAILABLE"
        active, blockers = _field(model) if model else (None, [])
        receipt = handoff.get(rid)
        market = _market(active, clock(model.get("as_of_utc"))) if model and active and not blockers else None
        records.append({
            "race_id": rid,
            "collector_import_verified": receipt.get("import_record_verified") if receipt else None,
            "collector_blockers": (receipt or {}).get("blockers", row.get("collector_blockers", [])),
            "expected_model_sha256": row.get("report_sha256"),
            "model_sha256": row["report_sha256"] if model else None,
            "model_versions": model.get("model_versions") if model else None,
            "model_as_of_utc": model.get("as_of_utc") if model else None,
            "model_created_at_utc": model.get("report_created_at_utc") if model else None,
            "full_field": bool(model and not blockers),
            "same_freeze_win": market,
            "win_observed_at": active[0].get("win_odds_observed_at_utc") if market else None,
            "primary_stop_reason": blockers[0] if blockers else reason,
            "model_blockers": blockers,
            "pit_certified": False,
        })
    ledger["current_observations"] = {
        "source_report_sha256": source_sha, "cohort_index_sha256": digest(cohort_raw),
        "collector_handoff_sha256": handoff_sha, "collector_handoff_status": handoff_status,
        "records": records,
    }
    ledger["observed_with_current"] = len({r["race_id"] for r in ledger["records"]} | set(current))
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("originals", "scorecard", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--index-sha")
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--current-cohort", type=Path)
    parser.add_argument("--collector-handoff", type=Path)
    args = parser.parse_args()
    current = (args.source_report, args.current_cohort, args.collector_handoff)
    if any(current) and not all(current):
        parser.error("Current-run paths must be supplied together")
    if args.index_sha:
        result = build_ledger(args.originals, args.scorecard, args.index_sha)
    elif all(current) and args.scorecard.is_dir():
        diagnostic = args.scorecard / "source-unavailable.json"
        diagnostic_raw = diagnostic.read_bytes() if diagnostic.is_file() else None
        if diagnostic_raw:
            unavailable = json.loads(diagnostic_raw)
            if (unavailable.get("schema") != "MVP016_CUMULATIVE_SCORECARD_SOURCE_UNAVAILABLE_V1"
                    or unavailable.get("scorecard_generated") is not False
                    or unavailable.get("bet_authority") is not False):
                raise ValueError("SCORECARD_SOURCE_DIAGNOSTIC_INVALID")
        else:
            unavailable = {"source_reason": "DEV009_OUTPUT_MISSING"}
        result = {
            "schema": "HBI_RESEARCH_LEDGER_V1", "scope": "CURRENT_OBSERVATIONS_ONLY",
            "scorecard_source_reason": unavailable["source_reason"],
            "scorecard_diagnostic_sha256": digest(diagnostic_raw) if diagnostic_raw else None,
            "observed": None, "records": [], "bet_authority": False, "pit_certified": 0,
        }
    else:
        parser.error("--index-sha is required for the archived scorecard")
    if all(current):
        attach_current(result, *current)
    body = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(body)
    print(digest(body))


if __name__ == "__main__":
    main()
