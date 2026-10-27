"""Regression tests for immutable-PR protected strategy file classification.

Runs the *exact bash body* from the GitHub Actions workflow in throwaway local
Git histories. These tests never alter protected production strategy code.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

WORKFLOW = (
    Path(__file__).parents[1] / ".github/workflows/protected-strategy-files.yml"
)


def _script() -> str:
    content = WORKFLOW.read_text(encoding="utf-8")
    section = content.split("      - name: Detect protected strategy changes\n", 1)[1]
    section = section.split("      - name: Require explicit strategy approval\n", 1)[0]
    return textwrap.dedent(section.split("        run: |\n", 1)[1])


def _git(root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return process.stdout.strip()


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture()
def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.test")
    _write(
        root, ".github/workflows/protected-strategy-files.yml",
        "protected strategy checks present at base\n",
    )
    _write(root, "src/betting/engine.py", "base\n")
    _write(root, "README.md", "initial\n")
    base = _commit(root, "base")
    _git(root, "checkout", "-b", "feature")
    return root, base


def _run(root: Path, base: str, head: str, tmp_path: Path):
    output = tmp_path / "step-output"
    env = {
        **os.environ,
        "BASE_SHA": base,
        "HEAD_SHA": head,
        "GITHUB_OUTPUT": str(output),
    }
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _script()],
        cwd=root, env=env, capture_output=True, text=True, check=False,
    )
    return result, output.read_text(encoding="utf-8") if output.exists() else ""


def test_unprotected_research_change_does_not_need_strategy_approval(
    repository, tmp_path
):
    root, base = repository
    _write(root, "docs/DATA004E_DOUBLE_READ.md", "research\n")
    head = _commit(root, "research-only")
    completed, status = _run(root, base, head, tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "protected_changed=false" in status
    assert "bootstrap=false" in status


def test_protected_engine_change_still_requires_explicit_approval(
    repository, tmp_path
):
    root, base = repository
    _write(root, "src/betting/engine.py", "unapproved changed strategy\n")
    head = _commit(root, "change a protected file")
    completed, status = _run(root, base, head, tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "protected_changed=true" in status
    assert "bootstrap=false" in status
    assert "strategy-change-approved" in WORKFLOW.read_text(encoding="utf-8")


def test_rename_does_not_hide_deletion_of_protected_source(
    repository, tmp_path
):
    root, base = repository
    _git(root, "mv", "src/betting/engine.py", "docs/renamed_engine.py")
    head = _commit(root, "move protected strategy to unprotected path")
    completed, status = _run(root, base, head, tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "protected_changed=true" in status
    assert "src/betting/engine.py" in completed.stdout


def test_advanced_main_does_not_change_frozen_pr_comparison(
    repository, tmp_path
):
    root, base = repository
    _write(root, "docs/frozen.txt", "feature\n")
    head = _commit(root, "research PR")
    _git(root, "checkout", "main")
    _write(root, "src/betting/engine.py", "another PR merged into main\n")
    _commit(root, "main advances after PR review")
    _git(root, "checkout", "feature")
    completed, status = _run(root, base, head, tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "protected_changed=false" in status


def test_missing_commit_fails_closed(repository, tmp_path):
    root, base = repository
    _write(root, "docs/research.txt", "source\n")
    head = _commit(root, "research")
    completed, status = _run(root, "0" * 40, head, tmp_path)
    assert completed.returncode != 0
    assert "Missing immutable PR" in completed.stdout
    assert "protected_changed=false" not in status
    assert base != head


def test_unrelated_commit_histories_fail_closed(repository, tmp_path):
    root, base = repository
    _git(root, "checkout", "--orphan", "unrelated")
    _git(root, "rm", "-rf", ".")
    _write(root, "docs/unrelated.txt", "separate root\n")
    head = _commit(root, "unrelated source")
    completed, status = _run(root, base, head, tmp_path)
    assert completed.returncode != 0
    assert "No merge base" in completed.stdout
    assert "protected_changed=false" not in status


def test_partial_history_is_not_silently_accepted(repository, tmp_path):
    root, base = repository
    _write(root, "docs/research.txt", "source\n")
    head = _commit(root, "research")
    # Convert the fixture into a deliberately shallow repository.
    (root / ".git/shallow").write_text(head + "\n", encoding="utf-8")
    completed, status = _run(root, base, head, tmp_path)
    assert completed.returncode != 0
    assert "needs complete Git history" in completed.stdout
    assert "protected_changed=false" not in status
