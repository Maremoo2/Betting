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


def make_plan(start, end, pin, inventory, *, campaign=None):
    start, end = stamp(start), stamp(end)
    day = campaign['day'] if campaign else '2026-11-22'
    repo = campaign['repo'] if campaign else REPO
    branch = campaign['branch'] if campaign else BRANCH
    if repo not in {REPO, 'Maremoo2/betting-hq-private-research'} or branch == 'main':
        raise ValueError('ACCEPTANCE_REPOSITORY_BRANCH_SHA_BOUNDARY')
    if campaign and (campaign.get("start") != start.isoformat() or campaign.get("end") != end.isoformat()
                or stamp(campaign["frozen_at_utc"]) >= start
                or stamp(campaign["source_completed_at_utc"]) > stamp(campaign["frozen_at_utc"])
                or not inventory or len({r["race_id"] for r in inventory}) != len(inventory)
                or any(r.get("country") not in {"NO", "SE"} for r in inventory)):
        raise ValueError("FROZEN_CAMPAIGN_CLOCK_OR_SCOPE_INVALID")
    if (start.date().isoformat() != day or end.date() != start.date()
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
    plan = {'schema': 'RELEASE003_ONE_OFF_CLOUD_CLOCK_V1', 'repo': repo, 'branch': branch,
            'day': day, 'pin': pin, 'start': start.isoformat(), 'end': end.isoformat(),
            'ticks': ticks, 'source_inventory_sha256': hashlib.sha256(
                json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
            'scope_rule': 'ALL_PHYSICAL_COLLECTOR_RACES_PLUS_LATER_DISCOVERIES_NOT_PRODUCTS',
            'production_activation': False, 'bet_authority': False}
    if campaign:
        plan['campaign'] = campaign
    return plan


def api(path, method='GET', payload=None):
    repository = os.environ.get('GITHUB_REPOSITORY', REPO)
    if repository not in {REPO, 'Maremoo2/betting-hq-private-research'} or not path.startswith(f'/repos/{repository}/'):
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


def reconcile_clock(plan, inventory, receipts, runs, reports, *, observed_at):
    """Reconcile an immutable clock, not certify source/PIT or a whole phase.

    Caller retains authenticated API/ZIP receipts separately. No dispatch, source
    access, backfill, probability calculation or notification is performed here.
    An accepted POST or a green workflow is insufficient without its day journal.
    """
    from hbi.prewatch_shadow_handoff import completion_health

    now = stamp(observed_at)
    regenerated = make_plan(plan['start'], plan['end'], plan['pin'], inventory, campaign=plan.get('campaign'))
    if regenerated != plan:
        raise ValueError('FROZEN_ACCEPTANCE_PLAN_CONFLICT')
    expected_races = {row['race_id'] for row in inventory}
    if len(expected_races) != len(inventory):
        raise ValueError('ACCEPTANCE_INVENTORY_DUPLICATE_RACE')
    by_receipt = {}
    for receipt in receipts:
        tick = receipt['planned_at_utc']
        if tick not in plan['ticks'] or receipt.get('head') != plan['pin']:
            raise ValueError('ACCEPTANCE_RECEIPT_CLOCK_OR_HEAD_CONFLICT')
        old = by_receipt.get(tick)
        if old is not None and old != receipt:
            raise ValueError('ACCEPTANCE_RECEIPT_REVISION_CONFLICT')
        by_receipt[tick] = receipt
    by_run, quarantined = {}, []
    seen_ids = set()
    for run in runs:
        title = run.get('display_title', '')
        if not title.startswith('V3313 tick '):
            continue
        tick = title.removeprefix('V3313 tick ')
        if run['id'] in seen_ids:
            raise ValueError('ACCEPTANCE_DUPLICATE_RUN_INVENTORY')
        seen_ids.add(run['id'])
        if (tick not in plan['ticks'] or run.get('head_sha') != plan['pin']
                or run.get('head_branch') != plan['branch']
                or run.get('event') != 'workflow_dispatch'):
            quarantined.append({'run_id': run['id'], 'reason': 'RUN_CLOCK_OR_HEAD_CONFLICT'})
            continue
        by_run.setdefault(tick, []).append(run)
    rows = []
    for tick in plan['ticks']:
        planned = stamp(tick)
        receipt = by_receipt.get(tick)
        found = by_run.get(tick, [])
        row = {'planned_at_utc': tick, 'dispatch_receipt': receipt,
               'workflow_run_ids': [run['id'] for run in found], 'issues': []}
        if planned > now:
            row['status'] = 'FUTURE_NOT_DUE'
            if found:
                row['issues'].append('FUTURE_TICK_ALREADY_DISPATCHED')
        elif len(found) > 1:
            row['status'] = 'DUPLICATE_RUNS'
        elif not found:
            if now <= planned + timedelta(seconds=120):
                row['status'] = 'WITHIN_DISPATCH_WINDOW'
            else:
                row['status'] = 'NO_WORKFLOW_RUN'
        else:
            run = found[0]
            created = stamp(run['created_at'])
            row['creation_lag_seconds'] = (created - planned).total_seconds()
            if created > now or created < planned:
                row['issues'].append('RUN_CREATION_CLOCK_CONFLICT')
            if row['creation_lag_seconds'] > 120:
                row['issues'].append('LATE_RUN_CREATION')
            if run['status'] != 'completed':
                row['status'] = 'RUN_PENDING'
            elif run.get('conclusion') != 'success':
                row['status'] = 'RUN_FAILED'
            else:
                report = reports.get(run['id'])
                if report is None:
                    row['status'] = 'ACCEPTANCE_ARTIFACT_MISSING'
                elif (not report.get('inventory')
                      or not expected_races <= set(report['inventory'])
                      or completion_health([report])['incomplete_observations']
                      or any(report.get(key) is not False for key in (
                          'bet_authority', 'production_activated', 'champion_changed'))):
                    row['status'] = 'ACCEPTANCE_ARTIFACT_INVALID'
                else:
                    row['status'] = 'COMPLETED_WITH_TERMINAL_JOURNAL'
                    row['journal_evidence_mode'] = report.get('evidence_mode')
                    row['prospective_predictions'] = report['counts']['prospective_predictions']
            if receipt and receipt.get('workflow_run_id') not in (None, run['id']):
                row['issues'].append('RECEIPT_RUN_ID_CONFLICT')
        if receipt and receipt['status'] != 'DISPATCH_ACCEPTED_OBSERVATION_PENDING':
            row['issues'].append('CONTROLLER_DISPATCH_NOT_CONFIRMED')
        if not receipt:
            row['receipt_state'] = 'NOT_PUBLISHED_OR_NOT_RECORDED'
        rows.append(row)
    good = 'COMPLETED_WITH_TERMINAL_JOURNAL'
    pending = {'FUTURE_NOT_DUE', 'WITHIN_DISPATCH_WINDOW', 'RUN_PENDING'}
    failed = [row for row in rows if row['issues'] or row['status'] not in pending | {good}]
    window_complete = now >= stamp(plan['end'])
    acknowledged = all(row['dispatch_receipt'] for row in rows)
    complete = (window_complete and acknowledged and not failed and not quarantined
                and all(row['status'] == good for row in rows))
    # Reuse the existing two-observation health convention for missed journal
    # deliveries, rather than mistaking two complete reports around a gap for health.
    gap_streak = peak_gap_streak = 0
    for row in rows:
        if row['status'] in ('NO_WORKFLOW_RUN', 'RUN_FAILED', 'ACCEPTANCE_ARTIFACT_MISSING',
                             'ACCEPTANCE_ARTIFACT_INVALID', 'DUPLICATE_RUNS'):
            gap_streak += 1
            peak_gap_streak = max(peak_gap_streak, gap_streak)
        else:
            gap_streak = 0
    return {
        'schema': 'RELEASE003_CLOCK_RECONCILIATION_V1', 'observed_at_utc': now.isoformat(),
        'pin': plan['pin'], 'expected_ticks': len(rows), 'observations': rows,
        'window_complete': window_complete, 'closed_receipts': len(by_receipt),
        'workflow_runs_observed': sum(len(group) for group in by_run.values()),
        'known_failed_ticks': len(failed), 'quarantined_runs': quarantined,
        'status': ('BLOCKED_INTEGRATION' if failed or quarantined else
                   'BLOCKED_SOURCE' if window_complete and not acknowledged else
                   'TECHNICALLY_COMPLETE' if complete else 'WAIT_LIVE'),
        'clock_reconciliation_complete': complete,
        'alert_required': peak_gap_streak >= 2,
        'notification_delivery': 'NOT_ACTIVATED',
        'full_day_accepted': False, 'pit_certified': False, 'bet_authority': False,
        'note': 'Clock reconciliation does not grant whole-day, phase, model or PIT acceptance.',
    }


def run_phase(plan, phase, out, *, request=api, clock=lambda: datetime.now(UTC), sleep=time.sleep):
    out.mkdir(parents=True, exist_ok=True)
    repo, branch_name = plan['repo'], plan['branch']
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
                branch = request(f'/repos/{repo}/branches/' + urllib.parse.quote(branch_name, safe=''))
                if branch['commit']['sha'] != plan['pin']:
                    raise ValueError('ACCEPTANCE_HEAD_MOVED_STOP_DISPATCH')
                lookup = (f'/repos/{repo}/actions/workflows/{WORKFLOW}/runs?'
                          'event=workflow_dispatch&per_page=20&branch='
                          + urllib.parse.quote(branch_name, safe=''))
                existing = request(lookup)
                already = [r for r in existing['workflow_runs']
                           if r.get('display_title') == 'V3313 tick ' + value
                           and r['head_sha'] == plan['pin']]
                if len(already) > 1:
                    raise ValueError('DUPLICATE_ACCEPTANCE_TICK_ALREADY_EXISTS')
                if not already:
                    state_input = {}
                    if plan.get('campaign'):
                        index = plan['ticks'].index(value)
                        if index == 0:
                            previous_run = plan['campaign']['seed_state']['run_id']
                        else:
                            previous_title = 'V3313 tick ' + plan['ticks'][index - 1]
                            previous = [r for r in existing['workflow_runs']
                                        if r.get('display_title') == previous_title
                                        and r.get('head_sha') == plan['pin']]
                            if len(previous) != 1:
                                raise ValueError('EXACT_PREVIOUS_STATE_RUN_MISSING_NO_FALLBACK')
                            producer = request(f"/repos/{repo}/actions/runs/{previous[0]['id']}")
                            if producer.get('head_sha') != plan['pin']:
                                raise ValueError('EXACT_PREVIOUS_WRITER_CODE_CHANGED')
                            jobs = request(f"/repos/{repo}/actions/runs/{previous[0]['id']}/jobs?per_page=100")["jobs"]
                            writers = [job for job in jobs if job.get('name') == 'source-pilot']
                            if (len(writers) != 1 or writers[0].get('status') != 'completed'
                                    or writers[0].get('conclusion') != 'success'):
                                raise ValueError('EXACT_PREVIOUS_STATE_WRITER_NOT_SUCCESSFUL')
                            previous_run = previous[0]['id']
                        state_input['acceptance_state_run'] = str(previous_run)
                        row['state_source_run_id'] = previous_run
                    request(f'/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches', 'POST', {
                        'ref': branch_name, 'inputs': {'execute': 'true', 'shadow_acceptance': 'true',
                        'acceptance_schedule': 'false', 'acceptance_day': plan['day'],
                        'acceptance_pin_sha': plan['pin'], 'acceptance_tick_utc': value, **state_input}})
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
        if row['status'] != 'DISPATCH_ACCEPTED_OBSERVATION_PENDING':
            print(f"::error title=Isolated acceptance window blocked::{value} {row['status']} {row.get('reason', '')}")
        if row.get('reason') == 'ACCEPTANCE_HEAD_MOVED_STOP_DISPATCH':
            break
    (out / 'phase-summary.json').write_text(json.dumps({
        'phase': phase, 'observations': rows, 'full_day_accepted': False,
        'alert_required': any(r['status'] != 'DISPATCH_ACCEPTED_OBSERVATION_PENDING' for r in rows),
        'note': 'Dispatch receipts are not completed race/field/market/PIT acceptance.'}, indent=2))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', type=int, choices=[0, 1, 2], required=True)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    pin = os.environ['ACCEPTANCE_PIN_SHA']
    manifest = os.environ.get('ACCEPTANCE_MANIFEST')
    campaign = json.loads(Path(manifest).read_bytes()) if manifest else None
    repo = campaign['repo'] if campaign else REPO
    branch = campaign['branch'] if campaign else BRANCH
    if (os.environ['GITHUB_REPOSITORY'] != repo
            or os.environ['GITHUB_REF_NAME'] != branch or os.environ['GITHUB_SHA'] != pin):
        raise ValueError('ACCEPTANCE_REPOSITORY_BRANCH_SHA_BOUNDARY')
    inventory = campaign['races'] if campaign else json.loads(Path('research/release003-20261122-scope.json').read_bytes())['races']
    plan = make_plan(os.environ['ACCEPTANCE_START_UTC'], os.environ['ACCEPTANCE_END_UTC'],
                     pin, inventory, campaign=campaign)
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
