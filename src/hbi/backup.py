from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_paths(values: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in values:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_dir():
            files.extend(item for item in sorted(path.rglob("*")) if item.is_file())
        else:
            files.append(path)
    return files


def sqlite_integrity(db_path: Path) -> str:
    with sqlite3.connect(str(db_path)) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def build_manifest(
    *,
    db_path: Path,
    include: list[str],
) -> dict[str, object]:
    integrity = sqlite_integrity(db_path)
    if integrity.lower() != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")

    files = _collect_paths([str(db_path), *include])
    unique: dict[str, Path] = {str(path): path for path in files}
    entries = [
        {
            "path": path,
            "size_bytes": file_path.stat().st_size,
            "sha256": _sha256(file_path),
        }
        for path, file_path in sorted(unique.items())
    ]
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "sqlite_integrity": integrity,
        "github_repository": os.getenv("GITHUB_REPOSITORY"),
        "github_sha": os.getenv("GITHUB_SHA"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "files": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--include", nargs="*", default=[])
    args = parser.parse_args()

    manifest = build_manifest(
        db_path=Path(args.db),
        include=list(args.include),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
