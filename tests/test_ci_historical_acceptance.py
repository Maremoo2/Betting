"""Synthetic negative CI contracts, never replacement research evidence."""
import copy
import json

import pytest

from hbi import ci_originals as ci


@pytest.fixture
def sources(monkeypatch):
    doc = ci.catalog()
    monkeypatch.setattr(ci, "catalog", lambda: doc)
    monkeypatch.setattr(ci, "verify_cache", lambda: {"verified_count": 29})
    return doc


def skipped():
    return {g["key"]: "skipped" for g in ci.approved_loss()["groups"]}


def test_all_nine_exact_lost_groups_reported_without_research_pass(sources):
    result = ci.historical_status(skipped())
    assert len(result["groups"]) == 9
    assert all(r["status"] == "SOURCE_UNRECOVERABLE" for r in result["groups"])
    assert result["technical_status"] == "PASS_WITH_DOCUMENTED_SOURCE_DEBT"
    assert not result["all_research_evidence_verified"]


@pytest.mark.parametrize("fault", ["new_gap", "zip_hash", "member_hash", "removed", "extra", "corrupt_cache"])
def test_new_gaps_or_changed_originals_block_technical_acceptance(sources, monkeypatch, fault):
    retained = next(e for e in sources["sources"] if e["state"] == "VERIFIED_ORIGINAL")
    missing = next(e for e in sources["sources"] if e["state"] == "SOURCE_UNRECOVERABLE")
    if fault == "new_gap": retained["state"] = "SOURCE_UNRECOVERABLE"
    if fault == "zip_hash": missing["zip_sha256"] = "0" * 64
    if fault == "member_hash": missing["locked_members"] = {"manifest.json": "0" * 64}
    if fault == "removed": sources["sources"].remove(retained)
    if fault == "extra": sources["sources"].append({**retained, "artifact_id": 999})
    if fault == "corrupt_cache":
        def bad(): raise ValueError("CI_ORIGINAL_MEMBER_SHA_MISMATCH")
        monkeypatch.setattr(ci, "verify_cache", bad)
    result = ci.historical_status(skipped())
    assert result["technical_status"] == "FAIL_REGRESSION"
    assert len(result["groups"]) == 9
    assert all(g["status"] == "SYSTEM_ERROR" for g in result["groups"])


def test_available_historical_test_failure_is_not_a_source_exception(sources, monkeypatch):
    # Simulate one authentic old source being present under unchanged pins.
    for row in sources["sources"]: row["state"] = "VERIFIED_ORIGINAL"
    outcomes = {g["key"]: "success" for g in ci.approved_loss()["groups"]}
    assert ci.historical_status(outcomes)["historical_status"] == "PASS"
    for bad in ("failure", "cancelled", "skipped", ""):
        changed = dict(outcomes, hist01=bad)
        assert ci.historical_status(changed)["technical_status"] == "FAIL_REGRESSION"


def test_missing_or_fabricated_test_outcomes_block(sources):
    assert ci.historical_status({})["technical_status"] == "FAIL_REGRESSION"
    assert ci.historical_status(dict(skipped(), hist01="success"))["technical_status"] == "FAIL_REGRESSION"


def test_exception_file_cannot_be_changed(monkeypatch, tmp_path):
    path = tmp_path / "unapproved.json"
    path.write_text(json.dumps({"all_missing_are_allowed": True}))
    monkeypatch.setattr(ci, "APPROVED_LOSS", path)
    with pytest.raises(ValueError, match="APPROVAL_SHA_MISMATCH"):
        ci.approved_loss()


def needs():
    return {"test": {"result": "success"}, "replay-v2-independent-readback": {"result": "success"},
            "historical-research-evidence": {"result": "failure", "outputs": {
                "technical_status": "PASS_WITH_DOCUMENTED_SOURCE_DEBT"}}}


def test_explicit_source_debt_never_becomes_all_ci_pass():
    assert ci.technical_acceptance(needs())["all_ci_checks_pass"] is False


@pytest.mark.parametrize("job", ["test", "replay-v2-independent-readback", "historical-research-evidence"])
@pytest.mark.parametrize("status", ["cancelled", "skipped", "failure"])
def test_actual_failure_or_nonrun_jobs_block(job, status):
    n = copy.deepcopy(needs())
    n[job]["result"] = status
    if job == "historical-research-evidence": n[job]["outputs"]["technical_status"] = "FAIL_REGRESSION"
    with pytest.raises(ValueError): ci.technical_acceptance(n)


def test_unknown_history_output_cannot_hide_failure():
    n = needs()
    n["historical-research-evidence"]["outputs"] = {}
    with pytest.raises(ValueError): ci.technical_acceptance(n)


def test_final_verdict_checks_infrastructure_failures_after_status_upload():
    from pathlib import Path

    text = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()
    job = text.split("  historical-research-evidence:", 1)[1].split("  technical-acceptance:", 1)[0]
    assert "technical_status: ${{ steps.history_verdict.outputs.technical_status }}" in job
    assert job.index("Publish historical evidence status") < job.index("id: history_verdict")
    final = job.split("id: history_verdict", 1)[1]
    assert "PRIOR_JOB_STATUS: ${{ job.status }}" in final
    assert 'if [ "$PRIOR_JOB_STATUS" != success ]' in final
    assert "technical_status=FAIL_REGRESSION" in final


def test_main_and_bounded_dispatch_use_the_same_required_jobs():
    from pathlib import Path

    text = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()
    for job in ["replay-v2-independent-readback", "historical-research-evidence", "technical-acceptance"]:
        body = text.split("  " + job + ":", 1)[1].split("    steps:", 1)[0]
        assert "github.ref == 'refs/heads/main'" in body
        assert "github.event_name == 'workflow_dispatch'" in body
