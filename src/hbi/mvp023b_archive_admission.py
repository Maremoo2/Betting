"""MVP-023B/P1-A: read-only, monthly acceptance of the *existing* native archive.

Reuses MVP-023A coverage and Rikstoto original receipts. Never crawls, opens
2025, trains a model, touches HBI state, or extracts an untrusted ZIP into source.
Only selected 2015-2024 files are copied into a disposable monthly view.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from rikstoto_crawler.transport import digest

from .mvp023a_historical_coverage import build_coverage

SCHEMA = "MVP023B_NATIVE_MONTH_ACCEPTANCE_V1"
MONTH = re.compile(r"20(?:1[5-9]|2[0-4])-(?:0[1-9]|1[0-2])$")
SHA = re.compile(r"[0-9a-f]{64}$")


def _safe(root: Path, source: Path) -> bytes:
    """Do not resolve attacker-supplied file components through symlinks."""
    relative = source.relative_to(root)
    part = root
    for name in relative.parts:
        if name in {"", ".", ".."}:
            raise ValueError("PATH_TRAVERSAL_REFUSED")
        part = part / name
        if part.is_symlink():
            raise ValueError("SYMLINK_ARCHIVE_SOURCE_REFUSED")
    if not source.is_file():
        raise ValueError("SOURCE_ARCHIVE_MEMBER_NOT_FILE:" + relative.as_posix())
    if source.stat().st_size > 500_000_000:
        raise ValueError("ORIGINAL_MEMBER_TOO_LARGE")
    return source.read_bytes()


def _stage(root: Path, view: Path, relative: str, originals: dict) -> bytes:
    source = root / relative
    raw = _safe(root, source)
    sha = hashlib.sha256(raw).hexdigest()
    if relative in originals and originals[relative] != sha:
        raise ValueError("CONFLICTING_ORIGINAL_MEMBER_SHA")
    originals[relative] = sha
    target = view / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
            raise ValueError("CONFLICTING_STAGED_MONTH_ORIGINAL")
    else:
        target.write_bytes(raw)
    return raw


def _weekly(root: Path, view: Path, month: str, relative: str, originals: dict) -> list[dict]:
    if not re.fullmatch(r"weekly/20\d{2}-W\d{2}-MARKET\.zip", relative):
        raise ValueError("UNSUPPORTED_WEEKLY_NATIVE_PATH")
    _stage(root, view, relative, originals)
    with ZipFile(view / relative) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        if (
            len(names) != len(set(names)) or "MANIFEST.json" not in names
            or any("/" in n or "\\" in n or ".." in n or n.startswith(".") for n in names)
            or sum(i.file_size for i in entries) > 500_000_000
        ):
            raise ValueError("UNSAFE_OR_OVERSIZED_WEEKLY_ARCHIVE")
        manifest = json.loads(archive.read("MANIFEST.json"))
        days = manifest.get("days")
        if (
            manifest.get("stage") != "MARKET_ONLY"
            or manifest.get("retrospective") is not True
            or not isinstance(days, list) or not days
            or any(type(d) is not str or not d.startswith(month + "-") for d in days)
            or len(days) != len(set(days))
            or set(names) != {"MANIFEST.json", *(d + ".json" for d in days)}
            or not isinstance(manifest.get("files_sha256"), dict)
        ):
            raise ValueError("WEEKLY_OTHER_MONTH_OR_INVALID_MANIFEST_REFUSED")
        records = []
        for day in days:
            data = archive.read(day + ".json")
            if hashlib.sha256(data).hexdigest() != manifest["files_sha256"].get(day + ".json"):
                raise ValueError("WEEKLY_DAY_ORIGINAL_SHA_MISMATCH")
            records.append(json.loads(data))
        return records


def _selected_days(root: Path, view: Path, month: str, folder: str,
                   originals: dict) -> list[dict]:
    source = root / folder
    if source.is_symlink():
        raise ValueError("SYMLINK_ARCHIVE_DIRECTORY_REFUSED")
    selected = []
    for file in sorted(source.glob(month + "-*.json")):
        try:
            day = date.fromisoformat(file.stem)
        except ValueError as exc:
            raise ValueError("INVALID_NATIVE_DAY_FILENAME") from exc
        if day.strftime("%Y-%m") != month:
            raise ValueError("OUT_OF_MONTH_SOURCE_DAY_REFUSED")
        data = _stage(root, view, folder + "/" + file.name, originals)
        selected.append(json.loads(data))
    return selected


def admit_month(root: Path, month: str, *, weekly: tuple[str, ...] = ()) -> dict:
    if not isinstance(month, str) or MONTH.fullmatch(month) is None:
        raise ValueError("2015_2024_ONLY_LOCKBOX_2025_FORBIDDEN")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("NATIVE_ARCHIVE_ROOT_INVALID_OR_SYMLINKED")
    # The caller's root may contain a 2025 lockbox: do not enumerate, hash,
    # parse or read any other month's inventory/day/result/original cache.
    originals: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="mvp023b-source-only-") as tmp:
        view = Path(tmp)
        inventory = root / "inventory" / (month + ".json")
        if inventory.exists() or inventory.is_symlink():
            _stage(root, view, "inventory/" + month + ".json", originals)
        markets = _selected_days(root, view, month, "market-days", originals)
        results = _selected_days(root, view, month, "result-days", originals)
        for name in weekly:
            markets.extend(_weekly(root, view, month, name, originals))
        if not originals:
            raise ValueError("NO_AUTHENTIC_MONTHLY_ORIGINAL_FILES_AVAILABLE")
        market_rows = [row for day in markets for row in day.get("races", [])
                       if isinstance(row, dict)]
        source_paths = set()
        for row in market_rows:
            for receipt in row.get("sources") or []:
                if isinstance(receipt, dict) and isinstance(receipt.get("path"), str):
                    path = receipt["path"]
                    # The per-race original API reference must be a member
                    # of this month; historical aliases across months are not
                    # relabeled as evidence for this month.
                    if month not in path:
                        raise ValueError("OUT_OF_MONTH_SOURCE_RECEIPT_REFUSED")
                    source_paths.add(("raw-markets", path))
        for day in results:
            for outcome in day.get("outcomes", []):
                if outcome.get("status") != "VERIFIED_FULL_FIELD":
                    continue
                rid = outcome.get("race_id", "")
                match = re.fullmatch(
                    r"RIKSTOTO:([A-Z0-9]+_NR_(20\d{2}-\d{2}-\d{2})):([1-9]\d*)", rid
                )
                if match is None or not match.group(2).startswith(month):
                    raise ValueError("RESULT_MONTH_OR_PHYSICAL_RACE_CONFLICT")
                source_paths.add((
                    "raw-results",
                    f"/results/raceDays/{match.group(1)}/{match.group(3)}/completeresults",
                ))
        # Only open originals referenced by selected, SHA-frozen month records.
        missing = []
        for directory, path in sorted(source_paths):
            cache = hashlib.sha256(path.encode()).hexdigest() + ".json"
            relative = directory + "/" + cache
            source = root / relative
            if not source.exists() and not source.is_symlink():
                missing.append(relative)
                continue
            raw = _stage(root, view, relative, originals)
            stored = json.loads(raw)
            if (stored.get("path") != path or not stored.get("url", "").endswith(path)
                    or not isinstance(stored.get("body"), dict)
                    or stored.get("body_sha256") != digest(stored["body"])):
                raise ValueError("RAW_ORIGINAL_PATH_SHA_OR_SOURCE_CONFLICT")
        coverage = build_coverage(view)
        count = coverage["counts"]
        if any(row["year"] == 2025 for row in coverage["by_race"]):
            raise ValueError("2025_LOCKBOX_INDIRECTLY_EXPOSED")
        # Do not allow "no original races" to mean certified zero coverage.
        manifest = [{"path": path, "sha256": sha} for path, sha in sorted(originals.items())]
        return {
            "schema": SCHEMA, "month": month, "research_only": True,
            "bet_authority": False, "source_root": str(root),
            "read_only_native_files_sha256": manifest,
            "source_manifest_sha256": digest(manifest),
            "source_file_count": len(manifest),
            "missing_referenced_originals": sorted(missing),
            "physical_races": count.get("physical_races", 0),
            "full_field_verified": count.get("FULL_FIELD_VERIFIED", 0),
            "provider_identity_not_independent": True,
            "official_results_verified": count.get("RESULT_VERIFIED", 0),
            "model_training_eligible": 0, "benter_fit_eligible": 0,
            "history_pit_verified": False, "2025_lockbox_opened": False,
            "per_country": coverage["by_country"], "per_track": coverage["by_track"],
            "category_counts": count, "main_blockers": coverage["primary_blockers"],
            "origin_basis": "ONLY_SELECTED_SHA_CHECKED_NATIVE_MONTH_ORIGINALS",
            "original_archive_complete": False,
            "qualification": "RETROSPECTIVE_RESEARCH_ONLY",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--weekly-zip", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = admit_month(args.root, args.month, weekly=tuple(args.weekly_zip))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
