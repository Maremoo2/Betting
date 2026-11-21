import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'ci_retry', Path(__file__).parents[1] / 'scripts/github_retry.py'
)
retry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry)


def test_partial_binary_failure_not_written_before_success(capfdbinary):
    results = iter([
        subprocess.CompletedProcess([], 1, b'corrupt partial', b'HTTP 403 rate limit'),
        subprocess.CompletedProcess([], 0, b'original zip', b''),
    ])
    waits = []
    assert retry.run(['api', 'repos/example/actions/artifacts/1/zip'],
                     execute=lambda *a, **k: next(results), sleep=waits.append) == 0
    assert capfdbinary.readouterr().out == b'original zip'
    assert waits == [1]


@pytest.mark.parametrize('error,retries', [
    (b'HTTP 403 forbidden', 1), (b'no artifact matches', 1),
    (b'HTTP 404 not found', 1), (b'HTTP 503 unavailable', 4),
    (b'HTTP 403 API rate limit exceeded', 4),
])
def test_missing_or_persistently_unavailable_source_remains_failure(error, retries):
    calls = []

    def execute(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess([], 1, b'', error)

    assert retry.run(['run', 'download', '1'], execute=execute, sleep=lambda _: None) == 1
    assert len(calls) == retries


@pytest.mark.parametrize('args', [['run', 'rerun', '1'], ['api', '/x', '-X', 'POST']])
def test_write_commands_rejected(args):
    with pytest.raises(ValueError, match='READ_ONLY'):
        retry.run(args)
