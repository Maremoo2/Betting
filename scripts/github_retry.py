"""Bounded retry for read-only CI artifact operations; never hide missing originals."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath


def transient(stderr: bytes) -> bool:
    message = stderr.decode('utf-8', errors='replace').lower()
    return any(text in message for text in (
        'rate limit', 'http 429', 'http 500', 'http 502', 'http 503',
        'http 504', 'connection reset', 'tls handshake timeout',
        'temporary failure in name resolution',
    ))


def request(args: list[str], *, execute=subprocess.run, sleep=time.sleep):
    """Return only complete successful bytes; never cache a partial response."""
    for attempt in range(4):
        try:
            result = execute(['gh', *args], capture_output=True, check=False, timeout=180)
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(args, 1, b'', b'HTTP 504 artifact timeout')
        if result.returncode == 0:
            return result
        if not transient(result.stderr) or attempt == 3:
            return result
        sys.stderr.write(f'CI_SOURCE_TRANSIENT_RETRY attempt={attempt + 1}/3\n')
        sleep(2 ** attempt)
    raise AssertionError('unreachable')


def cached_download(args: list[str], cache: Path, *, execute=subprocess.run,
                    sleep=time.sleep) -> int:
    """One run inventory and one ZIP download per immutable artifact per CI job."""
    run_id = int(args[2])
    repo = args[args.index('--repo') + 1]
    name = args[args.index('--name') + 1]
    destination = Path(args[args.index('--dir') + 1])
    if run_id <= 0 or len(repo.split('/')) != 2 or any(c in repo for c in '.\\'):
        raise ValueError('CI_ARTIFACT_REFERENCE_INVALID')
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f'{repo}:{run_id}'.encode()).hexdigest()
    inventory = cache / (key + '.json')
    if not inventory.exists():
        result = request(['api', f'repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100'],
                         execute=execute, sleep=sleep)
        if result.returncode:
            sys.stderr.buffer.write(result.stderr)
            return result.returncode
        doc = json.loads(result.stdout)
        # Fail explicitly rather than silently losing a paginated artifact.
        if doc.get('total_count', 0) > 100:
            raise ValueError('CI_ARTIFACT_INVENTORY_PAGINATION_REQUIRED')
        inventory.write_bytes(result.stdout)
    doc = json.loads(inventory.read_bytes())
    matches = [a for a in doc['artifacts'] if a['name'] == name]
    if len(matches) != 1 or matches[0].get('expired') is not False:
        raise ValueError('CI_ORIGINAL_SOURCE_MISSING_EXPIRED_OR_AMBIGUOUS')
    artifact = matches[0]
    aid = artifact['id']
    if type(aid) is not int or aid <= 0:
        raise ValueError('CI_ARTIFACT_REFERENCE_INVALID')
    if artifact.get('workflow_run', {}).get('id', run_id) != run_id:
        raise ValueError('CI_ARTIFACT_SOURCE_RUN_CONFLICT')
    target = cache / f'{aid}.zip'
    receipt = cache / f'{aid}.receipt.json'
    cache_hit = target.exists()
    if not target.exists():
        result = request(['api', f'repos/{repo}/actions/artifacts/{aid}/zip'],
                         execute=execute, sleep=sleep)
        if result.returncode:
            sys.stderr.buffer.write(result.stderr)
            return result.returncode
        digest = hashlib.sha256(result.stdout).hexdigest()
        expected = artifact.get('digest')
        if expected and expected != 'sha256:' + digest:
            raise ValueError('CI_ORIGINAL_INTEGRITY_SHA_MISMATCH')
        target.write_bytes(result.stdout)
        receipt.write_text(json.dumps({'repo': repo, 'run_id': run_id, 'artifact_id': aid,
                                       'sha256': digest, 'github_digest': expected}),
                           encoding='utf-8')
    proof = json.loads(receipt.read_bytes())
    raw = target.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if (proof['repo'] != repo or proof['run_id'] != run_id or proof['artifact_id'] != aid
            or proof['sha256'] != digest
            or (artifact.get('digest') and artifact['digest'] != 'sha256:' + digest)):
        raise ValueError('CI_CACHED_ORIGINAL_INTEGRITY_CONFLICT')
    with zipfile.ZipFile(target) as archive:
        seen = set()
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or ':' in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000
                    or item.filename.casefold() in seen):
                raise ValueError('CI_ORIGINAL_ZIP_UNSAFE_PATH')
            seen.add(item.filename.casefold())
            if item.is_dir():
                continue
            out = destination.joinpath(*path.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.is_symlink() or any(p.is_symlink() for p in out.parents):
                raise ValueError('CI_ORIGINAL_DESTINATION_SYMLINK')
            data = archive.read(item)
            if out.exists():
                if out.read_bytes() != data:
                    raise ValueError('CI_ORIGINAL_DESTINATION_CONFLICT')
            else:
                with out.open('xb') as handle:
                    handle.write(data)
            if out.read_bytes() != data:
                raise ValueError('CI_ORIGINAL_EXTRACTION_READBACK_CONFLICT')
    sys.stderr.write(f'CI_ORIGINAL_VERIFIED artifact={aid} run={run_id} '
                     f'cache_hit={cache_hit} sha256={digest}\n')
    return 0


def run(args: list[str], *, execute=subprocess.run, sleep=time.sleep) -> int:
    if not (args[:1] == ['api'] or args[:2] == ['run', 'download']):
        raise ValueError('CI_ARTIFACT_READ_ONLY_COMMAND_REQUIRED')
    if any(flag in args for flag in ('--method', '-X', '--field', '--raw-field', '-f', '-F', '--input')):
        raise ValueError('CI_ARTIFACT_READ_ONLY_COMMAND_REQUIRED')
    if (os.environ.get('RUNNER_TEMP') and args[:2] == ['run', 'download']
            and all(flag in args for flag in ('--repo', '--name', '--dir'))):
        try:
            return cached_download(args, Path(os.environ['RUNNER_TEMP']) / 'ci-original-cache',
                                   execute=execute, sleep=sleep)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
            sys.stderr.write(f'CI_ORIGINAL_SOURCE_OR_INTEGRITY_FAILURE:{exc}\n')
            return 1
    result = request(args, execute=execute, sleep=sleep)
    if result.returncode == 0:
        sys.stdout.buffer.write(result.stdout)
    else:
        sys.stderr.buffer.write(result.stderr)
        sys.stderr.write('\nCI_ORIGINAL_SOURCE_UNAVAILABLE: not a replay PASS\n')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1:]))
