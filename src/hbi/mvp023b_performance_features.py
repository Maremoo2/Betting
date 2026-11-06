"""MVP-023B/P1-B: historic performance features, source-replayed, no model/PIT.

Uses independently bound M7B1A NO official historical start rows; never
links by horse name and does not open any 2025 source *member*. The underlying
2026 target sample is already exposed and NOT 2015-2024 training proof.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from .date_overview import DailyArchive
from .history_semantic_benchmark import KNOWN_SHA
from .history_source_verification import (
    PROGRAM_SHA,
    SOURCE_SHA,
    bind_verified,
    dnt_review,
)
from .pdf_semantic_validation import checked_bytes, truth_data
from .pdf_validation import sha

SCHEMA = "MVP023B_HORSE_PERFORMANCE_RESEARCH_V1"
SHA = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^DNT_REGISTRATION:[1-9]\d+$")
RID = re.compile(r"^RIKSTOTO:[A-Z0-9]+_NR_(20\d{2}-\d{2}-\d{2}):[1-9]\d*$")


def replay_existing_no_2026_originals(root: Path) -> list[dict]:
    """Source-bound 2026 NO prior results only, using existing M7B1A reviews.

    ZIP is SHA pinned, but no 2025 original ZIP member is decompressed/read.
    Every selected result is validated against a stable 2026 target
    registration and exact prior race/date/provider official result row.
    """
    root = Path(root)
    fixtures = root / "tests/fixtures"
    raw = checked_bytes(fixtures / "m7b1a-official-sources-v1.zip", SOURCE_SHA)
    claims = json.loads((root / "docs/M7B1A_REVIEW_CLAIMS.json").read_bytes())
    register = json.loads((root / "docs/M7B1A_TRACK_REGISTER.json").read_bytes())
    truth = truth_data(fixtures / "m7a1-ground-truth-v1.json", KNOWN_SHA)
    by_id = {row["observation_id"]: row for row in truth["rows"]}
    program = DailyArchive(fixtures / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    if claims.get("schema") != "M7B1A_OBSERVATION_REVIEW_CLAIMS_V1":
        raise ValueError("UNREGISTERED_OFFICIAL_REVIEW_CLAIMS")
    if not claims.get("no_cases"):
        raise ValueError("NO_AUTHENTIC_OFFICIAL_NO_HISTORY_ROWS")
    output = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = archive.infolist()
        names = [f.filename for f in files]
        if (len(names) != len(set(names)) or sum(f.file_size for f in files) > 10_000_000
                or any("/" in n or "\\" in n or ".." in n for n in names)):
            raise ValueError("UNSAFE_OFFICIAL_ARCHIVE")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != "M7B1A_OFFICIAL_SOURCE_ARCHIVE_V1":
            raise ValueError("OFFICIAL_ARCHIVE_SCHEMA_CONFLICT")
        for case in claims["no_cases"]:
            row = by_id[case["observation_id"]]
            # Prohibit indirect 2025 candidate opening: only decompressed
            # member bodies that are independently registered as 2026.
            day = row["historical_date"]
            member = case["source_member"]
            if (not day.startswith("2026-")
                    or not RID.fullmatch(row["target_race_id"])
                    or "_NR_2026-" not in row["target_race_id"]
                    or "2025" in member or case["country"] != "NO"):
                raise ValueError("HISTORICAL_LOCKBOX_OR_SOURCE_SCOPE_REFUSED")
            meta = manifest["sources"][member]
            if not meta.get("url", "").endswith("/" + day):
                raise ValueError("SOURCE_MEMBER_DATE_CONFLICT")
            body = archive.read(member)
            if (sha(body) != meta.get("sha256") or len(body) != meta.get("bytes")
                    or meta.get("status") != 200):
                raise ValueError("OFFICIAL_MEMBER_ORIGINAL_SHA_MISMATCH")
            review = dnt_review(row, case, (meta, body), program)
            bound = bind_verified(row, review, register)
            if bound["status"] != "VERIFIED" or bound["pit_status"] != "UNVERIFIED":
                raise ValueError("UNEXPECTED_ORIGINAL_VERIFICATION_STATE")
            output.append({
                "observation_id": row["observation_id"],
                "target_race_id": row["target_race_id"],
                "target_selection_id": str(row["target_program_number"]),
                "horse_identity": review["horse_identity"],
                "historical_date": day,
                "historical_race_number": row["historical_race_number"],
                "historical_track": review["track"]["name"],
                "historical_country": "NO",
                "values": dict(review["values"]),
                "source": {
                    "archive_sha256": SOURCE_SHA,
                    "member": member, "member_sha256": meta["sha256"],
                    "url": meta["url"], "observed_at": meta["observed_at"],
                    "target_program_sha256": PROGRAM_SHA,
                    "target_pdf_sha256": row["pdf_sha256"],
                },
                "identity_method": bound["method"],
                "historical_asof_attested": False,
                "model_eligible": False, "bet_authority": False,
            })
    return output


def _result(value: object, disqualified: object) -> str:
    if disqualified is True:
        if type(value) is int and value > 0:
            raise ValueError("DISQUALIFICATION_AND_POSITIVE_PLACING_CONFLICT")
        return "DQ"
    if type(value) is int and value > 0:
        return "WIN" if value == 1 else "PLACED" if value <= 3 else "FINISHED"
    if value == "UNPLACED":
        return "UNPLACED"
    if value in ("UNKNOWN", "NOT_REPORTED", None):
        return "UNKNOWN"
    raise ValueError("UNSUPPORTED_HISTORICAL_RESULT_SEMANTICS")


def _safe_value(row: dict) -> dict:
    values = row.get("values")
    if not isinstance(values, dict):
        raise ValueError("ORIGINAL_OFFICIAL_VALUES_REQUIRED")
    allowed = {"placing", "distance_m", "km_time", "start_method",
               "gallop_flag", "disqualification_flag"}
    if set(values) != allowed:
        raise ValueError("UNREVIEWED_MARKET_OR_FUTURE_RESULT_FIELD")
    result = _result(values["placing"], values["disqualification_flag"])
    distance = values["distance_m"]
    if type(distance) is not int or not 300 <= distance <= 9999:
        raise ValueError("INVALID_HISTORY_DISTANCE_UNIT")
    km = values["km_time"]
    if (type(km) in (int, float) and not (40 <= km <= 300)
            or type(km) not in (int, float) and km != "NOT_REPORTED"):
        raise ValueError("KM_TIME_SEMANTICS_UNVERIFIED")
    method = values["start_method"]
    if method not in {"AUTO", "VOLT", "UNKNOWN"}:
        raise ValueError("UNKNOWN_START_METHOD_SEMANTICS")
    for kind in ("gallop_flag", "disqualification_flag"):
        flag = values[kind]
        if type(flag) is not bool and flag != "NOT_REPORTED":
            raise ValueError("AMBIGUOUS_EVENT_CODE_NOT_BOOLEAN")
    return {"result": result, "distance_m": distance,
            "km_time_s_per_km": km if type(km) in (int, float) else None,
            "start_method": method,
            "gallop": values["gallop_flag"],
            "dq": values["disqualification_flag"]}


def build_performance_features(rows: list[dict], *, evidence_mode: str = "TEST_ONLY") -> dict:
    """Aggregate only observed, independently bound *prior* starts.

    Public aggregation is TEST_ONLY by default. An authentic claim requires
    invocation through replay_existing_no_2026_originals(), not caller JSON.
    Even original replay remains retrospective and never PIT/model-eligible.
    """
    if evidence_mode not in {"TEST_ONLY", "SOURCE_REPLAYED_NO_2026"}:
        raise ValueError("UNSUPPORTED_RESEARCH_EVIDENCE_MODE")
    seen, identity, groups = set(), {}, defaultdict(list)
    if not isinstance(rows, list):
        raise ValueError("EXPECTED_VERIFIED_PRIOR_START_LIST")
    for item in rows:
        if not isinstance(item, dict) or item.get("model_eligible") is not False:
            raise ValueError("UNVERIFIED_PRIOR_START_OR_PREMATURE_MODEL_APPROVAL")
        target = item.get("target_race_id")
        match = RID.fullmatch(str(target))
        if match is None or match.group(1).startswith("2025"):
            raise ValueError("TARGET_RACE_OR_2025_LOCKBOX_REFUSED")
        prior = date.fromisoformat(item["historical_date"])
        target_date = date.fromisoformat(match.group(1))
        if prior.year == 2025:
            raise ValueError("CANDIDATE_2025_HISTORICAL_LOCKBOX_UNOPENED")
        if prior >= target_date:
            raise ValueError("FUTURE_OR_SAME_DAY_HISTORY_LEAKAGE")
        name = item.get("horse_identity")
        if not isinstance(name, str) or ID.fullmatch(name) is None:
            raise ValueError("BLOCKED_IDENTITY_NAME_TMP_OR_ATG_NOT_STABLE_DNT_ID")
        selection_id = item.get("target_selection_id")
        if not isinstance(selection_id, str) or not selection_id.isdecimal() or int(selection_id) <= 0:
            raise ValueError("TARGET_SELECTION_ID_MISSING")
        target_key = (target, selection_id)
        if target_key in identity and identity[target_key] != name:
            raise ValueError("CROSS_START_HORSE_IDENTITY_COLLISION")
        identity[target_key] = name
        source = item.get("source")
        if (not isinstance(source, dict)
                or not SHA.fullmatch(str(source.get("archive_sha256", "")))
                or not SHA.fullmatch(str(source.get("member_sha256", "")))
                or not SHA.fullmatch(str(source.get("target_program_sha256", "")))
                or not isinstance(source.get("url"), str)
                or not source["url"].startswith("https://www.travsport.no/travbaner/")
                or not isinstance(source.get("member"), str)
                or "2025" in source["member"]
                or not isinstance(source.get("observed_at"), str)
                or item.get("identity_method") != "EXACT_OFFICIAL_HISTORICAL_RACE_AND_STABLE_HORSE_CHAIN"
                or item.get("historical_asof_attested") is not False
                or item.get("bet_authority") is not False):
            raise ValueError("ORIGINAL_IDENTITY_TIME_OR_SOURCE_RECEIPT_MISSING")
        history_race = (item.get("historical_country"), item.get("historical_track"),
                        item["historical_date"], item.get("historical_race_number"), name)
        if history_race in seen:
            raise ValueError("DUPLICATE_PHYSICAL_HISTORICAL_START")
        seen.add(history_race)
        values = _safe_value(item)
        groups[target_key].append({**values,
            "historical_date": prior.isoformat(), "source_start_id": (
                f"{history_race[0]}:{history_race[1]}:{prior}:{history_race[3]}:{name}"
            ), "source_sha256": source["member_sha256"],
            "source_url": source["url"], "observed_at": source["observed_at"]})
    assembled = []
    for (target, selection), prior_rows in sorted(groups.items()):
        prior_rows.sort(key=lambda h: (h["historical_date"], h["source_start_id"]), reverse=True)
        qualified = [r for r in prior_rows if r["result"] != "UNKNOWN"]
        def ratio(selected: list[dict], measure) -> dict:
            eligible = [h for h in selected if h["result"] != "UNKNOWN"]
            return {"value": (sum(bool(measure(h)) for h in eligible) / len(eligible)
                              if eligible else None),
                    "denominator": len(eligible),
                    "source_start_ids": [h["source_start_id"] for h in eligible],
                    "status": "RETROSPECTIVE_ONLY" if eligible else "MISSING"}
        facts = {
            "observed_prior_starts": {"value": len(prior_rows), "denominator": len(prior_rows),
                "history_completeness": "UNKNOWN", "status": "RETROSPECTIVE_ONLY"},
            "days_since_latest_observed_start": {
                "value": (date.fromisoformat(target.split("_NR_")[1][:10])
                          - date.fromisoformat(prior_rows[0]["historical_date"])).days,
                "last_observed_not_proven_last_actual": True,
                "status": "RETROSPECTIVE_ONLY"},
            "observed_win_rate": ratio(qualified, lambda r: r["result"] == "WIN"),
            "observed_top3_rate": ratio(qualified, lambda r: r["result"] in {"WIN", "PLACED"}),
            "observed_gallop_rate": {
                "value": None, "denominator": 0, "status": "MISSING",
                "reason": "NEGATIVE_GALLOP_NOT_EXPLICITLY_REPORTED"},
            "observed_dq_rate": {
                "value": None, "denominator": 0, "status": "MISSING",
                "reason": "NEGATIVE_DQ_NOT_EXPLICITLY_REPORTED"},
        }
        for n in (3, 5, 10):
            selected = prior_rows[:n]
            facts[f"last_{n}_observed_results"] = {
                "value": [{"source_start_id": r["source_start_id"],
                           "historical_date": r["historical_date"],
                           "result": r["result"]} for r in selected],
                "denominator": len(selected), "history_completeness": "UNKNOWN",
                "status": "RETROSPECTIVE_ONLY"}
            facts[f"last_{n}_observed_win_rate"] = ratio(
                selected, lambda r: r["result"] == "WIN")
        methods = Counter(r["start_method"] for r in prior_rows if r["start_method"] != "UNKNOWN")
        distances = Counter(str(r["distance_m"]) for r in prior_rows)
        facts["observed_start_method_counts"] = {
            "value": dict(sorted(methods.items())), "denominator": sum(methods.values()),
            "target_method_comparability": "UNKNOWN", "status": "RETROSPECTIVE_ONLY"}
        facts["observed_distance_counts_m"] = {
            "value": dict(sorted(distances.items())), "denominator": sum(distances.values()),
            "target_distance_comparability": "UNKNOWN", "status": "RETROSPECTIVE_ONLY"}
        contexts = defaultdict(list)
        for r in prior_rows:
            if r["km_time_s_per_km"] is not None and r["start_method"] != "UNKNOWN":
                contexts[(r["distance_m"], r["start_method"])].append(r)
        comparative = {f"{dist}:{method}": records for (dist, method), records in contexts.items()
                       if len(records) >= 2}
        facts["mean_km_time_same_distance_method"] = {
            "value": {key: mean(r["km_time_s_per_km"] for r in values)
                      for key, values in sorted(comparative.items())} or None,
            "denominator": {key: len(values) for key, values in sorted(comparative.items())},
            "status": "RETROSPECTIVE_ONLY" if comparative else "MISSING",
            "reason": "NO_REPLICATED_IDENTICAL_DISTANCE_METHOD_CONTEXT" if not comparative else None}
        for key in ("driver", "trainer", "opponent_strength", "target_post_position_context"):
            facts[key] = {"value": None, "status": "BLOCKED_SOURCE",
                          "reason": "NOT_IN_VERIFIED_HISTORICAL_OFFICIAL_RESULTS"}
        assembled.append({
            "target_race_id": target, "target_selection_id": selection,
            "horse_identity": identity[(target, selection)],
            "observed_start_source_ids": [r["source_start_id"] for r in prior_rows],
            "observed_source_sha256": [r["source_sha256"] for r in prior_rows],
            "prior_start_count": len(prior_rows),
            "features": facts, "qualification": "RETROSPECTIVE_PERFORMANCE_RECONSTRUCTION",
            "asof_verified": False, "pit_verified": False, "model_eligible": False,
            "bet_authority": False,
        })
    return {
        "schema": SCHEMA, "evidence_mode": evidence_mode,
        "source_scope": "EXPOSED_2026_NO_DNT_VERIFIED_PRIOR_STARTS"
        if evidence_mode == "SOURCE_REPLAYED_NO_2026" else "TEST_ONLY",
        "source_observations": len(rows), "unique_horses_for_target": len(assembled),
        "historical_date_years": sorted({r["historical_date"][:4] for r in rows}),
        "materialized": assembled,
        "retrospective_qualified_horses": len(assembled),
        "historical_asof_verified_horses": 0, "trained_model": False,
        "2025_lockbox_opened": False, "model_eligible_races": 0,
        "fundamental_training_ready": False, "benter_fit_ready": False,
        "bet_authority": False,
        "limits": [
            "Verified individual starts are NOT a complete horse lifetime history.",
            "Last-N represents N latest *observed* starts only, not guaranteed true career last N.",
            "Original historical provider observed dates are not first-publication PIT receipts.",
            "Target data and original official results are from exposed 2026; no 2015-24 training claim.",
        ],
    }


def run_authentic_research(root: Path) -> dict:
    return build_performance_features(
        replay_existing_no_2026_originals(root),
        evidence_mode="SOURCE_REPLAYED_NO_2026",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_authentic_research(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
