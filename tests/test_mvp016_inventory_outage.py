"""MVP-016: a transient source outage cannot erase cumulative scorecard coverage.

These are contract tests and, in PR CI, exact SHA-256 verified GitHub originals.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.mvp016_inventory_guard import OUTAGE_REASON, guard, inventory_status

OUTAGE_SHA = "b14c61c979c656e49da382d574f3416293303e582b3b864b646df592282c4ac7"
HEALTHY_SHA = "ecb4477a0ec5fc9c954862943ab8b39876d7b13c6adf701bf4e777eaa9f9df33"
FALSE_ZERO_SHA = "be7604e5b9604aa5439769e716038ad863854588fb6340b8333b4f77392e4481"


def _manifest(*, outage: bool = True) -> dict:
    return {
        "schema": "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1",
        "bet_authority": False,
        "selected_artifacts": [],
        "missing_originals": [{"reason": OUTAGE_REASON}] if outage else [],
        **({} if outage else {"github_artifact_inventory_sha256": "a" * 64}),
    }


def test_outage_is_not_zero_races(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    out = tmp_path / "scorecard"
    assert guard(path, output_dir=out) is False
    result = json.loads((out / "source-unavailable.json").read_text())
    assert result["status"] == "BLOCKED_SOURCE"
    assert result["source_reason"] == OUTAGE_REASON
    assert result["scorecard_generated"] is False
    assert result["cumulative_physical_races"] is None
    assert result["paired_champion_core004"] is None
    assert result["triple_evaluable"] is None
    assert result["bet_authority"] is False
    assert result["pit_certified"] is False
    assert not (out / "index.json").exists()


def test_verified_cumulative_inventory_proceeds_without_shadow_output(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(outage=False)), encoding="utf-8")
    out = tmp_path / "scorecard"
    assert guard(path, output_dir=out) is True
    assert not out.exists()


@pytest.mark.parametrize("mutation", [
    {"schema": "UNKNOWN"},
    {"bet_authority": True},
    {"selected_artifacts": None},
    {"missing_originals": None},
    {"github_artifact_inventory_sha256": None},
])
def test_broken_or_unattributed_inventory_is_never_scored(tmp_path, mutation):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({**_manifest(outage=False), **mutation}))
    allowed, _ = inventory_status(json.loads(path.read_text()))
    assert allowed is False
    assert guard(path, output_dir=tmp_path / "no_score") is False
    assert not (tmp_path / "no_score/index.json").exists()


def test_missing_original_manifest_blocks_without_fabrication(tmp_path):
    assert guard(tmp_path / "missing.json", output_dir=tmp_path / "output") is False
    info = json.loads((tmp_path / "output/source-unavailable.json").read_text())
    assert info["source_reason"] == "DEV011_MANIFEST_ORIGINAL_UNVERIFIABLE"


def test_authentic_inventory_outage_and_prior_good_main_run(tmp_path):
    root_name = os.environ.get("MVP016_INVENTORY_OUTAGE_ORIGINAL_ROOT")
    if not root_name:
        pytest.skip("Exact GitHub originals are downloaded by PR CI only")
    root = Path(root_name)
    sources = {
        "outage": (root / "outage/manifest.json", OUTAGE_SHA),
        "good": (root / "healthy/manifest.json", HEALTHY_SHA),
        "false_zero": (root / "false_zero/index.json", FALSE_ZERO_SHA),
    }
    parsed = {}
    for name, (path, expected_sha) in sources.items():
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected_sha
        parsed[name] = json.loads(raw)
    assert parsed["false_zero"]["counts"]["physical_races"] == 0
    assert parsed["false_zero"]["counts"]["paired_champion_core004"] == 0
    assert parsed["false_zero"]["cumulative_original_inventory"]["missing_originals"] == [
        {"reason": OUTAGE_REASON}
    ]
    assert inventory_status(parsed["outage"]) == (False, OUTAGE_REASON)
    assert inventory_status(parsed["good"])[0] is True
    out = tmp_path / "new-run"
    assert guard(sources["outage"][0], output_dir=out) is False
    report = json.loads((out / "source-unavailable.json").read_text())
    assert report["cumulative_physical_races"] is None
    assert report["scorecard_generated"] is False
    assert not (out / "index.json").exists()
