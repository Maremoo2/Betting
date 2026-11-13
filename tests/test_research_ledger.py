import json
from copy import deepcopy
from datetime import UTC, datetime
from zipfile import ZipFile

import pytest
from test_prospective_outcome_scorecard import RID, FakeOfficial, archive

from hbi.prospective_outcome_scorecard import digest, evaluate_archive
from hbi.research_ledger import attach_current, build_ledger


@pytest.mark.parametrize(("fault", "status"), [
    ("none", "TRIPLE_EVALUABLE"), ("no_model", "BLOCKED_SOURCE"),
    ("duplicate", None), ("result_conflict", "BLOCKED_SOURCE"),
    ("missing_result", "BLOCKED_SOURCE"), ("wrong_freeze", "BLOCKED_SOURCE"),
    ("missing_hash", "BLOCKED_SOURCE"),
])
def test_offline_ledger_preserves_denominator(tmp_path, fault, status):
    models, _ = archive(tmp_path)
    output = tmp_path / "scorecard"
    source = evaluate_archive(
        models_root=models, output_dir=output, fetch_official=True, client=FakeOfficial(),
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    original = source["records"][0]
    original["source_model_path"] = "models/00000000001/race-001/shadow.json"
    original["original_freeze_history"][0]["source_model_path"] = original["source_model_path"]
    source["cumulative_original_inventory"] = {
        "selected_artifacts": [{"kind": "model", "source_run_id": "00000000001", "artifact_id": 10}],
        "missing_originals": [],
    }
    if fault == "duplicate":
        source["records"].append(original)
    elif fault == "missing_hash":
        original["source_model_original_sha256"] = None
    elif fault == "result_conflict":
        original["reasons"].append("CONFLICTING_OFFICIAL_RESULT_RECEIPTS")
    elif fault == "wrong_freeze":
        original["original_freeze_history"][0]["model_sha256"] = "a" * 64
    zpath = tmp_path / "10.zip"
    if fault != "no_model":
        with ZipFile(zpath, "w") as z:
            for path in (models / "00000000001").rglob("*.json"):
                z.write(path, path.relative_to(models / "00000000001").as_posix())
    index = json.dumps(source).encode()
    scorecard = tmp_path / "scorecard.zip"
    with ZipFile(scorecard, "w") as z:
        z.writestr("index.json", index)
        for path in output.rglob("*.raw.json"):
            if fault != "missing_result":
                z.write(path, path.relative_to(output).as_posix())
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.zip")}
    if fault == "duplicate":
        with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_RACE"):
            build_ledger(tmp_path, scorecard, digest(index))
    else:
        report = build_ledger(tmp_path, scorecard, digest(index))
        assert report["observed"] == 1
        row = report["records"][0]
        assert (row["race_id"], row["evaluation_status"]) == (RID, status)
        assert not report["bet_authority"] and report["pit_certified"] == 0
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.zip")} == before
    assert not list(tmp_path.rglob("*.sqlite"))

@pytest.mark.parametrize("disposition", ["rejected", "error", "verified", "missing", "tampered"])
def test_current_observation_preserves_original_and_benchmark(tmp_path, disposition):
    models, _ = archive(tmp_path)
    directory = models / "00000000001"
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "schema_version": "CORE_003_SHADOW_PILOT_V1",
        "bet_count": 0,
        "races_in_fixed_cohort": [RID],
    }))
    handoff = tmp_path / "handoff.json"
    receipts = [{"race_id": RID, "import_record_verified": True, "blockers": ["SOURCE_BLOCKED"]}]
    handoff.write_text(json.dumps({
        "source_report_sha256": digest(source.read_bytes()),
        "bet_authority": False, "pit_certified": False, "records": receipts,
    }))
    index_path = directory / "cohort-index.json"
    index = json.loads(index_path.read_bytes())
    index.update({
        "original_cohort": [RID], "source_report_sha256": digest(source.read_bytes()),
        "collector_handoff_sha256": digest(handoff.read_bytes()), "collector_handoff": receipts,
        "pit_certified": False, "errors": [], "not_processed": [],
    })
    shadow = directory / "race-001" / "shadow.json"
    expected = digest(shadow.read_bytes())
    if disposition in {"rejected", "error"}:
        index["processed"] = []
        key = "not_processed" if disposition == "rejected" else "errors"
        index[key] = [{"race_id": RID, "reason": disposition}]
    elif disposition == "missing":
        shadow.unlink()
    elif disposition == "tampered":
        shadow.write_bytes(b"{}")
    index_path.write_text(json.dumps(index))
    historical = {"records": [{"race_id": RID, "winner_selection_id": "old"}]}
    first = attach_current(deepcopy(historical), source, directory, handoff)
    revised = {"records": [{"race_id": RID, "winner_selection_id": "revised"}]}
    second = attach_current(deepcopy(revised), source, directory, handoff)
    assert first == attach_current(deepcopy(first), source, directory, handoff)
    assert first["current_observations"] == second["current_observations"]
    assert first["records"] == historical["records"]
    assert first["observed_with_current"] == 1
    row = first["current_observations"]["records"][0]
    assert row["collector_import_verified"] is True
    assert row["model_sha256"] == (expected if disposition == "verified" else None)
    assert not row["pit_certified"]
    assert "winner_selection_id" not in row
    if disposition != "verified":
        assert row["same_freeze_win"] is None
        assert not row["full_field"]
