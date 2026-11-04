"""MVP-017: source-backed health never substitutes a false 0/0/0 benchmark."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp017_research_health import classify_snapshot, summarize

EARLY_SHA = "62b0d78ca75847d2f2bfe895af240e45eada96a7719aefe4f880c1da02cbe178"
EARLY_MANIFEST_SHA = "ecb4477a0ec5fc9c954862943ab8b39876d7b13c6adf701bf4e777eaa9f9df33"
OUTAGE_SHA = "be7604e5b9604aa5439769e716038ad863854588fb6340b8333b4f77392e4481"
OUTAGE_MANIFEST_SHA = "b14c61c979c656e49da382d574f3416293303e582b3b864b646df592282c4ac7"
RECENT_SHA = "8a8012777ac49256e95aab9f3f5e2555a938cb8117826d6f47ddb5410f2343e5"
RECENT_MANIFEST_SHA = "657b6f177e540c53f293f0beadb1ea0811130c544bf1f8a3cc185bf1ca831e94"
V1_SHA = "9ecf547e1792522b15865163bff765c2a87ce90d5220496a7f9f46be369861a6"


def _json(path: Path, value: dict) -> str:
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _good(tmp_path: Path, run: int = 10) -> dict:
    folder = tmp_path / str(run)
    folder.mkdir()
    manifest = folder / "manifest.json"
    scorecard = folder / "index.json"
    source_sha = _json(manifest, {
        "schema": "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1",
        "bet_authority": False,
        "coverage_complete": False,
        "github_artifact_inventory_sha256": "c" * 64,
        "missing_originals": [{"reason": "UNINDEXED_LEGACY_MODEL_ORIGINAL"}],
    })
    score_sha = _json(scorecard, {
        "schema": "DEV009_PROSPECTIVE_OUTCOME_SCORECARD_V1",
        "model_originals_verified_by_sha": True, "bet_authority": False,
        "cumulative_original_inventory": {
            "github_artifact_inventory_sha256": "c" * 64,
        },
        "counts": {
            "physical_races": 1, "paired_champion_core004": 1,
            "triple_evaluable": 1, "model_pair_only": 0,
            "pit_certified_paired": 0,
        },
        "records": [{
            "race_id": "RIKSTOTO:S1_NR_2026-11-03:1",
            "status": "EVALUABLE_RESEARCH_ONLY",
            "benchmark_status": "TRIPLE_EVALUABLE",
            "bet_authority": False,
        }],
    })
    return {
        "run_id": run, "github_head_sha": "d" * 64,
        "scorecard_path": str(scorecard), "scorecard_sha256": score_sha,
        "coverage_manifest_path": str(manifest),
        "coverage_manifest_sha256": source_sha,
    }


def _outage(tmp_path: Path, run: int = 11, *, false_zero: bool = False) -> dict:
    folder = tmp_path / str(run)
    folder.mkdir()
    manifest = folder / "manifest.json"
    scorecard = folder / "index.json"
    ms = _json(manifest, {
        "schema": "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1",
        "bet_authority": False,
        "missing_originals": [{"reason": "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"}],
    })
    if false_zero:
        ss = _json(scorecard, {"counts": {"physical_races": 0}})
    else:
        ss = "f" * 64
    return {
        "run_id": run, "github_head_sha": "d" * 64,
        "scorecard_path": str(scorecard), "scorecard_sha256": ss,
        "coverage_manifest_path": str(manifest), "coverage_manifest_sha256": ms,
    }


def test_latest_good_is_current_even_when_original_coverage_incomplete(tmp_path):
    now = _good(tmp_path)
    output = summarize([now])
    assert output["status"] == output["latest_supplied_run_status"] == "CURRENT_VALID"
    assert output["last_verified_counts"]["physical_races"] == 1
    assert output["last_verified_original_coverage_complete"] is False
    assert output["bet_authority"] is False
    assert output["run_metadata_independently_authenticated"] is False


def test_last_valid_survives_real_source_outage_without_0_0_0(tmp_path):
    good = _good(tmp_path, run=10)
    bad = _outage(tmp_path, run=11)
    out = summarize([bad, good])
    assert out["status"] == "LAST_KNOWN_VALID"
    assert out["latest_supplied_run_status"] == "SOURCE_UNAVAILABLE"
    assert out["latest_supplied_run_id"] == 11
    assert out["last_verified_run_id"] == 10
    assert out["last_verified_counts"]["physical_races"] == 1
    assert out["supplied_snapshots"][0]["counts"] is None


def test_false_zero_is_inconsistent_and_not_current(tmp_path):
    good = _good(tmp_path, run=10)
    bad = _outage(tmp_path, run=11, false_zero=True)
    out = summarize([bad, good])
    assert out["status"] == "LAST_KNOWN_VALID"
    assert out["latest_supplied_run_status"] == "INCONSISTENT"
    assert out["latest_source_reason"] == "FALSE_ZERO_SCORECARD_FROM_SOURCE_OUTAGE"
    assert out["last_verified_counts"]["physical_races"] == 1
    assert out["supplied_snapshots"][0]["counts"] is None


def test_no_verified_history_is_not_evaluated_or_source_unavailable(tmp_path):
    assert summarize([])["status"] == "NOT_EVALUATED"
    only_bad = summarize([_outage(tmp_path)])
    assert only_bad["status"] == "SOURCE_UNAVAILABLE"
    assert only_bad["last_verified_counts"] is None
    assert only_bad["bet_authority"] is False


def test_conflicting_original_inventory_cannot_be_current(tmp_path):
    good = _good(tmp_path, run=10)
    malformed = _good(tmp_path, run=11)
    score = Path(malformed["scorecard_path"])
    doc = json.loads(score.read_text())
    doc["cumulative_original_inventory"]["github_artifact_inventory_sha256"] = "e" * 64
    malformed["scorecard_sha256"] = _json(score, doc)
    out = summarize([good, malformed])
    assert out["status"] == "LAST_KNOWN_VALID"
    assert out["latest_source_reason"] == "SCORECARD_AND_INVENTORY_SOURCE_CONFLICT"


def test_duplicate_runs_or_bad_metadata_refused(tmp_path):
    good = _good(tmp_path)
    with pytest.raises(ValueError, match="DUPLICATE_GITHUB_RUN"):
        summarize([good, good])
    with pytest.raises(ValueError, match="SOURCE_RUN_OR_HEAD_SHA_INVALID"):
        classify_snapshot({**good, "github_head_sha": "a"})


def test_genuine_git_healthy_outage_recent_and_v1_originals():
    folder = os.environ.get("MVP017_RESEARCH_HEALTH_ORIGINAL_ROOT")
    if not folder:
        pytest.skip("Exact SHA-backed GitHub originals only in PR CI")
    root = Path(folder)
    source = [
        (41814068321, "early", EARLY_SHA, EARLY_MANIFEST_SHA),
        (41817026855, "outage", OUTAGE_SHA, OUTAGE_MANIFEST_SHA),
        (41820503559, "recent", RECENT_SHA, RECENT_MANIFEST_SHA),
    ]
    snapshots = []
    for run, name, score_sha, manifest_sha in source:
        path = root / name
        assert hashlib.sha256((path / "index.json").read_bytes()).hexdigest() == score_sha
        assert hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest() == manifest_sha
        snapshots.append({
            "run_id": run, "github_head_sha": "d" * 64,
            "scorecard_path": str(path / "index.json"),
            "scorecard_sha256": score_sha,
            "coverage_manifest_path": str(path / "manifest.json"),
            "coverage_manifest_sha256": manifest_sha,
        })
    v1 = root / "v1/research-v1/v1-system-audit.json"
    assert hashlib.sha256(v1.read_bytes()).hexdigest() == V1_SHA
    current = summarize(snapshots, v1_audit_path=v1, v1_audit_sha256=V1_SHA)
    assert current["status"] == "CURRENT_VALID"
    assert current["last_verified_run_id"] == 41820503559
    assert current["last_verified_counts"]["physical_races"] == 64
    assert current["last_verified_counts"]["paired_champion_core004"] == 16
    assert current["last_verified_counts"]["triple_evaluable"] == 14
    assert current["last_verified_counts"]["pit_certified_paired"] == 0
    assert current["v1_system_audit"]["runtime_replay_parity"] == "FAIL"
    assert current["v1_system_audit"]["settlement_integrity"] == "FAIL"
    fallback = summarize(snapshots[:2])
    assert fallback["status"] == "LAST_KNOWN_VALID"
    assert fallback["last_verified_run_id"] == 41814068321
    assert fallback["last_verified_counts"]["physical_races"] == 63
    assert fallback["latest_supplied_run_status"] == "INCONSISTENT"
    assert fallback["latest_source_reason"] == "FALSE_ZERO_SCORECARD_FROM_SOURCE_OUTAGE"
