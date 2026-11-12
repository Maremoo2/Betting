"""Resolve the newest successfully scheduled Collector source run for one Oslo date.

Research-only; GitHub Actions run metadata identifies capture provenance, NOT PIT.
Requires authenticated GitHub CLI metadata obtained by caller; no web scraping.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = "Maremoo2/rikstoto-program-collector"
WORKFLOW = "rikstoto-morning.yml"


def resolve_daily_run(
    runs: object, *, date_oslo: str | None = None, current: datetime | None = None,
) -> dict[str, object]:
    """Never substitute last available *different* day or failed/manual runs."""
    now = current or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("COLLECTOR_DISCOVERY_CLOCK_NAIVE")
    day = date.fromisoformat(date_oslo) if date_oslo else now.astimezone(OSLO).date()
    if not isinstance(runs, list):
        raise TypeError("COLLECTOR_RUN_INVENTORY_NOT_LIST")
    valid = []
    for row in runs:
        if not isinstance(row, dict):
            continue
        if (row.get("event") != "schedule" or row.get("headBranch") != "main"
                or row.get("status") != "completed"
                or row.get("conclusion") != "success"
                or not isinstance(row.get("headSha"), str)
                or HEX40.fullmatch(row["headSha"]) is None
                or type(row.get("databaseId")) is not int
                or row["databaseId"] < 1):
            continue
        try:
            created = datetime.fromisoformat(str(row["createdAt"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if created.tzinfo is None or created.utcoffset() is None:
            continue
        created_utc = created.astimezone(UTC)
        if created_utc > now.astimezone(UTC):
            continue
        if created_utc.astimezone(OSLO).date() == day:
            valid.append((created_utc, row))
    if not valid:
        raise ValueError("COLLECTOR_AUTHORIZED_RUN_UNAVAILABLE_FOR_OSLO_DATE")
    valid.sort(key=lambda pair: (pair[0], pair[1]["databaseId"]), reverse=True)
    if len(valid) > 1 and valid[0][0] == valid[1][0]:
        raise ValueError("COLLECTOR_AUTHORIZED_RUN_AMBIGUOUS")
    stamp, winner = valid[0]
    return {
        "schema": "CLOUD_RUN003_COLLECTOR_DISCOVERY_V1",
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "day_oslo": day.isoformat(),
        "run_id": winner["databaseId"],
        "source_head_sha": winner["headSha"],
        "run_created_at_utc": stamp.isoformat(),
        "authorization": "SCHEDULE_COMPLETED_SUCCESS_MAIN",
        "source_archive_verified": False,
        "model_ready": False,
        "bet_authorized": False,
        "pit_certified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-json", required=True, type=Path)
    parser.add_argument("--date-oslo", default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--github-output", type=Path, default=None)
    args = parser.parse_args()
    resolved = resolve_daily_run(
        json.loads(args.runs_json.read_text(encoding="utf-8")),
        date_oslo=args.date_oslo,
    )
    args.output.write_text(json.dumps(resolved, sort_keys=True, indent=2) + "\n")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"run_id={resolved['run_id']}\n")
            handle.write(f"day_oslo={resolved['day_oslo']}\n")
            handle.write(f"collector_sha={resolved['source_head_sha']}\n")
    print(json.dumps(resolved, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
