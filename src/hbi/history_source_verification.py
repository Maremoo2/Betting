"""Bounded offline official-source review; never changes PDF/parser or model gates."""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import zipfile
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from .date_overview import DailyArchive, timestamp
from .history_semantic_benchmark import HOLDOUT_SHA, KNOWN_SHA
from .history_semantic_benchmark import run as semantic_run
from .pdf_semantic_validation import checked_bytes, classify, official_review, truth_data
from .pdf_validation import sha
from .provider_capability import name_key
from .swedish_identity import resolve

SOURCE_SHA = "96d6a3c4a344a61b3d42b8173fff1b02fa44a4c1a430902db559d684960f8eb9"
OFFICIAL_SHA = "f717e0ab2767abc436cadcf0ceecfbbe524233bb162db2ad1d6e71b9d3ebeabf"
PROGRAM_SHA = "a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e"
ATG_SHA = "a053ce855c230c8e10450dfcecca3447873718512269bfc2b132c2d66f84745c"
STATES = ("VERIFIED", "CANDIDATE_ONLY", "AMBIGUOUS", "UNRESOLVED", "CONFLICTING_EVIDENCE")


class _CheckedReview(dict):
    """Internal source-check result; serialized claims/statuses cannot promote rows."""


def checked_source(source):
    meta, body = source
    if (meta.get("status") != 200 or meta.get("sha256") != sha(body)
            or meta.get("bytes") != len(body) or not meta.get("url") or not meta.get("observed_at")):
        raise ValueError("OFFICIAL_PROVENANCE_REQUIRED")
    timestamp(meta["observed_at"])
    return meta, body


def row_binding(row):
    return {key: row[key] for key in ("observation_id", "target_race_id", "target_horse_name",
        "target_program_number", "pdf_sha256", "pdf_page", "raw_history_line", "historical_track",
        "historical_date", "historical_race_number")}


class ResultCells(HTMLParser):
    """Read cells of one already identified official HTML result row, not PDFs."""
    def __init__(self):
        super().__init__()
        self.cells, self.current = [], None

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.current is not None:
            self.cells.append(" ".join("".join(self.current).split()))
            self.current = None


def sources(path, *, expected_sha=SOURCE_SHA, expected_schema="M7B1A_OFFICIAL_SOURCE_ARCHIVE_V1"):
    with zipfile.ZipFile(io.BytesIO(checked_bytes(path, expected_sha))) as z:
        if len(z.namelist()) != len(set(z.namelist())) or sum(i.file_size for i in z.infolist()) > 10_000_000:
            raise ValueError("INVALID_OFFICIAL_ARCHIVE")
        manifest = json.loads(z.read("manifest.json"))
        if manifest["schema"] != expected_schema:
            raise ValueError("UNREVIEWED_SOURCE_SCHEMA")
        records = {}
        for member, meta in manifest["sources"].items():
            body = z.read(member)
            if meta["sha256"] != sha(body) or meta["bytes"] != len(body) or meta["status"] != 200:
                raise ValueError("OFFICIAL_PROVENANCE_CONFLICT")
            timestamp(meta["observed_at"])
            records[member] = (meta, body)
        return records


