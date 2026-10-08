"""One upload ZIP per ISO calendar week, generated offline from verified freezes."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .exports import bundle, export, frozen_rows
from .integrity import run as integrity
from .job import file_hash, freeze, read
from .transport import write_json


def week_id(day):
    year, week, _ = date.fromisoformat(day).isocalendar()
    return f"{year}-W{week:02}"


def weekly(root, *, stage="pre"):
    if stage not in {"pre", "post", "both"}:
        raise ValueError("invalid export stage")
    root = Path(root)
    rows, source_freeze = frozen_rows(root)
    quality = read(root / "quality.json") if (root / "quality.json").exists() else {}
    configured = quality.get("config", {}).get("days", [])
    groups = {}
    for day in configured:
        groups.setdefault(week_id(day), [])
    for row in rows:
        groups.setdefault(week_id(row["date"]), []).append(row)
    output = root / "exports" / "weekly"
    output.mkdir(parents=True, exist_ok=True)
    files = []
    for week, subset in sorted(groups.items()):
        subset.sort(key=lambda r: (r["date"], r["track"], r["race_number"]))
        derived = output / "_data" / week
        derived.mkdir(parents=True, exist_ok=True)
        manifest = freeze(derived, subset)
        ids = {r["race_id"] for r in subset}
        monday = date.fromisocalendar(int(week[:4]), int(week[-2:]), 1)
        expected = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
        observed = [d for d in quality.get("observed_days", []) if week_id(d) == week]
        coverage = {"week": week, "week_start": expected[0], "week_end": expected[-1],
                    "observed_days": observed, "missing_days": sorted(set(expected) - set(observed)),
                    "race_count": len(subset), "race_ids": sorted(ids),
                    "source_PRE_sha256": source_freeze["file_sha256"],
                    "weekly_PRE_sha256": manifest["file_sha256"],
                    "collection_scope": quality.get("config", "UNKNOWN"),
                    "all_races_claimed": False,
                    "rejected_races": {k: v for k, v in quality.get("rejected", {}).items()
                                       if any(d in k for d in expected)},
                    "fetch_errors": {k: v for k, v in quality.get("fetch_errors", {}).items()
                                     if any(d in k for d in expected)},
                    "coverage_known": bool(quality), "prospective": False}
        preamble = (f"# {week}\n\n{expected[0]}–{expected[-1]}; {len(subset)} accepted races.\n\n"
                    f"Missing days: {', '.join(coverage['missing_days']) or 'none'}. "
                    "Collection scope/rejections are listed in MANIFEST.json; this is not a claim of all races.\n\n")
        for kind in ("PRE", "POST"):
            if kind == "PRE" and stage not in {"pre", "both"}:
                continue
            if kind == "POST" and stage not in {"post", "both"}:
                continue
            if kind == "PRE":
                export(derived)
                names = [derived / "exports" / name for name in ("PRE.md", "PRE.csv", "COLLECTIVE.csv")]
                if all("product" in c and "leg" in c for r in subset for c in r["collective"].values()):
                    integrity(derived)
                    content = (derived / "integrity/PRE-WINNER-integrity.md").read_text(encoding="utf-8")
                else:
                    content = "# Integrity\n\nNOT_CONFIGURED: legacy archive lacks explicit product/leg metadata.\n"
                (derived / "exports/INTEGRITY.md").write_text(content, encoding="utf-8")
                names.extend([derived / "exports/INTEGRITY.md", derived / "pre.jsonl"])
            else:
                verified_count = 0
                verified_ids = set()
                result_rejections = {}
                display = read(root / "post-display.json")
                if display["pre_freeze"]["file_sha256"] != source_freeze["file_sha256"]:
                    raise ValueError("POST summary source freeze mismatch")
                filtered = {**display, "rows": [r for r in display["rows"] if r["race_id"] in ids],
                            "rejected": {k: v for k, v in display["rejected"].items() if k in ids},
                            "pre_freeze": manifest}
                write_json(derived / "post-display.json", filtered)
                if (root / "post-results.json").exists():
                    results = read(root / "post-results.json")
                    if results["pre_freeze"]["file_sha256"] != source_freeze["file_sha256"]:
                        raise ValueError("POST results source freeze mismatch")
                    verified_count = sum(r["race_id"] in ids for r in results["rows"])
                    verified_ids = {r["race_id"] for r in results["rows"] if r["race_id"] in ids}
                    result_rejections = {k: v for k, v in results["rejected"].items() if k in ids}
                    write_json(derived / "post-results.json", {**results,
                        "rows": [r for r in results["rows"] if r["race_id"] in ids],
                        "rejected": {k: v for k, v in results["rejected"].items() if k in ids},
                        "pre_freeze": manifest})
                export(derived, stage="post")
                names = [derived / "exports" / name for name in ("POST.md", "POST.csv", "DIVIDENDS.csv")]
                names.append(derived / "post-display.json")
            markdown = derived / "exports" / (kind + ".md")
            markdown.write_text(preamble + markdown.read_text(encoding="utf-8"), encoding="utf-8")
            package_manifest = {**coverage, "stage": kind,
                                "files_sha256": {p.name: file_hash(p) for p in names}}
            if kind == "POST":
                package_manifest["missing_result_races"] = sorted(ids - {r["race_id"] for r in filtered["rows"]})
                package_manifest["full_result_verified_races"] = verified_count
                package_manifest["unverified_result_races"] = sorted(ids - verified_ids)
                package_manifest["result_rejections"] = result_rejections
            manifest_path = derived / "exports/MANIFEST.json"
            write_json(manifest_path, package_manifest)
            target = output / f"Rikstoto_{kind}_{week}.zip"
            bundle(target, [*names, manifest_path])
            files.append(str(target))
    frozen_rows(root)
    return {"weekly_files": files, "pre_unchanged": True}
