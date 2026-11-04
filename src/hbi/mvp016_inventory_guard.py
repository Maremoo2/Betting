"""MVP-016: never represent a failed GitHub inventory read as zero races.

The only outputs are original-backed, read-only status diagnostics. Neither this
guard nor the workflow repairs, backfills, scores, certifies PIT, or authorizes bets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1"
OUTAGE_REASON = "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"
DOWNLOAD_REASON = "ORIGINAL_ARTIFACT_DOWNLOAD_UNAVAILABLE"


def inventory_status(doc: dict) -> tuple[bool, str]:
    """An explicit full-inventory outage is not an empty physical cohort."""
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != SCHEMA
        or doc.get("bet_authority") is not False
        or not isinstance(doc.get("missing_originals"), list)
        or not isinstance(doc.get("selected_artifacts"), list)
    ):
        return False, "DEV011_CUMULATIVE_INVENTORY_MANIFEST_INVALID"
    reasons = [
        item.get("reason")
        for item in doc["missing_originals"]
        if isinstance(item, dict)
    ]
    if OUTAGE_REASON in reasons:
        return False, OUTAGE_REASON
    if doc.get("github_artifact_inventory_sha256") is None:
        return False, "DEV011_INVENTORY_SHA256_MISSING"
    integrity = doc.get("original_integrity_failures", [])
    if not isinstance(integrity, list) or integrity:
        return False, "DOWNLOADED_ORIGINAL_INTEGRITY_FAILED"
    return True, "CUMULATIVE_INVENTORY_AVAILABLE_RESEARCH_ONLY"


def _download_status(doc: dict, receipt: Path | None) -> tuple[bool, str, int, str | None]:
    """Fail closed when ANY artifact GET failed in this exact run.

    A complete inventory page list alone does not prove all selected source
    bytes were retrieved. The failure receipt is diagnostic metadata, never an
    authority to construct originals, results, model inputs or PIT.
    """
    if receipt is None:
        return True, "NO_FAILURE_RECEIPT_REQUIRED", 0, None
    if not receipt.is_file() or receipt.is_symlink():
        return False, "DEV011_DOWNLOAD_FAILURE_RECEIPT_MISSING", 0, None
    raw = receipt.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if not raw:
        return True, "ALL_SELECTED_ARTIFACT_DOWNLOADS_REPORTED_SUCCESS", 0, checksum
    try:
        text = raw.decode("utf-8")
        lines = text.splitlines()
        selected = {
            (str(row["source_run_id"]), str(row["name"]), str(row["kind"]))
            for row in doc["selected_artifacts"]
            if row.get("expired") is False
        }
        observed = set()
        for line in lines:
            pieces = tuple(line.split("\t"))
            if (len(pieces) != 3 or pieces not in selected or pieces in observed):
                return False, "DEV011_DOWNLOAD_FAILURE_RECEIPT_INVALID", len(lines), checksum
            observed.add(pieces)
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        return False, "DEV011_DOWNLOAD_FAILURE_RECEIPT_INVALID", 0, checksum
    return False, DOWNLOAD_REASON, len(observed), checksum


def guard(
    manifest: Path, *, output_dir: Path, failed_downloads: Path | None = None
) -> bool:
    """A blocked run publishes a distinct status, NEVER a scorecard index."""
    try:
        if not manifest.is_file() or manifest.is_symlink():
            raise ValueError("DEV011_MANIFEST_ORIGINAL_NOT_AVAILABLE")
        source = json.loads(manifest.read_bytes())
        allowed, status = inventory_status(source)
        if allowed:
            downloaded, reason, failure_count, failure_sha = _download_status(
                source, failed_downloads
            )
            if not downloaded:
                allowed, status = False, reason
        else:
            failure_count, failure_sha = 0, None
    except (OSError, ValueError, TypeError, AttributeError):
        allowed, status = False, "DEV011_MANIFEST_ORIGINAL_UNVERIFIABLE"
        failure_count, failure_sha = 0, None
    if allowed:
        return True
    output_dir.mkdir(parents=True, exist_ok=False)
    diagnostic = {
        "schema": "MVP016_CUMULATIVE_SCORECARD_SOURCE_UNAVAILABLE_V1",
        "status": "BLOCKED_SOURCE",
        "source_reason": status,
        "failed_downloads_count": failure_count,
        "failed_downloads_receipt_sha256": failure_sha,
        "cumulative_physical_races": None,
        "paired_champion_core004": None,
        "triple_evaluable": None,
        "scorecard_generated": False,
        "prior_verified_scorecard_invalidated": False,
        "originals_reconstructed": False,
        "pit_certified": False,
        "bet_authority": False,
    }
    (output_dir / "source-unavailable.json").write_text(
        json.dumps(diagnostic, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--failed-downloads-tsv", type=Path)
    args = parser.parse_args(argv)
    if guard(
        args.manifest, output_dir=args.output_dir,
        failed_downloads=args.failed_downloads_tsv,
    ):
        print("MVP016_CUMULATIVE_ORIGINAL_INVENTORY_AVAILABLE")
        return 0
    print("::error::MVP016_CUMULATIVE_ORIGINAL_INVENTORY_BLOCKED_NOT_ZERO_COVERAGE")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
