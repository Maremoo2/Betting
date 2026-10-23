"""Research-only normalization extension and A-C quality report over frozen history.

Reuses collector records, semantic extraction and official source validators. No
PDF discovery, copied result fields, model admission or identity/PIT approval.
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter
from copy import deepcopy
from datetime import date
from itertools import combinations
from pathlib import Path

from .date_overview import DailyArchive, timestamp
from .history_semantic_benchmark import HOLDOUT_SHA, KNOWN_SHA
from .history_semantic_benchmark import run as semantic_run
from .history_semantics import HEADER, fact
from .history_source_verification import (
    ATG_SHA,
    OFFICIAL_SHA,
    PROGRAM_SHA,
    atg_review,
    bind_verified,
    dnt_review,
)
from .history_source_verification import (
    run as source_run,
)
from .history_source_verification import (
    sources as official_sources,
)
from .pdf_semantic_validation import BUNDLE_SHA, checked_bytes, classify, read_sources, truth_data
from .provider_capability import name_key
from .swedish_identity import biography, resolve

SOURCE_SHA = "f362a51b18c7cde53c826838011526a9b3aeb6ad1ebd4f7df73af8cbaf58c335"
VERSION = "0.1.0"


def source_integrity(row, originals):
    try:
        meta, pages = originals[row["pdf_sha256"]]
        page = pages[row["pdf_page"] - 1]
        ref = row["source_evidence"]
        header = ref["horse_header"]
        lines = page.splitlines()
        raw = row["raw_history_line"]
        timestamp(ref["source_observed_at"])
        parsed = HEADER.match(raw)
        return (meta["pdf_sha256"] == row["pdf_sha256"] and row["pdf_page"] > 0
            and ref["bundle_sha256"] == BUNDLE_SHA and lines.count(raw) == 1 and header in lines
            and header.startswith(f"{row['target_program_number']} {row['target_horse_name']},")
            and lines.index(header) < ref["extracted_line_number"] - 1
            and lines[ref["extracted_line_number"] - 1] == raw and parsed is not None
            and parsed[2] == date.fromisoformat(row["historical_date"]).strftime("%d.%m.%y")
            and int(parsed[3]) == row["historical_race_number"])
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def refine_pdf(row, semantic, context, register, book, source_ok):
    """Derive only from raw PDF codes and checked namespace, never official values."""
    if book["schema"] != "M7B1B_RESULT_CODEBOOK_V1" or book["version"] != "0.3.0-research" or book["model_eligible"] is not False:
        raise ValueError("UNREVIEWED_RESEARCH_CODEBOOK")
    result = deepcopy(semantic)
    result["research_normalization_version"] = book["version"]
    result["normalization_changes"] = []
    if (not source_ok or not context or not semantic["history_accepted"]
            or semantic["raw_text"] != row["raw_history_line"]):
        return result
    try:
        bound = bind_verified(row, context["review"], register)
    except (ValueError, KeyError, TypeError):
        return result
    country = bound["track"]["country"]  # Context only; no review.values read here.
    for rule in book["pdf_rules"]:
        signatures = {"SE_D_PLACING_DQ": ("SE", "pdf_placing_code", "d"), "NO_DG_TIME_DQ": ("NO", "pdf_time_code", "dg")}
        signature = signatures.get(rule["id"])
        if not signature or rule["country"] != signature[0] or rule.get(signature[1]) != signature[2]:
            raise ValueError("UNREVIEWED_CODE_NAMESPACE_RULE")
        if not any(c["pdf_sha256"] == row["pdf_sha256"] and c["pdf_page"] == row["pdf_page"] for c in rule["reviewed_pdf_contexts"]):
            continue
        if rule["country"] != country:
            continue
        if "pdf_placing_code" in rule and semantic["raw_codes"]["placing"] != rule["pdf_placing_code"]:
            continue
        if "pdf_time_code" in rule and semantic["raw_codes"]["km_time"] != rule["pdf_time_code"]:
            continue
        field = rule["field"]
        old = result["fields"][field]
        if old["status"] == "EXTRACTED":
            continue
        # This bounded rule family is deliberately not an arbitrary field copier.
        if field != "disqualification_flag" or rule["value"] is not True:
            raise ValueError("UNREVIEWED_PDF_NORMALIZATION_RULE")
        raw = semantic["raw_codes"]["placing"] if "pdf_placing_code" in rule else semantic["raw_codes"]["km_time"]
        result["fields"][field] = fact(True, "EXTRACTED", raw, rule["id"])
        result["result_status"] = "DISQUALIFIED"
        result["normalization_changes"].append({"field": field, "before": old, "after": result["fields"][field],
            "rule": rule["id"], "evidence_role": "CODEBOOK_RULE_PLUS_BOUND_NAMESPACE_NOT_OFFICIAL_VALUE_COPY"})
    return result


def evaluate(row, semantic, context, register, originals, policy):
    if (policy["schema"] != "M7B1B_EXCLUSION_POLICY_V1" or policy["version"] != VERSION
            or policy["positive_evidence_required"] is not True or policy["model_eligible"] is not False or policy["allowed_use"] != "RESEARCH_ONLY"
            or policy["gates"]["D"]["status"] != "NOT_APPROVED" or policy["gates"]["E"]["status"] != "NOT_APPROVED"):
        raise ValueError("RESEARCH_POLICY_CANNOT_APPROVE_MODELS_IDENTITY_OR_PIT")
    reasons, categories = set(), set()
    source_ok = source_integrity(row, originals)
    if source_ok:
        categories.add("SOURCE_VERIFIED")
    else:
        reasons.add("SOURCE_PROVENANCE_OR_LOCATION_CONFLICT")
        categories.add("EXCLUDED_SOURCE_CONFLICT")
    temporal = False
    try:
        temporal = date.fromisoformat(row["historical_date"]) < date.fromisoformat(row["target_race_id"].split(":")[1][-10:])
    except (ValueError, KeyError, TypeError):
        pass
    if not temporal:
        reasons.add("FUTURE_SAME_DAY_OR_INVALID_HISTORY_DATE")
    if (semantic.get("model_eligible") is not False or semantic.get("allowed_use") != "RESEARCH_ONLY"
            or semantic.get("pit_status") != "UNVERIFIED"):
        reasons.add("UNAUTHORIZED_ADMISSION_CLAIM")
    missing = []
    malformed = []
    for key in policy["core_fields"]:
        f = semantic.get("fields", {}).get(key, {})
        value = f.get("value")
        if f.get("status") not in policy["field_statuses"]:
            malformed.append(key)
        if f.get("status") != "EXTRACTED" or value in ("UNKNOWN", "NOT_REPORTED", "NOT_APPLICABLE", None):
            missing.append(key)
        elif ((key in ("distance_m", "historical_race_number", "placing") and (type(value) is not int or value <= 0)
                and not (key == "placing" and value == "UNPLACED"))
                or key == "km_time" and (type(value) not in (int, float) or not 0 < value < float("inf"))
                or key == "start_method" and value not in ("AUTO", "VOLT")):
            malformed.append(key)
    unknown = [k for k in ("placing", "km_time") if semantic.get("fields", {}).get(k, {}).get("status") == "UNKNOWN_CODE"]
    if unknown:
        reasons.add("UNKNOWN_RESULT_OR_TIME_CODE")
        categories.add("EXCLUDED_UNKNOWN_RESULT_CODE")
    if missing:
        reasons.add("QUANTITATIVE_CORE_FIELDS_UNAVAILABLE")
    conflict = False
    physical = context.get("status", "UNRESOLVED") if context else "UNRESOLVED"
    if physical == "VERIFIED":
        try:
            bind_verified(row, context["review"], register)
        except (ValueError, KeyError, TypeError):
            physical = "CONFLICTING_EVIDENCE"
            conflict = True
        else:
            for field, expected in context["review"]["values"].items():
                f = semantic["fields"][field]
                if (f["status"] == "EXTRACTED" and expected not in ("UNKNOWN", "NOT_REPORTED", None)
                        and classify(expected, f["value"]) == "INCORRECT"):
                    conflict = True
    if conflict or physical == "CONFLICTING_EVIDENCE":
        reasons.add("OFFICIAL_SOURCE_OR_VALUE_CONFLICT")
        categories.add("EXCLUDED_SOURCE_CONFLICT")
    if physical != "VERIFIED":
        reasons.add("PHYSICAL_RACE_VENUE_UNVERIFIED")
        categories.add("EXCLUDED_AMBIGUOUS_TRACK" if physical == "AMBIGUOUS" else "EXCLUDED_TRACK_UNVERIFIED")
    for key in policy["core_fields"]:
        f = semantic.get("fields", {}).get(key, {})
        if f.get("status") == "EXTRACTED" and classify(row[key], f.get("value")) == "INCORRECT":
            malformed.append(key)
        if row[key] == "UNKNOWN" and f.get("status") == "EXTRACTED":
            malformed.append(key)
    if malformed:
        reasons.add("MALFORMED_OR_UNSUPPORTED_SEMANTIC_VALUES")
    b = "FAIL" if not source_ok or not temporal or conflict or malformed or "UNAUTHORIZED_ADMISSION_CLAIM" in reasons else "EXPLICIT_UNKNOWN" if missing else "PASS"
    if b == "PASS":
        categories.add("SEMANTIC_VERIFIED")
    if source_ok and temporal and not conflict and physical == "VERIFIED" and b != "FAIL":
        categories.add("IDENTITY_RESEARCH_CANDIDATE")
    reasons.update(("HISTORICAL_HORSE_IDENTITY_NOT_APPROVED", "PIT_NOT_APPROVED", "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED"))
    categories.update(("EXCLUDED_IDENTITY_UNVERIFIED", "EXCLUDED_TEMPORAL_RISK", "RESEARCH_PENDING"))
    return {"gates": {"A": "PASS" if source_ok else "FAIL", "B": b, "C": "PASS" if source_ok and temporal and physical == "VERIFIED" and not conflict else "NOT_VERIFIED",
        "D": "NOT_APPROVED", "E": "NOT_APPROVED"}, "categories": sorted(categories), "exclusion_reasons": sorted(reasons),
        "missing_core_fields": missing, "unknown_code_fields": unknown, "malformed_fields": malformed,
        "physical_status": physical, "allowed_use": "RESEARCH_ONLY", "model_eligible": False, "pit_status": "UNVERIFIED"}


def target24_context(row, originals, fixtures):
    """Existing archived target full field + PDF pedigree, not Gate D admission."""
    with zipfile.ZipFile(io.BytesIO(checked_bytes(fixtures / "m7a1-atg-results-v1.zip", OFFICIAL_SHA))) as z:
        target = json.loads(z.read("atg-2026-10-24_7_1.json"))["payload"]["races"][0]
    if (row["target_race_id"] != "RIKSTOTO:S1_NR_2026-10-24:1" or target["id"] != "2026-10-24_7_1"
            or target["date"] != "2026-10-24" or target["number"] != 1 or target["sport"] != "trot"
            or target["track"]["countryCode"] != "SE" or target["track"]["id"] != 7):
        raise ValueError("EXISTING_TARGET_CONTEXT_NOT_APPLICABLE")
    meta = originals[row["pdf_sha256"]][0]
    docs = [d for d in meta["archived_parser_output"] if d["race"]["race_number"] == 1]
    if len(docs) != 1:
        raise ValueError("TARGET_PDF_FIELD_AMBIGUOUS")
    entrants = docs[0]["entrants"]
    a = [(h["program_number"], name_key(h["name"])) for h in entrants]
    b = [(h["number"], name_key(h["horse"]["name"])) for h in target["starts"]]
    if len(set(a)) != len(a) or len(set(b)) != len(b) or set(a) != set(b):
        raise ValueError("TARGET_FULL_FIELD_CONFLICT")
    number = row["target_program_number"]
    pdf = next(h for h in entrants if h["program_number"] == number)
    horse = next(h["horse"] for h in target["starts"] if h["number"] == number)
    bio = biography(pdf["identity_text"])
    expected = (horse["age"], horse["sex"], name_key(horse["pedigree"]["father"]["name"]), name_key(horse["pedigree"]["mother"]["name"]))
    if bio != expected or type(horse["id"]) is not int or name_key(pdf["name"]) != name_key(row["target_horse_name"]):
        raise ValueError("TARGET_PDF_BIOGRAPHY_CONFLICT")
    return {"horse_id": horse["id"], "pedigree": list(bio[2:]),
        "proof": {"archive_sha256": OFFICIAL_SHA, "target_member": "atg-2026-10-24_7_1.json",
            "pdf_sha256": row["pdf_sha256"], "program_number": number,
            "method": "EXISTING_TARGET_FULL_FIELD_AND_PDF_BIOGRAPHY", "role": "BOUNDED_SOURCE_CONTEXT_NOT_GATE_D_APPROVAL"}}


def run(root):
    root = Path(root)
    docs, fixtures = root / "docs", root / "tests/fixtures"
    policy = json.loads((docs / "M7B1B_EXCLUSION_POLICY.json").read_bytes())
    book = json.loads((docs / "M7B1B_CODEBOOK.json").read_bytes())
    register = json.loads((docs / "M7B1B_TRACK_REGISTER.json").read_bytes())
    rows = truth_data(fixtures / "m7a1-ground-truth-v1.json", KNOWN_SHA)["rows"]
    rows += json.loads(checked_bytes(fixtures / "m7b1-holdout-v1.json", HOLDOUT_SHA))["rows"]
    by_id = {r["observation_id"]: r for r in rows}
    baseline = semantic_run(root, None, archived=True)
    parsed = {r["observation_id"]: r["semantic"] for group in ("known", "holdout") for r in baseline[group]["observations"]}
    before_context = {r["observation_id"]: r for r in source_run(root)["observations"]}
    context = deepcopy(before_context)
    sources = official_sources(fixtures / "m7b1b-official-sources-v1.zip", expected_sha=SOURCE_SHA, expected_schema="M7B1B_OFFICIAL_SOURCE_ARCHIVE_V1")
    program = DailyArchive(fixtures / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    links = resolve(program, fixtures / "atg-se-2026-10-20-identity.zip", ATG_SHA)["links"]
    originals = read_sources(fixtures / "m7a-pdf-validation.zip")
    attempts = {}
    for claim in json.loads((docs / "M7B1B_REVIEW_CLAIMS.json").read_bytes())["claims"]:
        row = by_id[claim["observation_id"]]
        try:
            if claim["kind"] == "DNT":
                review = dnt_review(row, claim, sources[claim["source_member"]], program)
            else:
                mid, number = row["target_race_id"].split(":")[1:]
                if claim["horse_id"] == 793918:
                    identity = {"horse_id": 793918, "pedigree": ["creatine", "restless"], "proof": "EXISTING_M7A1_SOURCE_CHAIN_REPLAYED_IN_SOURCE_RUN"}
                elif row["target_race_id"] == "RIKSTOTO:S1_NR_2026-10-24:1":
                    identity = target24_context(row, originals, fixtures)
                    if identity["horse_id"] != claim["horse_id"]:
                        raise ValueError("TARGET_STABLE_ID_CONFLICT")
                else:
                    found = [x for x in links if x["raceday_key"] == mid and x["race_number"] == int(number) and x["selection_id"] == str(row["target_program_number"])
                        and x["status"] == "IDENTITY_VERIFIED" and x["provider_identity"]["id"] == str(claim["horse_id"])]
                    if len(found) != 1:
                        raise ValueError("NO_EXISTING_BOUND_TARGET_LINK")
                    identity = {"horse_id": claim["horse_id"], "pedigree": list(found[0]["biography"][2:]), "proof": found[0]["proof"]}
                review = atg_review(row, claim, sources[claim["source_member"]], identity)
            context[row["observation_id"]] = bind_verified(row, review, register)
            attempts[row["observation_id"]] = {"status": "CHECKED_OFFICIAL_SOURCE", "source_member": claim["source_member"], "source": review["source"]}
        except (ValueError, KeyError, TypeError) as exc:
            attempts[row["observation_id"]] = {"status": "RESEARCH_PENDING", "source_member": claim["source_member"], "reason": str(exc)}
    calendar_checks = json.loads((docs / "M7B1B_REVIEW_CLAIMS.json").read_bytes())["calendar_checks"]
    for check in calendar_checks:
        if not check["result_source_members"]:
            attempts[check["observation_id"]] = {"status": "CALENDAR_CHECKED_NO_MATCHING_RESULT", "source_member": check["source_member"],
                "source": sources[check["source_member"]][0], "reason": "Existing target context available but dated calendar lacks exact candidate venue/race result, including qualification cases. No neighbouring race or name substituted."}
    output = []
    gaps = []
    for row in rows:
        oid = row["observation_id"]
        source_ok = source_integrity(row, originals)
        before = parsed[oid]
        after = refine_pdf(row, before, context.get(oid), register, book, source_ok)
        old = evaluate(row, before, before_context.get(oid), register, originals, policy)
        new = evaluate(row, after, context.get(oid), register, originals, policy)
        original = before_context[oid]
        if original["status"] == "VERIFIED":
            for field, status in original["adapter_vs_official"].items():
                if status != "NOT_EXTRACTED":
                    continue
                changed = after["fields"][field]["status"] == "EXTRACTED"
                classification = "CORRECTED_AND_VERIFIED" if changed else "DOCUMENTED_NOT_REPRESENTED_IN_PDF" if field == "start_method" else "INTENTIONALLY_EXCLUDED_UNKNOWN_COMPOSITION"
                gaps.append({"observation_id": oid, "field": field, "classification": classification,
                    "cause": "SCOPED_CODE_NORMALIZATION" if changed else "ABSENT_UNAMBIGUOUS_PDF_METHOD_MARKER" if field == "start_method" else "COMPONENT_IS_NOT_WHOLE_CODE_GRAMMAR",
                    "raw_history_line": row["raw_history_line"], "pdf_sha256": row["pdf_sha256"], "pdf_page": row["pdf_page"],
                    "before": before["fields"][field], "after": after["fields"][field], "official_control": original["review"]["source"]})
        attempt = attempts.get(oid, {"status": "NOT_REQUESTED_NO_EXISTING_BOUND_TARGET_CHAIN_OR_QUALIFIER_RESULT",
            "reason": "Existing archives/venue candidates checked; no exact approved historical-source binding. Candidate provider IDs/aliases alone do not verify this observation. Needs bounded identity/source research in M7B2a."})
        output.append({"observation_id": oid, "target_horse_name": row["target_horse_name"], "target_race_id": row["target_race_id"],
            "target_country": "NO" if row["target_race_id"].split(":")[1].startswith("BJ_") else "SE",
            "historical_country": context[oid]["track"]["country"] if context[oid]["status"] == "VERIFIED" else "UNKNOWN",
            "historical_venue": context[oid]["track"] if context[oid]["status"] == "VERIFIED" else "UNKNOWN",
            "historical_date": row["historical_date"], "historical_race_number": row["historical_race_number"],
            "gallop_evidence": "AFFIRMATIVE" if after["fields"]["gallop_flag"]["value"] is True else after["fields"]["gallop_flag"]["status"],
            "dq_evidence": "AFFIRMATIVE" if after["fields"]["disqualification_flag"]["value"] is True else after["fields"]["disqualification_flag"]["status"],
            "start_kind": "QUALIFICATION" if after["fields"]["qualification_flag"]["value"] is True else "NOT_MARKED_QUALIFICATION_IN_SOURCE",
            "printed_track": row["historical_track"], "pdf_sha256": row["pdf_sha256"], "pdf_page": row["pdf_page"],
            "raw_history_line": row["raw_history_line"], "raw_codes": after["raw_codes"], "result_status": after["result_status"],
            "candidates": register["codes"][row["historical_track"]]["candidates"], "before": old, "after": new,
            "before_fields": before["fields"], "after_fields": after["fields"], "changes": after["normalization_changes"],
            "venue_review": attempt if original["status"] != "VERIFIED" else {"status": "BASELINE_ALREADY_VERIFIED"},
            "original_venue_status": original["status"], "source_observed_at": row["source_evidence"]["source_observed_at"],
            "official_control": context[oid].get("review", {}).get("source", "NOT_AVAILABLE"),
            "identity_admission": "NOT_APPROVED", "allowed_use": "RESEARCH_ONLY", "model_eligible": False})
    return report(output, gaps, policy)


def report(rows, gaps, policy):
    summary = {}
    for side in ("before", "after"):
        counts = {g: dict(Counter(r[side]["gates"][g] for r in rows)) for g in "ABCDE"}
        active, attrition = list(rows), [{"gate": "INPUT", "remaining": len(rows), "excluded_here": []}]
        for g in "ABCDE":
            kept = [r for r in active if r[side]["gates"][g] == "PASS"]
            attrition.append({"gate": g, "remaining": len(kept), "excluded_here": [r["observation_id"] for r in active if r not in kept]})
            active = kept
        summary[side] = {"gate_counts": counts, "sequential_attrition": attrition,
            "venue_status": dict(Counter(r[side]["physical_status"] for r in rows)),
            "identity_research_candidates": sum("IDENTITY_RESEARCH_CANDIDATE" in r[side]["categories"] for r in rows)}
    excluded = Counter(x for r in rows for x in r["after"]["exclusion_reasons"])
    overlap = Counter(pair for r in rows for pair in combinations(r["after"]["exclusion_reasons"], 2))
    groups = {}
    for dimension in ("target_country", "historical_country", "printed_track", "historical_date", "target_horse_name", "result_status", "gallop_evidence", "dq_evidence", "start_kind"):
        groups[dimension] = {}
        for value in sorted({r[dimension] for r in rows}):
            subset = [r for r in rows if r[dimension] == value]
            groups[dimension][value] = {"observations": len(subset), "A": sum(r["after"]["gates"]["A"] == "PASS" for r in subset),
                "B": sum(r["after"]["gates"]["B"] == "PASS" for r in subset), "C": sum(r["after"]["gates"]["C"] == "PASS" for r in subset),
                "identity_study": sum("IDENTITY_RESEARCH_CANDIDATE" in r["after"]["categories"] for r in subset),
                "quantitative_ABC": sum(all(r["after"]["gates"][g] == "PASS" for g in "ABC") for r in subset)}
    return {"schema": "M7B1B_GATE_REPORT_V1", "version": VERSION, "rows": len(rows), "summary": summary,
        "gap_classification_counts": dict(Counter(g["classification"] for g in gaps)), "gaps": gaps,
        "previously_unverified_reviewed": sum(r["original_venue_status"] != "VERIFIED" for r in rows),
        "exclusion_reason_counts": dict(sorted(excluded.items())),
        "reason_overlap_pairs": [{"reasons": list(pair), "observations": n} for pair, n in sorted(overlap.items())],
        "bias_groups": groups, "policy_version": policy["version"], "observations": rows,
        "representative": False, "model_eligible": 0, "gate_D_approved": 0, "gate_E_approved": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = run(args.root)
    with args.output.open("x") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({k: result[k] for k in ("rows", "summary", "gap_classification_counts", "previously_unverified_reviewed", "model_eligible")}, indent=2))


if __name__ == "__main__":
    main()
