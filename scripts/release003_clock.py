"""One-off RELEASE-003 acceptance clock; dispatches only the existing isolated probe.

Not a production scheduler, model or collector. Never runs on main. Every missed or
failed tick is preserved; no retrospective dispatch of missed observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = 'Maremoo2/Betting'
BRANCH = 'p0/v3313-shadow-collector-integration-20261121'
WORKFLOW = 'core-003-shadow-pilot.yml'
PHASE_SECONDS = 4.5 * 3600


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('CLOCK_TIMEZONE_REQUIRED')
    return result.astimezone(UTC)


def make_plan(start, end, pin, inventory):
    start, end = stamp(start), stamp(end)
    if (start.date().isoformat() != '2026-11-22' or end.date() != start.date()
            or not timedelta(0) < end - start <= timedelta(hours=13.5)
            or len(pin) != 40 or any(c not in '0123456789abcdef' for c in pin)):
        raise ValueError('ONE_OFF_ACCEPTANCE_BOUNDARY_INVALID')
    first = min(stamp(r['start_utc']) for r in inventory)
    last = max(stamp(r['start_utc']) for r in inventory)
    if start >= first - timedelta(minutes=4) or end < last + timedelta(minutes=60):
        raise ValueError('ACCEPTANCE_WINDOW_DOES_NOT_COVER_ORIGINAL_PROGRAMME')
    ticks = []
    tick = start
    while tick < end:
        ticks.append(tick.isoformat())
        tick += timedelta(minutes=5)
    if len(ticks) > 162:
        raise ValueError('ACCEPTANCE_TICK_LIMIT')
    return {'schema': 'RELEASE003_ONE_OFF_CLOUD_CLOCK_V1', 'repo': REPO, 'branch': BRANCH,
            'day': '2026-11-22', 'pin': pin, 'start': start.isoformat(), 'end': end.isoformat(),
            'ticks': ticks, 'source_inventory_sha256': hashlib.sha256(
                json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
            'scope_rule': 'ALL_PHYSICAL_COLLECTOR_RACES_PLUS_LATER_DISCOVERIES_NOT_PRODUCTS',
            'production_activation': False, 'bet_authority': False}


def api(path, method='GET', payload=None):
    if not path.startswith(f'/repos/{REPO}/'):
        raise ValueError('ACCEPTANCE_API_SCOPE_INVALID')
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request('https://api.github.com' + path, data=data, method=method,
                                    headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                                             'Accept': 'application/vnd.github+json',
                                             'Content-Type': 'application/json'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            message = exc.read().decode(errors='replace')
            transient = exc.code == 429 or (method == 'GET' and exc.code in (500, 502, 503, 504)) or (
                exc.code == 403 and 'rate limit' in message.lower())
            if not transient or attempt == 3:
                raise RuntimeError(f'ACCEPTANCE_HTTP_{exc.code}:{message[:300]}') from None
            time.sleep(2 ** attempt)
    raise AssertionError('unreachable')


def run_phase(plan, phase, out, *, request=api, clock=lambda: datetime.now(UTC), sleep=time.sleep):
    out.mkdir(parents=True, exist_ok=True)
    low = stamp(plan['start']) + timedelta(seconds=phase * PHASE_SECONDS)
    high = min(stamp(plan['end']), low + timedelta(seconds=PHASE_SECONDS))
    rows = []
    for value in plan['ticks']:
        tick = stamp(value)
        if not low <= tick < high:
            continue
        while clock() < tick:
            sleep(min(30, (tick - clock()).total_seconds()))
        observed = clock()
        row = {'planned_at_utc': value, 'dispatch_observed_at_utc': observed.isoformat(),
               'head': plan['pin'], 'source_workflow': WORKFLOW, 'workflow_run_id': None}
        if (observed - tick).total_seconds() > 120:
            row['status'] = 'MISSED_CONTROLLER_SLOT_NOT_BACKFILLED'
        else:
            try:
                branch = request(f'/repos/{REPO}/branches/' + urllib.parse.quote(BRANCH, safe=''))
                if branch['commit']['sha'] != plan['pin']:
                    raise ValueError('ACCEPTANCE_HEAD_MOVED_STOP_DISPATCH')
                lookup = (f'/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?'
                          'event=workflow_dispatch&per_page=20&branch='
                          + urllib.parse.quote(BRANCH, safe=''))
                existing = request(lookup)
                already = [r for r in existing['workflow_runs']
                           if r.get('display_title') == 'V3313 tick ' + value
                           and r['head_sha'] == plan['pin']]
                if len(already) > 1:
                    raise ValueError('DUPLICATE_ACCEPTANCE_TICK_ALREADY_EXISTS')
                if not already:
                    request(f'/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches', 'POST', {
                        'ref': BRANCH, 'inputs': {'execute': 'true', 'shadow_acceptance': 'true',
                        'acceptance_schedule': 'false', 'acceptance_day': plan['day'],
                        'acceptance_pin_sha': plan['pin'], 'acceptance_tick_utc': value}})
                row['status'] = 'DISPATCH_ACCEPTED_OBSERVATION_PENDING'
                for _ in range(3):
                    sleep(2)
                    runs = request(lookup)
                    found = [r for r in runs['workflow_runs']
                             if r.get('display_title') == 'V3313 tick ' + value
                             and r['head_sha'] == plan['pin']]
                    if len(found) > 1:
                        raise ValueError('DUPLICATE_ACCEPTANCE_TICK_ALREADY_EXISTS')
                    if len(found) == 1:
                        row['workflow_run_id'] = found[0]['id']
                        row['workflow_created_at'] = found[0]['created_at']
                        break
            except (ValueError, RuntimeError, OSError, KeyError) as exc:
                row['status'] = 'DISPATCH_BLOCKED'
                row['reason'] = str(exc)
        rows.append(row)
        with (out / 'ticks.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, sort_keys=True) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        if row.get('reason') == 'ACCEPTANCE_HEAD_MOVED_STOP_DISPATCH':
            break
    (out / 'phase-summary.json').write_text(json.dumps({
        'phase': phase, 'observations': rows, 'full_day_accepted': False,
        'note': 'Dispatch receipts are not completed race/field/market/PIT acceptance.'}, indent=2))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', type=int, choices=[0, 1, 2], required=True)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    pin = os.environ['ACCEPTANCE_PIN_SHA']
    if (os.environ['GITHUB_REPOSITORY'] != REPO
            or os.environ['GITHUB_REF_NAME'] != BRANCH or os.environ['GITHUB_SHA'] != pin):
        raise ValueError('ACCEPTANCE_REPOSITORY_BRANCH_SHA_BOUNDARY')
    inventory = json.loads(Path('research/release003-20261122-scope.json').read_bytes())['races']
    plan = make_plan(os.environ['ACCEPTANCE_START_UTC'], os.environ['ACCEPTANCE_END_UTC'],
                     pin, inventory)
    out = Path(os.environ['RUNNER_TEMP']) / f'release003-clock-{args.phase}'
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'plan.json'
    raw = (json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError('FROZEN_ACCEPTANCE_PLAN_CONFLICT')
    else:
        with target.open('xb') as handle:
            handle.write(raw)
    if not args.plan_only:
        run_phase(plan, args.phase, out)


if __name__ == '__main__':
    main()
