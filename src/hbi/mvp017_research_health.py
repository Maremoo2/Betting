"""MVP-017 read-only GitHub-original-backed research health.

Separate CURRENT_VALID and LAST_KNOWN_VALID, even across a misleading
0/0/0 scorecard. Explicit HEAD/run attribution is supplied by a caller;
source SHA validates exact original bytes but does not authenticate GitHub
metadata by itself. No refit, provider request, PIT approval or BET.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "MVP017_RESEARCH_HEALTH_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
GITHUB_COMMIT_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
STATUS = ("CURRENT_VALID", "LAST_KNOWN_VALID", "SOURCE_UNAVAILABLE",
          "INCONSISTENT", "NOT_EVALUATED")


def _raw(path: Path, expected_sha: str) -> dict:
    if (not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha)
            or path.is_symlink() or not path.is_file()):
        raise ValueError("ORIGINAL_FILE_OR_PIN_INVALID")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha:
        raise ValueError("ORIGINAL_SHA_MISMATCH")
    try:
        doc = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ValueError("ORIGINAL_JSON_INVALID") from exc
    if not isinstance(doc, dict):
        raise TypeError("ORIGINAL_DOCUMENT_NOT_OBJECT")
    return doc


def classify_snapshot(entry: dict) -> dict:
    """Validate one GitHub-run original pair. Fail closed on any conflict."""
    rid = entry.get("run_id")
    sha = entry.get("github_head_sha")
    if (type(rid) is not int or rid <= 0 or not isinstance(sha, str)
            or not GITHUB_COMMIT_SHA.fullmatch(sha)):
        raise ValueError("SOURCE_RUN_OR_HEAD_SHA_INVALID")
    base = {
        "run_id": rid, "github_head_sha_claim": sha,
        "status": "INCONSISTENT", "counts": None,
        "original_coverage_complete": None, "generated_at_utc": None,
        "source_reason": "UNVERIFIED_SOURCE",
        "scorecard_sha256": entry.get("scorecard_sha256"),
        "coverage_manifest_sha256": entry.get("coverage_manifest_sha256"),
    }
    try:
        manifest = _raw(
            Path(entry["coverage_manifest_path"]), entry["coverage_manifest_sha256"]
        )
    except (ValueError, KeyError, TypeError, OSError):
        return base | {"status": "SOURCE_UNAVAILABLE",
                       "source_reason": "SOURCE_MANIFEST_UNAVAILABLE_OR_SHA_MISMATCH"}
    if (manifest.get("schema") != "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1"
            or manifest.get("bet_authority") is not False):
        return base | {"source_reason": "MANIFEST_CONTRACT_INVALID"}
    outage = any(
        isinstance(row, dict)
        and row.get("reason") == "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"
        for row in (manifest.get("missing_originals") or [])
    )
    if outage:
        try:
            score = _raw(Path(entry["scorecard_path"]), entry["scorecard_sha256"])
        except (ValueError, KeyError, TypeError, OSError):
            score = None
        # A real outage never becomes a valid 0/0/0 scorecard.
        if score is not None and isinstance(score.get("counts"), dict):
            return base | {"source_reason": "FALSE_ZERO_SCORECARD_FROM_SOURCE_OUTAGE"}
        return base | {"status": "SOURCE_UNAVAILABLE",
                       "source_reason": "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"}
    if (not isinstance(manifest.get("github_artifact_inventory_sha256"), str)
            or not SHA.fullmatch(manifest["github_artifact_inventory_sha256"])):
        return base | {"source_reason": "INVENTORY_SOURCE_SHA_MISSING"}
    try:
        score = _raw(Path(entry["scorecard_path"]), entry["scorecard_sha256"])
    except (ValueError, KeyError, TypeError, OSError):
        return base | {"status": "SOURCE_UNAVAILABLE",
                       "source_reason": "SCORECARD_MISSING_OR_SHA_MISMATCH"}
    if (score.get("schema") != "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1"
            or score.get("bet_authority") is not False
            or score.get("model_originals_verified_by_sha") is not True):
        return base | {"source_reason": "SCORECARD_SOURCE_CONTRACT_INVALID"}
    inventory = score.get("cumulative_original_inventory") or {}
    if inventory.get("github_artifact_inventory_sha256") != (
        manifest["github_artifact_inventory_sha256"]
    ):
        return base | {"source_reason": "SCORECARD_AND_INVENTORY_SOURCE_CONFLICT"}
    counts = score.get("counts")
    records = score.get("records")
    if not isinstance(counts, dict) or not isinstance(records, list):
        return base | {"source_reason": "SCORECARD_RECORDS_OR_COUNTS_MISSING"}
    names = [row.get("race_id") for row in records if isinstance(row, dict)]
    pairs = [row for row in records if isinstance(row, dict)
             and row.get("status") == "EVALUABLE_RESEARCH_ONLY"]
    triples = [row for row in pairs if row.get("benchmark_status") == "TRIPLE_EVALUABLE"]
    if (len(names) != len(records) or len(names) != len(set(names))
            or len(names) != counts.get("physical_races")
            or len(pairs) != counts.get("paired_champion_core004")
            or len(triples) != counts.get("triple_evaluable")
            or len(pairs) - len(triples) != counts.get("model_pair_only")
            or not all(row.get("bet_authority") is False for row in records)
            or type(counts.get("pit_certified_paired")) is not int
            or counts["pit_certified_paired"] < 0):
        return base | {"source_reason": "PHYSICAL_RACE_COUNTS_OR_STATUS_CONFLICT"}
    return base | {
        "status": "CURRENT_VALID",
        "source_reason": "VALID_ORIGINAL_INVENTORY_AND_SCORECARD_RESEARCH_ONLY",
        "counts": {
            "physical_races": len(records),
            "paired_champion_core004": len(pairs),
            "triple_evaluable": len(triples),
            "model_pair_only": len(pairs) - len(triples),
            "pit_certified_paired": counts["pit_certified_paired"],
        },
        "original_coverage_complete": manifest.get("coverage_complete") is True,
        "generated_at_utc": score.get("generated_at_utc"),
    }


def summarize(
    snapshots: list[dict], *, v1_audit_path: Path | None = None,
    v1_audit_sha256: str | None = None,
) -> dict[str, Any]:
    """Sort by supplied GitHub run IDs; no silent fall-through to zero."""
    if not isinstance(snapshots, list):
        raise TypeError("SNAPSHOTS_NOT_LIST")
    by_run: dict[int, dict] = {}
    for entry in snapshots:
        if not isinstance(entry, dict):
            raise TypeError("SNAPSHOT_NOT_OBJECT")
        value = classify_snapshot(entry)
        if value["run_id"] in by_run:
            raise ValueError("DUPLICATE_GITHUB_RUN")
        by_run[value["run_id"]] = value
    ordered = sorted(by_run.values(), key=lambda x: x["run_id"], reverse=True)
    latest = ordered[0] if ordered else None
    valid = next((row for row in ordered if row["status"] == "CURRENT_VALID"), None)
    if latest is None:
        health = "NOT_EVALUATED"
    elif latest["status"] == "CURRENT_VALID":
        health = "CURRENT_VALID"
    elif valid is not None:
        health = "LAST_KNOWN_VALID"
    else:
        health = latest["status"]
    v1 = {"status": "NOT_EVALUATED", "original_sha256": None,
          "temporal_integrity": None, "runtime_replay_parity": None,
          "settlement_integrity": None, "provider_integrity": None}
    if v1_audit_path is not None:
        if v1_audit_sha256 is None:
            raise ValueError("V1_ORIGINAL_SHA_REQUIRED")
        original = _raw(v1_audit_path, v1_audit_sha256)
        if (original.get("schema_version") != "HBI_V1_SYSTEM_AUDIT_V1"
                or not all(isinstance(original.get(k), dict) for k in (
                    "temporal_integrity", "runtime_replay_parity",
                    "settlement_integrity", "provider_integrity",
                ))):
            raise ValueError("V1_ORIGINAL_CONTRACT_INVALID")
        v1 = {
            "status": "ORIGINAL_SYSTEM_AUDIT_LOADED_NOT_P0_CLEARED",
            "original_sha256": v1_audit_sha256,
            **{key: original[key].get("status") for key in (
                "temporal_integrity", "runtime_replay_parity",
                "settlement_integrity", "provider_integrity",
            )},
        }
    return {
        "schema": SCHEMA,
        "status": health,
        "latest_supplied_run_status": latest["status"] if latest else "NOT_EVALUATED",
        "latest_supplied_run_id": latest["run_id"] if latest else None,
        "latest_source_reason": latest["source_reason"] if latest else None,
        "last_verified_run_id": valid["run_id"] if valid else None,
        "last_verified_source_sha256": {
            "scorecard": valid["scorecard_sha256"],
            "coverage_manifest": valid["coverage_manifest_sha256"],
        } if valid else None,
        "last_verified_counts": valid["counts"] if valid else None,
        "last_verified_original_coverage_complete": (
            valid["original_coverage_complete"] if valid else None
        ),
        "last_verified_generated_at_utc": valid["generated_at_utc"] if valid else None,
        "supplied_snapshots": ordered,
        "v1_system_audit": v1,
        "run_metadata_independently_authenticated": False,
        "status_is_not_model_or_bet_approval": True,
        "pit_certification_performed": False,
        "bet_authority": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--v1-audit", type=Path)
    parser.add_argument("--v1-audit-sha256")
    args = parser.parse_args(argv)
    if args.snapshot_manifest.is_symlink() or not args.snapshot_manifest.is_file():
        raise ValueError("SNAPSHOT_INPUT_MISSING")
    candidates = json.loads(args.snapshot_manifest.read_bytes())
    if not isinstance(candidates, list):
        raise TypeError("SNAPSHOT_INPUT_NOT_LIST")
    result = summarize(
        candidates, v1_audit_path=args.v1_audit,
        v1_audit_sha256=args.v1_audit_sha256,
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "index.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
