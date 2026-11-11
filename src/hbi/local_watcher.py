"""Five-minute Windows watcher entry point. Task registration is operator-owned."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .governance import load_governance
from .manifest import GOVERNANCE
from .schedule import evaluate_shadow_watcher_schedule
from .state_artifact import _verify_canonical_sqlite
from .watcher import run_watcher

INTERVAL = timedelta(minutes=5)
MAX_CLOCK_OFFSET_SECONDS = 0.25
FAILURE_STATUSES = {"FAILED", "SOURCE_FAILURE", "INCOMPLETE_RACES"}


@contextmanager
def writer_lock(path: Path):
    import msvcrt

    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("WATCHER_WRITER_BUSY") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def clock_offset(server: str) -> float:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", server):
        raise ValueError("WATCHER_CLOCK_SERVER_INVALID")
    sample = subprocess.run(
        ["w32tm.exe", "/stripchart", f"/computer:{server}", "/dataonly", "/samples:1"],
        capture_output=True, text=True, errors="replace", timeout=8, check=False,
    )
    offsets = re.findall(r"([+-]\d+[.,]\d+)s\s*$", sample.stdout, re.MULTILINE)
    if sample.returncode or len(offsets) != 1:
        raise RuntimeError("WATCHER_CLOCK_UNVERIFIED")
    offset = float(offsets[0].replace(",", "."))
    if abs(offset) > MAX_CLOCK_OFFSET_SECONDS:
        raise RuntimeError("WATCHER_CLOCK_OFFSET_EXCEEDED")
    return offset


def slot_start(now: datetime) -> datetime:
    return now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)


def journal_path(root: Path, slot: datetime) -> Path:
    return root / f"{slot:%Y%m%dT%H%MZ}.json"


def write_journal(path: Path, record: dict) -> None:
    temp = path.with_suffix(f".{uuid4().hex}.tmp")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def recent_gaps(root: Path, slot: datetime) -> list[dict[str, str]]:
    """Check the last hour, excluding time before this journal's first run."""
    records = sorted(root.glob("????????T????Z.json"))
    if not records:
        return []
    first = datetime.strptime(records[0].stem + "+0000", "%Y%m%dT%H%MZ%z")
    candidate = max(first, slot - timedelta(hours=1))
    gaps = []
    while candidate < slot:
        if evaluate_shadow_watcher_schedule(candidate).should_run:
            path = journal_path(root, candidate)
            status = json.loads(path.read_text(encoding="utf-8"))["status"] if path.exists() else "MISSING"
            if status in FAILURE_STATUSES | {"MISSING", "RUNNING"}:
                gaps.append({"slot": candidate.isoformat(), "status": status})
        candidate += INTERVAL
    return gaps


def run_tick(state: Path, journal: Path, clock_server: str) -> dict:
    now = datetime.now(UTC)
    if not evaluate_shadow_watcher_schedule(now).should_run:
        return {"status": "OUTSIDE_OSLO_WINDOW"}
    state = state.resolve()
    journal = journal.resolve(strict=True)
    slot = slot_start(now)
    path = journal_path(journal, slot)
    with writer_lock(state.with_suffix(state.suffix + ".watcher-lock")):
        if path.exists():
            return {"status": "ALREADY_CLAIMED", "slot": slot.isoformat()}
        record = {"slot": slot.isoformat(), "started_at": now.isoformat(), "status": "RUNNING"}
        write_journal(path, record)
        try:
            record["recent_gaps"] = recent_gaps(journal, slot)
            # Manifest and provenance both need the pinned governance document.
            # Check before any provider fetch or decision writes.
            load_governance(GOVERNANCE)
            record["clock_offset_seconds"] = clock_offset(clock_server)
            # SQLite runs on the pre-staged local copy, including recovery of its WAL.
            _verify_canonical_sqlite(state, include_wal=True)
            if slot_start(datetime.now(UTC)) != slot:
                raise RuntimeError("WATCHER_SLOT_EXPIRED_DURING_PREFLIGHT")
            audit = run_watcher(db_path=str(state), skip_frozen=True)
            record["audit"] = asdict(audit)
            if audit.fetch_failures or audit.fundamental_failures or audit.status != "OK":
                record["status"] = "SOURCE_FAILURE"
            elif audit.cutoff_rejections or any(
                not receipt.get("decision_persisted_before_t4")
                for receipt in audit.t4_attempts
            ):
                record["status"] = "INCOMPLETE_RACES"
            else:
                record["status"] = "COMPLETE"
        except Exception as exc:  # noqa: BLE001 - task boundary records all failures
            record["status"] = "FAILED"
            record["error_type"] = type(exc).__name__
            record["error"] = str(exc)
        record["finished_at"] = datetime.now(UTC).isoformat()
        write_journal(path, record)
        return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--clock-server", required=True)
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.health:
        result = {
            "status": "HEALTH_CHECK",
            "has_journal": any(args.journal.glob("????????T????Z.json")),
            "recent_gaps": recent_gaps(args.journal, slot_start(datetime.now(UTC))),
        }
    else:
        result = run_tick(args.state, args.journal, args.clock_server)
    print(json.dumps(result))
    if result.get("status") in FAILURE_STATUSES or (
        args.health and (not result["has_journal"] or result["recent_gaps"])
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