def dnt_review(row, case, source, program):
    meta, body = checked_source(source)
    expected_url = f"https://www.travsport.no/travbaner/{case['track_slug']}/results/{row['historical_date']}"
    if case["country"] != "NO" or meta["url"] != expected_url or meta["final_url"] != expected_url:
        raise ValueError("DNT_COUNTRY_OR_SOURCE_CONFLICT")
    text = body.decode("utf-8")
    canonical = f"https://www.travsport.no/travbaner/{case['track_slug']}/results/"
    if canonical not in text or f"<title>{case['official_track_name']}" not in html.unescape(text):
        raise ValueError("DNT_TRACK_CONFLICT")
    mid, number = row["target_race_id"].split(":")[1:]
    original = program.read(f"meetings/{mid}/starts.json")["response"]["result"][number]
    target = [h for h in original if h["startNumber"] == row["target_program_number"]]
    if (len(target) != 1 or target[0]["horseRegistrationNumber"] != case["registration"]
            or name_key(target[0]["horseName"]) != name_key(row["target_horse_name"])):
        raise ValueError("DNT_TARGET_REGISTRATION_CONFLICT")
    matches = []
    for match in re.finditer(r"<tr\b[^>]*>.*?</tr>", text, re.DOTALL):
        if f'href="/sportsbasen/sportssok/horse/{case["registration"]}"' not in match[0]:
            continue
        races = re.findall(r'<span class="sr-only">Løp (\d+)</span>', text[:match.start()])
        if races and int(races[-1]) == row["historical_race_number"]:
            cells = ResultCells()
            cells.feed(match[0])
            heading = text.rfind("<h2", 0, match.start())
            table = text.find("<table", heading)
            intro = html.unescape(text[heading:table])
            method = "AUTO" if re.search(r"\bAutostart\b", intro) else "VOLT" if re.search(r"\bVolt(?:e)?start\b", intro) else "UNKNOWN"
            matches.append((cells.cells, method))
    if len(matches) != 1:
        raise ValueError("DNT_HISTORICAL_REGISTRATION_OR_RACE_NOT_FOUND")
    cells, method = matches[0]
    if len(cells) < 6 or name_key(cells[2]) != name_key(row["target_horse_name"]):
        raise ValueError("DNT_OFFICIAL_ROW_CONFLICT")
    prefixes = {"bjerke-travbane": "BJ", "jarlsberg-travbane": "JA", "biri-travbane": "BI", "momarken-travbane": "MO",
        "klosterskogen-travbane": "KL", "varig-orkla-arena": "OR"}
    if f"{prefixes[case['track_slug']]}_NR_{row['historical_date']}/{row['historical_race_number']}" not in text:
        raise ValueError("DNT_HISTORICAL_DATE_NOT_CORROBORATED")
    time = re.fullmatch(r"(\d+),(\d)(?:\s*[ag]+)?", cells[5])
    values = {"placing": int(cells[0]) if cells[0].isdigit() and int(cells[0]) > 0 else
        "UNPLACED" if cells[0] == "0" else "UNKNOWN", "distance_m": int(cells[3]),
        "km_time": 60 + int(time[1]) + int(time[2]) / 10 if time else "NOT_REPORTED",
        "start_method": method,
        "gallop_flag": True if "g" in cells[5] or cells[0] == "Disk. galopp" else "NOT_REPORTED",
        "disqualification_flag": True if cells[0] == "Disk. galopp" else "NOT_REPORTED"}
    return _CheckedReview({"source_binding": row_binding(row), "track": {"country": "NO", "name": case["official_track_name"], "stable_provider_id": "NOT_REPORTED",
        "official_track_uri": canonical.removesuffix("results/")}, "horse_identity": f"DNT_REGISTRATION:{case['registration']}",
        "date": row["historical_date"], "race_number": row["historical_race_number"], "values": values,
        "raw_official_result": {"cells": cells[:6], "start_method_from_race_terms": method}, "source": meta,
        "identity_proof": {"role": "BOUNDED_RETROSPECTIVE_REGISTRATION_REVIEW_NOT_GLOBAL_IDENTITY_ADMISSION",
            "target_starts": program.source(f"meetings/{mid}/starts.json"), "target_registration": case["registration"]}})


def atg_review(row, case, source, identity):
    meta, body = checked_source(source)
    payload = json.loads(body)
    races = payload.get("races", [])
    if len(races) != 1:
        raise ValueError("AMBIGUOUS_OFFICIAL_RACE")
    race = races[0]
    if (case["country"] != "SE" or race["track"]["countryCode"] != case["country"]
            or race["date"] != row["historical_date"] or race["number"] != row["historical_race_number"]
            or race["sport"] != "trot" or race["status"] != "results"
            or race["id"] != f"{row['historical_date']}_{race['track']['id']}_{row['historical_race_number']}"
            or meta["url"] != f"https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{race['id']}"
            or meta["url"] != meta["final_url"]):
        raise ValueError("ATG_OFFICIAL_RACE_OR_COUNTRY_CONFLICT")
    selected = [s for s in race["starts"] if s["horse"]["id"] == case["horse_id"]]
    if len(selected) != 1 or not identity or identity["horse_id"] != case["horse_id"]:
        raise ValueError("ATG_STABLE_IDENTITY_NOT_VERIFIED")
    start = selected[0]
    if (name_key(start["horse"]["name"]) != name_key(row["target_horse_name"])
            or tuple(name_key(start["horse"]["pedigree"][k]["name"]) for k in ("father", "mother")) != tuple(identity["pedigree"])):
        raise ValueError("ATG_PEDIGREE_OR_HORSE_CONFLICT")
    if row["historical_track"].casefold() != race["track"]["sportSystemCode"].casefold():
        raise ValueError("ATG_PRINTED_TRACK_CODE_CONFLICT")
    result = start["result"]
    placing = result.get("place")
    if ("place" in result and (type(placing) is not int or placing < 0)
            or result.get("disqualified") is True and type(placing) is int and placing > 0
            or any(key in result and type(result[key]) is not bool for key in ("galloped", "disqualified"))):
        raise ValueError("ATG_CONFLICTING_OR_INVALID_RESULT_VALUES")
    km = result.get("kmTime", {})
    if "code" in km and set(km) & {"minutes", "seconds", "tenths"}:
        raise ValueError("ATG_CODE_AND_NUMERIC_TIME_CONFLICT")
    values = {"placing": result["place"] if type(result.get("place")) is int and result["place"] > 0 else
        "UNPLACED" if result.get("place") == 0 else "UNKNOWN",
        "distance_m": start["distance"], "km_time": 60 * km["minutes"] + km["seconds"] + km["tenths"] / 10
        if set(km) == {"minutes", "seconds", "tenths"} else "NOT_REPORTED",
        "start_method": {"auto": "AUTO", "volte": "VOLT"}.get(race["startMethod"], "UNKNOWN"),
        "gallop_flag": result.get("galloped", "NOT_REPORTED"),
        "disqualification_flag": result.get("disqualified", "NOT_REPORTED")}
    return _CheckedReview({"source_binding": row_binding(row), "track": {"country": "SE", "name": race["track"]["name"], "stable_provider_id": {"namespace": "ATG_TRACK", "value": race["track"]["id"]}},
        "date": race["date"], "race_number": race["number"], "horse_identity": f"ATG_HORSE:{case['horse_id']}",
        "values": values, "raw_official_result": result, "source": meta, "identity_proof": identity})


