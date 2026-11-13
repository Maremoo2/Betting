"""Assemble a Nordic research day from existing, completed CORE-003 artifacts."""

import argparse
import json
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from .hq_acceptance import pinned_zip, run
from .private_win_archive import _put_once
from .prospective_outcome_scorecard import digest
from .providers.rikstoto import OSLO

REPO = "Maremoo2/Betting"
PREFIXES = {
    "ledger": "research-ledger",
    "core": "core003-pilot-report",
    "cohort": "bet-mvp-shadow",
    "handoff": "collector-handoff",
    "collector": "pit003a-collector-evidence",
}


def pages(endpoint):
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise ValueError("Unexpected source repository")
    return json.loads(subprocess.check_output(["gh", "api", "--paginate", "--slurp", endpoint]))


def day_runs(day):
    """Filter UTC API inventory on the exact Oslo civil-day bounds."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=OSLO)
    end = start + timedelta(days=1)
    query = f"created={start.date() - timedelta(days=1)}..{end.date()}"
    endpoint = f"repos/{REPO}/actions/workflows/core-003-shadow-pilot.yml/runs?branch=main&{query}&per_page=100"
    return sorted(
        (r for page in pages(endpoint) for r in page["workflow_runs"]
         if start <= datetime.fromisoformat(r["created_at"]) < end),
        key=lambda r: (r["created_at"], r["id"]),
    )


def inventory(day, archive):
    runs = day_runs(day)
    pinned = {}

    def retain(artifact, pin):
        try:
            pinned_zip(archive, artifact, pin, download=True)
        except subprocess.CalledProcessError:
            return False
        pinned[artifact] = pin
        return True

    sources = []
    gaps = []
    for entry in runs:
        rid = entry["id"]
        if entry["status"] != "completed":
            gaps.append({"run_id": rid, "reason": entry["conclusion"] or entry["status"]})
            continue
        if entry["conclusion"] != "success":
            gaps.append({"run_id": rid, "reason": entry["conclusion"]})
        names = {f"{prefix}-{rid}": key for key, prefix in PREFIXES.items()}
        names["core003-pilot-state"] = "db"
        matches = {}
        for page in pages(f"repos/{REPO}/actions/runs/{rid}/artifacts?per_page=100"):
            for artifact in page["artifacts"]:
                key = names.get(artifact["name"])
                pin = artifact.get("digest") or ""
                if key and not artifact["expired"] and pin.startswith("sha256:"):
                    if key in matches:
                        raise ValueError(f"Duplicate artifact role: {rid}/{key}")
                    matches[key] = (str(artifact["id"]), pin.removeprefix("sha256:"))
        for role in ("core", "cohort"):
            if role in matches:
                artifact, pin = matches[role]
                if not retain(artifact, pin):
                    matches.pop(role)
                    gaps.append({"run_id": rid, "role": role, "reason": "ORIGINAL_DOWNLOAD_FAILED"})
        missing = set(names.values()) - matches.keys()
        if missing:
            gaps.append({"run_id": rid, "missing_roles": sorted(missing)})
        sources.append((rid, matches))
    complete = [(rid, files) for rid, files in sources if set(files) == {*PREFIXES, "db"}]
    if not complete:
        raise ValueError("No completed run with all report inputs")
    for rid, files in reversed(complete):
        failed = [role for role, (artifact, pin) in files.items() if not retain(artifact, pin)]
        if not failed:
            break
        gaps.append({"run_id": rid, "missing_roles": failed, "reason": "ORIGINAL_DOWNLOAD_FAILED"})
    else:
        raise ValueError("No complete report source could be recovered")

    def member_pin(artifact, name):
        with ZipFile(archive / f"{artifact}.zip") as z:
            return digest(z.read(name))

    ledger = files["ledger"][0]
    args = ["--date", day.isoformat(), "--run", str(rid), "--report-at", datetime.now(OSLO).isoformat(),
            "--ledger-sha", member_pin(ledger, "index.json"), "--db", "pilot.sqlite"]
    for role in PREFIXES:
        args.extend([f"--{role}", f"{files[role][0]}.zip"])
    for source_run, members in sources:
        if source_run == rid:
            continue
        for role, option, member in (
            ("cohort", "--prior-cohort", "cohort-index.json"),
            ("core", "--timing-core", "core003-pilot-report.json"),
        ):
            if role in members:
                artifact = members[role][0]
                args.extend([option, f"{artifact}.zip", member_pin(artifact, member)])
    return {"artifacts": pinned, "state_artifact": files["db"][0], "args": args,
            "runs": [r["id"] for r in runs], "gaps": gaps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    for name in ("archive", "stage", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve()
    archive.mkdir(parents=True, exist_ok=True)
    config = inventory(args.date, archive)
    snapshot = json.dumps(config, indent=2, sort_keys=True).encode()
    _put_once(archive / f"day-{digest(snapshot)}.json", snapshot)
    run(config, archive, args.stage.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
