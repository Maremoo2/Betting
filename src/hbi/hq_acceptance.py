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

    args = [
        str(archive / arg) if re.fullmatch(r"[1-9][0-9]*\.zip", arg) else
        str(stage / arg) if arg in {"pilot.sqlite", "official"} else arg
        for arg in config["args"]
    ]
    if "result_race_id" not in config:
        return render_daily(args, archive, stage, output, config)
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
    if "score_example" in config:
        score = replay_score_example(config, archive, stage / "score-example")
        _put_once(output / "historical-score.json", json.dumps(score, indent=2).encode())
    _put_once(output / "acceptance.json", json.dumps(summary, sort_keys=True, indent=2).encode())
    return summary


def replay_score_example(config, archive, stage):
    from .hq_daily_report import official_observation

    example = config["score_example"]
    rid = example["race_id"]
    stage.mkdir()
    with ZipFile(archive / f"{example['scorecard']}.zip") as scores:
        index = json.loads(scores.read("index.json"))
        row = next(row for row in index["records"] if row["race_id"] == rid)
        for receipt in row["original_result_receipts"]:
            role = receipt["role"]
            if role not in {"complete", "raceday"}:
                raise ValueError("Unexpected result role")
            _put_once(stage / f"{role}.raw.json", scores.read(receipt["raw_path"].split("/", 1)[1]))
            _put_once(stage / f"{role}.receipt.json", json.dumps(receipt).encode())
    with ZipFile(archive / f"{example['cohort']}.zip") as models:
        member = row["source_model_path"].split("/", 2)[2]
        raw = models.read(member)
    if digest(raw) != row["source_model_original_sha256"]:
        raise ValueError("Scored original model SHA mismatch")
    model = json.loads(raw)
    if model["race"]["race_id"] != rid:
        raise ValueError("Scored original race mismatch")
    result = official_observation(rid, stage, model)
    expected = {
        label: {"log_loss": row["score"][f"{key}_log_loss"],
                "brier": row["score"][f"{key}_multiclass_brier"]}
        for label, key in (("Champion", "champion"), ("CORE-004", "core004"), ("WIN", "market"))
    }
    if result["scores"] != expected:
        raise ValueError("Original DEV-009 scores did not reproduce")
    return {"race_id": rid, "model_sha256": digest(raw), **result}


def render_daily(args, archive, stage, output, config):
    """Attach official results for all started races in the original programme."""
    from datetime import UTC, datetime

    from .hq_daily_report import official_observation

    preview = stage / "preview"
    command = [sys.executable, "-m", "hbi.hq_daily_report", *args, "--nordic"]
    subprocess.run([*command, "--output", str(preview)], check=True)
    day = json.loads((preview / "betting-hq.json").read_bytes())
    client = RikstotoClient()
    attachments = []
    results = []
    now = datetime.now(UTC)
    for race in day["races"]:
        start = clock(race["start"])
        if start is None or now <= start:
            continue
        rid = race["race_id"]
        folder = stage / rid.replace(":", "-")
        folder.mkdir()
        try:
            capture_result(folder, rid, client)
            official_observation(rid, folder, None)
        except (ValueError, KeyError, TypeError) as exc:
            results.append({"race_id": rid, "status": "BLOCKED", "reason": str(exc)})
            continue
        files = {path.name: path.read_bytes() for path in folder.iterdir()}
        version = digest(json.dumps({name: digest(body) for name, body in files.items()}, sort_keys=True).encode())
        target = archive / "results" / version
        target.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            _put_once(target / name, body)
        attachments.extend(["--official-result", rid, str(target)])
        results.append({"race_id": rid, "status": "LINKED", "result_version_sha256": version})
    if attachments:
        at = command.index("--report-at") + 1
        command[at] = max(clock(command[at]), datetime.now(UTC)).isoformat()
    subprocess.run([*command, *attachments, "--output", str(output)], check=True)
    rendered = json.loads((output / "betting-hq.json").read_bytes())
    if "score_example" in config:
        score = replay_score_example(config, archive, stage / "score-example")
        _put_once(output / "historical-score.json", json.dumps(score, indent=2).encode())
    summary = {"source_runs": config["runs"], "source_gaps": config["gaps"], "results": results,
               "observed": len(rendered["races"]),
               "complete_rosters": sum(r["active"] is not None for r in rendered["races"]),
               "model_freezes": sum(bool(r["analysis"]) for r in rendered["races"]),
               "scored": sum(bool((r["official"] or {}).get("scores")) for r in rendered["races"]),
               "report_sha256": digest((output / "betting-hq.json").read_bytes()),
               "bet_authority": False, "pit_certified": False}
    _put_once(output / "daily-status.json", json.dumps(summary, indent=2).encode())
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
