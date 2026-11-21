"""Tests for research-only pre-watch handoff; never a betting happy path."""
import json

import pytest

from hbi.prewatch_shadow_handoff import build_handoff, write_once_and_readback

HASH = "a" * 64
DECISION = "2026-11-21T10:00:00+00:00"


def source(**kwargs):
    report = {
        "race_id": "RIKSTOTO:TEST:1",
        "source_imported_to_sqlite": True,
        "model_input_approved": False,
        "independent_identity_attested": False,
        "runners": [
            {"start_number": 1, "scratched": False},
            {"start_number": 2, "scratched": False},
        ],
        "model_input_sources": {
            "collector_starts_sha256": HASH,
            "collector_program_pdf_sha256": HASH,
            "collector_manifest_sha256": HASH,
        },
        "blockers": ["IDENTITY_CROSS_PROVIDER_NOT_ATTESTED"],
    }
    report.update(kwargs)
    return report


def handoff(src, **kwargs):
    return build_handoff(src, decision_time=DECISION, **kwargs)


def test_source_readiness_does_not_promote_identity_or_model():
    report = handoff(source())
    assert report["source_status"] == "SOURCE_READY"
    assert report["model_calibration_verified"] is False
    assert report["probabilities"] is None
    assert report["expected_value"] is None
    assert report["bet_authorized"] is False


def test_missing_import_blocks_source():
    assert handoff(source(source_imported_to_sqlite=False))["source_status"] == "DATA_BLOCKED"


def test_even_asserted_model_and_win_need_existing_betting_v33():
    report = handoff(
        source(model_input_approved=True, independent_identity_attested=True),
        model_run={
            "status": "READY",
            "shadow_eligible": True,
            "calibration_verified": True,
            "model_version": "test",
        },
        win_snapshot={
            "observed_at": "2026-11-21T09:59:00+00:00",
            "race_id": "RIKSTOTO:TEST:1",
            "source_verified": True,
            "full_field_verified": True,
            "odds": {"1": 2.5, "2": 3.5},
        },
    )
    assert report["shadow_status"] == "NEEDS_EXISTING_V33_REVIEW"
    assert report["bet_authorized"] is False
    assert report["expected_value"] is None


def test_future_market_not_used():
    report = handoff(
        source(),
        win_snapshot={
            "observed_at": "2026-11-21T10:01:00+00:00",
            "odds": {"1": 2.5, "2": 3.5},
        },
    )
    assert report["market_status"] == "MARKET_PENDING"


def test_partial_market_not_usable():
    report = handoff(
        source(),
        win_snapshot={
            "observed_at": "2026-11-21T09:59:00+00:00",
            "race_id": "RIKSTOTO:TEST:1",
            "source_verified": True,
            "full_field_verified": True,
            "odds": {"1": 2.5},
        },
    )
    assert report["market_status"] == "MARKET_PENDING"


def test_duplicate_selection_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_START_NUMBER"):
        handoff(source(runners=[{"start_number": 1, "scratched": False}] * 2))


def test_naive_decision_time_rejected():
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        build_handoff(source(), decision_time="2026-11-21T10:00:00")


def test_append_only_with_readback(tmp_path):
    path = tmp_path / "shadow.json"
    report = handoff(source())
    digest = write_once_and_readback(report, path)
    assert len(digest) == 64
    assert json.loads(path.read_text()) == report
    with pytest.raises(FileExistsError):
        write_once_and_readback(report, path)


def test_cli_consumes_original_collector_import_report(tmp_path, monkeypatch):
    import sys
    from hbi.prewatch_shadow_handoff import main

    report_path = tmp_path / "collector.json"
    output_path = tmp_path / "prewatch.json"
    report_path.write_text(json.dumps({"records": [source()]}))
    monkeypatch.setattr(
        sys, "argv",
        [
            "shadow", "--collector-report", str(report_path),
            "--decision-time", DECISION, "--out", str(output_path),
        ],
    )
    main()
    result = json.loads(output_path.read_text())
    assert len(result["races"]) == 1
    assert result["races"][0]["source_status"] == "SOURCE_READY"
    assert result["bet_authorized"] is False
