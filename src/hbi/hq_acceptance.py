"""Run the existing HQ report against pinned originals on an isolated host."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from .private_win_archive import _put_once
from .prospective_outcome_scorecard import _capture, clock, digest
from .providers.rikstoto import RikstotoClient


def pinned_zip(root, artifact_id, expected, *, download=False):
    if not re.fullmatch(r"[1-9][0-9]*", artifact_id):
        raise ValueError("Invalid artifact ID")
    target = root / f"{artifact_id}.zip"
    if not target.exists() and download:
        repository = os.environ["GITHUB_REPOSITORY"]
        if repository != "Maremoo2/Betting":
            raise ValueError("Unexpected archive repository")
        body = subprocess.check_output(["gh", "api", f"repos/{repository}/actions/artifacts/{artifact_id}/zip"])
        if digest(body) != expected:
            raise ValueError(f"Artifact SHA mismatch: {artifact_id}")
        _put_once(target, body)
    if target.is_symlink() or digest(target.read_bytes()) != expected:
        raise ValueError(f"Artifact SHA mismatch: {artifact_id}")
    return target


def capture_result(root, race_id, client):
    match = re.fullmatch(r"RIKSTOTO:([A-Z0-9_\-]+):([1-9][0-9]*)", race_id)
    if match is None:
        raise ValueError("Invalid result race ID")
    meeting, number = match.groups()
    for role, endpoint in (
        ("complete", f"/results/raceDays/{meeting}/{number}/completeresults"),
        ("raceday", f"/results/racedays/{meeting}/raceresults"),
    ):
        _, receipt = _capture(client, endpoint, root, role)
        receipt.pop("raw_path")
        _put_once(root / f"{role}.receipt.json", json.dumps(receipt, sort_keys=True).encode())
        if receipt["error_kind"]:
            raise ValueError(f"Official source unavailable: {role}")


def run(config, archive, stage, output, *, download=False, saved_result=None):
    output.mkdir(parents=True, exist_ok=False)
    archive.mkdir(parents=True, exist_ok=True)
    stage.mkdir(parents=True, exist_ok=False)
    for artifact_id, sha in config["artifacts"].items():
        pinned_zip(archive, artifact_id, sha, download=download)
    state = archive / f"{config['state_artifact']}.zip"
    with ZipFile(state) as source:
        _put_once(stage / "pilot.sqlite", source.read("core003-pilot.sqlite"))

    result = stage / "official"
    if saved_result is not None:
        shutil.copytree(saved_result, result)
    else:
        result.mkdir()
        capture_result(result, config["result_race_id"], RikstotoClient())
    names = ("complete.raw.json", "complete.receipt.json", "raceday.raw.json", "raceday.receipt.json")
    result_files = [result / name for name in names]
    observed = max(clock(json.loads(path.read_bytes())["observed_at_utc"])
                   for path in result_files if path.name.endswith(".receipt.json"))
    version = digest(json.dumps({p.name: digest(p.read_bytes()) for p in result_files}, sort_keys=True).encode())
    result_archive = archive / "results" / version
    result_archive.mkdir(parents=True, exist_ok=True)
    for path in result_files:
        _put_once(result_archive / path.name, path.read_bytes())

    args = [
        str(archive / arg) if re.fullmatch(r"[1-9][0-9]*\.zip", arg) else
        str(stage / arg) if arg in {"pilot.sqlite", "official"} else arg
        for arg in config["args"]
    ]
    report_at = args.index("--report-at") + 1
    args[report_at] = max(clock(args[report_at]), observed).isoformat()
    subprocess.run([sys.executable, "-m", "hbi.hq_daily_report", *args, "--nordic",
                    "--output", str(output)], check=True)
    report = json.loads((output / "betting-hq.json").read_bytes())
    summary = {
        "observed": len(report["races"]),
        "complete_rosters": sum(race["active"] is not None for race in report["races"]),
        "complete_win_fields": sum(
            race["full_market"] or bool(race["analysis"] and all(
                runner["win"] is not None for runner in race["analysis"]["runners"]
            )) for race in report["races"]
        ),
        "runners_with_p_win": sum(len(race["analysis"]["runners"]) for race in report["races"] if race["analysis"]),
        "without_model": sum(not race["analysis"] for race in report["races"]),
        "model_freezes": sum(bool(race["analysis"]) for race in report["races"]),
        "result_observations": sum(bool(race["official"]) for race in report["races"]),
        "scored": sum(bool((race["official"] or {}).get("scores")) for race in report["races"]),
        "result_version_sha256": version,
        "report_sha256": digest((output / "betting-hq.json").read_bytes()),
        "bet_authority": False, "pit_certified": False,
    }
    _put_once(output / "acceptance.json", json.dumps(summary, sort_keys=True, indent=2).encode())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "archive", "stage", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--saved-result", type=Path)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(json.loads(args.config.read_bytes()), args.archive.resolve(), args.stage.resolve(),
                         args.output.resolve(), download=args.download, saved_result=args.saved_result)))


if __name__ == "__main__":
    main()
