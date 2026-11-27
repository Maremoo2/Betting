"""Private read credentials must stay outside replay/tests and public artifacts."""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def workflow_steps():
    return re.split(r"(?=^      - )", (ROOT / ".github/workflows/ci.yml").read_text(), flags=re.MULTILINE)


def test_only_reviewed_first_party_fetch_step_receives_private_secret():
    steps = workflow_steps()
    secret_steps = [s for s in steps if "RESEARCH_ARCHIVE_READ_TOKEN:" in s]
    assert len(secret_steps) == 2  # Producer and independent retained-source reader.
    for step in secret_steps:
        assert "github.event.pull_request.head.repo.full_name == 'Maremoo2/Betting'" in step
        assert "github.event.pull_request.user.login == 'Maremoo2'" in step
        assert "python -I -S scripts/ci_originals.py fetch" in step
        assert "pytest" not in step
        for path in ("scripts/ci_originals.py", "src/hbi/ci_originals.py", "docs/CI_HISTORICAL_SOURCES.json"):
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() in step
    step = secret_steps[0]
    assert "python -I -S scripts/mvp016_source_recovery.py" in step
    for path in ("scripts/mvp016_source_recovery.py", "docs/MVP016_SOURCE_ARCHIVE.json"):
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() in step
    replay = next(s for s in steps if "id: mvp016_original" in s)
    assert "RESEARCH_ARCHIVE_READ_TOKEN" not in replay
    assert steps.index(step) < steps.index(replay)


def test_public_mvp016_artifact_contains_only_explicit_replay_report():
    steps = workflow_steps()
    upload = next(s for s in steps if "name: Upload MVP-016 original empty cohort replay (NO BET)" in s)
    paths = re.findall(r"^          path: (.*)$", upload, re.MULTILINE)
    assert paths == ["${{ runner.temp }}/mvp016-empty/mvp016-empty-original-replay.json"]
    assert "permissions:\n  contents: read\n" in steps[0]


def test_separate_readback_pins_this_attempts_upload_not_reused_name():
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "replay_v2_artifact_id: ${{ steps.replay_v2_publish.outputs.artifact-id }}" in text
    publish = next(s for s in workflow_steps() if "name: Publish V2 SQLite and receipt" in s)
    assert "id: replay_v2_publish" in publish
    job = text.split("  replay-v2-independent-readback:", 1)[1]
    assert 'run: test -n "$REPLAY_ARTIFACT_ID"' in job
    assert "artifact-ids: ${{ needs.test.outputs.replay_v2_artifact_id }}" in job
    assert "name: core003-authentic-replay-v2-readback-" not in job


def test_historical_ci_has_no_expiring_source_calls_or_raw_sqlite_upload():
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "gh run download" not in text
    assert "/actions/artifacts/" not in text
    assert "path: ${{ runner.temp }}/core003-v2-output/" not in text
    assert "path: ${{ runner.temp }}/core003-v2-encrypted/" in text
    assert "ci_readback_transport open" in text
    assert "verify-cache" in text
