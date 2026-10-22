"""Research-only audit of the existing collector parser. No parsing alternative."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from .date_overview import timestamp
from .provider_capability import name_key

PARSER_SHA256 = "2ea5c70dfa76a2c8dbc358bbfcb97657efe1f831a5f799cb3790b9064a1ae64d"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_parser(path, expected):
    path = Path(path)
    if expected != PARSER_SHA256 or sha(path.read_bytes()) != expected:
        raise ValueError("UNREVIEWED_PARSER_VERSION")
    spec = importlib.util.spec_from_file_location("reviewed_collector_pdf_program", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_extended_pdf


def physical_candidates(doc, canonical):
    """Route a whole printed field; this does not establish horse identity."""
    field = [(h["program_number"], name_key(h["name"])) for h in doc["entrants"]]
    if not field or len(field) != len(set(field)) or len({n for n, _ in field}) != len(field):
        return []
    matches = []
    for mid, envelope in canonical.items():
        if envelope.get("response", {}).get("success") is not True:
            continue
        for number, horses in envelope["response"]["result"].items():
            target = [(h["startNumber"], name_key(h["horseName"])) for h in horses]
            if len(target) == len(field) and sorted(target) == sorted(field):
                matches.append(f"{mid}#{number}")
    return matches


def inspect_document(metadata, pages, parsed):
    rows, fields = [], []
    for di, doc in enumerate(parsed["races"]):
        candidates = physical_candidates(doc, metadata["canonical_starts"])
        fields.append({"source_section": di, "printed_race_number": doc["race"]["race_number"],
            "physical_candidates": candidates, "status": "FIELD_ROUTED_NOT_IDENTITY_VERIFIED" if len(candidates) == 1 else "UNRESOLVED"})
        for hi, horse in enumerate(doc["entrants"]):
            header_pages = [i + 1 for i, text in enumerate(pages) if horse["header_text"] in text]
            for pi, prior in enumerate(horse["past_starts"]):
                raw = prior["raw_text"]
                locations = [{"page": i + 1, "line": j + 1} for i, text in enumerate(pages)
                    for j, line in enumerate(text.splitlines()) if line == raw]
                valid_date = bool(prior["date"] and date.fromisoformat(prior["date"]) < date.fromisoformat(metadata["date"]))
                rows.append({"source_pointer": f"/races/{di}/entrants/{hi}/past_starts/{pi}",
                    "horse_name": horse["name"], "printed_race_number": doc["race"]["race_number"],
                    "program_number": horse["program_number"], "raw_history_line": raw,
                    "pdf_sha256": metadata["pdf_sha256"], "source_url": doc["race"]["source_url"],
                    "source_observed_at": doc["race"]["captured_at_utc"], "published_at": None,
                    "header_pages": header_pages, "locations": locations,
                    "cross_page_candidate": bool(locations and header_pages and any(p["page"] not in header_pages for p in locations)),
                    "historical_start_date": prior["date"], "historical_race_number": prior["race_number"],
                    "parser_status": "SOURCE_LINE_LOCATED" if len(locations) == 1 and valid_date else "UNRESOLVED",
                    "unparsed_fields": [k for k in ("track", "distance_m", "placing", "kilometre_time") if prior.get(k) is None],
                    "qualification_status": "UNRESOLVED", "horse_identity": "NOT_ESTABLISHED_BY_PDF",
                    "official_result_status": "UNVERIFIED_SOURCE_EXCERPT", "feature_status": "NOT_VALIDATED",
                    "pit_status": "UNRESOLVED", "model_eligible": False,
                    "exclusion_reasons": ["HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "HISTORICAL_RACE_AND_IDENTITY_NOT_VERIFIED",
                        "PDF_DATE_IS_NOT_AVAILABILITY_PROOF", "RESULT_SEMANTICS_AND_QUALIFICATION_UNVALIDATED"]})
    counts = {"race_sections": len(parsed["races"]), "horses": sum(len(r["entrants"]) for r in parsed["races"]), "history_rows": len(rows)}
    return {"meeting_id": metadata["meeting_id"], "date": metadata["date"], "pdf_sha256": metadata["pdf_sha256"],
        "source_archive_sha256": metadata["source_archive_sha256"], "source_archive_member": metadata["source_archive_member"],
        "source_archive_asset_url": metadata["source_archive_asset_url"], "pages": len(pages), "counts": counts,
        "reported_counts_match": all(counts[k] == v for k, v in metadata["reported_counts"].items()),
        "parser_qa": parsed["qa"], "fields": fields, "observations": rows,
        "status_counts": dict(Counter(r["parser_status"] for r in rows)),
        "cross_page_history_rows": sum(r["cross_page_candidate"] for r in rows), "model_eligible": 0}


def run(bundle_path, expected_sha, parser_path, parser_sha):
    from pypdf import PdfReader

    raw = Path(bundle_path).read_bytes()
    if sha(raw) != expected_sha:
        raise ValueError("BUNDLE_SHA256_MISMATCH")
    parse = load_parser(parser_path, parser_sha)
    reports = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or sum(i.file_size for i in archive.infolist()) > 100_000_000:
            raise ValueError("INVALID_VALIDATION_BUNDLE")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["schema"] != "M7A_ORIGINAL_PDF_SUBSET_V1":
            raise ValueError("UNKNOWN_VALIDATION_BUNDLE")
        for spec in manifest["sources"]:
            metadata_raw = archive.read(spec["metadata_member"])
            if sha(metadata_raw) != spec["metadata_sha256"]:
                raise ValueError("METADATA_HASH_MISMATCH")
            metadata = json.loads(metadata_raw)
            binary = archive.read(metadata["pdf_member"])
            if sha(binary) != metadata["pdf_sha256"]:
                raise ValueError("PDF_HASH_MISMATCH")
            race = metadata["archived_parser_output"][0]["race"]
            timestamp(race["captured_at_utc"])
            pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(binary)).pages]
            parsed = parse("\n\n".join(pages), meeting_id=metadata["meeting_id"], date=metadata["date"],
                url=race["source_url"], captured_at=race["captured_at_utc"], track=race["track"])
            reports.append(inspect_document(metadata, pages, parsed))
    return {"schema": "M7A_PDF_VALIDATION_V1", "bundle_sha256": expected_sha, "parser_sha256": parser_sha,
        "documents": reports, "independent_DATA_003_60": "NOT_AVAILABLE; ACCURACY_NOT_MEASURABLE",
        "model_eligible": 0, "terminal_status": "M7A_PARTIAL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bundle", "sha256", "parser-path", "parser-sha256", "output"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--result-bundle")
    parser.add_argument("--result-sha256")
    args = parser.parse_args()
    try:
        report = run(args.bundle, args.sha256, args.parser_path, args.parser_sha256)
        if bool(args.result_bundle) != bool(args.result_sha256):
            raise ValueError("RESULT_BUNDLE_AND_HASH_REQUIRED_TOGETHER")
        if args.result_bundle:
            proof = verify_flying_finn(load_result_evidence(args.result_bundle, args.result_sha256))
            linked = [r for d in report["documents"] if d["date"] == "2026-10-21"
                for r in d["observations"] if r["horse_name"] == "FLYING FINN"
                and r["historical_start_date"] == "2026-09-23" and r["historical_race_number"] == 8]
            if len(linked) != 1 or "23.09.26-8|1 1 1 2140 11,1a" not in linked[0]["raw_history_line"]:
                raise ValueError("PDF_OFFICIAL_LINK_NOT_PROVEN")
            linked[0]["official_result_status"] = "RESULT_VERIFIED"
            linked[0]["retrospective_result_proof"] = proof
            proof["archive_sha256"] = args.result_sha256
            report["independent_result_check"] = proof
        with Path(args.output).open("x") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"terminal_status": report["terminal_status"], "model_eligible": 0,
        "documents": [{k: d[k] for k in ("meeting_id", "counts", "reported_counts_match", "parser_qa", "status_counts", "cross_page_history_rows")} for d in report["documents"]]}, ensure_ascii=False, indent=2))


def load_result_evidence(path, expected_sha):
    raw = Path(path).read_bytes()
    if sha(raw) != expected_sha:
        raise ValueError("RESULT_ARCHIVE_HASH_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or sum(x.file_size for x in archive.infolist()) > 20_000_000:
            raise ValueError("INVALID_RESULT_ARCHIVE")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["schema"] != "M7A_ATG_VALIDATION_V1":
            raise ValueError("UNKNOWN_RESULT_SCHEMA")
        evidence = {}
        for member, expected in manifest["files_sha256"].items():
            body = archive.read(member)
            if sha(body) != expected:
                raise ValueError("RESULT_MEMBER_HASH_MISMATCH")
            evidence[member] = json.loads(body)
    return evidence


def verify_flying_finn(evidence):
    """One source-specific independent check, not a general results adapter."""
    matches, refs = [], []
    for day, number, selection in [("2026-09-23", 8, 1), ("2026-10-21", 9, 5)]:
        calendar = evidence[f"atg-calendar-{day}.json"]
        expected_calendar = f"https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/{day}?headToHeadEnabled=true"
        if not calendar["success"] or calendar["status_code"] != 200 or calendar["url"] != expected_calendar or calendar["payload"]["date"] != day:
            raise ValueError("CALENDAR_UNVERIFIED")
        ids = [r["id"] for t in calendar["payload"]["tracks"]
            if t["name"] == "Solvalla" and t["countryCode"] == "SE" and t["sport"] == "trot"
            for r in t["races"] if r["number"] == number]
        expected_id = f"{day}_5_{number}"
        if ids != [expected_id]:
            raise ValueError("OFFICIAL_RACE_AMBIGUOUS")
        envelope = evidence[f"atg-{expected_id}.json"]
        if (not envelope["success"] or envelope["status_code"] != 200
                or envelope["url"] != f"https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{expected_id}"):
            raise ValueError("OFFICIAL_RESULT_SOURCE_UNVERIFIED")
        timestamp(envelope["observed_at"])
        races = envelope["payload"]["races"]
        if len(races) != 1:
            raise ValueError("OFFICIAL_RACE_AMBIGUOUS")
        race = races[0]
        if (race["id"] != expected_id or race["date"] != day or race["number"] != number
                or race["track"]["name"] != "Solvalla" or race["track"]["countryCode"] != "SE"
                or race["sport"] != "trot"):
            raise ValueError("OFFICIAL_RACE_CONFLICT")
        field = race["starts"]
        if (len({s["number"] for s in field}) != len(field)
                or len({s["horse"]["id"] for s in field}) != len(field)
                or sum(name_key(s["horse"]["name"]) == "flyingfinn" for s in field) != 1):
            raise ValueError("OFFICIAL_FIELD_IDENTITY_CONFLICT")
        starts = [s for s in field if s["number"] == selection]
        if len(starts) != 1:
            raise ValueError("OFFICIAL_HORSE_AMBIGUOUS")
        start = starts[0]
        horse = start["horse"]
        if (horse["id"] != 788027 or name_key(horse["name"]) != "flyingfinn"
                or name_key(horse["pedigree"]["father"]["name"]) != "readlyexpress"
                or name_key(horse["pedigree"]["mother"]["name"]) != "railin"):
            raise ValueError("OFFICIAL_HORSE_CONFLICT")
        matches.append(start)
        refs.append({"url": envelope["url"], "observed_at": envelope["observed_at"],
            "race_id": expected_id, "selection": selection, "role": "RETROSPECTIVE_VALIDATION_ONLY"})
    result = matches[0]["result"]  # Target-race result is deliberately never read.
    if (type(result.get("place")) is not int or result["place"] != 1
            or result.get("kmTime") != {"minutes": 1, "seconds": 11, "tenths": 1}
            or any(type(v) is not int for v in result.get("kmTime", {}).values())):
        raise ValueError("PDF_OFFICIAL_RESULT_CONFLICT")
    return {"horse": "Flying Finn", "stable_identity": "ATG_HORSE:788027", "historical_race": "2026-09-23_5_8",
        "target_race": "2026-10-21_5_9", "place": 1, "km_time_seconds": 71.1,
        "official_result_status": "RESULT_VERIFIED", "pre_race_identity_availability": "UNRESOLVED",
        "pit_status": "UNRESOLVED", "model_eligible": False, "source_refs": refs}


if __name__ == "__main__":
    main()
