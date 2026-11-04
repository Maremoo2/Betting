"""DEV-011 cumulative provenance regressions; only the optional CI replay uses real bytes."""
import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_prospective_outcome_scorecard import FakeOfficial, archive

from hbi.dev011_coverage import finalize, pinned_official, plan
from hbi.prospective_outcome_scorecard import evaluate_archive

RACE = "RIKSTOTO:S1_NR_2026-11-03:8"


def _artifact(run, aid, name, *, expired=False, branch="main"):
    return {
        "id": aid, "name": name, "expired": expired,
        "workflow_run": {"id": run, "head_branch": branch},
        "created_at": "2026-11-03T13:00:00Z",
    }


def _empty(root, number):
    folder = root / str(number)
    folder.mkdir()
    (folder / "cohort-index.json").write_text(json.dumps({
        "schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1",
        "bet_authority": False, "processed": [],
        "original_cohort": [f"RIKSTOTO:TEST_NR_2026-11-04:{number}"],
    }))
    return folder


def _seed(tmp_path):
    models, rows = archive(tmp_path)
    official_root = tmp_path / "results"
    official_root.mkdir()
    result = evaluate_archive(
        models_root=models, output_dir=official_root / "10",
        fetch_official=True, client=FakeOfficial(),
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert result["counts"]["paired_champion_core004"] == 1
    assert result["records"][0]["bet_authority"] is False
    return models, official_root, rows


def test_full_pagination_retains_original_older_than_20_empty_runs(tmp_path):
    models, official, _ = _seed(tmp_path)
    (models / '00000000001').rename(models / '1')
    for number in range(11, 33):
        _empty(models, number)
    newest = [
        _artifact(n, 1000 + n, f"bet-mvp-shadow-{n}") for n in range(11, 33)
    ]
    old = _artifact(1, 1000, "bet-mvp-shadow-1")
    result_artifact = _artifact(10, 1010, "dev009-outcome-scorecards-10")
    other = [_artifact(100 + i, 5000 + i, f"unrelated-{i}") for i in range(125)]
    entries = newest + other + [old, result_artifact]
    pages = [
        {"total_count": len(entries), "artifacts": entries[:100]},
        {"total_count": len(entries), "artifacts": entries[100:]},
    ]
    inventory = plan(pages, current_run_id=9999, inventory_sha="a" * 64)
    assert inventory["github_pages_enumerated"] == 2
    assert len(inventory["selected_artifacts"]) == 24
    assert old["id"] in {e["artifact_id"] for e in inventory["selected_artifacts"]}
    assert result_artifact["id"] in {
        e["artifact_id"] for e in inventory["selected_artifacts"]
    }
    # Earlier latest-20 selection would contain only empty archives.
    assert old not in newest[:20]
    covered = finalize(inventory, models_root=models, results_root=official)
    assert covered["coverage_complete"] is True
    assert covered["missing_originals"] == []
    assert covered["recovered_artifacts"] == 24
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(covered))
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "cumulative",
        prior_results_root=official, coverage_manifest=manifest,
        fetch_official=False, now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    selected = [row for row in score["records"] if row["race_id"] == RACE]
    assert len(selected) == 1
    row = selected[0]
    assert row["outcome_source_mode"] == "PINNED_ARCHIVED_ORIGINAL"
    assert row["winner_selection_id"] == "1"
    assert row["score"]["champion_log_loss"] > 0
    assert row["score"]["core004_log_loss"] > 0
    assert row["score"]["market_log_loss"] > 0
    assert score["counts"]["paired_champion_core004"] == 1
    assert score["counts"]["pit_certified_paired"] == 0
    assert score["counts"]["physical_races"] == 23
    assert score["cumulative_completeness"] == "COMPLETE_AVAILABLE_ORIGINAL_INVENTORY"
    assert score["bet_authority"] is False
    assert score["v33_evaluator_called"] is False
    assert row["original_result_receipts"][0]["archived_original_from_run"] == "10"


def test_expired_original_reported_as_blocked(tmp_path):
    inventory = plan([{"total_count": 1, "artifacts": [
        _artifact(1, 30, "bet-mvp-shadow-1", expired=True)
    ]}], current_run_id=99, inventory_sha="b" * 64)
    assert inventory["coverage_complete"] is False
    out = finalize(inventory, models_root=tmp_path, results_root=tmp_path)
    assert out["status"] == "INCOMPLETE_ORIGINAL_COVERAGE"
    assert out["missing_originals"][0]["reason"] == "EXPIRED_ORIGINAL_ARTIFACT"


