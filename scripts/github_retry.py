"""Bounded retry for read-only CI artifact operations; never hide missing originals."""
from __future__ import annotations

import subprocess
import sys
import time


def transient(stderr: bytes) -> bool:
    message = stderr.decode('utf-8', errors='replace').lower()
    return any(text in message for text in (
        'rate limit', 'http 429', 'http 500', 'http 502', 'http 503',
        'http 504', 'connection reset', 'tls handshake timeout',
        'temporary failure in name resolution',
    ))


def run(args: list[str], *, execute=subprocess.run, sleep=time.sleep) -> int:
    if not (args[:1] == ['api'] or args[:2] == ['run', 'download']):
        raise ValueError('CI_ARTIFACT_READ_ONLY_COMMAND_REQUIRED')
    if any(flag in args for flag in ('--method', '-X', '--field', '-f', '-F', '--input')):
        raise ValueError('CI_ARTIFACT_READ_ONLY_COMMAND_REQUIRED')
    for attempt in range(4):
        try:
            result = execute(['gh', *args], capture_output=True, check=False, timeout=180)
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(args, 1, b'', b'HTTP 504 artifact timeout')
        if result.returncode == 0:
            # Failed partial ZIP output must never precede the successful bytes.
            sys.stdout.buffer.write(result.stdout)
            return 0
        if not transient(result.stderr) or attempt == 3:
            sys.stderr.buffer.write(result.stderr)
            sys.stderr.write('\nCI_ORIGINAL_SOURCE_UNAVAILABLE: not a replay PASS\n')
            return result.returncode
        sys.stderr.write(f'CI_SOURCE_TRANSIENT_RETRY attempt={attempt + 1}/3\n')
        sleep(2 ** attempt)
    raise AssertionError('unreachable')


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1:]))
