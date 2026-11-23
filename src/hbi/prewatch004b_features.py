"""PREWATCH-004B: source-preserving historic feature diagnostics for all races.

Consumes exact original Collector ZIP via the existing P0 verifier and reuses the
M7B1 history_semantics research adapter. Parser-extracted PDF cells and programme
history lines are NOT official historical result gold, permanent horse identity,
provider publication PIT, or authorized Champion features.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .collector_handoff import OriginalArchive, name_key
from .history_semantics import VERSION as SEMANTIC_VERSION
from .history_semantics import normalize_prior
from .prewatch004_pack import _write_once, digest, make_day_packs

SCHEMA = "PREWATCH004B_VERIFIED_FEATURE_AUDIT_V1"
PACK_SCHEMA = "PREWATCH004B_RACE_FEATURE_CONTEXT_V1"
UNKNOWN = "UNKNOWN"
STATUS = ("VERIFIED", "PARTIAL", "UNKNOWN", "BLOCKED")
# Deliberately no guessed track register: track abbreviations can collide.
CODEBOOK = {
    "schema": "M7B1_HISTORY_CODEBOOK_V1",
    "version": SEMANTIC_VERSION,
    "track_register": {},
}


def _utc(raw: str) -> datetime:
    instant = datetime.fromisoformat(raw)
    if instant.utcoffset() is None:
        raise ValueError("PREWATCH004B_NAIVE_SOURCE_CLOCK")
    return instant.astimezone(UTC)


def _field(value: Any, status: str, *, denominator: int = 0,
           basis: str, source_sha256: str | None = None) -> dict[str, Any]:
    if status not in STATUS or type(denominator) is not int or denominator < 0:
        raise ValueError("PREWATCH004B_UNSUPPORTED_FEATURE_STATUS")
    return {
        "value": value, "status": status, "denominator": denominator,
        "basis": basis, "source_sha256": source_sha256,
        "bet_authority": False,
    }


def build_feature_context(
    pack: dict[str, Any], original_doc: dict[str, Any],
) -> dict[str, Any]:
    """Bind every prior line back to the immutable, already reconciled PDF."""
    if pack.get("schema") != "PREWATCH004_RACE_INTELLIGENCE_SOURCE_V1":
        raise ValueError("PREWATCH004B_UNTRUSTED_SOURCE_PACK")
    race = pack["race"]
    if (original_doc.get("race", {}).get("meeting_id")
            != pack["race_id"].split(":")[1]
            or original_doc["race"].get("race_number") != race["race_number"]):
        raise ValueError("PREWATCH004B_PHYSICAL_RACE_MISMATCH")
    observed = _utc(pack["source"]["observed_at_utc"])
    start = _utc(race["start_time_utc"])
    if observed >= start:
        raise ValueError("PREWATCH004B_SNAPSHOT_NOT_BEFORE_START")
    day = date.fromisoformat(pack["date_oslo"])
    entrants = original_doc.get("entrants")
    if not isinstance(entrants, list):
        raise TypeError("PREWATCH004B_ORIGINAL_ENTRANTS_REQUIRED")
    by_number = {}
    for entrant in entrants:
        if not isinstance(entrant, dict) or type(entrant.get("program_number")) is not int:
            raise ValueError("PREWATCH004B_ORIGINAL_NUMBER_INVALID")
        number = str(entrant["program_number"])
        if number in by_number:
            raise ValueError("PREWATCH004B_DUPLICATE_ORIGINAL_NUMBER")
        by_number[number] = entrant
    if {x["selection_id"] for x in pack["runners"]} != set(by_number):
        raise ValueError("PREWATCH004B_FULL_FIELD_ORIGINAL_MISMATCH")

    enriched = []
    for runner in pack["runners"]:
        number = runner["selection_id"]
        original = by_number[number]
        if name_key(original.get("name", "")) != name_key(runner["horse_name"]):
            raise ValueError("PREWATCH004B_HORSE_IDENTITY_CONFLICT")
        priors = original.get("past_starts")
        if not isinstance(priors, list) or len(priors) != len(runner["source_history"]):
            raise ValueError("PREWATCH004B_SOURCE_PRIORS_COUNT_CONFLICT")
        observations = []
        seen = set()
        for prior, pinned in zip(priors, runner["source_history"], strict=True):
            if (not isinstance(prior, dict)
                    or prior.get("raw_text") != pinned["raw_text"]
                    or digest(prior["raw_text"].encode("utf-8")) != pinned["raw_sha256"]
                    or prior.get("date") != (
                        pinned["date_candidate"] if pinned["date_candidate"] != UNKNOWN else None
                    )):
                raise ValueError("PREWATCH004B_HISTORY_ORIGINAL_BINDING_FAILED")
            sha = pinned["raw_sha256"]
            duplicated = sha in seen
            seen.add(sha)
            semantic = normalize_prior(
                prior, target_date=day.isoformat(),
                provenance={
                    "source_run_id": pack["source"]["run_id"],
                    "program_pdf_original_sha256":
                        pack["source"]["program_pdf_original_sha256"],
                    "prior_raw_sha256": sha,
                    "race_id": pack["race_id"], "selection_id": number,
                    "source_observed_at_utc": observed.isoformat(),
                    "historical_horse_identity": "UNRESOLVED",
                },
                codebook=CODEBOOK,
            )
            if (semantic["model_eligible"] is not False
                    or semantic["pit_status"] != "UNVERIFIED"
                    or semantic["allowed_use"] != "RESEARCH_ONLY"):
                raise ValueError("PREWATCH004B_UNSAFE_SEMANTIC_PROMOTION")
            event = prior.get("date")
            try:
                valid_date = (isinstance(event, str)
                              and date.fromisoformat(event) < day)
            except ValueError:
                valid_date = False
            if valid_date and event == day.isoformat():
                valid_date = False
            if duplicated:
                reasons = ["DUPLICATED_SOURCE_HISTORY_RAW_ROW"]
                state = "BLOCKED"
            elif not valid_date:
                reasons = ["MISSING_INVALID_OR_FUTURE_HISTORY_DATE"]
                state = "BLOCKED"
            elif semantic["history_accepted"] is True:
                reasons = ["OFFICIAL_HISTORIC_RESULT_NOT_INDEPENDENTLY_VERIFIED"]
                state = "PARTIAL"
            else:
                reasons = ["HISTORY_SEMANTICS_UNRESOLVED"] + semantic["exclusion_reasons"]
                state = "UNKNOWN"
            fields = semantic["fields"]
            observations.append({
                "raw_sha256": sha, "date_candidate": event or UNKNOWN,
                "source_status": "PDF_RAW_ORIGINAL_BOUND",
                "source_observed_before_target_start": True,
                "semantic_status": state,
                "semantic_adapter_version": SEMANTIC_VERSION,
                "field_candidates": {
                    key: {
                        "value": fields[key]["value"],
                        "status": fields[key]["status"],
                        "basis": fields[key]["basis"],
                    }
                    for key in (
                        "historical_date", "distance_m", "start_method",
                        "placing", "gallop_flag", "disqualification_flag",
                    )
                },
                "verified_official_result": False,
                "permanent_horse_identity_verified": False,
                "pit_certified": False,
                "problems": sorted(set(reasons)),
            })
        good = [x for x in observations if x["semantic_status"] == "PARTIAL"]
        date_candidates = [x for x in observations if x["semantic_status"] in ("PARTIAL", "UNKNOWN")
                           and isinstance(x["date_candidate"], str)
                           and x["date_candidate"] != UNKNOWN]
        extracted_distances = [x for x in good
                               if x["field_candidates"]["distance_m"]["status"] == "EXTRACTED"]
        extracted_g = [x for x in good
                       if x["field_candidates"]["gallop_flag"]["status"] == "EXTRACTED"
                       and x["field_candidates"]["gallop_flag"]["value"] is True]
        extracted_dq = [x for x in good
                        if x["field_candidates"]["disqualification_flag"]["status"] == "EXTRACTED"
                        and x["field_candidates"]["disqualification_flag"]["value"] is True]
        no_gold = ("NO_INDEPENDENT_OFFICIAL_RESULT_AND_PERMANENT_HORSE_ID_"
                   "BEFORE_TARGET_CUTOFF")
        features = {
            "raw_program_history_rows": _field(
                len(observations), "VERIFIED", denominator=len(observations),
                basis="ORIGINAL_PROGRAM_PDF_LINE_COUNT_WITH_SHA",
                source_sha256=pack["source"]["program_pdf_original_sha256"],
            ),
            "dated_prior_raw_line_candidates": _field(
                len(date_candidates), "PARTIAL" if date_candidates else "UNKNOWN",
                denominator=len(observations),
                basis="COLLECTOR_DATE_CANDIDATES_NOT_HISTORICAL_RESULT_GOLD",
            ),
            "semantic_extracted_prior_rows": _field(
                len(good), "PARTIAL" if good else "UNKNOWN",
                denominator=len(observations),
                basis="RESEARCH_HISTORY_SEMANTIC_ADAPTER_NOT_MODEL_ELIGIBLE",
            ),
            "research_extracted_distance_rows": _field(
                len(extracted_distances), "PARTIAL" if extracted_distances else "UNKNOWN",
                denominator=len(observations),
                basis="PDF_CELL_CANDIDATES_NOT_INDEPENDENTLY_VERIFIED_RESULT",
            ),
            "research_explicit_gallop_markers": _field(
                len(extracted_g), "PARTIAL" if extracted_g else "UNKNOWN",
                denominator=len(observations),
                basis="POSITIVE_PDF_MARKERS_NOT_VERIFIED_GALLOP_RATE",
            ),
            "research_explicit_dq_markers": _field(
                len(extracted_dq), "PARTIAL" if extracted_dq else "UNKNOWN",
                denominator=len(observations),
                basis="POSITIVE_PDF_MARKERS_NOT_VERIFIED_DQ_RATE",
            ),
        }
        for key in (
            "permanent_horse_id", "last_verified_start_date",
            "verified_historical_result_count", "verified_wins",
            "verified_top3", "verified_win_rate", "verified_top3_rate",
            "verified_gallop_rate", "verified_dq_rate",
            "verified_distance_history", "verified_start_method_history",
            "verified_historical_class", "opponent_strength",
        ):
            features[key] = _field(UNKNOWN, "UNKNOWN", basis=no_gold)
        for n in (3, 5, 10):
            features[f"verified_last_{n}_results"] = _field(
                UNKNOWN, "UNKNOWN", basis="INCOMPLETE_UNATTESTED_HISTORY_INDEX",
            )
        enriched.append({
            "selection_id": number, "horse_name": runner["horse_name"],
            "scratched": runner["scratched"],
            "post_position_asof_capture": runner["post_position"],
            "source_history_count": len(observations),
            "research_source_extractions": observations,
            "verified_racing_features": features,
            "historical_results_with_original_PIT_and_identity": 0,
            "permanent_identity_attested": False,
            "pit_eligible": False, "model_eligible": False,
            "bet_authorized": False,
        })

    return {
        "schema": PACK_SCHEMA,
        "race_id": pack["race_id"], "source_run_id": pack["source"]["run_id"],
        "source_race_pack_sha256": digest(
            (json.dumps(pack, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        ),
        "source": pack["source"],
        "race": pack["race"],
        "listed_count": len(enriched),
        "active_count": sum(not r["scratched"] for r in enriched),
        "runners": enriched,
        "historical_feature_admission": "BLOCKED_WITHOUT_INDEPENDENT_ORIGINAL_RESULT_PIT",
        "history_semantics": "RESEARCH_ONLY",
        "phase_a_status": "NOT_RUN",
        "pit_certified": False, "bet_authorized": False,
    }


def coverage_report(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    if len({x["race_id"] for x in contexts}) != len(contexts):
        raise ValueError("PREWATCH004B_DUPLICATE_PHYSICAL_RACE")
    active = [r for x in contexts for r in x["runners"] if not r["scratched"]]
    listed = [r for x in contexts for r in x["runners"]]
    def summarise(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "total": len(rows),
            "with_raw_history": sum(r["source_history_count"] > 0 for r in rows),
            "raw_history_ge3": sum(r["source_history_count"] >= 3 for r in rows),
            "raw_history_ge5": sum(r["source_history_count"] >= 5 for r in rows),
            "raw_history_ge10": sum(r["source_history_count"] >= 10 for r in rows),
            "semantic_extracted_ge1": sum(any(
                q["semantic_status"] == "PARTIAL" for q in r["research_source_extractions"]
            ) for r in rows),
            "with_extracted_distance": sum(any(
                q["field_candidates"]["distance_m"]["status"] == "EXTRACTED"
                and q["semantic_status"] == "PARTIAL"
                for q in r["research_source_extractions"]
            ) for r in rows),
            "with_extracted_gallop_positive": sum(any(
                q["field_candidates"]["gallop_flag"]["value"] is True
                and q["semantic_status"] == "PARTIAL"
                for q in r["research_source_extractions"]
            ) for r in rows),
            "independently_verified_historic_results": 0,
            "verified_gallop_dq_history": 0,
            "verified_distance_method_history": 0,
            "permanent_cross_provider_horse_id": 0,
            "complete_pit_history_attested": 0,
        }
    by_meeting = Counter(x["race"]["track"] for x in contexts)
    return {
        "schema": SCHEMA,
        "source_run_id": contexts[0]["source_run_id"] if contexts else UNKNOWN,
        "physical_race_count_source_discovered": len(contexts),
        "tracks_discovered": dict(sorted(by_meeting.items())),
        "listed_runner_coverage": summarise(listed),
        "active_runner_coverage": summarise(active),
        "history_raw_rows_total": sum(r["source_history_count"] for r in listed),
        "history_semantic_rows_total": sum(sum(
            q["semantic_status"] == "PARTIAL" for q in r["research_source_extractions"]
        ) for r in listed),
        "independent_whole_day_denominator_verified": False,
        "original_provider_result_coverage_attested": False,
        "decision_cutoff_PIT_certified": False,
        "phase_a_completed": 0,
        "bet_authorized": False,
        "blockers": [
            "NO_INDEPENDENT_HISTORICAL_OFFICIAL_RESULT_ORIGINALS_FOR_THIS_DAILY_COHORT",
            "NO_ATTESTED_PERMANENT_HORSE_IDENTITY_FOR_TARGETS",
            "NO_COMPLETE_PRESTART_HISTORY_INDEX",
            "SOURCE_CAPTURE_DOES_NOT_PROVE_HISTORIC_PROVIDER_FIRST_PUBLICATION",
            "PDF_RESEARCH_SEMANTICS_NOT_OFFICIAL_HISTORICAL_RESULT_GOLD",
        ],
    }


def make_feature_day_packs(
    archive: Path, checksum: Path, dest: Path, *, day: str | None = None,
) -> dict[str, Any]:
    """Revalidate entire original archive, then make immutable diagnostics."""
    with tempfile.TemporaryDirectory(prefix="prewatch004b-") as work:
        source_dir = Path(work) / "source"
        p0 = make_day_packs(archive, checksum, source_dir, date_oslo=day)
        source = OriginalArchive(archive)
        original_docs = {}
        meeting_ids = {
            ref["race_id"].split(":")[1] for ref in p0["source_packs"]
        }
        for mid in meeting_ids:
            path = f"{source.prefix}meetings/{mid}/structured_program.json"
            raw = source.read(path)
            for doc in json.loads(raw)["races"]:
                key = (mid, doc["race"]["race_number"])
                if key in original_docs:
                    raise ValueError("PREWATCH004B_DUPLICATE_PHYSICAL_RACE")
                original_docs[key] = doc
        outputs = []
        for record in p0["source_packs"]:
            source_path = source_dir / record["file"]
            raw = source_path.read_bytes()
            if digest(raw) != record["sha256"]:
                raise ValueError("PREWATCH004B_P0_SOURCE_HASH_CONFLICT")
            pack = json.loads(raw)
            mid = pack["race_id"].split(":")[1]
            n = pack["race"]["race_number"]
            if (mid, n) not in original_docs:
                raise ValueError("PREWATCH004B_ORIGINAL_RACE_NOT_FOUND")
            enriched = build_feature_context(pack, original_docs[(mid, n)])
            fname = f"features_{mid}_{n}.json"
            content = (json.dumps(enriched, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
            outputs.append((fname, content, enriched))
        report = coverage_report([entry for _, _, entry in outputs])
        report["source_original_archive_sha256"] = p0["source_packs"][0]["sha256"] if False else UNKNOWN
        report["source_p0_races"] = p0["source_discovered_physical_races"]
        report["source_p0_listed_runners"] = p0["listed_runners"]
        report["files"] = [{"filename": f, "sha256": digest(raw)}
                           for f, raw, _ in outputs]
        if dest.is_symlink():
            raise ValueError("PREWATCH004B_OUTPUT_DIRECTORY_SYMLINK")
        dest.mkdir(parents=True, exist_ok=True)
        for filename, raw, _ in outputs:
            _write_once(dest / filename, raw)
        _write_once(dest / "features_coverage.json",
                    (json.dumps(report, sort_keys=True, indent=2) + "\n").encode())
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="PREWATCH-004B offline historic feature diagnostics (NO BET)")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date-oslo")
    args = parser.parse_args()
    report = make_feature_day_packs(
        args.archive, args.checksum, args.output, day=args.date_oslo,
    )
    print(json.dumps({
        key: value for key, value in report.items() if key != "files"
    }, sort_keys=True))


if __name__ == "__main__":
    main()
