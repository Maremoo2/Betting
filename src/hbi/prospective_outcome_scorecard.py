"""DEV-009: post-race, original-receipt-only model scoring; strictly research-only.

Reads immutable CORE-003 frozen reports selected before any outcomes and fetches
only public official Rikstoto result GET endpoints. Does not write state, settle
tickets, re-fit models, certify PIT or call any betting decision function.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .evaluation import calibration_bins, log_loss, multiclass_brier
from .probability import normalize_market_odds
from .providers.rikstoto import OriginalBytesFetchResult, RikstotoClient

SCHEMA = "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
COHORT = "BET_MVP_002_FIXED_COHORT_INDEX_V1"
MODEL = "BET_MVP_001_FROZEN_SHADOW_V1"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def clock(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        return parsed.astimezone(UTC) if parsed.utcoffset() is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def original(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("MISSING_OR_UNSAFE_ORIGINAL")
    return path.read_bytes()


def read_archived_models(root: Path) -> tuple[list[dict], list[dict], list[str]]:
    """Only frozen original archive members; never choose a model by its result."""
    candidates: list[dict] = []
    errors: list[dict] = []
    expected_races: set[str] = set()
    indexes = sorted(root.glob("*/cohort-index.json")) if root.is_dir() else []
    if (root / "cohort-index.json").is_file():
        indexes.insert(0, root / "cohort-index.json")
    for index in indexes:
        try:
            raw_index = original(index)
            data = json.loads(raw_index)
            if (not isinstance(data, dict) or data.get("schema") != COHORT
                    or data.get("bet_authority") is not False
                    or not isinstance(data.get("processed"), list)):
                raise ValueError("FROZEN_COHORT_CONTRACT_INVALID")
            declared = data.get("original_cohort")
            if declared is None:
                declared = [e.get("race_id") for e in data["processed"] if isinstance(e, dict)]
                declared += [e.get("race_id") for e in data.get("not_processed", [])
                             if isinstance(e, dict)]
            if (not isinstance(declared, list) or not declared
                    or any(not isinstance(x, str) or not x for x in declared)
                    or len(declared) != len(set(declared))):
                raise ValueError("DECLARED_PHYSICAL_COHORT_INVALID")
            # Denominator is frozen BEFORE any source files are scored.
            expected_races.update(declared)
            used: set[str] = set()
            local_candidates: list[dict] = []
            for entry in data["processed"]:
                race_id = entry.get("race_id") if isinstance(entry, dict) else None
                directory = entry.get("directory") if isinstance(entry, dict) else None
                if (not isinstance(race_id, str) or not race_id
                        or race_id in used or not isinstance(directory, str)
                        or re.fullmatch(r"bet-mvp-shadow/race-[0-9]{3,}", directory) is None):
                    raise ValueError("UNSAFE_OR_DUPLICATE_COHORT_ENTRY")
                used.add(race_id)
                path = index.parent / directory.split("/")[-1] / "shadow.json"
                report_raw = original(path)
                expected = entry.get("report_sha256")
                if not isinstance(expected, str) or digest(report_raw) != expected:
                    raise ValueError("FROZEN_MODEL_SHA256_MISMATCH")
                report = json.loads(report_raw)
                if (not isinstance(report, dict) or report.get("schema") != MODEL
                        or (report.get("race") or {}).get("race_id") != race_id):
                    raise ValueError("FROZEN_MODEL_RACE_ID_MISMATCH")
                local_candidates.append({
                    "race_id": race_id, "model": report,
                    "model_sha256": digest(report_raw),
                    "cohort_index_sha256": digest(raw_index),
                    "original_model_path": str(path),
                })
            candidates.extend(local_candidates)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append({"source": str(index), "reason": str(exc)})
    by_race: dict[str, dict] = {}
    for item in candidates:
        race_id = item["race_id"]
        # Deterministic before-results first frozen model, not the best score.
        key = (str(item["model"].get("report_created_at_utc") or ""),
               item["original_model_path"])
        if race_id not in by_race or key < (
            str(by_race[race_id]["model"].get("report_created_at_utc") or ""),
            by_race[race_id]["original_model_path"],
        ):
            by_race[race_id] = item
    return [by_race[k] for k in sorted(by_race)], errors, sorted(expected_races)


def _probs(rows: list[dict], field: str) -> dict[str, float] | None:
    out = {}
    for row in rows:
        key = row["selection_id"]
        value = row.get(field)
        if (type(value) not in (float, int) or not math.isfinite(value)
                or value <= 0 or value >= 1 or key in out):
            return None
        out[key] = float(value)
    return out if len(out) >= 2 and math.isclose(
        math.fsum(out.values()), 1.0, rel_tol=0, abs_tol=1e-9
    ) else None


def _field(model: dict) -> tuple[list[dict] | None, list[str]]:
    blocks = []
    race = model.get("race") or {}
    start = clock(race.get("start_time_utc"))
    freeze = clock(model.get("report_created_at_utc"))
    asof = clock(model.get("as_of_utc"))
    if (start is None or freeze is None or asof is None
            or not asof <= freeze <= start - timedelta(minutes=4)):
        blocks.append("FROZEN_MODEL_MISSED_T4_OR_INVALID_CLOCK")
    if model.get("run_kind") != "PROSPECTIVE_ATTEMPT":
        blocks.append("NOT_PROSPECTIVE_FROZEN_MODEL")
    if model.get("bet_authority") is not False:
        blocks.append("UNEXPECTED_BET_AUTHORITY")
    if (model.get("model_status") != "MODEL_READY"
            or model.get("source_archive_is_immutable_read_only") is not True):
        blocks.append("FROZEN_RESEARCH_MODEL_NOT_READY")
    rows = model.get("runners")
    if not isinstance(rows, list) or not rows:
        return None, blocks + ["FROZEN_FIELD_MISSING"]
    if any(not isinstance(row, dict) or type(row.get("scratched")) is not bool
           or type(row.get("start_number")) is not int
           or not isinstance(row.get("selection_id"), str)
           or not row["selection_id"] for row in rows):
        return None, blocks + ["INVALID_FROZEN_FIELD_ROW"]
    if (len(rows) != model.get("field_size")
            or len({r["selection_id"] for r in rows}) != len(rows)
            or len({r["start_number"] for r in rows}) != len(rows)):
        blocks.append("INCOMPLETE_OR_COLLIDING_FROZEN_FIELD")
    active = [r for r in rows if not r["scratched"]]
    if len(active) < 2 or len(active) != model.get("active_runners"):
        blocks.append("ACTIVE_FULL_FIELD_MISMATCH")
    if _probs(active, "champion_p_win") is None:
        blocks.append("CHAMPION_FULL_FIELD_INVALID")
    if _probs(active, "core004_p_win") is None:
        blocks.append("CORE004_FULL_FIELD_INVALID")
    return active, blocks


def _capture(client: RikstotoClient, path: str, folder: Path, role: str) -> tuple[dict | None, dict]:
    fetched = client._fetch(path, retain_raw_body=True)
    rec: dict[str, Any] = {
        "role": role, "source_uri": fetched.url, "http_status": fetched.status_code,
        "observed_at_utc": (
            fetched.response_completed_at.isoformat()
            if fetched.response_completed_at else None
        ), "http_date_not_publication_proof": fetched.http_date,
        "http_etag": fetched.http_etag, "http_last_modified": fetched.http_last_modified,
        "raw_sha256": None, "raw_path": None, "error_kind": None,
    }
    if (not isinstance(fetched, OriginalBytesFetchResult)
            or not fetched.success or fetched.status_code != 200
            or not fetched.raw_body or digest(fetched.raw_body) != fetched.response_body_sha256):
        rec["error_kind"] = "OFFICIAL_GET_OR_RAW_HASH_FAILED"
        return None, rec
    rawpath = folder / f"{role}.raw.json"
    with rawpath.open("xb") as out:
        out.write(fetched.raw_body)
    rec["raw_sha256"] = digest(fetched.raw_body)
    rec["raw_path"] = str(rawpath)
    try:
        envelope = json.loads(fetched.raw_body)
        if (not isinstance(envelope, dict) or envelope.get("success") is not True
                or not isinstance(envelope.get("result"), dict)):
            rec["error_kind"] = "OFFICIAL_RESULT_ENVELOPE_INVALID"
            return None, rec
        return envelope["result"], rec
    except (ValueError, TypeError):
        rec["error_kind"] = "OFFICIAL_RESULT_JSON_INVALID"
        return None, rec


def _official_winner(
    complete: dict, raceday: dict, *, active: list[dict], race_no: int,
) -> tuple[str | None, str | None]:
    if complete.get("isComplete") is not True:
        return None, "OFFICIAL_FINISH_NOT_COMPLETE"
    rows = complete.get("results")
    if not isinstance(rows, list) or not rows:
        return None, "OFFICIAL_FINISH_ROWS_MISSING"
    observed = {}
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("startNumber")) not in (str, int)
                or not str(row["startNumber"]).isdigit()
                or type(row.get("place")) is not int or row["place"] < 0):
            return None, "OFFICIAL_FINISH_ROW_INVALID"
        key = str(int(row["startNumber"]))
        if key in observed:
            return None, "OFFICIAL_DUPLICATE_RUNNER"
        observed[key] = row
    expected = {str(r["start_number"]): r for r in active}
    if set(observed) != set(expected):
        return None, "OFFICIAL_ACTIVE_FIELD_MISMATCH"
    for no, row in observed.items():
        # If the official source publishes a name, it must not contradict the
        # frozen pre-start identity. Names by themselves never prove PIT.
        name = row.get("horseName")
        if isinstance(name, str) and name.strip() and (
            name.strip().casefold() != str(expected[no].get("horse_name", "")).strip().casefold()
        ):
            return None, "OFFICIAL_FROZEN_RUNNER_NAME_DISAGREES"
    winners = [number for number, row in observed.items() if row["place"] == 1]
    if len(winners) != 1:
        return None, "OFFICIAL_WINNER_NOT_UNIQUE"
    winner_number = winners[0]
    try:
        payout = raceday["finalOdds"]["winOdds"][str(race_no)][winner_number]
        amount = payout["odds"]
        if (payout.get("payoutStatus") != "Dividends"
                or isinstance(amount, bool) or not math.isfinite(float(amount))
                or float(amount) <= 0):
            return None, "OFFICIAL_WINNER_DIVIDEND_UNVERIFIED"
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return None, "OFFICIAL_WINNER_DIVIDEND_MISSING"
    return expected[winner_number]["selection_id"], None


def _market(active: list[dict], asof: datetime | None) -> dict[str, float] | None:
    if asof is None:
        return None
    times = {row.get("win_odds_observed_at_utc") for row in active}
    if len(times) != 1 or clock(next(iter(times))) is None or clock(next(iter(times))) > asof:
        return None
    try:
        odds = {r["selection_id"]: r.get("win_odds") for r in active}
        if (any(type(v) not in (float, int) or not math.isfinite(v) or v <= 1
                for v in odds.values()) or len(odds) != len(active)
                or any(r.get("win_odds_provider") != "rikstoto" for r in active)):
            return None
        return normalize_market_odds(odds)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def evaluate_archive(
    *, models_root: Path, output_dir: Path, fetch_official: bool = False,
    client: RikstotoClient | None = None, now: datetime | None = None,
    attestation_index: Path | None = None,
) -> dict:
    """Return all observed races, including blocked ones. No synthetic winners."""
    output_dir.mkdir(parents=True, exist_ok=False)
    models, archive_errors, expected_races = read_archived_models(models_root)
    pit: dict[str, list[dict]] = {}
    if attestation_index is not None:
        try:
            raw = original(attestation_index)
            parsed = json.loads(raw)
            if parsed.get("schema") != "PIT_T4_ATTESTATION_INDEX_V1":
                raise ValueError("PIT_ATTESTATION_SCHEMA_INVALID")
            for row in parsed.get("results") or []:
                if isinstance(row, dict):
                    pit.setdefault(str(row.get("race_id")), []).append(row)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            archive_errors.append({"source": str(attestation_index), "reason": str(exc)})
    api = client or RikstotoClient()
    current = now or datetime.now(UTC)
    output = {
        "schema": SCHEMA, "authority": "READ_ONLY_RESEARCH_SCORECARD",
        "generated_at_utc": current.isoformat(), "source_archive_root": str(models_root),
        "model_originals_verified_by_sha": True,
        "archive_errors": archive_errors, "records": [], "metrics": None,
        "no_model_promotion": True, "pit_certification_performed": False,
        "v33_evaluator_called": False, "bet_authority": False, "stake_nok": None,
    }
    for item in models:
        model = item["model"]
        race = model.get("race") or {}
        rid = item["race_id"]
        start = clock(race.get("start_time_utc"))
        active, reasons = _field(model)
        p1 = _probs(active, "champion_p_win") if active else None
        p2 = _probs(active, "core004_p_win") if active else None
        pmarket = _market(active, clock(model.get("as_of_utc"))) if active else None
        rows = pit.get(rid, [])
        attested = (
            len(rows) == 1 and rows[0].get("model_report_sha256") == item["model_sha256"]
            and rows[0].get("pit_status") == "INDEPENDENT_PIT_CERTIFIED"
        )
        record = {
            "race_id": rid, "cohort": "UPSTREAM_PIT_CERTIFIED" if attested else "PROSPECTIVE_NOT_PIT_CERTIFIED",
            "source_model_original_sha256": item["model_sha256"],
            "source_cohort_index_sha256": item["cohort_index_sha256"],
            "source_model_path": item["original_model_path"],
            "source_database_sha256": model.get("source_database_sha256"),
            "model_as_of_utc": model.get("as_of_utc"),
            "model_created_at_utc": model.get("report_created_at_utc"),
            "race_start_utc": race.get("start_time_utc"),
            "original_result_receipts": [], "complete_active_field": bool(active and not reasons),
            "active_runners": len(active or []), "winner_selection_id": None,
            "status": "NOT_EVALUABLE", "reasons": sorted(set(reasons)),
            "score": None, "market_baseline_available": bool(pmarket),
            "bet_authority": False,
        }
        if start is None or current <= start:
            record["reasons"].append("RACE_NOT_YET_STARTED")
        elif not fetch_official:
            record["reasons"].append("OFFICIAL_RESULTS_NOT_FETCHED")
        elif active and not reasons:
            match = re.fullmatch(r"RIKSTOTO:([A-Z0-9_-]+):([0-9]+)", rid)
            if match is None or int(match.group(2)) != race.get("race_no"):
                record["reasons"].append("PHYSICAL_RACE_ID_INVALID")
            else:
                key, number = match.group(1), int(match.group(2))
                path = output_dir / ("official-" + digest(rid.encode())[:16])
                path.mkdir()
                complete, r1 = _capture(
                    api, f"/results/raceDays/{key}/{number}/completeresults",
                    path, "complete",
                )
                raceday, r2 = _capture(
                    api, f"/results/racedays/{key}/raceresults", path, "raceday",
                )
                record["original_result_receipts"] = [r1, r2]
                for receipt in (r1, r2):
                    when = clock(receipt["observed_at_utc"])
                    if (receipt["error_kind"] is not None or when is None
                            or when <= start):
                        record["reasons"].append(
                            receipt["error_kind"] or "OFFICIAL_RESULT_OBSERVED_BEFORE_START"
                        )
                if complete is not None and raceday is not None and not record["reasons"]:
                    winner, why = _official_winner(
                        complete, raceday, active=active, race_no=number
                    )
                    if why is not None:
                        record["reasons"].append(why)
                    elif p1 is not None and p2 is not None:
                        record["winner_selection_id"] = winner
                        record["score"] = {
                            "champion_log_loss": log_loss(p1, winner),
                            "champion_multiclass_brier": multiclass_brier(p1, winner),
                            "core004_log_loss": log_loss(p2, winner),
                            "core004_multiclass_brier": multiclass_brier(p2, winner),
                        }
                        if pmarket is not None:
                            record["score"].update({
                                "market_log_loss": log_loss(pmarket, winner),
                                "market_multiclass_brier": multiclass_brier(pmarket, winner),
                            })
                        record["status"] = "EVALUABLE_RESEARCH_ONLY"
                        # Start number is source-confirmed, not a stable cross-provider ID.
                        record["winner_identity_scope"] = "OFFICIAL_IN_RACE_START_NUMBER_NOT_STABLE_CROSS_PROVIDER_ID"
        record["reasons"] = sorted(set(record["reasons"]))
        output["records"].append(record)

    present = {row["race_id"] for row in output["records"]}
    for rid in expected_races:
        if rid not in present:
            output["records"].append({
                "race_id": rid, "cohort": "PROSPECTIVE_NOT_PIT_CERTIFIED",
                "status": "NOT_EVALUABLE", "reasons": ["NO_VERIFIED_FROZEN_MODEL"],
                "source_model_original_sha256": None,
                "complete_active_field": False, "active_runners": 0,
                "winner_selection_id": None, "score": None,
                "market_baseline_available": False, "original_result_receipts": [],
                "bet_authority": False,
            })
    output["records"].sort(key=lambda row: row["race_id"])
    paired = [row for row in output["records"] if row["score"] is not None]
    metric_keys = ("champion_log_loss", "champion_multiclass_brier",
                   "core004_log_loss", "core004_multiclass_brier")
    output["metrics_by_cohort"] = {}
    for cohort_name in ("UPSTREAM_PIT_CERTIFIED", "PROSPECTIVE_NOT_PIT_CERTIFIED"):
        group = [r for r in paired if r["cohort"] == cohort_name]
        if group:
            values = {key: math.fsum(r["score"][key] for r in group) / len(group)
                      for key in metric_keys}
            values["core004_minus_champion_log_loss"] = (
                values["core004_log_loss"] - values["champion_log_loss"]
            )
            values["core004_minus_champion_brier"] = (
                values["core004_multiclass_brier"] - values["champion_multiclass_brier"]
            )
            output["metrics_by_cohort"][cohort_name] = {
                "physical_races": len(group), "metrics": values,
            }
        else:
            output["metrics_by_cohort"][cohort_name] = {
                "physical_races": 0, "metrics": None,
            }
    if paired and len({r["cohort"] for r in paired}) == 1:
        metric = {key: math.fsum(r["score"][key] for r in paired) / len(paired)
                  for key in metric_keys}
        metric["core004_minus_champion_log_loss"] = (
            metric["core004_log_loss"] - metric["champion_log_loss"]
        )
        metric["core004_minus_champion_brier"] = (
            metric["core004_multiclass_brier"] - metric["champion_multiclass_brier"]
        )
        with_market = [row for row in paired if "market_log_loss" in row["score"]]
        metric["market_paired_races"] = len(with_market)
        for key in ("market_log_loss", "market_multiclass_brier"):
            metric[key] = (
                math.fsum(r["score"][key] for r in with_market) / len(with_market)
                if with_market else None
            )
        output["metrics"] = metric
    output["counts"] = {
        "physical_races": len(output["records"]),
        "complete_prediction_fields": sum(r["complete_active_field"] for r in output["records"]),
        "official_results_verified": len(paired),
        "paired_champion_core004": len(paired),
        "pit_certified_paired": sum(
            r["cohort"] == "UPSTREAM_PIT_CERTIFIED" for r in paired
        ),
        "prospective_not_pit_certified_paired": sum(
            r["cohort"] != "UPSTREAM_PIT_CERTIFIED" for r in paired
        ),
        "not_evaluable": len(output["records"]) - len(paired),
    }
    # Descriptive only; no calibration claim with an inadequate physical-race n.
    output["calibration"] = {"status": "INSUFFICIENT_DISTINCT_RACES",
                             "min_distinct_races": 30, "bins": None}
    if len(paired) >= 30 and len({r["cohort"] for r in paired}) == 1:
        # Never compute calibration from per-runner data for the wrong snapshot.
        by_sha = {item["model_sha256"]: item["model"] for item in models}
        values = []
        for row in paired:
            original_model = by_sha[row["source_model_original_sha256"]]
            winner = row["winner_selection_id"]
            values.extend(
                (float(h["champion_p_win"]), h["selection_id"] == winner)
                for h in original_model["runners"] if h["scratched"] is False
            )
        bins = calibration_bins(values, width=0.1)
        output["calibration"] = {
            "status": "DESCRIPTIVE_UNCALIBRATED" if all(
                b["n"] >= 20 for b in bins
            ) else "SPARSE_BINS_NO_CALIBRATION_CLAIM",
            "min_distinct_races": 30, "bins": bins,
        }
    output["status"] = "EVALUABLE_RESEARCH_ONLY" if paired else "NOT_EVALUABLE"
    with (output_dir / "index.json").open("x", encoding="utf-8") as out:
        json.dump(output, out, indent=2, sort_keys=True, ensure_ascii=False,
                  allow_nan=False)
        out.write("\n")
    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models-root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--attestation-index", type=Path)
    p.add_argument("--fetch-official", action="store_true")
    a = p.parse_args(argv)
    report = evaluate_archive(
        models_root=a.models_root, output_dir=a.output_dir,
        attestation_index=a.attestation_index, fetch_official=a.fetch_official,
    )
    print(json.dumps({"schema": report["schema"], "status": report["status"],
                      "counts": report["counts"], "bet_authority": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
