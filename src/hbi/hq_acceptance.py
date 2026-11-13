"""Run the existing HQ report against pinned originals on an isolated host."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from .hq_daily_report import (
    OfficialResultUnavailable,
    official_atg_observation,
    official_observation,
)
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
            if receipt["error_kind"] == "OFFICIAL_GET_OR_RAW_HASH_FAILED" and receipt.get("http_status") != 200:
                raise OfficialResultUnavailable(f"Official source unavailable: {role}")
            raise ValueError(f"Official result failed validation: {role}")


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
    if "--ledger" not in args:
        args = [*args, *rebuild_daily_ledger(args, stage)]
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


def rebuild_daily_ledger(args, stage):
    from .research_ledger import attach_current

    source = stage / "core003-pilot-report.json"
    handoff = stage / "collector-handoff.json"
    for option, target in (("--core", source), ("--handoff", handoff)):
        with ZipFile(args[args.index(option) + 1]) as archive:
            _put_once(target, archive.read(target.name))
    with ZipFile(args[args.index("--cohort") + 1]) as archive:
        for name in archive.namelist():
            if name == "cohort-index.json" or re.fullmatch(r"race-[0-9]{3,}/shadow\.json", name):
                target = stage / name
                target.parent.mkdir(exist_ok=True)
                _put_once(target, archive.read(name))
    ledger = attach_current(
        {"schema": "HBI_RESEARCH_LEDGER_V1", "bet_authority": False, "pit_certified": 0,
         "records": [], "scope": "LOCAL_DAILY_CURRENT_OBSERVATIONS_REPLAY"},
        source, stage, handoff,
    )
    raw = json.dumps(ledger, sort_keys=True).encode()
    path = stage / "daily-ledger.zip"
    with ZipFile(path, "x") as archive:
        archive.writestr("index.json", raw)
    return ["--ledger", str(path), "--ledger-sha", digest(raw)]


def replay_score_example(config, archive, stage):
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


def result_version(files):
    return digest(json.dumps({name: digest(body) for name, body in files.items()}, sort_keys=True).encode())


def checked_result_version(archive, race, version):
    if not re.fullmatch(r"[0-9a-f]{64}", version):
        raise ValueError("Invalid archived result version")
    target = archive / "results" / version
    files = {path.name: path.read_bytes() for path in target.iterdir()}
    if result_version(files) != version:
        raise ValueError("Archived result version SHA mismatch")
    observation = (official_atg_observation(race, target) if race.get("calendar_only")
                   else official_observation(race["race_id"], target, None))
    return target, observation


def result_references(archive, race_id):
    return archive / "result-refs" / race_id.replace(":", "-")


def remember_result(archive, race_id, version, observation):
    directory = result_references(archive, race_id)
    directory.mkdir(parents=True, exist_ok=True)
    receipt_at = max(clock(r["observed_at_utc"]) for r in observation["receipts"].values())
    _put_once(directory / f"{version}.json", json.dumps({
        "race_id": race_id, "version": version, "observed_at_utc": receipt_at.isoformat(),
    }, sort_keys=True).encode())


def latest_saved_result(archive, race):
    directory = result_references(archive, race["race_id"])
    pins = [json.loads(path.read_bytes()) for path in directory.glob("*.json")]
    if not pins:
        return None
    for pin in pins:
        if pin["race_id"] != race["race_id"] or clock(pin["observed_at_utc"]) is None:
            raise ValueError("Archived result reference mismatch")
    latest = max(clock(pin["observed_at_utc"]) for pin in pins)
    versions = {pin["version"] for pin in pins if clock(pin["observed_at_utc"]) == latest}
    if len(versions) != 1:
        raise ValueError("Conflicting archived result references at same time")
    version = versions.pop()
    target, observation = checked_result_version(archive, race, version)
    observed = max(clock(r["observed_at_utc"]) for r in observation["receipts"].values())
    if observed != latest:
        raise ValueError("Archived result reference clock mismatch")
    return target, version


def render_daily(args, archive, stage, output, config):
    """Attach official results for all started races in the original programme."""
    from datetime import UTC, datetime

    from .providers.atg import AtgClient

    calendar_status = None
    atg_client = AtgClient()
    saved_calendar = config.get("atg_calendar_sha256")
    if saved_calendar:
        if not re.fullmatch(r"[0-9a-f]{64}", saved_calendar):
            raise ValueError("Invalid archived ATG calendar SHA")
        path = archive / f"atg-calendar-{saved_calendar}.json"
        receipt = json.loads(path.with_suffix(".receipt.json").read_bytes())
        if digest(path.read_bytes()) != saved_calendar or receipt.get("sha256") != saved_calendar:
            raise ValueError("Archived ATG calendar SHA mismatch")
        args = [*args, "--atg-calendar", str(path), "--atg-calendar-sha", saved_calendar]
        calendar_status = {"status": "VERIFIED_BYTES", **receipt}
    elif config.get("compare_atg_calendar"):
        atg = atg_client.calendar_day(
            date.fromisoformat(args[args.index("--date") + 1]), retain_raw_body=True,
        )
        if (atg.success and atg.status_code == 200 and atg.response_completed_at is not None
                and atg.raw_body and digest(atg.raw_body) == atg.response_body_sha256):
            sha = atg.response_body_sha256
            saved = archive / f"atg-calendar-{sha}.json"
            _put_once(saved, atg.raw_body)
            receipt = {"source_uri": atg.url, "http_status": atg.status_code,
                       "observed_at_utc": atg.response_completed_at.isoformat(), "sha256": sha}
            receipt_path = saved.with_suffix(".receipt.json")
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_bytes())
            else:
                _put_once(receipt_path, json.dumps(receipt, sort_keys=True).encode())
            args = [*args, "--atg-calendar", str(saved), "--atg-calendar-sha", sha]
            calendar_status = {"status": "VERIFIED_BYTES", **receipt}
        else:
            calendar_status = {"status": "BLOCKED_ATG_CALENDAR", "source_uri": atg.url,
                               "http_status": atg.status_code}

    preview = stage / "preview"
    command = [sys.executable, "-m", "hbi.hq_daily_report", *args, "--nordic"]
    subprocess.run([*command, "--output", str(preview)], check=True)
    day = json.loads((preview / "betting-hq.json").read_bytes())
    client = RikstotoClient()
    attachments = []
    results = []
    now = (
        clock(args[args.index("--report-at") + 1])
        if "result_versions" in config else datetime.now(UTC)
    )
    for race in day["races"]:
        start = clock(race["start"])
        calendar_only = race.get("calendar_only")
        if calendar_only:
            if race["calendar_status"] != "results":
                continue
        elif start is None or now <= start:
            continue
        rid = race["race_id"]
        saved_version = config.get("result_versions", {}).get(rid)
        if saved_version is not None:
            target, _ = checked_result_version(archive, race, saved_version)
            attachments.extend(["--official-result", rid, str(target)])
            results.append({"race_id": rid, "status": "LINKED", "result_version_sha256": saved_version})
            continue
        if config.get("result_versions") is not None:
            results.append({"race_id": rid, "status": "BLOCKED", "reason": "NO_PINNED_OFFICIAL_RESULT"})
            continue
        folder = stage / rid.replace(":", "-")
        folder.mkdir()
        try:
            if calendar_only:
                atg_result = atg_client.race_game(rid.removeprefix("ATG:"), retain_raw_body=True)
                if atg_result.status_code != 200:
                    raise OfficialResultUnavailable("ATG_OFFICIAL_RESULT_ORIGINAL_UNAVAILABLE")
                if (not atg_result.success or atg_result.response_completed_at is None
                        or not atg_result.raw_body or digest(atg_result.raw_body) != atg_result.response_body_sha256):
                    raise ValueError("ATG_OFFICIAL_RESULT_ORIGINAL_INVALID")
                _put_once(folder / "game.raw.json", atg_result.raw_body)
                _put_once(folder / "game.receipt.json", json.dumps({
                    "source_uri": atg_result.url, "http_status": atg_result.status_code,
                    "observed_at_utc": atg_result.response_completed_at.isoformat(),
                    "sha256": atg_result.response_body_sha256,
                }, sort_keys=True).encode())
                observation = official_atg_observation(race, folder)
            else:
                capture_result(folder, rid, client)
                observation = official_observation(rid, folder, None)
        except OfficialResultUnavailable as exc:
            previous = latest_saved_result(archive, race)
            if previous is None:
                results.append({"race_id": rid, "status": "BLOCKED", "reason": str(exc)})
            else:
                target, version = previous
                attachments.extend(["--official-result", rid, str(target)])
                results.append({"race_id": rid, "status": "LINKED", "result_version_sha256": version,
                                "retrieval": "ARCHIVED_AFTER_SOURCE_UNAVAILABLE", "source_failure": str(exc)})
            continue
        except (ValueError, KeyError, TypeError) as exc:
            results.append({"race_id": rid, "status": "BLOCKED", "reason": str(exc)})
            continue
        files = {path.name: path.read_bytes() for path in folder.iterdir()}
        version = result_version(files)
        target = archive / "results" / version
        target.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            _put_once(target / name, body)
        if observation is not None:
            remember_result(archive, rid, version, observation)
        attachments.extend(["--official-result", rid, str(target)])
        results.append({"race_id": rid, "status": "LINKED", "result_version_sha256": version})
    if attachments and "result_versions" not in config:
        at = command.index("--report-at") + 1
        command[at] = max(clock(command[at]), datetime.now(UTC)).isoformat()
    subprocess.run([*command, *attachments, "--output", str(output)], check=True)
    rendered = json.loads((output / "betting-hq.json").read_bytes())
    if "score_example" in config:
        score = replay_score_example(config, archive, stage / "score-example")
        _put_once(output / "historical-score.json", json.dumps(score, indent=2).encode())
    summary = {"source_runs": config["runs"], "source_gaps": config["gaps"], "results": results,
               "calendar_reconciliation": calendar_status,
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
