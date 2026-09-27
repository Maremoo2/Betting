import json
from pathlib import Path

from hbi.backup import build_manifest
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


def test_backup_manifest_hashes_database_and_exports(tmp_path):
    db = tmp_path / "hbi.sqlite"
    store = SQLiteStore(db)
    store.initialize(SCHEMA)
    store.checkpoint()

    export = tmp_path / "report.json"
    export.write_text('{"ok": true}', encoding="utf-8")

    manifest = build_manifest(
        db_path=db,
        include=[str(export)],
    )

    assert manifest["sqlite_integrity"] == "ok"
    paths = {row["path"] for row in manifest["files"]}
    assert str(db) in paths
    assert str(export) in paths
    assert all(len(row["sha256"]) == 64 for row in manifest["files"])

    encoded = json.dumps(manifest)
    assert "sqlite_integrity" in encoded
