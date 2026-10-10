"""Organize committed archive days without writing to the crawler's source tree."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .transport import digest, write_json


def file_hash(data):
    return sha256(data).hexdigest()


def copy_frozen(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError(f"Existing organized freeze differs: {target}")
        return
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(target)


def organize(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Source and output must be separate non-overlapping directories')
    expected, empty_months = defaultdict(set), defaultdict(list)
    for path in sorted((source / 'inventory').glob('*.json')):
        meetings = json.loads(path.read_text(encoding='utf-8'))['body']['result']
        if not meetings:
            empty_months[path.stem[:4]].append(path.stem)
        for meeting in meetings:
            day = meeting['raceDayKey'][-10:]
            date.fromisoformat(day)
            expected[day[:4]].add(day)
    completed, weeks, totals = defaultdict(list), defaultdict(list), defaultdict(Counter)
    for post_path in sorted((source / 'result-days').glob('*.json')):
        day = post_path.stem
        parsed = date.fromisoformat(day)
        pre_path = source / 'market-days' / post_path.name
        pre_bytes, post_bytes = pre_path.read_bytes(), post_path.read_bytes()
        pre, post = json.loads(pre_bytes), json.loads(post_bytes)
        if (pre.get('stage') != 'MARKET_ONLY' or post.get('stage') != 'RESULTS'
                or digest(pre['races']) != pre['sha256']
                or post['pre_sha256'] != pre['sha256']):
            raise ValueError(f'Daily freeze integrity failure: {day}')
        year = str(parsed.year)
        copy_frozen(output / year / 'PRE' / pre_path.name, pre_bytes)
        copy_frozen(output / year / 'POST' / post_path.name, post_bytes)
        completed[year].append(day)
        totals[year].update(post['summary']['counts'])
        iso = parsed.isocalendar()
        weeks[(year, f'{iso.year}-W{iso.week:02d}')].append((day, pre_bytes, post_bytes))
    for (year, week), items in weeks.items():
        for stage, index in [('PRE', 1), ('POST', 2)]:
            target = output / year / 'weekly' / f'{week}-{stage}.zip'
            hashes = {day + '.json': file_hash(item[index]) for item in items for day in [item[0]]}
            manifest = {'stage': 'MARKET_ONLY' if stage == 'PRE' else 'RESULTS',
                        'calendar_year': year, 'iso_week': week,
                        'days': [item[0] for item in items], 'files_sha256': hashes,
                        'all_discovered_days_for_year_week_collected': all(
                            day in completed[year] for day in expected[year]
                            if date.fromisoformat(day).isocalendar()[:2]
                            == date.fromisoformat(items[0][0]).isocalendar()[:2]),
                        'coverage_scope': 'CALENDAR_YEAR_SLICE_OF_ISO_WEEK',
                        'historical_not_prospective': True}
            if target.exists():
                with ZipFile(target) as archive:
                    old = json.loads(archive.read('MANIFEST.json'))
                    if old == manifest:
                        if archive.testzip() is not None or any(
                                file_hash(archive.read(name)) != h for name, h in hashes.items()):
                            raise ValueError(f'Package integrity failure: {target}')
                        continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.zip.tmp')
            with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
                archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2))
                for item in items:
                    archive.writestr(item[0] + '.json', item[index])
            temporary.replace(target)
    reports = []
    for year in sorted(set(expected) | set(completed) | set(empty_months)):
        days = set(completed[year])
        discovered = expected[year]
        report = {'year': year, 'days_completed': len(days),
                  'days_discovered': len(discovered), 'completed_dates': sorted(days),
                  'missing_discovered_dates': sorted(discovered - days),
                  'empty_discovery_months_not_proof_of_no_racing': empty_months[year],
                  'counts': dict(totals[year]),
                  'status': ('DISCOVERED_DAYS_COLLECTED_QC_REQUIRED'
                             if discovered and discovered <= days else 'IN_PROGRESS'),
                  'training_ready': False, 'historical_not_prospective': True}
        write_json(output / year / 'STATUS.json', report)
        reports.append(report)
    index = {'schema_version': 'HBI_ARCHIVE_YEAR_INDEX_V1',
             'source': str(source), 'years': reports,
             'note': 'PRE and POST stay separate. Collection completion is not training/QC approval.'}
    write_json(output / 'INDEX.json', index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args()
    if args.interval < 30:
        parser.error('Minimum interval is 30 seconds')
    while True:
        result = organize(args.source, args.output)
        print(json.dumps({'years': len(result['years']),
                          'days': sum(y['days_completed'] for y in result['years'])}), flush=True)
        if not args.watch or (Path(args.source) / 'FINAL.json').exists():
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
