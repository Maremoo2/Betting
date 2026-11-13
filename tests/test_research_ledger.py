import json
from datetime import UTC, datetime
from zipfile import ZipFile

import pytest
from test_prospective_outcome_scorecard import RID, FakeOfficial, archive

from hbi.prospective_outcome_scorecard import digest, evaluate_archive
from hbi.research_ledger import build_ledger


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
