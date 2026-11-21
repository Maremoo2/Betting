import hashlib
import importlib.util
import io
import json
import subprocess
import zipfile
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


def fixture_download(tmp_path, *, tamper=False, filename='source.json'):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr(filename, b'{"original":true}')
    raw = buffer.getvalue()
    inventory = {'total_count': 1, 'artifacts': [{
        'id': 123, 'name': 'original', 'expired': False,
        'workflow_run': {'id': 55},
        'digest': 'sha256:' + ('0' * 64 if tamper else hashlib.sha256(raw).hexdigest()),
    }]}
    calls = []

    def execute(args, **kwargs):
        calls.append(args)
        data = raw if args[-1].endswith('/zip') else json.dumps(inventory).encode()
        return subprocess.CompletedProcess(args, 0, data, b'')

    args = ['run', 'download', '55', '--repo', 'owner/repo', '--name', 'original',
            '--dir', str(tmp_path / 'one')]
    return args, execute, calls


def test_download_once_reuse_checks_bytes_for_different_steps(tmp_path):
    args, execute, calls = fixture_download(tmp_path)
    cache = tmp_path / 'cache'
    assert retry.cached_download(args, cache, execute=execute) == 0
    args[-1] = str(tmp_path / 'two')
    assert retry.cached_download(args, cache, execute=execute) == 0
    assert len(calls) == 2  # One inventory and one ZIP, rather than four API requests.
    assert (tmp_path / 'one/source.json').read_bytes() == (tmp_path / 'two/source.json').read_bytes()
    (cache / '123.zip').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='INTEGRITY'):
        retry.cached_download(args, cache, execute=execute)
    assert len(calls) == 2  # Corruption cannot be hidden by a fresh download.


@pytest.mark.parametrize('tamper,filename,reason', [
    (True, 'source.json', 'SHA_MISMATCH'), (False, '../escape', 'UNSAFE_PATH'),
])
def test_invalid_original_not_extracted(tmp_path, tamper, filename, reason):
    args, execute, _ = fixture_download(tmp_path, tamper=tamper, filename=filename)
    with pytest.raises(ValueError, match=reason):
        retry.cached_download(args, tmp_path / 'cache', execute=execute)
    assert not (tmp_path / 'one/source.json').exists()


def test_existing_different_original_not_overwritten(tmp_path):
    args, execute, _ = fixture_download(tmp_path)
    target = tmp_path / 'one/source.json'
    target.parent.mkdir()
    target.write_bytes(b'another original')
    with pytest.raises(ValueError, match='DESTINATION_CONFLICT'):
        retry.cached_download(args, tmp_path / 'cache', execute=execute)
    assert target.read_bytes() == b'another original'
