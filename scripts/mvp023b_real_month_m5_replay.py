"""Read-only SHA-checked historic native month -> existing M5 -> 023A research audit.

Does not use a newly-written dataset loader, train a model, read 2025, or
treat discovered inventory metadata as verified full-field training races.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from hbi.backfill import run_batch
from hbi.mvp023a_dataset_partitions import build_partitioned_dataset
from hbi.mvp023a_feature_audit import audit_feature_dataset

MONTH = re.compile(r"20(?:1[5-9]|2[0-4])-(?:0[1-9]|1[0-2])$")
PREFIXES = ("inventory/", "market-days/", "result-days/", "raw-markets/", "raw-results/")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replay(root: Path, admission_path: Path, month: str, output: Path) -> dict:
    if MONTH.fullmatch(month) is None:
        raise ValueError("2025_LOCKBOX_AND_NONHISTORIC_MONTH_FORBIDDEN")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("UNSAFE_OR_MISSING_NATIVE_SOURCE_ROOT")
    admission = json.loads(Path(admission_path).read_bytes())
    if (
        admission.get("schema") != "MVP023B_NATIVE_MONTH_ACCEPTANCE_V1"
        or admission.get("month") != month
        or admission.get("2025_lockbox_opened") is not False
        or admission.get("bet_authority") is not False
        or admission.get("origin_basis") != "ONLY_SELECTED_SHA_CHECKED_NATIVE_MONTH_ORIGINALS"
    ):
        raise ValueError("HISTORICAL_MONTH_SOURCE_ADMISSION_REQUIRED")
    receipts = admission.get("read_only_native_files_sha256")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("HISTORICAL_MONTH_ORIGINAL_RECEIPTS_MISSING")
    if admission.get("source_file_count") != len(receipts):
        raise ValueError("HISTORICAL_MONTH_SOURCE_DENOMINATOR_CONFLICT")
    from rikstoto_crawler.transport import digest

    if admission.get("source_manifest_sha256") != digest(receipts):
        raise ValueError("HISTORICAL_MONTH_RECEIPT_MANIFEST_SHA_CONFLICT")
    selected: dict[str, bytes] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise TypeError("INVALID_ORIGINAL_RECEIPT")
        path, expected = receipt.get("path"), receipt.get("sha256")
        if not isinstance(path, str) or not isinstance(expected, str):
            raise TypeError("INVALID_ORIGINAL_PATH_OR_SHA")
        parts = Path(path).parts
        if (
            Path(path).is_absolute() or ".." in parts or "\\" in path
            or not path.startswith(PREFIXES)
            or "2025-" in path or path in selected
        ):
            raise ValueError("UNSAFE_OR_DUPLICATE_ORIGINAL_ARCHIVE_MEMBER")
        target = root
        for part in parts:
            target = target / part
            if target.is_symlink():
                raise ValueError("SYMLINKED_ORIGINAL_SOURCE_REFUSED")
        data = target.read_bytes()
        if _sha(data) != expected:
            raise ValueError("HISTORICAL_ORIGINAL_BYTES_SHA_CONFLICT")
        if not path.startswith("raw-"):
            # Refuse metadata/day content referring to a forbidden lockbox.
            if month not in path:
                raise ValueError("CROSS_MONTH_ORIGINAL_REFUSED")
        selected[path] = data
    if not any(name.startswith("raw-markets/") for name in selected):
        raise ValueError("NO_ORIGINAL_RAW_MARKET_RECEIPTS")
    # Research-only replay from disposable copies. NEVER edit source originals.
    output.mkdir(parents=True, exist_ok=False)
    # Retain a byte-verified derived archive and relative M5 manifest alongside
    # the write-once report; do not depend on a deleted CI temporary directory.
    native = output / "native-month.zip"
    with zipfile.ZipFile(native, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(selected.items()):
            archive.writestr(name, raw)
    specification = {
        "schema": "HBI_BACKFILL_INPUT_V1",
        "cohort": "MVP023B_AUTHENTIC_HISTORICAL_SOURCE_ONLY_" + month,
        "archives": [{
            "path": "native-month.zip",
            "format": "CRAWLER_NATIVE_ZIP",
            "sha256": _sha(native.read_bytes()),
        }],
    }
    source_manifest = output / "m5-input.json"
    with source_manifest.open("x", encoding="utf-8") as handle:
        json.dump(specification, handle, sort_keys=True, indent=2)
        handle.write("\\n")
    m5 = run_batch(source_manifest, output / "m5")
    features = audit_feature_dataset(output / "m5")
    partitions, inputs, labels = build_partitioned_dataset(output / "m5")
    if (
        m5.get("races") != len(inputs)
        or features.get("physical_races") != len(inputs)
        or partitions.get("races") != len(inputs)
        or features.get("source_dataset_sha256") != partitions.get("source_m5_dataset_sha256")
        or features.get("source_manifest_sha256") != partitions.get("source_m5_manifest_sha256")
        or {r["race_id"] for r in inputs} != {r["race_id"] for r in labels}
        or {r["race_id"] for r in inputs} != {r["race_id"] for r in features["by_race"]}
    ):
        raise ValueError("HISTORIC_M5_FEATURE_DATASET_COHORT_OR_SHA_CONFLICT")
    if any(not str(x["date"]).startswith(month) for x in inputs):
        raise ValueError("CROSS_MONTH_HISTORICAL_DATASET_REFUSED")
    if partitions["model_training_eligible"] or features["training_ready_races"]:
        raise ValueError("UNAUTHORIZED_HISTORICAL_MODEL_PIT_PROMOTION")
    report = {
        "schema": "MVP023B_REAL_MONTH_M5_FEATURE_REPLAY_V1",
        "research_only": True, "bet_authority": False,
        "month": month, "source_archive_files_verified": len(selected),
        "admission_manifest_sha256": admission["source_manifest_sha256"],
        "m5_original_dataset_sha256": m5["dataset_sha256"],
        "replay_archive_sha256": specification["archives"][0]["sha256"],
        "replay_archive_relative_path": "native-month.zip",
        "replay_manifest_relative_path": "m5-input.json",
        "source_inventory_physical_entries": admission["physical_races"],
        "native_market_full_field_verified": admission["full_field_verified"],
        "native_official_results_verified": admission["official_results_verified"],
        "m5_physical_races": len(inputs),
        "m5_imported_runners": m5["imported_runners"],
        "m5_result_verified_races": sum(v["result_verified_races"] for v in m5["per_month"].values()),
        "m5_feature_audit_races": features["physical_races"],
        "m5_dataset_partition_races": partitions["races"],
        "m5_training_eligible": 0,
        "benter_fit_ready": False, "historic_pit_verified": False,
        "2025_lockbox_opened": False,
        "features_status": {
            name: {"eligible_runners": value["eligible_runners"],
                   "main_blocker": value["main_blocker"]}
            for name, value in features["features"].items()
        },
        "limitations": [
            "This is one real historical month subset, not complete 2015-2024 coverage.",
            "Discovery metadata count is not the imported full-field M5 denominator.",
            "No historical horse-performance features are PIT-certified.",
            "No market executable price, training, Benter fitting or production bet.",
        ],
    }
    with (output / "historic-m5-feature-replay.json").open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = replay(args.root, args.admission, args.month, args.output)
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