def test_original_not_downloaded_is_not_reconstructed(tmp_path):
    inventory = plan([{"total_count": 1, "artifacts": [
        _artifact(1, 30, "bet-mvp-shadow-1")
    ]}], current_run_id=99, inventory_sha="b" * 64)
    out = finalize(inventory, models_root=tmp_path, results_root=tmp_path)
    assert out["coverage_complete"] is False
    assert out["missing_originals"][0]["reason"] == "MISSING_OR_UNVERIFIABLE_ORIGINAL"



@pytest.mark.parametrize("layout", ["flat", "per_race"])
def test_existing_unindexed_legacy_model_stays_unscored_but_is_not_called_missing(
    tmp_path, layout,
):
    root = tmp_path / "models"
    folder = root / "17"
    folder.mkdir(parents=True)
    if layout == "flat":
        (folder / "shadow.json").write_text('{"run_kind":"PROSPECTIVE_ATTEMPT"}')
    else:
        (folder / "RIKSTOTO_TEST_RACE_1").mkdir()
        (folder / "RIKSTOTO_TEST_RACE_1/shadow.json").write_text(
            '{"run_kind":"PROSPECTIVE_ATTEMPT"}'
        )
    inventory = plan([{"total_count": 1, "artifacts": [
        _artifact(17, 3017, "bet-mvp-shadow-17")
    ]}], current_run_id=99, inventory_sha="b" * 64)
    out = finalize(inventory, models_root=root, results_root=tmp_path / "empty")
    assert out["coverage_complete"] is False
    assert out["recovered_artifacts"] == 0
    assert out["missing_originals"] == [{
        "artifact_id": 3017, "source_run_id": 17, "kind": "model",
        "reason": "UNINDEXED_LEGACY_MODEL_ORIGINAL",
    }]
    assert out["selected_artifacts"][0]["status"] == "UNINDEXED_LEGACY_MODEL_ORIGINAL"
    from hbi.prospective_outcome_scorecard import read_archived_models
    assert read_archived_models(root)[0] == []


def test_unindexed_legacy_original_symlink_is_never_attested(tmp_path):
    root = tmp_path / "models"
    folder = root / "17"
    folder.mkdir(parents=True)
    external = tmp_path / "outside.json"
    external.write_text('{"run_kind":"PROSPECTIVE_ATTEMPT"}')
    (folder / "shadow.json").symlink_to(external)
    inventory = plan([{"total_count": 1, "artifacts": [
        _artifact(17, 3017, "bet-mvp-shadow-17")
    ]}], current_run_id=99, inventory_sha="b" * 64)
    out = finalize(inventory, models_root=root, results_root=tmp_path / "results")
    assert out["missing_originals"][0]["reason"] == "MISSING_OR_UNVERIFIABLE_ORIGINAL"
    assert out["coverage_complete"] is False


def test_authentic_nov2_five_legacy_originals_exist_without_cohort_indexes(tmp_path):
    root_text = os.environ.get("MVP014_LEGACY_ORIGINALS_ROOT")
    if not root_text:
        pytest.skip("Requires five actual GitHub Actions original artifacts")
    models = Path(root_text)
    sha_by_run = {
        41456642411: "9c4e0d2862ef1988a8babad2529a5f13ce3c896c10a857038d910a9cc187127b",
        41459303701: "3f01e5563c1d12c7ae3549e6e6e2c9753524d1d063b741b639e97cf9d2aa460f",
        41461113601: "380db85cbf812f52446a53492f41e88e9a6a8a823de4e2912f27e02e5f7b713b",
        41462919513: "c6317248eb9346b454ff0af99be607190e07e2b67aeb794a1aa4cf1887a78a13",
        41463276002: "acaa528c62854bb1514dc164f16bca0efff99f2c92f26bc191d012ccb5a41d62",
    }
    synthetic_inventory = [_artifact(
        run, 13147076977 + i, f"bet-mvp-shadow-{run}"
    ) for i, run in enumerate(sha_by_run)]
    inventory = plan([{
        "total_count": len(synthetic_inventory), "artifacts": synthetic_inventory,
    }], current_run_id=9999999, inventory_sha="b" * 64)
    for run, expected_sha in sha_by_run.items():
        folder = models / str(run)
        assert folder.is_dir()
        assert not (folder / "cohort-index.json").exists()
        members = sorted(folder.rglob("shadow.json"))
        assert members
        assert hashlib.sha256(members[0].read_bytes()).hexdigest() == expected_sha
    out = finalize(inventory, models_root=models, results_root=tmp_path / "empty")
    assert len(out["missing_originals"]) == 5
    assert all(x["reason"] == "UNINDEXED_LEGACY_MODEL_ORIGINAL"
               for x in out["missing_originals"])
    assert out["recovered_artifacts"] == 0 and out["coverage_complete"] is False
    from hbi.prospective_outcome_scorecard import read_archived_models
    assert read_archived_models(models)[0] == []


