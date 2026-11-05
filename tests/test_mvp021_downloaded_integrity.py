"""A successful download command cannot attest incomplete or changed members."""
import hashlib
import json

import pytest
from test_dev011_coverage import _artifact, _empty

from hbi.dev011_coverage import finalize, plan
from hbi.mvp016_inventory_guard import guard


@pytest.mark.parametrize("damage", ["missing_index", "truncated_index", "missing_member", "changed_member"])
def test_download_success_with_unverifiable_bytes_cannot_publish(tmp_path, damage):
    models = tmp_path / "models"
    models.mkdir()
    folder = _empty(models, 17)
    index = folder / "cohort-index.json"
    if damage == "missing_index":
        index.unlink()
    elif damage == "truncated_index":
        index.write_bytes(b'{"schema":')
    else:
        doc = json.loads(index.read_bytes())
        doc["processed"] = [{"directory": "bet-mvp-shadow/race-001",
                             "report_sha256": hashlib.sha256(b"original").hexdigest()}]
        index.write_text(json.dumps(doc))
        if damage == "changed_member":
            (folder / "race-001").mkdir()
            (folder / "race-001/shadow.json").write_bytes(b"changed")
    manifest = plan([{"total_count": 1, "artifacts": [
        _artifact(17, 3017, "bet-mvp-shadow-17")
    ]}], current_run_id=99, inventory_sha="b" * 64)
    finalized = finalize(manifest, models_root=models, results_root=tmp_path / "results")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(finalized))
    failures = tmp_path / "failures.tsv"
    failures.write_bytes(b"")  # gh reported success; no transport failure.
    out = tmp_path / "new-scorecard"
    assert not guard(path, output_dir=out, failed_downloads=failures)
    diagnostic = json.loads((out / "source-unavailable.json").read_bytes())
    assert diagnostic["source_reason"] == "DOWNLOADED_ORIGINAL_INTEGRITY_FAILED"
    assert diagnostic["cumulative_physical_races"] is None
    assert diagnostic["prior_verified_scorecard_invalidated"] is False
    assert not (out / "index.json").exists()


@pytest.mark.parametrize("kind", ["empty", "legacy", "explicit_source_block"])
def test_genuine_empty_and_old_source_blocks_are_distinct_from_damage(tmp_path, kind):
    models = tmp_path / "models"
    models.mkdir()
    folder = _empty(models, 17)
    if kind != "empty":
        (folder / "cohort-index.json").unlink()
        if kind == "legacy":
            (folder / "shadow.json").write_bytes(b'{"run_kind":"PROSPECTIVE_ATTEMPT"}')
        else:
            (folder / "source-unavailable.json").write_text(json.dumps({
                "schema": "MVP016_CUMULATIVE_SCORECARD_SOURCE_UNAVAILABLE_V1",
                "scorecard_generated": False, "bet_authority": False,
            }))
    manifest = plan([{"total_count": 1, "artifacts": [
        _artifact(17, 3017, "bet-mvp-shadow-17")
    ]}], current_run_id=99, inventory_sha="b" * 64)
    finalized = finalize(manifest, models_root=models, results_root=tmp_path / "results")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(finalized))
    failures = tmp_path / "failures.tsv"
    failures.write_bytes(b"")
    assert guard(path, output_dir=tmp_path / "new-scorecard", failed_downloads=failures)
    assert finalized["original_integrity_failures"] == []
    assert finalized["coverage_complete"] == (kind == "empty")
