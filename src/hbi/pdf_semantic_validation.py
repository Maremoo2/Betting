"""Compare a frozen manual PDF transcription with the existing collector parser.

No historical field is extracted by this module. It only reads manual expected
values, invokes the reviewed parser, and scores its existing output fields.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from .date_overview import timestamp
from .pdf_validation import PARSER_SHA256, load_parser, physical_candidates, sha, verify_flying_finn
from .provider_capability import name_key

FIELDS = {
    "historical_date": "date", "historical_track": "track", "historical_race_number": "race_number",
    "distance_m": "distance_m", "start_method": "start_method", "placing": "placing",
    "km_time": "kilometre_time", "gallop_flag": "gallop_flag",
    "disqualification_flag": "disqualification_flag", "qualification_flag": "qualification_flag",
}
STATUSES = ("CORRECT", "INCORRECT", "NOT_EXTRACTED", "AMBIGUOUS_SOURCE", "NOT_APPLICABLE")
REQUIRED = {*FIELDS, "target_race_id", "target_horse_name", "target_horse_identity", "pdf_sha256",
    "pdf_page", "raw_history_line", "result_status", "source_evidence", "field_confidence", "ambiguity_reason"}
BUNDLE_SHA = "1d4108180de1a191a3df502fde0e2ff4d2b74fc3f3b6eee30b701a18cb9e81a9"


def checked_bytes(path, expected):
    raw = Path(path).read_bytes()
    if sha(raw) != expected:
        raise ValueError("INPUT_SHA256_MISMATCH")
    return raw


def truth_data(path, expected):
    truth = json.loads(checked_bytes(path, expected))
    if truth["schema"] != "M7A1_MANUAL_PDF_TRUTH_V1" or truth["version"] != "1.0.0":
        raise ValueError("UNSUPPORTED_TRUTH_VERSION")
    rows = truth["rows"]
    if len(rows) != 60 or len({r["observation_id"] for r in rows}) != 60:
        raise ValueError("SIXTY_UNIQUE_OBSERVATIONS_REQUIRED")
    starts = set()
    for row in rows:
        if not REQUIRED.issubset(row) or not set(FIELDS).issubset(row["field_confidence"]):
            raise ValueError("INCOMPLETE_TRUTH_RECORD")
        if (row["model_eligible"] is not False or row["allowed_use"] != "RESEARCH_ONLY"
                or row["pit_status"] != "UNVERIFIED"):
            raise ValueError("GROUND_TRUTH_CANNOT_ADMIT_MODELS")
        if any(row[k] is None for k in REQUIRED):
            raise ValueError("EXPLICIT_MISSINGNESS_REQUIRED")
        for key in ("historical_race_number", "distance_m"):
            value = row[key]
            if not (type(value) is int and value > 0 or value in ("UNKNOWN", "NOT_REPORTED")):
                raise ValueError("INVALID_TYPED_REFERENCE_VALUE")
        time = row["km_time"]
        if not (type(time) in (int, float) and math.isfinite(time) and time > 0 or time in ("UNKNOWN", "NOT_REPORTED")):
            raise ValueError("INVALID_TYPED_REFERENCE_VALUE")
        for key in ("gallop_flag", "disqualification_flag", "qualification_flag"):
            if type(row[key]) is not bool and row[key] not in ("UNKNOWN", "NOT_REPORTED"):
                raise ValueError("INVALID_TYPED_REFERENCE_VALUE")
        if row["start_method"] not in ("AUTO", "VOLT", "UNKNOWN", "NOT_REPORTED"):
            raise ValueError("INVALID_TYPED_REFERENCE_VALUE")
        if row["source_evidence"]["bundle_sha256"] != BUNDLE_SHA or type(row["pdf_page"]) is not int or row["pdf_page"] < 1:
            raise ValueError("INVALID_SOURCE_REFERENCE")
        event = date.fromisoformat(row["historical_date"])
        target = date.fromisoformat(row["target_race_id"].split(":")[1][-10:])
        if event >= target:
            raise ValueError("FUTURE_HISTORY_IN_TRUTH")
        key = (row["target_race_id"], row["target_horse_name"], row["historical_date"], row["historical_track"], row["historical_race_number"])
        if key in starts:
            raise ValueError("DUPLICATE_HISTORICAL_START")
        starts.add(key)
        timestamp(row["source_evidence"]["source_observed_at"])
    return truth


def classify(expected, actual):
    if expected == "UNKNOWN":
        return "AMBIGUOUS_SOURCE"
    if expected in ("NOT_REPORTED", "NOT_APPLICABLE"):
        return "NOT_APPLICABLE"
    if actual is None or actual == "":
        return "NOT_EXTRACTED"
    if isinstance(expected, bool):
        correct = type(actual) is bool and actual == expected
    elif isinstance(expected, (float, int)):
        correct = type(actual) in (int, float) and math.isfinite(actual) and actual == expected
    else:
        correct = type(actual) is str and actual == expected
    return "CORRECT" if correct else "INCORRECT"


def read_sources(bundle):
    from pypdf import PdfReader

    sources = {}
    with zipfile.ZipFile(io.BytesIO(checked_bytes(bundle, BUNDLE_SHA))) as z:
        manifest = json.loads(z.read("manifest.json"))
        for spec in manifest["sources"]:
            raw = z.read(spec["metadata_member"])
            if sha(raw) != spec["metadata_sha256"]:
                raise ValueError("SOURCE_METADATA_HASH_MISMATCH")
            meta = json.loads(raw)
            pdf = z.read(meta["pdf_member"])
            if sha(pdf) != meta["pdf_sha256"]:
                raise ValueError("ORIGINAL_PDF_HASH_MISMATCH")
            pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages]
            sources[meta["pdf_sha256"]] = (meta, pages)
    return sources


def compare(rows, parsed_sources, source_pages):
    results = []
    for row in rows:
        pages = source_pages[row["pdf_sha256"]]
        if row["pdf_page"] > len(pages):
            raise ValueError("PDF_PAGE_NOT_FOUND")
        page = pages[row["pdf_page"] - 1]
        raw = row["raw_history_line"]
        line_number = row["source_evidence"]["extracted_line_number"]
        lines = page.splitlines()
        header = row["source_evidence"]["horse_header"]
        if (page.splitlines().count(raw) != 1 or header not in lines or type(line_number) is not int
                or not 1 <= line_number <= len(lines) or lines[line_number - 1] != raw
                or lines.index(header) >= line_number - 1
                or not header.startswith(f"{row['target_program_number']} {row['target_horse_name']},")):
            raise ValueError("MANUAL_SOURCE_REFERENCE_NOT_REPRODUCIBLE")
        matches = []
        for doc, physical in parsed_sources[row["pdf_sha256"]]:
            for horse in doc["entrants"]:
                for prior in horse["past_starts"]:
                    if prior["raw_text"] == raw:
                        matches.append((horse, prior, physical))
        unique = matches[0] if len(matches) == 1 else None
        structural = "NOT_EXTRACTED"
        if unique:
            horse, prior, physical = unique
            key, number = row["target_race_id"].split(":")[1:]
            structural = "CORRECT" if (name_key(horse["name"]) == name_key(row["target_horse_name"])
                and horse["program_number"] == row["target_program_number"]
                and physical == [f"{key}#{number}"]) else "INCORRECT"
        predicted = unique[1] if unique else {}
        values = {k: {"expected": row[k], "actual": predicted.get(field),
            "status": classify(row[k], predicted.get(field))} for k, field in FIELDS.items()}
        critical = []
        if structural != "CORRECT":
            critical.append("WRONG_OR_AMBIGUOUS_HORSE_OR_PHYSICAL_RACE")
        for k, value in values.items():
            if value["status"] == "INCORRECT":
                critical.append(f"INCORRECT_MODEL_INPUT:{k}")
            if value["status"] == "NOT_EXTRACTED":
                critical.append(f"MISSING_REQUIRED_SEMANTIC_INPUT:{k}")
            if value["status"] in ("NOT_APPLICABLE", "AMBIGUOUS_SOURCE") and value["actual"] is not None:
                critical.append(f"UNSUPPORTED_SOURCE_INTERPRETATION:{k}")
        results.append({"observation_id": row["observation_id"], "source_localization": "CORRECT",
            "history_line_found": bool(matches), "parser_matches": len(matches),
            "structural_assignment": structural, "fields": values, "critical_findings": critical,
            "model_eligible": False})
    metrics = {}
    for field in FIELDS:
        counts = Counter(r["fields"][field]["status"] for r in results)
        denominator = sum(counts[s] for s in ("CORRECT", "INCORRECT", "NOT_EXTRACTED"))
        metrics[field] = {"counts": {s: counts[s] for s in STATUSES}, "total_rows": len(rows),
            "scorable_denominator": denominator, "correct_numerator": counts["CORRECT"],
            "correct_fraction": counts["CORRECT"] / denominator if denominator else None}
    return {"schema": "M7A1_SEMANTIC_COMPARISON_V1", "rows": len(rows), "field_metrics": metrics,
        "source_localization": dict(Counter(r["source_localization"] for r in results)),
        "structural_assignment": dict(Counter(r["structural_assignment"] for r in results)),
        "history_lines_found": sum(r["history_line_found"] for r in results),
        "critical_findings": dict(Counter(f for r in results for f in r["critical_findings"])),
        "observations": results, "representative": False, "model_eligible": 0}


def run(truth_path, truth_sha, bundle_path, parser_path):
    truth = truth_data(truth_path, truth_sha)
    parse = load_parser(parser_path, PARSER_SHA256)
    sources = read_sources(bundle_path)
    parsed = {}
    for pdf_hash, (meta, pages) in sources.items():
        race = meta["archived_parser_output"][0]["race"]
        output = parse("\n\n".join(pages), meeting_id=meta["meeting_id"], date=meta["date"],
            url=race["source_url"], captured_at=race["captured_at_utc"], track=race["track"])
        parsed[pdf_hash] = [(doc, physical_candidates(doc, meta["canonical_starts"])) for doc in output["races"]]
    report = compare(truth["rows"], parsed, {h: pages for h, (_, pages) in sources.items()})
    report.update(truth_sha256=truth_sha, parser_sha256=PARSER_SHA256, source_bundle_sha256=BUNDLE_SHA,
        author_independence=truth["independence"], terminal_status="M7A.1_PARTIAL", recommendation="M7B_HOLD")
    return report


def official_review(truth, archive_path, archive_sha):
    """Separate official ATG evidence, never changes manual PDF values or PIT."""
    evidence = {}
    with zipfile.ZipFile(io.BytesIO(checked_bytes(archive_path, archive_sha))) as z:
        if len(z.namelist()) != len(set(z.namelist())) or sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError("INVALID_OFFICIAL_ARCHIVE")
        manifest = json.loads(z.read("manifest.json"))
        if manifest["schema"] != "M7A1_ATG_RESULT_REVIEW_V1":
            raise ValueError("UNKNOWN_OFFICIAL_EVIDENCE_SCHEMA")
        for name, expected in manifest["files_sha256"].items():
            raw = z.read(name)
            if sha(raw) != expected:
                raise ValueError("OFFICIAL_MEMBER_HASH_MISMATCH")
            evidence[name] = json.loads(raw)
    base = verify_flying_finn(evidence)  # Existing M7A stable-ID and pedigree chain.
    pure_target = evidence["atg-2026-10-24_7_1.json"]
    target_races = pure_target["payload"]["races"]
    pure_calendar = evidence["atg-calendar-2026-10-24.json"]
    if (not pure_target["success"] or pure_target["status_code"] != 200
            or pure_target["url"] != "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-10-24_7_1"
            or len(target_races) != 1 or not pure_calendar["success"]
            or pure_calendar["payload"]["date"] != "2026-10-24"):
        raise ValueError("PURE_EGO_TARGET_UNVERIFIED")
    target = target_races[0]
    if (target["id"] != "2026-10-24_7_1" or target["date"] != "2026-10-24" or target["number"] != 1
            or target["track"]["name"] != "Jägersro" or target["track"]["countryCode"] != "SE" or target["sport"] != "trot"):
        raise ValueError("PURE_EGO_TARGET_RACE_CONFLICT")
    selected = [x for x in target["starts"] if x["horse"]["id"] == 793918]
    if (len(selected) != 1 or selected[0]["number"] != 6
            or name_key(selected[0]["horse"]["name"]) != "pureego"
            or name_key(selected[0]["horse"]["pedigree"]["father"]["name"]) != "creatine"
            or name_key(selected[0]["horse"]["pedigree"]["mother"]["name"]) != "restless"):
        raise ValueError("PURE_EGO_TARGET_IDENTITY_CONFLICT")
    for day, rid, track in [("2026-10-24", "2026-10-24_7_1", "Jägersro"), ("2026-02-25", "2026-02-25_27_8", "Umåker")]:
        calendar = evidence[f"atg-calendar-{day}.json"]
        ids = [r["id"] for t in calendar["payload"]["tracks"]
            if t["name"] == track and t["countryCode"] == "SE" and t["sport"] == "trot"
            for r in t["races"] if r["number"] == int(rid.rsplit("_", 1)[1])]
        if (not calendar["success"] or calendar["status_code"] != 200 or calendar["payload"]["date"] != day
                or calendar["url"] != f"https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/{day}?headToHeadEnabled=true"
                or ids != [rid]):
            raise ValueError("PURE_EGO_CALENDAR_CONFLICT")
    timestamp(pure_target["observed_at"])
    pure_proof = {"stable_identity": "ATG_HORSE:793918", "target_race": target["id"],
        "source_url": pure_target["url"], "observed_at": pure_target["observed_at"],
        "proof": "EXACT_TARGET_FIELD_SELECTION_AND_PDF_NAME_SIRE_DAM_PLUS_SAME_HISTORICAL_STABLE_ID",
        "model_eligible": False, "pit_status": "UNVERIFIED"}
    reviewed = []
    for row in truth["rows"]:
        is_flying = row["target_horse_name"] == "FLYING FINN"
        is_pure = row["target_horse_name"] == "PURE EGO" and row["historical_date"] == "2026-02-25"
        if not (is_flying or is_pure):
            continue
        track_id, horse_id, track_name = (5, 788027, "Solvalla") if is_flying else (27, 793918, "Umåker")
        rid = f"{row['historical_date']}_{track_id}_{row['historical_race_number']}"
        member = f"atg-{rid}.json"
        envelope = evidence[member]
        if (envelope["url"] != f"https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{rid}"
                or not envelope["success"] or envelope["status_code"] != 200):
            raise ValueError("OFFICIAL_SOURCE_NOT_VERIFIED")
        timestamp(envelope["observed_at"])
        races = envelope["payload"]["races"]
        if len(races) != 1:
            raise ValueError("AMBIGUOUS_OFFICIAL_RACE")
        race = races[0]
        if (race["id"] != rid or race["date"] != row["historical_date"]
                or race["number"] != row["historical_race_number"] or race["sport"] != "trot"
                or race["track"]["countryCode"] != "SE" or race["track"]["name"] != track_name
                or row["historical_track"] != ("S" if is_flying else "U")):
            raise ValueError("OFFICIAL_RACE_CONFLICT")
        starts = race["starts"]
        if len({s["number"] for s in starts}) != len(starts) or len({s["horse"]["id"] for s in starts}) != len(starts):
            raise ValueError("OFFICIAL_FIELD_IDENTITY_CONFLICT")
        selected = [s for s in starts if s["horse"]["id"] == horse_id]
        if len(selected) != 1:
            raise ValueError("OFFICIAL_HORSE_IDENTITY_UNRESOLVED")
        horse = selected[0]["horse"]
        if (name_key(horse["name"]) != ("flyingfinn" if is_flying else "pureego")
                or name_key(horse["pedigree"]["father"]["name"]) != ("readlyexpress" if is_flying else "creatine")
                or name_key(horse["pedigree"]["mother"]["name"]) != ("railin" if is_flying else "restless")):
            raise ValueError("OFFICIAL_HORSE_IDENTITY_CONFLICT")
        result = selected[0]["result"]
        placing = result.get("place")
        if not (type(placing) is int and placing >= 0 or result.get("disqualified") is True):
            raise ValueError("OFFICIAL_RESULT_INCOMPLETE")
        time = result.get("kmTime", {})
        numeric_time = (60 * time["minutes"] + time["seconds"] + time["tenths"] / 10
            if set(time) == {"minutes", "seconds", "tenths"} and all(type(v) is int for v in time.values()) else None)
        official = {"placing": result.get("place"), "km_time": numeric_time,
            "gallop_flag": result.get("galloped"), "disqualification_flag": result.get("disqualified"),
            "distance_m": selected[0]["distance"], "start_method": {"auto": "AUTO", "volt": "VOLT", "volte": "VOLT"}.get(race["startMethod"])}
        comparisons = {field: classify(row[field], value) for field, value in official.items()}
        reviewed.append({"observation_id": row["observation_id"], "race_id": rid,
            "horse_identity": f"ATG_HORSE:{horse_id}", "identity_proof": base if is_flying else pure_proof,
            "raw_official_result": result, "official_values": official, "pdf_values": {k: row[k] for k in official},
            "comparison": comparisons, "result_status": ("CONFLICT" if "INCORRECT" in comparisons.values()
                else "UNRESOLVED" if "NOT_EXTRACTED" in comparisons.values() else "RESULT_VERIFIED"),
            "source": {"archive_sha256": archive_sha, "member": member, "member_sha256": manifest["files_sha256"][member],
                "url": envelope["url"], "observed_at": envelope["observed_at"]},
            "role": "RETROSPECTIVE_LABEL_REVIEW_ONLY", "pit_status": "UNVERIFIED", "model_eligible": False})
    return {"reviewed": len(reviewed), "status_counts": dict(Counter(r["result_status"] for r in reviewed)), "observations": reviewed,
        "selection_reason": "Five Flying Finn starts plus Pure Ego 2026-02-25: stable IDs and pedigree, wins, seconds, gallop/DQ, nonnumeric time, and one officially confirmed VOLT start; not representative", "model_eligible": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("truth", "truth-sha256", "bundle", "parser-path", "output"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--official-archive")
    parser.add_argument("--official-sha256")
    args = parser.parse_args()
    try:
        report = run(args.truth, args.truth_sha256, args.bundle, args.parser_path)
        if bool(args.official_archive) != bool(args.official_sha256):
            raise ValueError("OFFICIAL_ARCHIVE_AND_HASH_REQUIRED_TOGETHER")
        if args.official_archive:
            report["official_review"] = official_review(truth_data(args.truth, args.truth_sha256), args.official_archive, args.official_sha256)
            if report["official_review"]["reviewed"] == 6:
                report["terminal_status"] = "M7A.1_PASS"
        report["parser_model_readiness"] = "BLOCKED; VALIDATION_DELIVERY_PASS_IS_NOT_PARSER_OR_FEATURE_APPROVAL"
        with Path(args.output).open("x") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({k: v for k, v in report.items() if k not in ("observations", "official_review")}, indent=2))


if __name__ == "__main__":
    main()