def bind_verified(row, review, register):
    """Only a checked official chain can promote this exact observation, not code."""
    if (type(review) is not _CheckedReview or not review or not review.get("source") or not review.get("identity_proof")
            or not review["source"].get("url") or not review["source"].get("sha256")
            or not review["source"].get("observed_at")):
        raise ValueError("VERIFICATION_REQUIRES_SOURCE_AND_IDENTITY_PROOF")
    timestamp(review["source"]["observed_at"])
    if review.get("source_binding") != row_binding(row):
        raise ValueError("OFFICIAL_EVIDENCE_NOT_BOUND_TO_THIS_PDF_OBSERVATION")
    if (review["date"] != row["historical_date"] or review["race_number"] != row["historical_race_number"]
            or date.fromisoformat(review["date"]) >= date.fromisoformat(row["target_race_id"].split(":")[1][-10:])):
        raise ValueError("HISTORICAL_DATE_OR_RACE_CONFLICT")
    candidates = register["codes"][row["historical_track"]]["candidates"]
    if not any(x["country"] == review["track"]["country"] and name_key(x["official_name"]) == name_key(review["track"]["name"]) for x in candidates):
        raise ValueError("OFFICIAL_TRACK_CANDIDATE_CONFLICT")
    return {"status": "VERIFIED", "printed_code": row["historical_track"], "track": review["track"],
        "valid_on": review["date"], "method": "EXACT_OFFICIAL_HISTORICAL_RACE_AND_STABLE_HORSE_CHAIN",
        "review": review, "allowed_use": "RESEARCH_ONLY", "pit_status": "UNVERIFIED", "model_eligible": False}


