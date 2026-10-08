"""Bulk PRE research with exact deduplication and immutable output register."""
from __future__ import annotations

import json
import zipfile
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
from pathlib import Path

from rikstoto_crawler.exports import bundle, csv_file
from rikstoto_crawler.transport import digest, write_json

from .config_v1 import CONFIG, CONFIG_HASH
from .signals import classify, collective_consensus
from .validation import validate


def load_input(path):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names):
                raise ValueError("duplicate ZIP members")
            for name in ("MANIFEST.json", "pre.jsonl"):
                if archive.getinfo(name).file_size > 256 * 1024 * 1024:
                    raise ValueError("input too large")
            manifest = json.loads(archive.read("MANIFEST.json"))
            if manifest["stage"] != "PRE":
                raise ValueError("POST input forbidden")
            raw = archive.read("pre.jsonl")
            if (sha256(raw).hexdigest() != manifest["weekly_PRE_sha256"]
                    or sha256(raw).hexdigest() != manifest["files_sha256"]["pre.jsonl"]):
                raise ValueError("ZIP PRE hash mismatch")
    else:
        if not path.is_dir():
            raise ValueError("use a crawler archive directory or PRE weekly ZIP")
        manifest = json.loads((path / "freeze.json").read_text(encoding="utf-8"))
        raw = (path / "pre.jsonl").read_bytes()
        if sha256(raw).hexdigest() != manifest["file_sha256"]:
            raise ValueError("archive PRE hash mismatch")
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()], {
        "path": str(path), "pre_sha256": sha256(raw).hexdigest(), "coverage": manifest}


def process(rows):
    unique, conflicts, duplicate_count = {}, set(), 0
    for row in rows:
        race_id = row.get("race_id")
        if not race_id:
            conflicts.add("MISSING_RACE_ID")
            continue
        if race_id in unique:
            if digest(unique[race_id]) == digest(row):
                duplicate_count += 1
            else:
                conflicts.add(race_id)
        else:
            unique[race_id] = row
    qc = {"duplicate_records_skipped": duplicate_count,
          "conflicting_races": sorted(conflicts), "rejected_races": {},
          "post_read": False, "prospective": False, "execution": "NONE"}
    master, panels, runners = [], defaultdict(list), set()
    accepted = []
    for race_id, row in sorted(unique.items()):
        if race_id in conflicts:
            continue
        try:
            pwin, pools = validate(row)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            qc["rejected_races"][race_id] = str(exc)
            continue
        accepted.append(row)
        iso = date.fromisoformat(row["date"]).isocalendar()
        week = f"{iso.year}-W{iso.week:02}"
        for pool_id, normalized in sorted(pools.items()):
            pool = row["collective"][pool_id]
            for n in sorted(row["active_field"], key=int):
                runner = row["runners"][n]
                evidence = classify(normalized["pCOL"][n], pwin[n])
                observation = {"observation_id": digest([race_id, pool_id, n, CONFIG_HASH]),
                    "race_id": race_id, "meeting_id": row["raceday_key"], "week": week,
                    "date": row["date"], "country": row["country"], "track": row["track"],
                    "product": pool["product"], "leg": pool["leg"], "pool_id": pool_id,
                    "horse_no": n, "horse": runner["horse_name"], "horse_id": runner["horse_id"],
                    "horse_id_stable": runner["horse_id_stable"], "win_odds": runner["win_odds"],
                    "place_min": runner["place_min"], "place_max": runner["place_max"],
                    "win_pool_NOK": row["turnover"]["V"]["nok"],
                    "place_pool_NOK": row["turnover"]["P"]["nok"],
                    "collective_share": pool["raw_shares"][n],
                    "collective_pool_NOK": row["collective_turnover"][pool_id]["nok"],
                    "WIN_updated_at": runner["win_updated_at"], "COL_updated_at": pool["updated_at"],
                    "WIN_skew_seconds": normalized["skew"], "time_class": normalized["cohort"],
                    "pWIN": evidence["pWIN"], "pCOL": evidence["pCOL"], "delta": evidence["delta"],
                    "R": evidence["ratio"], "signal": evidence["signal"],
                    "ROBUST_CORE": evidence["ROBUST_CORE"], "BORDERLINE": evidence["BORDERLINE"],
                    "source_url": pool["source"]["url"], "source_hash": pool["source"]["body_sha256"],
                    "fetched_at": pool["source"]["fetched_at"],
                    "data_quality_flags": ";".join(row["data_quality_flags"]),
                    "snapshot_type": row["snapshot_kind"], "config_hash": CONFIG_HASH}
                master.append(observation)
                panels[(race_id, n, normalized["cohort"])].append(observation)
                runners.add((race_id, n))
    for panel in panels.values():
        eligible = len({r["product"] for r in panel}) == len(panel)
        family = ["STRONG_POS" if r["signal"] in {"STRONG_POS", "EXTREME_POS"} else
                  "STRONG_NEG" if r["signal"] in {"STRONG_NEG", "EXTREME_NEG"} else "NEUTRAL"
                  for r in panel]
        combined = collective_consensus(family) if eligible else {
            "DUAL_POOL_STRONG": False, "COL_CONSENSUS": "AMBIGUOUS_DUPLICATE_PRODUCT"}
        for row in panel:
            row.update(combined)
    master.sort(key=lambda r: (r["week"], r["date"], r["race_id"], r["pool_id"], int(r["horse_no"])))
    aggregates = {}
    for dimension in ("week", "date", "track", "country", "product", "time_class"):
        groups = defaultdict(list)
        for row in master:
            groups[row[dimension]].append(row)
        aggregates[dimension] = {key: {"observations": len(values),
            "races": len({r["race_id"] for r in values}),
            "signals": dict(Counter(r["signal"] for r in values))} for key, values in sorted(groups.items())}
    qc.update(accepted_races=len(accepted), race_days=len({r["raceday_key"] for r in accepted}),
              calendar_dates=len({r["date"] for r in accepted}), unique_race_runners=len(runners), runner_pool_observations=len(master),
              signals=dict(Counter(r["signal"] for r in master)), aggregates=aggregates,
              excluded_scratched_runners=sum(sum(r["scratched"] for r in row["runners"].values())
                                            for row in accepted))
    return master, qc


def run(inputs, output):
    rows, sources = [], []
    for item in inputs:
        values, source = load_input(item)
        rows.extend(values)
        sources.append(source)
    master, qc = process(rows)
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("immutable output exists; use a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "config_v1.json", {"config": CONFIG, "hash": CONFIG_HASH})
    headers = list(master[0]) if master else ["observation_id", "race_id", "signal"]
    csv_file(output / "PRE_MASTER.csv", headers, [[r[h] for h in headers] for r in master])
    csv_file(output / "PRE_SIGNALS.csv", headers,
             [[r[h] for h in headers] for r in master if r["signal"] != "NONE"])
    write_json(output / "PRE_QC.json", qc)
    files = sorted(output.iterdir())
    manifest = {"engine": CONFIG["version"], "config_hash": CONFIG_HASH, "sources": sources,
                "post_read": False, "prospective": False,
                "files_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in files}}
    write_json(output / "MANIFEST.json", manifest)
    bundle(output / "PRE_WINNER_BULK.zip", [*files, output / "MANIFEST.json"])
    return qc
