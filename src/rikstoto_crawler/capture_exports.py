"""Small weekly upload archives and an explicit, separately stored POST stage."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .transport import ArchiveClient, digest, write_json


def load_captures(root):
    return [(p, json.loads(p.read_text(encoding="utf-8")))
            for p in sorted((Path(root) / "captures").glob("*/*.json"))]


def weekly_v3(root):
    root = Path(root)
    weeks = defaultdict(list)
    for path, row in load_captures(root):
        iso = date.fromisoformat(row["day"]).isocalendar()
        weeks[f"{iso.year}-W{iso.week:02d}"].append((path, row))
    outputs = []
    for week, items in sorted(weeks.items()):
        manifest = {"schema_version": "RIKSTOTO_CAPTURE_UPLOAD_V3", "week": week,
                    "stage": "MARKET_RESEARCH", "captures": len(items),
                    "races": len({r["race_id"] for _, r in items}),
                    "days": sorted({r["day"] for _, r in items}),
                    "historical_is_not_prospective": True,
                    "files": {str(p.relative_to(root)): digest(r) for p, r in items}}
        destination = root / "weekly" / f"{week}-market-v3.zip"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
            archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
            archive.writestr("README.txt", "Research market captures only. No outcomes or betting decisions.\n"
                              "Missing/zero prices are not valid odds. See market and pool statuses.\n"
                              "Historical acquisition does not establish pre-race availability.\n")
            for path, _ in items:
                archive.write(path, str(path.relative_to(root)))
        outputs.append(str(destination))
    return outputs


def post_v3(root, *, client=None):
    root = Path(root)
    client = client or ArchiveClient(root)
    pools, output = {}, []
    for _, row in load_captures(root):
        for meta in row["product_coverage"]:
            if meta["product"] in {"V4", "V5", "V64", "V65", "V75", "V85", "V86", "DD"}:
                pools[meta["pool_id"]] = meta
    for pool_id, meta in sorted(pools.items()):
        key, product, first = pool_id.split("#")
        record = {"pool_id": pool_id, "product": meta["product"], "provider_product": product,
                  "stage": "POST", "system_values_status": "NOT_COLLECTED", "status": "FETCH_ERROR"}
        try:
            envelope = client.get(f"/game/prizepayout/{key}/{product}?raceNumber={int(first)}", result=True)
            record.update(status="RAW_FETCHED" if envelope["body"]["result"] else "EMPTY",
                          source=envelope, settlement_verified=False)
        except (OSError, ValueError, TypeError) as exc:
            record["reason"] = str(exc)
        if meta["product"] != "DD":
            try:
                system = client.get(f"/game/prizepayout/system/{key}/{product}", result=True)
                record.update(system_values_status="RAW_SCHEMA_UNVERIFIED" if system["body"]["result"] else "EMPTY",
                              system_values_source=system)
            except (OSError, ValueError, TypeError) as exc:
                record.update(system_values_status="FETCH_ERROR", system_values_error=str(exc))
        destination = root / "post-pools" / f"{digest(record)}.json"
        if not destination.exists():
            write_json(destination, record)
        output.append(record)
    return {"pools": len(output), "statuses": {r["pool_id"]: r["status"] for r in output}}