def test_missing_page_and_concurrent_change_rejected():
    pages = [{"total_count": 101, "artifacts": [_artifact(
        i, i + 1000, f"bet-mvp-shadow-{i}"
    ) for i in range(100)]}]
    with pytest.raises(ValueError, match="INCOMPLETE_ARTIFACT_PAGINATION"):
        plan(pages, current_run_id=900, inventory_sha="b" * 64)
    pages.append({"total_count": 102, "artifacts": []})
    with pytest.raises(ValueError, match="ARTIFACT_PAGINATION_CONCURRENT_CHANGE"):
        plan(pages, current_run_id=900, inventory_sha="b" * 64)


def test_wrong_model_sha_is_blocked_and_not_scored(tmp_path):
    models, official, _ = _seed(tmp_path)
    model = models / "00000000001/race-001/shadow.json"
    model.write_bytes(model.read_bytes() + b" ")
    inventory = plan([{"total_count": 1, "artifacts": [
        _artifact(1, 30, "bet-mvp-shadow-1")
    ]}], current_run_id=99, inventory_sha="b" * 64)
    out = finalize(inventory, models_root=models, results_root=official)
    assert out["coverage_complete"] is False
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out",
        prior_results_root=official, fetch_official=False,
    )
    assert score["counts"]["paired_champion_core004"] == 0
    assert score["bet_authority"] is False
    assert "FROZEN_MODEL_SHA256_MISMATCH" in str(score["archive_errors"])


def test_identical_duplicate_race_id_never_double_scored(tmp_path):
    models, official, _ = _seed(tmp_path)
    shutil.copytree(models / "00000000001", models / "00000000002")
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out",
        prior_results_root=official, fetch_official=False,
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert score["counts"]["physical_races"] == 1
    assert score["counts"]["paired_champion_core004"] == 1


def test_missing_official_result_is_not_evaluable(tmp_path):
    models, _, _ = _seed(tmp_path)
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out",
        prior_results_root=tmp_path / "no-results", fetch_official=False,
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert score["counts"]["official_results_verified"] == 0
    assert "OFFICIAL_RESULTS_NOT_FETCHED" in score["records"][0]["reasons"]


def test_tampered_pinned_original_is_rejected(tmp_path):
    models, official, _ = _seed(tmp_path)
    path = next((official / "10").glob("official-*/complete.raw.json"))
    path.write_bytes(path.read_bytes() + b"\n")
    candidates, errors = pinned_official(official)
    assert RACE not in candidates
    assert errors[RACE] == ["PINNED_RESULT_ORIGINAL_MISSING_OR_CHANGED"]
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out",
        prior_results_root=official, fetch_official=False,
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert score["counts"]["paired_champion_core004"] == 0
    assert "PINNED_RESULT_ORIGINAL_MISSING_OR_CHANGED" in score["records"][0]["reasons"]


def test_changed_valid_result_version_is_blocked(tmp_path):
    models, official, _ = _seed(tmp_path)
    shutil.copytree(official / "10", official / "11")
    raw = next((official / "11").glob("official-*/complete.raw.json"))
    changed = raw.read_bytes().replace(b'"place": 1', b'"place": 3', 1)
    assert changed != raw.read_bytes()
    raw.write_bytes(changed)
    idx = official / "11/index.json"
    doc = json.loads(idx.read_text())
    receipt = doc["records"][0]["original_result_receipts"][0]
    assert receipt["role"] == "complete"
    receipt["raw_sha256"] = hashlib.sha256(changed).hexdigest()
    idx.write_text(json.dumps(doc))
    candidates, errors = pinned_official(official)
    assert RACE not in candidates
    assert "CONFLICTING_OFFICIAL_RESULT_RECEIPTS" in errors[RACE]
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out",
        prior_results_root=official, fetch_official=False,
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert score["counts"]["paired_champion_core004"] == 0
    assert "CONFLICTING_OFFICIAL_RESULT_RECEIPTS" in score["records"][0]["reasons"]


