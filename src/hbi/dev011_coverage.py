"""DEV-011: immutable GitHub artifact inventory and archived official receipt reuse.

This is only an offline research input selector. It never modifies PIT recovery,
models, past decisions or betting authority. Artifact inclusion is decided by
provider run provenance, never by result quality or model scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1"
KIND = re.compile(r"(bet-mvp-shadow|dev009-outcome-scorecards)-([0-9]+)\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_original(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("ORIGINAL_NOT_AVAILABLE")
    doc = json.loads(path.read_bytes())
    if not isinstance(doc, dict):
        raise ValueError("ORIGINAL_NOT_OBJECT")
    return doc


def plan(pages: list[dict], *, current_run_id: int, inventory_sha: str) -> dict:
    """Full, uncapped pagination; no model-result-based or latest-N selection."""
    if not isinstance(pages, list) or not pages:
        raise ValueError("ARTIFACT_PAGES_MISSING")
    expected = pages[0].get("total_count")
    if type(expected) is not int or expected < 0:
        raise ValueError("ARTIFACT_TOTAL_COUNT_MISSING")
    seen: set[int] = set()
    selected = []
    observed = 0
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
            raise ValueError("ARTIFACT_PAGE_INVALID")
        if page.get("total_count") != expected:
            raise ValueError("ARTIFACT_PAGINATION_CONCURRENT_CHANGE")
        observed += len(page["artifacts"])
        for item in page["artifacts"]:
            aid = item.get("id")
            if type(aid) is not int or aid <= 0 or aid in seen:
                raise ValueError("ARTIFACT_DUPLICATE_OR_INVALID_ID")
            seen.add(aid)
            matched = KIND.fullmatch(str(item.get("name", "")))
            if not matched:
                continue
            parent = item.get("workflow_run") or {}
            run_id = parent.get("id")
            if (type(run_id) is not int or run_id != int(matched.group(2))
                    or parent.get("head_branch") != "main" or run_id == current_run_id):
                continue
            selected.append({
                "artifact_id": aid, "source_run_id": run_id,
                "name": str(item["name"]),
                "kind": "model" if matched.group(1) == "bet-mvp-shadow" else "result",
                "created_at": item.get("created_at"),
                "expired": item.get("expired") is True,
                "status": "EXPIRED_ORIGINAL_ARTIFACT" if item.get("expired") is True
                          else "PENDING_ORIGINAL_DOWNLOAD",
            })
    if observed != expected:
        raise ValueError("INCOMPLETE_ARTIFACT_PAGINATION")
    selected.sort(key=lambda r: (r["source_run_id"], r["artifact_id"]))
    return {
        "schema": SCHEMA, "authority": "READ_ONLY_RESEARCH",
        "bet_authority": False, "pit_certification_performed": False,
        "github_artifact_inventory_sha256": inventory_sha,
        "github_artifacts_enumerated": observed, "github_pages_enumerated": len(pages),
        "selected_artifacts": selected,
        "selection_rule": "ALL_MAIN_ORIGINALS_UNCAPPED_SORTED_BY_SOURCE_RUN_AND_ID",
        "missing_originals": [], "recovered_artifacts": 0,
        "coverage_complete": not any(r["expired"] for r in selected),
    }


def finalize(manifest: dict, *, models_root: Path, results_root: Path) -> dict:
    """Inspect on-disk downloaded original indexes without inventing recovery."""
    if manifest.get("schema") != SCHEMA or manifest.get("bet_authority") is not False:
        raise ValueError("INVENTORY_MANIFEST_INVALID")
    missing = []
    for entry in manifest["selected_artifacts"]:
        if entry["expired"]:
            missing.append({
                "artifact_id": entry["artifact_id"], "source_run_id": entry["source_run_id"],
                "kind": entry["kind"], "reason": "EXPIRED_ORIGINAL_ARTIFACT",
            })
            continue
        root = models_root if entry["kind"] == "model" else results_root
        path = root / str(entry["source_run_id"]) / (
            "cohort-index.json" if entry["kind"] == "model" else "index.json"
        )
        try:
            raw = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
            if not raw:
                raise ValueError("ORIGINAL_ARTIFACT_NOT_DOWNLOADED")
            doc = json.loads(raw)
            schema = ("BET_MVP_002_FIXED_COHORT_INDEX_V1" if entry["kind"] == "model"
                      else "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1")
            if (not isinstance(doc, dict) or doc.get("schema") != schema
                    or doc.get("bet_authority") is not False):
                raise ValueError("ARCHIVED_INDEX_CONTRACT_INVALID")
            entry["status"] = "ORIGINAL_INDEX_AVAILABLE"
            entry["original_index_sha256"] = sha(raw)
            if entry["kind"] == "model":
                processed = doc.get("processed")
                if not isinstance(processed, list):
                    raise ValueError("FROZEN_INDEX_PROCESSED_INVALID")
                for report in processed:
                    if not isinstance(report, dict):
                        raise ValueError("FROZEN_REPORT_ENTRY_INVALID")
                    directory = report.get("directory")
                    expected = report.get("report_sha256")
                    if (not isinstance(directory, str)
                            or re.fullmatch(r"bet-mvp-shadow/race-[0-9]{3,}", directory) is None
                            or not SHA256.fullmatch(str(expected))):
                        raise ValueError("FROZEN_MODEL_INDEX_CONTRACT_INVALID")
                    member = path.parent / directory.split("/")[-1] / "shadow.json"
                    if not member.is_file() or member.is_symlink() or sha(
                        member.read_bytes()
                    ) != expected:
                        raise ValueError("FROZEN_MODEL_ORIGINAL_SHA256_MISMATCH")
                entry["frozen_reports_declared"] = len(processed)
            else:
                entry["prior_scored_races_declared"] = sum(
                    r.get("status") == "EVALUABLE_RESEARCH_ONLY"
                    for r in doc.get("records", []) if isinstance(r, dict)
                )
        except (OSError, ValueError, TypeError):
            entry["status"] = "MISSING_OR_UNVERIFIABLE_ORIGINAL"
            missing.append({
                "artifact_id": entry["artifact_id"], "source_run_id": entry["source_run_id"],
                "kind": entry["kind"], "reason": entry["status"],
            })
    _, result_errors = pinned_official(results_root)
    for race_id, reasons in sorted(result_errors.items()):
        missing.append({
            "race_id": race_id,
            "kind": "result",
            "reason": ",".join(reasons),
        })
    manifest["pinned_result_races_checked"] = len(pinned_official(results_root)[0])
    manifest["missing_originals"] = missing
    manifest["recovered_artifacts"] = sum(
        r["status"] == "ORIGINAL_INDEX_AVAILABLE" for r in manifest["selected_artifacts"]
    )
    manifest["coverage_complete"] = not bool(missing)
    manifest["status"] = (
        "INCOMPLETE_ORIGINAL_COVERAGE" if missing else "ORIGINAL_INVENTORY_RECOVERED"
    )
    return manifest


def pinned_official(root: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Reuse first archived official response; fail on tampering/changed versions.

    Only previously *original-verified*, source-hashed result pairs qualify.
    An earlier failed scorecard is never upgraded to official proof.
    """
    verified: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    blocked: dict[str, list[str]] = defaultdict(list)
    if not root.is_dir():
        return {}, {}
    for index in sorted(root.glob("*/index.json"), key=lambda p: (int(p.parent.name), p.name)):
        try:
            doc = _json_original(index)
            if (doc.get("schema") != "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
                    or doc.get("bet_authority") is not False
                    or doc.get("v33_evaluator_called") is not False):
                continue
        except (OSError, ValueError, TypeError):
            continue
        for row in doc.get("records") or []:
            if not isinstance(row, dict) or row.get("status") != "EVALUABLE_RESEARCH_ONLY":
                continue
            rid = row.get("race_id")
            if not isinstance(rid, str) or not rid.startswith("RIKSTOTO:"):
                continue
            try:
                if (not SHA256.fullmatch(str(row.get("source_model_original_sha256", "")))
                        or row.get("bet_authority") is not False):
                    raise ValueError("PINNED_MODEL_OR_RESULT_METADATA_INVALID")
                recs = row.get("original_result_receipts")
                if not isinstance(recs, list) or len(recs) != 2:
                    raise ValueError("PINNED_RECEIPTS_INCOMPLETE")
                official_dir = index.parent / ("official-" + sha(rid.encode())[:16])
                payloads: dict[str, dict] = {}
                receipt_map = {}
                for rec in recs:
                    role = rec.get("role") if isinstance(rec, dict) else None
                    if role not in {"complete", "raceday"} or role in receipt_map:
                        raise ValueError("PINNED_RECEIPT_ROLE_INVALID")
                    if (rec.get("http_status") != 200 or rec.get("error_kind") is not None
                            or not SHA256.fullmatch(str(rec.get("raw_sha256", "")))
                            or not isinstance(rec.get("observed_at_utc"), str)
                            or not isinstance(rec.get("source_uri"), str)):
                        raise ValueError("PINNED_RECEIPT_METADATA_INVALID")
                    # The original CI runner's absolute raw_path is never trusted.
                    raw = official_dir / f"{role}.raw.json"
                    if not raw.is_file() or raw.is_symlink():
                        raise ValueError("PINNED_RESULT_ORIGINAL_MISSING")
                    body = raw.read_bytes()
                    if sha(body) != rec["raw_sha256"]:
                        raise ValueError("PINNED_RESULT_SHA256_MISMATCH")
                    parsed = json.loads(body)
                    if (not isinstance(parsed, dict) or parsed.get("success") is not True
                            or not isinstance(parsed.get("result"), dict)):
                        raise ValueError("PINNED_ORIGINAL_ENVELOPE_INVALID")
                    payloads[role] = {"body": body, "result": parsed["result"]}
                    receipt_map[role] = rec
                if set(payloads) != {"complete", "raceday"}:
                    raise ValueError("PINNED_RESULT_ORIGINAL_INCOMPLETE")
                verified[rid].append((index.parent.name, {
                    "source_model_sha256": row["source_model_original_sha256"],
                    "payloads": payloads, "receipts": receipt_map,
                    "source_run_id": index.parent.name,
                }))
            except (ValueError, TypeError, KeyError, OSError):
                blocked[rid].append("PINNED_RESULT_ORIGINAL_MISSING_OR_CHANGED")
    by_race = {}
    for rid, items in verified.items():
        items.sort(key=lambda v: int(v[0]))
        if (len({x[1]["source_model_sha256"] for x in items}) != 1
                or any(len({x[1]["receipts"][role]["raw_sha256"] for x in items}) != 1
                       for role in ("complete", "raceday"))):
            blocked[rid].append("CONFLICTING_OFFICIAL_RESULT_RECEIPTS")
        elif rid not in blocked:
            by_race[rid] = items[0][1]
    return by_race, {rid: sorted(set(reasons)) for rid, reasons in blocked.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--pages", type=Path, required=True)
    p.add_argument("--current-run-id", type=int, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--downloads-tsv", type=Path, required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--manifest", type=Path, required=True)
    f.add_argument("--models-root", type=Path, required=True)
    f.add_argument("--results-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        raw = args.pages.read_bytes()
        report = plan(json.loads(raw), current_run_id=args.current_run_id,
                      inventory_sha=sha(raw))
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest.open("x", encoding="utf-8") as file:
            json.dump(report, file, indent=2, sort_keys=True)
            file.write("\n")
        with args.downloads_tsv.open("x", encoding="utf-8") as file:
            for row in report["selected_artifacts"]:
                if not row["expired"]:
                    file.write(f'{row["source_run_id"]}\t{row["name"]}\t{row["kind"]}\n')
    else:
        report = finalize(_json_original(args.manifest),
                          models_root=args.models_root, results_root=args.results_root)
        args.manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
