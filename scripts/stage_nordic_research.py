"""Stage the existing Nordic research runtime with a verified canonical SQLite bootstrap."""

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from hbi.governance import load_governance
from hbi.manifest import CRITICAL_PATHS
from hbi.state_artifact import _verify_canonical_sqlite

GOVERNANCE_PATH = "docs/research_governance.json"
RUNTIME_PATHS = ("README.md", "pyproject.toml", "src", "db", GOVERNANCE_PATH)


def verify_bootstrap(checkout: Path, scratch: Path) -> str:
    """Exercise the same init-db command used by the hosted research job."""
    schema = checkout / "db/schema.sql"
    migrations = {p.name for p in (schema.parent / "migrations").glob("*.sql")}
    if not schema.is_file() or not migrations:
        raise ValueError("NORDIC_RUNTIME_SCHEMA_OR_MIGRATIONS_MISSING")
    if any(not (checkout / p).is_file() for p in (*CRITICAL_PATHS, GOVERNANCE_PATH)):
        raise ValueError("NORDIC_RUNTIME_PROTECTED_INPUT_MISSING")
    load_governance(checkout / GOVERNANCE_PATH)
    db = scratch / "seed.sqlite"
    command = [sys.executable, "-m", "hbi.cli", "--db", str(db), "init-db"]
    env = {**os.environ, "PYTHONPATH": str(checkout / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    for _ in range(2):
        subprocess.run(command, cwd=checkout, env=env, check=True, capture_output=True)
        with closing(sqlite3.connect(db)) as conn:
            if {row[0] for row in conn.execute("SELECT migration_id FROM schema_migrations")} != migrations:
                raise ValueError("NORDIC_RUNTIME_MIGRATIONS_NOT_VERIFIED")
            if conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise ValueError("NORDIC_RUNTIME_WAL_CHECKPOINT_FAILED")
    _verify_canonical_sqlite(db)
    moved = scratch / "restored.sqlite"
    shutil.copyfile(db, moved)
    _verify_canonical_sqlite(moved)
    pin = hashlib.sha256(db.read_bytes()).hexdigest()
    if hashlib.sha256(moved.read_bytes()).hexdigest() != pin:
        raise ValueError("NORDIC_RUNTIME_STATE_READBACK_MISMATCH")
    return pin


def stage(repo: Path, ref: str, output: Path) -> str:
    if output.exists():
        raise FileExistsError(output)
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=repo, text=True,
    ).strip()
    with TemporaryDirectory() as temp:
        root = Path(temp)
        bundle = root / "runtime.zip"
        subprocess.run(
            ["git", "archive", "--format=zip", "--output", str(bundle), commit, *RUNTIME_PATHS],
            cwd=repo, check=True,
        )
        checkout = root / "checkout"
        with ZipFile(bundle) as archive:
            archive.extractall(checkout)
        pin = verify_bootstrap(checkout, root)
        with bundle.open("rb") as source, output.open("xb") as destination:
            shutil.copyfileobj(source, destination)
    return pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"CANONICAL_SQLITE_BOOTSTRAP_SHA256={stage(Path(__file__).resolve().parents[1], args.ref, args.output)}")


if __name__ == "__main__":
    main()
