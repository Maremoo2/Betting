import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage_nordic_research", ROOT / "scripts/stage_nordic_research.py")
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


def test_staged_checkout_bootstraps_migrates_and_restores_canonical_sqlite(tmp_path):
    output = tmp_path / "runtime.zip"
    assert len(staging.stage(ROOT, "HEAD", output)) == 64
    with ZipFile(output) as archive:
        assert "db/schema.sql" in archive.namelist()
        assert "db/migrations/0010_release006_signal_integrity.sql" in archive.namelist()
        assert "docs/research_governance.json" in archive.namelist()
        assert not any(name.startswith(".github/") for name in archive.namelist())


def test_source_only_checkout_fails_before_opening_sqlite(tmp_path):
    (tmp_path / "src").mkdir()
    with pytest.raises(ValueError, match="SCHEMA_OR_MIGRATIONS_MISSING"):
        staging.verify_bootstrap(tmp_path, tmp_path)
    assert not (tmp_path / "seed.sqlite").exists()