def run(root):
    root = Path(root)
    fixtures = root / "tests/fixtures"
    truth = truth_data(fixtures / "m7a1-ground-truth-v1.json", KNOWN_SHA)
    holdout = json.loads(checked_bytes(fixtures / "m7b1-holdout-v1.json", HOLDOUT_SHA))
    rows = truth["rows"] + holdout["rows"]
    register = json.loads((root / "docs/M7B1A_TRACK_REGISTER.json").read_bytes())
    claims = json.loads((root / "docs/M7B1A_REVIEW_CLAIMS.json").read_bytes())
    raw = sources(fixtures / "m7b1a-official-sources-v1.zip")
    program = DailyArchive(fixtures / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    old = official_review(truth, fixtures / "m7a1-atg-results-v1.zip", OFFICIAL_SHA)
    by_id = {r["observation_id"]: r for r in rows}
    reviews = {}
    for obs in old["observations"]:
        row = by_id[obs["observation_id"]]
        reviews[obs["observation_id"]] = _CheckedReview({"source_binding": row_binding(row), "track": {"country": "SE", "name": "Solvalla" if row["historical_track"] == "S" else "Umåker",
            "stable_provider_id": {"namespace": "ATG_TRACK", "value": 5 if row["historical_track"] == "S" else 27}},
            "date": row["historical_date"], "race_number": row["historical_race_number"], "horse_identity": obs["horse_identity"],
            "values": {k: v if v is not None else "NOT_REPORTED" for k, v in obs["official_values"].items()},
            "raw_official_result": obs["raw_official_result"], "source": {**obs["source"], "sha256": obs["source"]["member_sha256"]},
            "identity_proof": obs["identity_proof"]})
    for case in claims["no_cases"]:
        row = by_id[case["observation_id"]]
        reviews[row["observation_id"]] = dnt_review(row, case, raw[case["source_member"]], program)
    links = resolve(program, fixtures / "atg-se-2026-10-20-identity.zip", ATG_SHA)["links"]
    for case in claims["se_cases"]:
        row = by_id[case["observation_id"]]
        if case["horse_id"] == 793918:
            identity = {"horse_id": 793918, "pedigree": ["creatine", "restless"], "proof": old["observations"][-1]["identity_proof"]}
        else:
            mid, number = row["target_race_id"].split(":")[1:]
            selected = [x for x in links if x["raceday_key"] == mid and x["race_number"] == int(number)
                and x["selection_id"] == str(row["target_program_number"]) and x["status"] == "IDENTITY_VERIFIED"
                and x["provider_identity"] == {"namespace": "ATG_HORSE", "id": str(case["horse_id"])}]
            if len(selected) != 1:
                raise ValueError("EXISTING_M6_IDENTITY_PROOF_NOT_REPRODUCED")
            identity = {"horse_id": case["horse_id"], "pedigree": list(selected[0]["biography"][2:]), "proof": selected[0]["proof"],
                "role": "EXISTING_RETROSPECTIVE_IDENTITY_EVIDENCE_NOT_AUTOMATIC_ADMISSION"}
        reviews[row["observation_id"]] = atg_review(row, case, raw[case["source_member"]], identity)
    codebook = json.loads((root / "docs/M7B1A_RESULT_CODEBOOK.json").read_bytes())
    baseline = semantic_run(root, None, archived=True)
    parsed = {r["observation_id"]: r for group in ("known", "holdout") for r in baseline[group]["observations"]}
    output = []
    for row in rows:
        code = row["historical_track"]
        status = register["codes"][code]["status"]
        record = {"observation_id": row["observation_id"], "target_race_id": row["target_race_id"], "target_horse_name": row["target_horse_name"], "pdf_sha256": row["pdf_sha256"], "pdf_page": row["pdf_page"],
            "raw_history_line": row["raw_history_line"], "historical_date": row["historical_date"],
            "printed_code": code, "printed_code_correct": parsed[row["observation_id"]]["fields"]["historical_track"]["status"] == "CORRECT",
            "status": status, "candidates": register["codes"][code]["candidates"], "reason": register["codes"][code]["reason"],
            "allowed_use": "RESEARCH_ONLY", "model_eligible": False, "pit_status": "UNVERIFIED"}
        review = reviews.get(row["observation_id"])
        if review:
            record.update(bind_verified(row, review, register))
            record["pdf_official_comparison"] = {k: classify(row[k], None if v in ("UNKNOWN", "NOT_REPORTED") else v) for k, v in review["values"].items()}
            semantic = parsed[row["observation_id"]]["semantic"]
            record["adapter_vs_official"] = {k: classify(v, semantic["fields"][k]["value"]
                if semantic["fields"][k]["status"] == "EXTRACTED" else None) for k, v in review["values"].items()}
        output.append(record)
    counts = Counter(r["status"] for r in output)
    migration = Counter((parsed[r["observation_id"]]["semantic"]["fields"]["track_identity"]["status"], r["status"]) for r in output)
    return {"schema": "M7B1A_SOURCE_VERIFICATION_V1", "version": "0.1.0", "rows": len(rows),
        "printed_codes_correct": sum(r["printed_code_correct"] for r in output),
        "baseline": {"unambiguous_candidates": 43, "unresolved_candidates": 47, "authoritatively_verified": "NOT_MEASURED"},
        "track_status_counts": {s: counts[s] for s in STATES},
        "baseline_candidate_migration": [{"before": a, "after": b, "rows": n} for (a, b), n in sorted(migration.items())], "official_starts_reviewed": len(reviews),
        "official_countries": dict(Counter(v["track"]["country"] for v in reviews.values())),
        "pdf_official_conflicts": sum("INCORRECT" in r.get("pdf_official_comparison", {}).values() for r in output),
        "adapter_incorrect_values": sum(v == "INCORRECT" for r in output for v in r.get("adapter_vs_official", {}).values()),
        "adapter_missing_official_values": sum(v == "NOT_EXTRACTED" for r in output for v in r.get("adapter_vs_official", {}).values()),
        "code_family_denominator": len(codebook["families"]),
        "code_family_verification_counts": dict(Counter(f["verification_status"] for f in codebook["families"])),
        "codebook_version": codebook["version"], "attempts_without_link": claims["attempts_without_link"], "observations": output, "source_archive_sha256": SOURCE_SHA, "known_sha256": KNOWN_SHA, "holdout_sha256": HOLDOUT_SHA,
        "representative": False, "model_eligible": 0, "pit_verified": 0, "terminal_status": "M7B1A_PARTIAL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root)
    with args.output.open("x") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}, indent=2))


if __name__ == "__main__":
    main()
