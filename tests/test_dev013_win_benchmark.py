"""DEV-013: deterministic pre-T4 model-version choice and original WIN pairing."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_prospective_outcome_scorecard import FakeOfficial, archive

from hbi.dev011_coverage import pinned_official
from hbi.prospective_outcome_scorecard import evaluate_archive, read_archived_models

RID = "RIKSTOTO:S1_NR_2026-11-03:8"
EARLY_SHA = "d3036bc47fab25a5e1ca5b621fba6b0d340537b03f953449ab84400298a3b1d4"
LATE_SHA = "f04dd8f19254764114739009383371e3367c445c917c8fac5b08cf085e814a6d"


def _freeze(root: Path, number: int, model: dict) -> None:
    folder = root / f"{number:011d}"
    (folder / "race-001").mkdir(parents=True, exist_ok=True)
    raw = json.dumps(model, sort_keys=True).encode()
    (folder / "race-001/shadow.json").write_bytes(raw)
    (folder / "cohort-index.json").write_text(json.dumps({
        "schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1",
        "bet_authority": False,
        "original_cohort": [RID],
        "processed": [{
            "race_id": RID, "directory": "bet-mvp-shadow/race-001",
            "report_sha256": hashlib.sha256(raw).hexdigest(),
        }],
    }))


def _set_market(model: dict, *, complete: bool, observation: str | None = None) -> None:
    for runner in model["runners"]:
        if not complete:
            runner["win_odds"] = None
            runner["win_odds_provider"] = None
            runner["win_odds_observed_at_utc"] = None
        elif observation is not None:
            runner["win_odds_observed_at_utc"] = observation


def _versions(
    tmp_path: Path, *, early_market: bool = False,
    later_market: bool = True, later_created: str = "2026-11-03T12:55:30+00:00",
    later_asof: str = "2026-11-03T12:55:20+00:00",
    later_win_observed: str = "2026-11-03T12:55:10+00:00",
) -> tuple[Path, dict, dict]:
    root, records = archive(tmp_path)
    early = copy.deepcopy(records[0][1])
    early["report_created_at_utc"] = "2026-11-03T12:55:00+00:00"
    early["as_of_utc"] = "2026-11-03T12:54:00+00:00"
    _set_market(early, complete=early_market)
    later = copy.deepcopy(records[0][1])
    later["report_created_at_utc"] = later_created
    later["as_of_utc"] = later_asof
    _set_market(later, complete=later_market, observation=later_win_observed)
    shutil.rmtree(root / "00000000001")
    _freeze(root, 1, early)
    _freeze(root, 2, later)
    return root, early, later


def _evaluate(root: Path, folder: Path, *, results: Path | None = None) -> dict:
    return evaluate_archive(
        models_root=root, output_dir=folder,
        fetch_official=results is None,
        client=FakeOfficial() if results is None else None,
        prior_results_root=results,
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )


def test_latest_qualified_t4_frozen_model_restores_win_without_result_selection(tmp_path):
    root, _, _ = _versions(tmp_path)
    data = _evaluate(root, tmp_path / "scored")
    row = data["records"][0]
    assert data["counts"]["paired_champion_core004"] == 1
    assert data["counts"]["triple_evaluable"] == 1
    assert row["benchmark_status"] == "TRIPLE_EVALUABLE"
    assert row["source_model_path"].endswith("00000000002/race-001/shadow.json")
    assert row["model_created_at_utc"] == "2026-11-03T12:55:30+00:00"
    assert row["benchmark_t4_cutoff_utc"] == "2026-11-03T12:56:00+00:00"
    assert row["win_provenance"] == "EMBEDDED_IN_VERIFIED_FROZEN_MODEL_SHA256"
    assert row["win_original_raw_sha256"] is None
    assert len(row["original_freeze_history"]) == 2
    assert sum(x["selected_benchmark_reference"] for x in row["original_freeze_history"]) == 1
    assert row["original_freeze_history"][0]["win_market_complete_on_same_freeze"] is False
    assert data["counts"]["pit_certified_paired"] == 0
    assert data["bet_authority"] is False


def test_later_missing_win_is_not_replaced_with_earlier_win(tmp_path):
    root, _, _ = _versions(tmp_path, early_market=True, later_market=False)
    data = _evaluate(root, tmp_path / "out")
    row = data["records"][0]
    assert row["source_model_path"].endswith("00000000002/race-001/shadow.json")
    assert row["benchmark_status"] == "MODEL_PAIR_ONLY"
    assert row["market_baseline_available"] is False
    assert data["counts"]["triple_evaluable"] == 0


@pytest.mark.parametrize("created,asof", [
    ("2026-11-03T12:56:01+00:00", "2026-11-03T12:55:50+00:00"),
    ("2026-11-03T12:55:30+00:00", "2026-11-03T12:55:40+00:00"),
])
def test_invalid_later_freeze_never_overwrites_pre_t4_model(tmp_path, created, asof):
    root, _, _ = _versions(
        tmp_path, early_market=True, later_created=created, later_asof=asof,
    )
    data = _evaluate(root, tmp_path / "out")
    row = data["records"][0]
    assert row["source_model_path"].endswith("00000000001/race-001/shadow.json")
    assert row["benchmark_status"] == "TRIPLE_EVALUABLE"
    assert row["original_freeze_history"][-1]["eligible_pre_t4"] is False


def test_win_observed_after_t4_is_never_used(tmp_path):
    root, _, _ = _versions(
        tmp_path, later_win_observed="2026-11-03T12:56:02+00:00",
    )
    data = _evaluate(root, tmp_path / "out")
    row = data["records"][0]
    assert row["source_model_path"].endswith("00000000002/race-001/shadow.json")
    assert row["benchmark_status"] == "MODEL_PAIR_ONLY"
    assert data["counts"]["triple_evaluable"] == 0


def test_missing_win_original_and_bad_active_field_are_fail_closed(tmp_path):
    root, _, _ = _versions(tmp_path, later_market=False)
    data = _evaluate(root, tmp_path / "out1")
    assert data["counts"]["model_pair_only"] == 1
    bad = root / "00000000002/race-001/shadow.json"
    model = json.loads(bad.read_bytes())
    model["runners"][0]["core004_p_win"] = None
    _freeze_rewrite = root / "00000000002"
    shutil.rmtree(_freeze_rewrite)
    _freeze(root, 2, model)
    data = _evaluate(root, tmp_path / "out2")
    assert data["records"][0]["source_model_path"].endswith(
        "00000000001/race-001/shadow.json"
    )
    assert data["counts"]["triple_evaluable"] == 0


def test_unverifiable_latest_original_is_rejected_not_reconstructed(tmp_path):
    root, _, _ = _versions(tmp_path)
    raw = root / "00000000002/race-001/shadow.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    data = _evaluate(root, tmp_path / "out")
    assert "FROZEN_MODEL_SHA256_MISMATCH" in str(data["archive_errors"])
    assert data["records"][0]["source_model_path"].endswith(
        "00000000001/race-001/shadow.json"
    )


def test_repeated_workflow_does_not_duplicate_physical_races(tmp_path):
    root, _, _ = _versions(tmp_path)
    shutil.copytree(root / "00000000002", root / "00000000003")
    data = _evaluate(root, tmp_path / "out")
    assert data["counts"]["physical_races"] == 1
    assert data["counts"]["paired_champion_core004"] == 1
    assert len(data["records"][0]["original_freeze_history"]) == 3


def test_identical_verified_official_result_reusable_with_different_model_sha(tmp_path):
    root, _, _ = _versions(tmp_path, early_market=True)
    later = root / "00000000002"
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    shutil.copytree(root / "00000000001", isolated / "00000000001")
    results = tmp_path / "results"
    results.mkdir()
    first = evaluate_archive(
        models_root=isolated, output_dir=results / "10",
        fetch_official=True, client=FakeOfficial(),
        now=datetime(2026, 11, 3, 14, tzinfo=UTC),
    )
    assert first["counts"]["paired_champion_core004"] == 1
    assert later.is_dir()
    pinned, errors = pinned_official(results)
    assert RID in pinned and not errors
    second = _evaluate(root, tmp_path / "after", results=results)
    assert second["counts"]["triple_evaluable"] == 1
    row = second["records"][0]
    assert row["outcome_source_mode"] == "PINNED_ARCHIVED_ORIGINAL"
    assert row["pinned_result_original_model_sha256"] != row["source_model_original_sha256"]
    assert row["winner_selection_id"] == "1"
    assert row["bet_authority"] is False


def test_changed_official_original_still_conflicts_even_with_multiple_model_shas(tmp_path):
    root, _, _ = _versions(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    _evaluate(root, results / "10")
    shutil.copytree(results / "10", results / "11")
    path = next((results / "11").glob("official-*/complete.raw.json"))
    changed = path.read_bytes().replace(b'"place": 1', b'"place": 3', 1)
    assert changed != path.read_bytes()
    path.write_bytes(changed)
    index = results / "11/index.json"
    report = json.loads(index.read_text())
    rec = report["records"][0]["original_result_receipts"][0]
    rec["raw_sha256"] = hashlib.sha256(changed).hexdigest()
    index.write_text(json.dumps(report))
    _, errors = pinned_official(results)
    assert "CONFLICTING_OFFICIAL_RESULT_RECEIPTS" in errors[RID]
    data = _evaluate(root, tmp_path / "out", results=results)
    assert data["counts"]["paired_champion_core004"] == 0
    assert "CONFLICTING_OFFICIAL_RESULT_RECEIPTS" in data["records"][0]["reasons"]


def test_authentic_eskilstuna_original_frozen_versions_and_official_receipts(tmp_path):
    models = os.environ.get("DEV013_AUTHENTIC_MODEL_ROOT")
    official = os.environ.get("DEV013_AUTHENTIC_RESULTS_ROOT")
    if not models or not official:
        pytest.skip("Original GitHub artifact bytes are required for this CI replay")
    root = Path(models)
    first = root / "41635474321/race-004/shadow.json"
    second = root / "41646155051/race-001/shadow.json"
    assert hashlib.sha256(first.read_bytes()).hexdigest() == EARLY_SHA
    assert hashlib.sha256(second.read_bytes()).hexdigest() == LATE_SHA
    all_models, errors, _ = read_archived_models(root)
    assert not errors
    chosen = next(x for x in all_models if x["race_id"] == RID)
    assert chosen["model_sha256"] == LATE_SHA
    hist = chosen["original_freeze_history"]
    assert len([x for x in hist if x["selected_benchmark_reference"]]) == 1
    assert any(x["model_sha256"] == EARLY_SHA and not
               x["win_market_complete_on_same_freeze"] for x in hist)
    assert any(x["model_sha256"] == LATE_SHA and
               x["win_market_complete_on_same_freeze"] for x in hist)
    result = _evaluate(root, tmp_path / "real-scorecard", results=Path(official))
    race = next(x for x in result["records"] if x["race_id"] == RID)
    assert race["benchmark_status"] == "TRIPLE_EVALUABLE"
    assert race["active_runners"] == 12
    assert race["source_model_original_sha256"] == LATE_SHA
    assert race["winner_selection_id"] == "5"
    assert race["score"]["champion_log_loss"] == pytest.approx(2.811230442450394)
    assert race["score"]["core004_log_loss"] == pytest.approx(3.050054520397332)
    assert race["score"]["market_log_loss"] == pytest.approx(1.802836992188997)
    assert race["outcome_source_mode"] == "PINNED_ARCHIVED_ORIGINAL"
    assert result["counts"]["pit_certified_paired"] == 0
    assert result["bet_authority"] is False
    assert result["stake_nok"] is None
    dest = os.environ.get("DEV013_CI_OUTPUT_DIR")
    if dest:
        out = Path(dest)
        out.mkdir(parents=True, exist_ok=True)
        (out / "original-replay.json").write_text(json.dumps({
            "evidence": "TWO_GENUINE_SHA_VERIFIED_PRE_T4_MODELS_AND_OFFICIAL_RESULTS",
            "race_id": RID,
            "old_reference_sha256": EARLY_SHA,
            "selected_reference_sha256": LATE_SHA,
            "cutoff": race["benchmark_t4_cutoff_utc"],
            "models_in_original_freeze_history": len(hist),
            "winner": race["winner_selection_id"],
            "scores": race["score"],
            "triple_evaluable_after": result["counts"]["triple_evaluable"],
            "pit_certified_paired": 0, "bet_authority": False,
        }, indent=2, sort_keys=True) + "\n")
