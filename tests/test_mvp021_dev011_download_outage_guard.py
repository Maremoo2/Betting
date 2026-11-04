"""P0: API 403 after successful pagination must NOT publish a partial benchmark."""
from __future__ import annotations

import hashlib
import json

import pytest

from hbi.mvp016_inventory_guard import guard, inventory_status


def manifest():
    return {
        "schema": "DEV011_CUMULATIVE_COVERAGE_MANIFEST_V1",
        "bet_authority": False,
        "github_artifact_inventory_sha256": "a" * 64,
        "missing_originals": [],
        "selected_artifacts": [
            {
                "source_run_id": 41880220139,
                "artifact_id": 13350305285,
                "name": "dev009-outcome-scorecards-41880220139",
                "kind": "result", "expired": False,
            },
            {
                "source_run_id": 41891430902,
                "artifact_id": 13353557656,
                "name": "bet-mvp-shadow-41891430902",
                "kind": "model", "expired": False,
            },
        ],
    }


def _stored(tmp_path, doc=None):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest() if doc is None else doc), encoding="utf-8")
    return path


def test_all_downloaded_allows_existing_scorecard_contract(tmp_path):
    original = _stored(tmp_path)
    failures = tmp_path / "download-failures.tsv"
    failures.write_bytes(b"")
    output = tmp_path / "scorecard"
    assert guard(original, output_dir=output, failed_downloads=failures)
    assert not output.exists()


def test_failed_original_download_is_explicitly_blocked_not_zero_scorecard(tmp_path):
    original = _stored(tmp_path)
    failures = tmp_path / "download-failures.tsv"
    raw = (
        b"41880220139\tdev009-outcome-scorecards-41880220139\tresult\n"
        b"41891430902\tbet-mvp-shadow-41891430902\tmodel\n"
    )
    failures.write_bytes(raw)
    output = tmp_path / "scorecard"
    assert not guard(original, output_dir=output, failed_downloads=failures)
    assert sorted(p.name for p in output.iterdir()) == ["source-unavailable.json"]
    report = json.loads((output / "source-unavailable.json").read_text())
    assert report["status"] == "BLOCKED_SOURCE"
    assert report["source_reason"] == "ORIGINAL_ARTIFACT_DOWNLOAD_UNAVAILABLE"
    assert report["failed_downloads_count"] == 2
    assert report["failed_downloads_receipt_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["prior_verified_scorecard_invalidated"] is False
    assert report["scorecard_generated"] is False
    assert report["cumulative_physical_races"] is None
    assert report["paired_champion_core004"] is None
    assert report["triple_evaluable"] is None
    assert report["pit_certified"] is False and report["bet_authority"] is False


@pytest.mark.parametrize("raw", [
    b"41880220139\twrong-name\tresult\n",
    b"41880220139\tdev009-outcome-scorecards-41880220139\tmodel\n",
    b"41880220139\tdev009-outcome-scorecards-41880220139\tresult\n"
    b"41880220139\tdev009-outcome-scorecards-41880220139\tresult\n",
    b"garbage",
    b"\xff\xfe",
])
def test_invalid_failed_download_receipt_blocks_source(tmp_path, raw):
    original = _stored(tmp_path)
    failures = tmp_path / "download-failures.tsv"
    failures.write_bytes(raw)
    output = tmp_path / "scorecard"
    assert not guard(original, output_dir=output, failed_downloads=failures)
    report = json.loads((output / "source-unavailable.json").read_text())
    assert report["source_reason"] == "DEV011_DOWNLOAD_FAILURE_RECEIPT_INVALID"
    assert report["bet_authority"] is False
    assert not (output / "index.json").exists()


def test_missing_failure_receipt_is_fail_closed(tmp_path):
    original = _stored(tmp_path)
    output = tmp_path / "scorecard"
    assert not guard(
        original, output_dir=output,
        failed_downloads=tmp_path / "missing.tsv",
    )
    report = json.loads((output / "source-unavailable.json").read_text())
    assert report["source_reason"] == "DEV011_DOWNLOAD_FAILURE_RECEIPT_MISSING"


def test_known_historical_legacy_missing_does_not_become_download_outage(tmp_path):
    doc = manifest()
    doc["missing_originals"] = [{
        "artifact_id": 13350305285, "kind": "result",
        "reason": "MISSING_OR_UNVERIFIABLE_ORIGINAL",
    }]
    original = _stored(tmp_path, doc)
    failures = tmp_path / "download-failures.tsv"
    failures.write_bytes(b"")
    assert inventory_status(doc)[0] is True
    assert guard(original, output_dir=tmp_path / "scorecard", failed_downloads=failures)


def test_existing_paginated_inventory_outage_stays_blocked(tmp_path):
    doc = manifest()
    doc["missing_originals"] = [{"reason": "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"}]
    original = _stored(tmp_path, doc)
    failures = tmp_path / "download-failures.tsv"
    failures.write_bytes(b"")
    assert not guard(original, output_dir=tmp_path / "scorecard", failed_downloads=failures)
    report = json.loads((tmp_path / "scorecard/source-unavailable.json").read_text())
    assert report["source_reason"] == "PAGINATED_GITHUB_INVENTORY_UNAVAILABLE"


def test_real_41898656060_manifest_contract_if_downloaded(tmp_path, monkeypatch):
    """Pin a genuine previous 403 source manifest; optional standalone replay."""
    import os
    from pathlib import Path

    root = os.environ.get("MVP021_ORIGINAL_COVERAGE_ROOT")
    if not root:
        pytest.skip("Set MVP021_ORIGINAL_COVERAGE_ROOT to downloaded original artifacts")
    archived = Path(root) / "41898656060" / "manifest.json"
    raw = archived.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "2f8f0341808be0e5f19346f0a24b33126714152b6ae5bf3cf671c3bf83fbe63b"
    )
    doc = json.loads(raw)
    assert doc["github_artifacts_enumerated"] == 4234
    assert doc["github_pages_enumerated"] == 43
    assert doc["recovered_artifacts"] == 112
    assert doc["pinned_result_races_checked"] == 0
    original = _stored(tmp_path, doc)
    failures = tmp_path / "download-failures.tsv"
    failures.write_text(
        "41880220139\tdev009-outcome-scorecards-41880220139\tresult\n",
        encoding="utf-8",
    )
    output = tmp_path / "scorecard"
    assert not guard(original, output_dir=output, failed_downloads=failures)
    assert json.loads((output / "source-unavailable.json").read_text())[
        "source_reason"
    ] == "ORIGINAL_ARTIFACT_DOWNLOAD_UNAVAILABLE"