def test_incomplete_champion_core004_field_still_blocked(tmp_path):
    models, _, _ = _seed(tmp_path)
    idx = models / "00000000001/cohort-index.json"
    doc = json.loads(idx.read_text())
    raw = models / "00000000001/race-001/shadow.json"
    model = json.loads(raw.read_bytes())
    model["runners"][0]["core004_p_win"] = None
    bytes_ = json.dumps(model, sort_keys=True).encode()
    raw.write_bytes(bytes_)
    doc["processed"][0]["report_sha256"] = hashlib.sha256(bytes_).hexdigest()
    idx.write_text(json.dumps(doc))
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out", fetch_official=False,
    )
    assert "CORE004_FULL_FIELD_INVALID" in score["records"][0]["reasons"]
    assert score["counts"]["paired_champion_core004"] == 0


def test_no_pit_authority_from_scorecard_or_reused_result(tmp_path):
    models, official, _ = _seed(tmp_path)
    score = evaluate_archive(
        models_root=models, output_dir=tmp_path / "out",
        prior_results_root=official, fetch_official=False,
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert score["counts"]["pit_certified_paired"] == 0
    assert score["records"][0]["cohort"] == "PROSPECTIVE_NOT_PIT_CERTIFIED"
    assert score["bet_authority"] is False
    assert score["stake_nok"] is None
    assert score["no_model_promotion"] is True


def test_authentic_eskilstuna_model_and_official_receipts_after_empty_runs(tmp_path):
    models = os.environ.get("DEV011_AUTHENTIC_MODEL_ROOT")
    results = os.environ.get("DEV011_AUTHENTIC_RESULTS_ROOT")
    if not models or not results:
        pytest.skip("Authentic GitHub model/results archives only available in PR CI")
    root = Path(models)
    original_path = root / "41646155051/race-001/shadow.json"
    before = hashlib.sha256(original_path.read_bytes()).hexdigest()
    assert before == "f04dd8f19254764114739009383371e3367c445c917c8fac5b08cf085e814a6d"
    synthetic = [41646155100 + i for i in range(21)]
    for run_id in synthetic:
        _empty(root, run_id)
    # Two originals are real: model GitHub artifact 13235845295 and official
    # research receipt 13243490434. The 21 later empty indexes and their
    # artifact metadata below are explicitly TEST_ONLY.
    artifact_rows = [_artifact(
        41646155051, 13235845295, "bet-mvp-shadow-41646155051"
    )] + [_artifact(run_id, 9900000 + i, f"bet-mvp-shadow-{run_id}")
         for i, run_id in enumerate(synthetic)]
    pages = [{"total_count": len(artifact_rows), "artifacts": artifact_rows}]
    inventory = plan(
        pages, current_run_id=77777777,
        inventory_sha=hashlib.sha256(json.dumps(pages).encode()).hexdigest(),
    )
    coverage = finalize(inventory, models_root=root, results_root=Path(results))
    assert coverage["coverage_complete"] is True
    assert coverage["recovered_artifacts"] == 22
    coverage["evidence_mode"] = "TEST_ONLY_SYNTHETIC_GITHUB_PAGES_WITH_REAL_SOURCE_BYTES"
    coverage["test_only_synthetic_empty_runs"] = 21
    coverage["original_model_artifact_id"] = 13235845295
    coverage["original_result_artifact_id"] = 13243490434
    evidence_dir = Path(os.environ.get("DEV011_CI_MANIFEST_DIR", tmp_path / "coverage"))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest = evidence_dir / "manifest.json"
    manifest.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n")
    report = evaluate_archive(
        models_root=root, output_dir=tmp_path / "authentic-scorecard",
        prior_results_root=Path(results), coverage_manifest=manifest,
        fetch_official=False, now=datetime(2026, 11, 3, 18, tzinfo=UTC),
    )
    assert report["cumulative_completeness"] == "COMPLETE_AVAILABLE_ORIGINAL_INVENTORY"
    row = next(r for r in report["records"] if r["race_id"] == RACE)
    assert row["source_model_original_sha256"] == before
    assert row["winner_selection_id"] == "5"
    assert row["status"] == "EVALUABLE_RESEARCH_ONLY"
    assert row["active_runners"] == 12
    assert row["score"]["champion_log_loss"] == pytest.approx(2.811230442450394)
    assert row["score"]["core004_log_loss"] == pytest.approx(3.050054520397332)
    assert row["score"]["market_log_loss"] == pytest.approx(1.802836992188997)
    assert report["counts"]["paired_champion_core004"] == 1
    assert report["counts"]["pit_certified_paired"] == 0
    assert report["bet_authority"] is False
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == before
    raw = row["original_result_receipts"]
    assert {r["role"] for r in raw} == {"complete", "raceday"}
    assert all(hashlib.sha256(Path(r["raw_path"]).read_bytes()).hexdigest()
               == r["raw_sha256"] for r in raw)
    assert row["outcome_source_mode"] == "PINNED_ARCHIVED_ORIGINAL"
