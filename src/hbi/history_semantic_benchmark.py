"""Offline research benchmark over existing collector records and frozen PDF truth.

This command writes only the requested research JSON report. No canonical DB,
identity, model, or betting admission is modified.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .history_semantics import VERSION, normalize_prior
from .pdf_semantic_validation import (
    BUNDLE_SHA,
    FIELDS,
    STATUSES,
    checked_bytes,
    classify,
    compare,
    read_sources,
    truth_data,
)
from .pdf_validation import PARSER_SHA256, load_parser, physical_candidates, sha

KNOWN_SHA = "82ca3f9e043cfc76c672b7efe15efe9da93090387972c762f4e306ffdaf1e39d"
HOLDOUT_SHA = "f9d9eaf36b778b7af13738dbf49dcff81690119b1987827d0d676d8a95f58b87"


def score(rows, parsed, sources, codebook):
    """Validate source location/block first; never silently use a wrong assignment."""
    baseline = compare(rows, parsed, {h: pages for h, (_, pages) in sources.items()})
    output = []
    for row, location in zip(rows, baseline["observations"], strict=True):
        matches = [(h, p) for d, _physical in parsed[row["pdf_sha256"]]
            for h in d["entrants"] for p in h["past_starts"] if p["raw_text"] == row["raw_history_line"]]
        structural = location["structural_assignment"]
        semantic = {}
        if structural == "CORRECT" and len(matches) == 1:
            horse, prior = matches[0]
            provenance = {**row["source_evidence"], "pdf_sha256": row["pdf_sha256"],
                "pdf_page": row["pdf_page"], "upstream_parser_sha256": PARSER_SHA256,
                "target_race_id": row["target_race_id"], "printed_horse": horse["name"],
                "horse_identity_status": "UNRESOLVED_NOT_NAME_VERIFIED"}
            semantic = normalize_prior(prior, target_date=row["target_race_id"].split(":")[1][-10:],
                provenance=provenance, codebook=codebook)
        values = {}
        critical = [] if structural == "CORRECT" else ["WRONG_OR_AMBIGUOUS_HORSE_OR_PHYSICAL_RACE"]
        for field in FIELDS:
            extracted = semantic.get("fields", {}).get(field, {})
            actual = extracted.get("value") if extracted.get("status") == "EXTRACTED" else None
            status = classify(row[field], actual)
            values[field] = {"expected": row[field], "actual": actual if actual is not None else "NOT_EXTRACTED",
                "status": status, "extraction_status": extracted.get("status", "NOT_EXTRACTED")}
            if status == "INCORRECT":
                critical.append(f"INCORRECT_MODEL_INPUT:{field}")
            elif status == "NOT_EXTRACTED":
                critical.append(f"MISSING_REQUIRED_SEMANTIC_INPUT:{field}")
        output.append({"observation_id": row["observation_id"], "source_localization": location["source_localization"],
            "history_line_found": location["history_line_found"], "structural_assignment": structural,
            "pdf_sha256": row["pdf_sha256"], "pdf_page": row["pdf_page"],
            "raw_history_line": row["raw_history_line"], "fields": values,
            "critical_findings": critical, "semantic": semantic})
    metrics = {}
    for field in FIELDS:
        counts = Counter(r["fields"][field]["status"] for r in output)
        assessed = counts["CORRECT"] + counts["INCORRECT"] + counts["NOT_EXTRACTED"]
        extracted = counts["CORRECT"] + counts["INCORRECT"]
        metrics[field] = {"assessable": assessed, "correct": counts["CORRECT"], "incorrect": counts["INCORRECT"],
            "not_extracted": counts["NOT_EXTRACTED"], "ambiguous_source": counts["AMBIGUOUS_SOURCE"],
            "not_applicable": counts["NOT_APPLICABLE"], "coverage": extracted / assessed if assessed else "NOT_APPLICABLE",
            "accuracy_among_extracted": counts["CORRECT"] / extracted if extracted else "NOT_APPLICABLE",
            "accuracy_among_assessable": counts["CORRECT"] / assessed if assessed else "NOT_APPLICABLE",
            "extraction_status_counts_all_rows": dict(Counter(r["fields"][field]["extraction_status"] for r in output)),
            "counts": {s: counts[s] for s in STATUSES}}
    track = Counter(r["semantic"].get("fields", {}).get("track_identity", {}).get("status", "NOT_EXTRACTED") for r in output)
    return {"rows": len(rows), "field_metrics": metrics, "observations": output,
        "baseline_field_metrics": baseline["field_metrics"], "representative": False, "model_eligible": 0,
        "source_localization": dict(Counter(r["source_localization"] for r in output)),
        "structural_assignment": dict(Counter(r["structural_assignment"] for r in output)),
        "critical_findings": dict(Counter(f for r in output for f in r["critical_findings"])),
        "track_identity_status_counts": dict(track),
        "track_identity_accuracy": "NOT_MEASURED_NO_INDEPENDENT_PHYSICAL_IDENTITY_GOLD"}


def run(root, parser_path, *, archived=False, include_holdout=True):
    root = Path(root)
    fixtures = root / "tests/fixtures"
    known = truth_data(fixtures / "m7a1-ground-truth-v1.json", KNOWN_SHA)
    book_path = root / "docs/M7B1_CODEBOOK.json"
    codebook = json.loads(book_path.read_bytes())
    sources = read_sources(fixtures / "m7a-pdf-validation.zip")
    parse = None if archived else load_parser(parser_path, PARSER_SHA256)
    parsed = {}
    for pdf_hash, (meta, pages) in sources.items():
        if archived:
            docs = meta["archived_parser_output"]
        else:
            race = meta["archived_parser_output"][0]["race"]
            docs = parse("\n\n".join(pages), meeting_id=meta["meeting_id"], date=meta["date"],
                url=race["source_url"], captured_at=race["captured_at_utc"], track=race["track"])["races"]
        parsed[pdf_hash] = [(doc, physical_candidates(doc, meta["canonical_starts"])) for doc in docs]
    result = {"schema": "M7B1_SEMANTIC_BENCHMARK_V1", "version": VERSION,
        "upstream_execution": "ARCHIVED_OUTPUT_ONLY" if archived else "ACTUAL_EXTERNAL_PARSER_EXECUTION",
        "source_bundle_sha256": BUNDLE_SHA, "upstream_parser_sha256": PARSER_SHA256,
        "codebook_sha256": sha(book_path.read_bytes()), "known_truth_sha256": KNOWN_SHA,
        "adapter_sha256": sha(Path(__file__).with_name("history_semantics.py").read_bytes()),
        "evaluator_sha256": sha(Path(__file__).read_bytes()), "model_eligible": 0,
        "known": score(known["rows"], parsed, sources, codebook)}
    if include_holdout:
        holdout = json.loads(checked_bytes(fixtures / "m7b1-holdout-v1.json", HOLDOUT_SHA))
        if holdout["schema"] != "M7B1_LOCKED_HOLDOUT_V1" or len(holdout["rows"]) != 30:
            raise ValueError("INVALID_LOCKED_HOLDOUT")
        known_keys = {(r["pdf_sha256"], r["raw_history_line"]) for r in known["rows"]}
        holdout_keys = {(r["pdf_sha256"], r["raw_history_line"]) for r in holdout["rows"]}
        if len(holdout_keys) != 30 or known_keys & holdout_keys:
            raise ValueError("HOLDOUT_OVERLAP_OR_DUPLICATE")
        result["holdout_truth_sha256"] = HOLDOUT_SHA
        result["holdout"] = score(holdout["rows"], parsed, sources, codebook)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--parser-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--known-only", action="store_true", help="Development: do not open holdout labels")
    args = parser.parse_args()
    report = run(args.root, args.parser_path, include_holdout=not args.known_only)
    with args.output.open("x") as f:  # Never silently overwrite a frozen first evaluation.
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    for group in ("known", "holdout"):
        if group in report:
            r = report[group]
            print(f"{group}: rows={r['rows']} structure={r['structural_assignment']} model_eligible=0")
            for field, metric in r["field_metrics"].items():
                print(f"  {field}: correct={metric['correct']}/{metric['assessable']} incorrect={metric['incorrect']} missing={metric['not_extracted']} ambiguous={metric['ambiguous_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
