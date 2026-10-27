"""DATA-004 offline diagnostics; never update canonical Betting/Collector data.

DATA-003B's 60 rows are developmental examples, not an independent holdout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

FIELDS = (
    "date", "track", "race_number", "distance", "start_method",
    "result_category", "placing", "km_time", "driver", "shoes", "wagon",
    "gallop", "dq",
)
STATUS_QUOTAS = {"PARSED": 20, "PARTIAL": 20, "UNPARSEABLE": 20}
# Quoted historical prize anchors the shoe/wagon fields, not free-text notes.
EQUIPMENT = re.compile(r"\b\d+['’]\s+(?P<shoes>[c¢]{2})\s+(?P<wagon>Va|Am)(?=\s|$)")
# Positive indicators ONLY; unknown codes and missing markers are not negatives.
POSITIVE_GALLOP = re.compile(
    r"\b\d{4}\s+(?:\d{1,2},\d{1,2}\s*(?:a?g)|br\s*g|ug|dg)(?=\s|$)",
    re.IGNORECASE,
)


def propose_historical_fields(
    text: str, *, parser_status: str, format_group: str
) -> dict[str, str]:
    """Research candidate: original literal equipment and positive gallop ONLY."""
    if parser_status not in {"PARSED", "PARTIAL"} or format_group != "TRAV_SPACED":
        return {}
    if "|" not in text:
        return {}
    historical_columns = text.split("|", 1)[1][:160]
    proposed: dict[str, str] = {}
    matches = list(EQUIPMENT.finditer(historical_columns))
    if len(matches) == 1:
        proposed.update(matches[0].groupdict())
    if POSITIVE_GALLOP.search(historical_columns):
        proposed["gallop"] = "True"
    return proposed


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _logical_name(path: Path) -> str:
    return re.sub(r"\(\d+\)(?=\.[^.]+$)", "", path.name)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-f0-9]{64})\s+(.+)", line)
        if not match or match[2] in checksums:
            raise ValueError("Malformed or repeated checksum entry")
        checksums[match[2]] = match[1]
    return checksums


def run_audit(
    gold_path: Path, fields_path: Path, checksums_path: Path
) -> dict[str, object]:
    checksums = _manifest(checksums_path)
    digest_checks: dict[str, str] = {}
    for path in (gold_path, fields_path):
        name = _logical_name(path)
        digest = _sha256(path)
        if checksums.get(name) != digest:
            raise ValueError(f"SHA256 mismatch or missing manifest entry: {name}")
        digest_checks[name] = digest

    gold, fields = _csv(gold_path), _csv(fields_path)
    if len(gold) != 60 or len(fields) != 780:
        raise ValueError("DATA-003B row-count contract is not satisfied")
    ids = [row["sample_id"] for row in gold]
    if len(set(ids)) != 60:
        raise ValueError("DATA-003B duplicate gold sample ID")
    if Counter(row["original_data002_status"] for row in gold) != STATUS_QUOTAS:
        raise ValueError("DATA-003B 20/20/20 stratification mismatch")
    if any(row["row_identity_status"] != "VERIFIED" for row in gold):
        raise ValueError("Original horse-row source identity is not VERIFIED")
    gold_by_id = {row["sample_id"]: row for row in gold}

    pairs: dict[tuple[str, str], dict[str, str]] = {}
    for row in fields:
        key = (row["sample_id"], row["field"])
        origin = gold_by_id.get(row["sample_id"])
        if origin is None or row["field"] not in FIELDS or key in pairs:
            raise ValueError(f"Unknown/duplicate field assessment {key!r}")
        for source_field, gold_field in (
            ("horse", "horse"),
            ("original_data002_status", "original_data002_status"),
            ("source_pdf", "pdf_path"),
            ("source_pdf_sha256", "pdf_sha256"),
            ("source_row", "original_pdf_row_text"),
            ("source_page", "source_pdf_page"),
        ):
            if row[source_field] != origin[gold_field]:
                raise ValueError(
                    f"Contradictory source field {source_field} for {key!r}"
                )
        field = row["field"]
        if (row["gold_status"] != origin[f"gold_{field}_status"] or
                row["gold_value"] != origin[f"gold_{field}"]):
            raise ValueError(f"Contradictory gold label for {key!r}")
        if row["gold_frozen_sha256"] != digest_checks[_logical_name(gold_path)]:
            raise ValueError(f"Incorrect frozen gold reference for {key!r}")
        pairs[key] = row
    for sample_id in ids:
        if {field for sid, field in pairs if sid == sample_id} != set(FIELDS):
            raise ValueError(f"Missing assessments for {sample_id}")

    baseline = Counter(item["comparison"] for item in fields)
    fixes: list[dict[str, str]] = []
    unverified_negative = 0
    for row in gold:
        sid = row["sample_id"]
        proposed = propose_historical_fields(
            row["original_pdf_row_text"],
            parser_status=row["original_data002_status"],
            format_group=pairs[(sid, "shoes")]["format_group"],
        )
        for field in ("shoes", "wagon", "gallop"):
            prior = pairs[(sid, field)]
            if prior["gold_status"] == "VERIFIED" and prior["comparison"] in {
                "MISSING", "WRONG",
            }:
                value = proposed.get(field)
                if value:
                    if value != prior["gold_value"]:
                        raise ValueError(
                            f"Candidate produces wrong value for {sid}/{field}"
                        )
                    fixes.append({
                        "sample_id": sid, "horse": row["horse"], "field": field,
                        "source_value": value, "baseline": prior["comparison"],
                    })
            if (field == "gallop" and prior["gold_status"] == "UNAVAILABLE"
                    and prior["parser_value"] == "False"):
                unverified_negative += 1
        for field, value in proposed.items():
            prior = pairs[(sid, field)]
            if prior["gold_status"] == "VERIFIED" and value != prior["gold_value"]:
                raise ValueError(f"Regressed verified value for {sid}/{field}")

    improvements = Counter(item["field"] for item in fixes)
    return {
        "schema_version": "DATA004_DIAGNOSTIC_V1",
        "status": "DEVELOPMENT_ONLY_HOLDOUT_REQUIRED",
        "production_parser_changed": False,
        "canonical_data_changed": False,
        "holdout_verified": False,
        "sample_is_representative": False,
        "source_sha256": digest_checks,
        "source_rows": len(gold),
        "field_assessments": len(fields),
        "original_status_distribution": dict(STATUS_QUOTAS),
        "baseline_comparisons": dict(baseline),
        "proposed_verified_fixes_by_field": dict(improvements),
        "proposed_verified_fix_count": len(fixes),
        "remaining_known_wrong": sum(
            x["comparison"] == "WRONG" for x in fields
        ) - sum(x["baseline"] == "WRONG" for x in fixes),
        "unverified_negative_gallop_flags": unverified_negative,
        "fixes": fixes,
        "limitations": [
            "Same DATA-003B examples used for development and evaluation; no independent holdout.",
            "Only already parsed/partial TRAV_SPACED rows are eligible.",
            "Unseen original PDFs must be independently checked before deployment.",
            "Joined columns, foreign racing, post/slot and unknown domain codes remain blocked.",
            "No probability, score, BET gate, or production Collector parser changed.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail-closed offline DATA-004 developmental regression"
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--fields", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_audit(args.gold, args.fields, args.checksums)
    data = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(data + "\n", encoding="utf-8")
    print(data)


if __name__ == "__main__":
    main()
