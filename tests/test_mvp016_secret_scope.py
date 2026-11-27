"""Private read credentials must stay outside replay/tests and public artifacts."""
import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_only_reviewed_first_party_fetch_step_receives_private_secret():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    secret_steps = [s for s in steps if "RESEARCH_ARCHIVE_READ_TOKEN" in s.get("env", {})]
    assert len(secret_steps) == 1
    step = secret_steps[0]
    assert "github.event.pull_request.head.repo.full_name == 'Maremoo2/Betting'" in step["if"]
    assert "github.event.pull_request.user.login == 'Maremoo2'" in step["if"]
    assert "python -I -S scripts/mvp016_source_recovery.py" in step["run"]
    assert "pytest" not in step["run"]
    for path in ("scripts/mvp016_source_recovery.py", "docs/MVP016_SOURCE_ARCHIVE.json"):
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() in step["run"]
    replay = next(s for s in steps if s.get("id") == "mvp016_original")
    assert "RESEARCH_ARCHIVE_READ_TOKEN" not in replay.get("env", {})
    assert steps.index(step) < steps.index(replay)


def test_public_mvp016_artifact_contains_only_explicit_replay_report():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    upload = next(s for s in steps if s.get("name") == "Upload MVP-016 original empty cohort replay (NO BET)")
    assert upload["with"]["path"] == "${{ runner.temp }}/mvp016-empty/mvp016-empty-original-replay.json"
    assert "*" not in upload["with"]["path"]
    assert workflow["permissions"]["contents"] == "read"
