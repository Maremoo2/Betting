"""CORE-002: read-only whole-card coverage audit using CORE-001's frozen baseline.

A card here is one track on one date; --track omitted audits every race record
for that date, explicitly separating unsupported and composite product references.
No BET instruction is ever issued. All records are historical, as-of reconstructions.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .race_core_review import MODEL_VERSION, analyze_race, write_report

FEATURE_KEYS = (
    'post_position', 'driver_or_jockey', 'trainer', 'age', 'sex',
    'history_total_starts', 'history_total_wins', 'current_year_starts',
    'current_year_wins', 'record_auto', 'record_volt', 'extra_distance_m',
    'total_earnings',
)
RUNNER_CSV_FIELDS = (
    'race_id', 'track', 'race_no', 'decision_at_utc', 'race_stage',
    'selection_id', 'horse_name', 'scratched', 'history_total_starts',
    'history_total_wins', 'p_win', 'fair_odds', 'minimum_watch_odds',
    'available_odds', 'theoretical_ev', 'normalized_market_p',
    'status', 'reason',
)
RACE_CSV_FIELDS = (
    'race_id', 'track', 'race_no', 'discipline', 'race_start_time_utc',
    'decision_at_utc', 'stage', 'roster_runners', 'roster_active',
    'analyzed_runners', 'p_win_runners', 'price_runners', 'watch_runners',
    'market_complete', 'history_known', 'fundamental_complete',
    'blocks', 'missing_fundamental_ids', 'missing_market_ids',
    'duplicate_reference_of',
)


def _read(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(query, params)
    fields = [d[0] for d in cursor.description]
    return [dict(zip(fields, r)) for r in cursor.fetchall()]


def _valid_date(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError('Race date must be YYYY-MM-DD')
    return value


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _stage(race: dict[str, Any], report: dict[str, Any]) -> str:
    if report['model_ready_for_research']:
        return 'FULL_BASELINE'
    if report['fundamental_ready_for_research']:
        return 'FUNDAMENTAL_ONLY'
    return 'BLOCKED'


def analyze_day(
    conn: sqlite3.Connection,
    *,
    race_date: str,
    track: str | None = None,
    cutoff_minutes: float = 4.0,
    discipline: str = 'trot',
    exclude_composite: bool = True,
    deduplicate_physical: bool = True,
) -> dict[str, Any]:
    """Assess ALL discovered race IDs; never silently drop incomplete races.

    Exclusion reasons are materialized for non-trot and compound raceday products.
    Denominators are observed canonical runners, NOT guessed hidden entries.
    """
    _valid_date(race_date)
    if not math.isfinite(cutoff_minutes) or not 0 < cutoff_minutes <= 120:
        raise ValueError('cutoff_minutes must be finite and in (0,120]')
    if not discipline or not discipline.strip():
        raise ValueError('discipline must be nonempty')
    race_records = _read(conn,
        'select race_id,track,race_no,discipline,start_time_utc '
        'from races where race_date=?'
        + (' and track=?' if track is not None else '')
        + ' order by track, start_time_utc, race_no, race_id',
        (race_date, track) if track is not None else (race_date,),
    )
    if not race_records:
        raise ValueError('No race records for requested date and track')

    entries: list[dict[str, Any]] = []
    horses: list[dict[str, Any]] = []
    per_race: dict[str, dict[str, Any]] = {}
    blocker_counts: Counter[str] = Counter()
    missing_feature_counts: Counter[str] = Counter()
    age_by_field: Counter[str] = Counter()
    missing_details: dict[str, list[dict[str, Any]]] = {}
    nonempty_rosters = 0
    # Multiple provider products can register the same physical race with slightly
    # different estimated start clocks. A duplicate is identified conservatively
    # within (track, race_number), only when starts are at most 10 minutes apart.
    # Prefer the reference having a fuller archived canonical roster; otherwise
    # use deterministic earliest-start/ID tie-breaking. The inferred identity is
    # explicitly an audit heuristic, never a model feature.
    duplicates: dict[str, str] = {}
    if deduplicate_physical:
        groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in race_records:
            if row['discipline'] == discipline and '/' not in str(row['track']):
                groups[(str(row['track']), int(row['race_no']))].append(row)
        for group in groups.values():
            if len(group) < 2:
                continue
            times = [datetime.fromisoformat(str(v['start_time_utc'])) for v in group]
            if (max(times) - min(times)).total_seconds() > 600:
                continue
            counts = {str(v['race_id']): conn.execute(
                'select count(*) from runners where race_id=?', (v['race_id'],)
            ).fetchone()[0] for v in group}
            chosen = min(group, key=lambda v: (
                -counts[str(v['race_id'])], str(v['start_time_utc']), str(v['race_id'])
            ))
            for v in group:
                if v['race_id'] != chosen['race_id']:
                    duplicates[str(v['race_id'])] = str(chosen['race_id'])
    for r in race_records:
        race_id = str(r['race_id'])
        roster = _read(conn, 'select selection_id,horse_name,scratched from runners '
                             'where race_id=? order by selection_id', (race_id,))
        active_roster = [x for x in roster if not bool(x['scratched'])]
        nonempty_rosters += bool(roster)
        row: dict[str, Any] = {
            'race_id': race_id, 'track': r['track'], 'race_no': r['race_no'],
            'discipline': r['discipline'], 'race_start_time_utc': r['start_time_utc'],
            'decision_at_utc': None, 'stage': None,
            'roster_runners': len(roster), 'roster_active': len(active_roster),
            'analyzed_runners': 0, 'p_win_runners': 0, 'price_runners': 0,
            'watch_runners': 0, 'market_complete': False,
            'history_known': 0, 'fundamental_complete': False,
            'blocks': [], 'missing_fundamental_ids': [], 'missing_market_ids': [],
            'duplicate_reference_of': duplicates.get(race_id),
        }
        if str(r['discipline']).lower() != discipline.lower():
            row['stage'] = 'SKIPPED_DISCIPLINE'
        elif exclude_composite and '/' in str(r['track']):
            row['stage'] = 'SKIPPED_COMPOSITE_PRODUCT'
        elif race_id in duplicates:
            row['stage'] = 'SKIPPED_DUPLICATE_REFERENCE'
        else:
            start = datetime.fromisoformat(str(r['start_time_utc']))
            if start.tzinfo is None or start.utcoffset() is None:
                raise ValueError(f'Naive start timestamp for {race_id}')
            cutoff = (start - timedelta(minutes=cutoff_minutes)).isoformat()
            report = analyze_race(conn, race_id=race_id, decision_at=cutoff)
            row['decision_at_utc'] = report['decision_at_utc']
            row['stage'] = _stage(row, report)
            row['analyzed_runners'] = len(report['runner_rows'])
            row['p_win_runners'] = sum(bool(x['p_win'] is not None) for x in report['runner_rows'])
            row['price_runners'] = sum(bool(x['p_win'] is not None and x['available_odds'] is not None
                                              and x['theoretical_ev'] is not None) for x in report['runner_rows'])
            row['watch_runners'] = sum(x['status'] == 'WATCH' for x in report['runner_rows'])
            row['market_complete'] = report['win_market_complete']
            row['fundamental_complete'] = report['fundamental_ready_for_research']
            row['history_known'] = report['known_history_runners']
            row['blocks'] = report['blocks']
            blocker_counts.update(report['blocks'])
            fund = _latest_cohort(conn, race_id, 'runner_fundamental_snapshots', cutoff)
            market = _latest_cohort(conn, race_id, 'provider_market_snapshots', cutoff)
            fby = {str(x['selection_id']): x for x in fund}
            mby = {str(x['selection_key']): x for x in market}
            active_ids = {str(x['selection_id']) for x in active_roster}
            row['missing_fundamental_ids'] = sorted(active_ids - set(fby))
            row['missing_market_ids'] = sorted(active_ids - set(mby))
            gaps = []
            for runner in active_roster:
                sid = str(runner['selection_id'])
                f = fby.get(sid)
                missing = [field for field in FEATURE_KEYS if not f or not _present(f.get(field))]
                missing_feature_counts.update(missing)
                for key in FEATURE_KEYS:
                    age_by_field[key] += 1
                if missing:
                    gaps.append({'selection_id': sid, 'horse_name': runner['horse_name'],
                                 'missing_features': missing})
            missing_details[race_id] = gaps
            for h in report['runner_rows']:
                horses.append({
                    'race_id': race_id, 'track': r['track'], 'race_no': r['race_no'],
                    'decision_at_utc': cutoff, 'race_stage': row['stage'],
                    **h,
                })
            per_race[race_id] = report
        entries.append(row)

    stages = Counter(x['stage'] for x in entries)
    attempted = [x for x in entries if not str(x['stage']).startswith('SKIPPED')]
    selected_runner_count = sum(x['roster_active'] for x in attempted)
    p_runner_count = sum(x['p_win_runners'] for x in attempted)
    priced_runner_count = sum(x['price_runners'] for x in attempted)
    full = stages['FULL_BASELINE']
    return {
        'schema_version': 'CORE_002_DAY_REVIEW_V1',
        'race_date': race_date, 'track': track, 'discipline': discipline,
        'cutoff_minutes_before_recorded_start': cutoff_minutes,
        'model_version': MODEL_VERSION,
        'authority': 'RESEARCH_ONLY_NO_REAL_BET',
        'summary': {
            'races_in_inventory': len(entries), 'races_with_any_roster': nonempty_rosters,
            'attempted_races': len(attempted), 'full_baseline_races': full,
            'fundamental_only_races': stages['FUNDAMENTAL_ONLY'],
            'blocked_races': stages['BLOCKED'],
            'skipped_discipline': stages['SKIPPED_DISCIPLINE'],
            'skipped_composite': stages['SKIPPED_COMPOSITE_PRODUCT'],
            'skipped_duplicate_references': stages['SKIPPED_DUPLICATE_REFERENCE'],
            'roster_active_attempted': selected_runner_count,
            'runner_rows_exported': len(horses),
            'runners_with_p_win': p_runner_count, 'runners_with_model_ev': priced_runner_count,
            'watch_runners': sum(x['watch_runners'] for x in attempted),
            'real_bet_count': 0,
            'race_baseline_coverage_pct': 100 * full / len(attempted) if attempted else None,
            'runner_p_coverage_pct': 100 * p_runner_count / selected_runner_count if selected_runner_count else None,
            'runner_ev_coverage_pct': 100 * priced_runner_count / selected_runner_count if selected_runner_count else None,
        },
        'blocker_counts': dict(sorted(blocker_counts.items())),
        'missing_feature_counts': {k: missing_feature_counts[k] for k in FEATURE_KEYS},
        'eligible_feature_denominators': {k: age_by_field[k] for k in FEATURE_KEYS},
        'races': entries,
        'runner_rows': horses,
        'missing_by_race': missing_details,
        'caveats': [
            'Archived race starts and runner rosters may have been updated after the historical cutoff.',
            'Source observed_at and feature_as_of are archived timestamps; independent publication timestamps are not proven.',
            'One race_id is a provider reference. Compound products and probable same-track/number duplicate references are excluded by default.',
            'Duplicate reference grouping requires the same track, race number and starts within ten minutes; this is an audit heuristic, not identity proof.',
            'Missing runner rosters cannot be counted as zero physical runners; coverage denominator is known active canonical entries only.',
            'Baseline p(win) reuses historical wins only, NOT form, class, track, driver, post, distance or pace.',
            'WATCH is research-only. No positive EV is asserted to be a calibrated real betting edge.',
            'No real money staking or live fetching performed.',
        ],
    }


def _latest_cohort(conn: sqlite3.Connection, race_id: str, table: str, cutoff: str) -> list[dict[str, Any]]:
    if table == 'runner_fundamental_snapshots':
        rows = _read(conn,
            'select observed_at_utc from runner_fundamental_snapshots '
            'where race_id=? and observed_at_utc<=? and feature_as_of_utc<=? '
            'order by observed_at_utc desc limit 1', (race_id, cutoff, cutoff))
        if not rows:
            return []
        return _read(conn, 'select * from runner_fundamental_snapshots '
                          'where race_id=? and observed_at_utc=? and feature_as_of_utc<=?',
                     (race_id, rows[0]['observed_at_utc'], cutoff))
    if table == 'provider_market_snapshots':
        rows = _read(conn, 'select observed_at_utc from provider_market_snapshots '
                           'where race_id=? and product=? and observed_at_utc<=? and '
                           '(provider_updated_at_utc is null or provider_updated_at_utc<=?) '
                           'order by observed_at_utc desc limit 1', (race_id, 'V', cutoff, cutoff))
        if not rows:
            return []
        return _read(conn, 'select * from provider_market_snapshots '
                          'where race_id=? and product=? and observed_at_utc=? and '
                          '(provider_updated_at_utc is null or provider_updated_at_utc<=?)',
                     (race_id, 'V', rows[0]['observed_at_utc'], cutoff))
    raise ValueError('Unsupported table')


def write_day_report(day: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'day_core.json').write_text(json.dumps(day, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with (folder / 'races.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=RACE_CSV_FIELDS, extrasaction='ignore')
        w.writeheader()
        for r in day['races']:
            w.writerow({**r, 'blocks': ';'.join(r['blocks']),
                        'missing_fundamental_ids': ';'.join(r['missing_fundamental_ids']),
                        'missing_market_ids': ';'.join(r['missing_market_ids'])})
    with (folder / 'runners.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=RUNNER_CSV_FIELDS, extrasaction='ignore')
        w.writeheader(); w.writerows(day['runner_rows'])
    s = day['summary']
    lines = [
        f"# CORE-002 | Hele løpsdagen {day['race_date']}", '',
        f"**Utvalg:** {day['track'] or 'alle baner'} · {day['discipline']} · T−{day['cutoff_minutes_before_recorded_start']:g} min fra arkivert start", '',
        f"**{s['full_baseline_races']}/{s['attempted_races']} løpsreferanser** har komplett, smal Champion-baseline ({_pct(s['race_baseline_coverage_pct'])}).",
        f"**{s['runners_with_p_win']}/{s['roster_active_attempted']} kjente aktive hester** har p(win) ({_pct(s['runner_p_coverage_pct'])}).",
        f"**{s['runners_with_model_ev']}/{s['roster_active_attempted']}** har modell-EV ({_pct(s['runner_ev_coverage_pct'])}).", '',
        (f"**Inventar:** {s['races_in_inventory']} løps-ID-er; {s['skipped_discipline']} annen disiplin, {s['skipped_composite']} kombinerte produkter utelatt. "
        f"{s['skipped_duplicate_references']} andre referanser for sannsynlig samme fysiske løp. "
        f"{s['fundamental_only_races']} kun fundamentale, {s['blocked_races']} blokkert. "
        f"{s['watch_runners']} forsknings-WATCH og **0 BET**."), '',
        '## Løp for løp', '',
        '| Bane | Løp | Aktive i kjent roster | p(win) | EV | Status | Hovedblokkering |',
        '|---|---:|---:|---:|---:|---|---|',
    ]
    for r in day['races']:
        block = ', '.join(r['blocks']) if r['blocks'] else '–'
        if r['duplicate_reference_of']:
            block = 'Samme fysiske løp som ' + r['duplicate_reference_of']
        lines.append(f"| {r['track']} | {r['race_no']} | {r['roster_active']} | {r['p_win_runners']} | "
                     f"{r['price_runners']} | {r['stage']} | {block} |")
    lines += ['', '## Dekning per bane', '',
              '| Bane | Vurderte løp | Full baseline | Kjente aktive | p(win) |',
              '|---|---:|---:|---:|---:|']
    grouped = defaultdict(list)
    for item in day['races']:
        if not item['stage'].startswith('SKIPPED'):
            grouped[item['track']].append(item)
    for track_name, group in sorted(grouped.items()):
        lines.append(f"| {track_name} | {len(group)} | {sum(r['stage']=='FULL_BASELINE' for r in group)} | "
                     f"{sum(r['roster_active'] for r in group)} | {sum(r['p_win_runners'] for r in group)} |")
    lines += ['', '## Hvor dataene mangler', '']
    if not day['blocker_counts']:
        lines.append('Ingen modellblokker i det valgte utvalget.')
    else:
        for code, n in sorted(day['blocker_counts'].items(), key=lambda x: (-x[1], x[0])):
            lines.append(f'- **{code}:** {n} løp')
    lines += ['', '## Manglende fundamentale variabler for kjente aktive hester', '',
              '| Variabel | Mangler | Dekning |', '|---|---:|---:|']
    for key, missing in sorted(day['missing_feature_counts'].items(), key=lambda x: (-x[1], x[0])):
        denom = day['eligible_feature_denominators'][key]
        lines.append(f'| {key} | {missing}/{denom} | {_pct(100 * (denom-missing)/denom if denom else None)} |')
    lines += ['', '**Merk:** Disse variablene er kartlagt, men brukes ikke av nåværende Champion-baseline.', '',
              '## Metodiske begrensninger', '']
    lines += [f'- {c}' for c in day['caveats']]
    (folder/'day_core.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def _pct(p: float | None) -> str:
    return '–' if p is None else f'{p:.1f}%'


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='CORE-002 read-only whole day WIN research coverage')
    p.add_argument('--db', required=True)
    p.add_argument('--date', required=True, dest='race_date')
    p.add_argument('--track')
    p.add_argument('--cutoff-minutes', type=float, default=4.)
    p.add_argument('--discipline', default='trot')
    p.add_argument('--include-composite', action='store_true')
    p.add_argument('--include-duplicate-references', action='store_true')
    p.add_argument('--out', required=True)
    p.add_argument('--details', action='store_true', help='write each assessed race as JSON/CSV/Markdown')
    a = p.parse_args(argv)
    db = Path(a.db).resolve()
    if not db.is_file():
        p.error('Database file does not exist')
    conn = sqlite3.connect('file:' + db.as_posix() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        day = analyze_day(conn, race_date=a.race_date, track=a.track,
                          cutoff_minutes=a.cutoff_minutes, discipline=a.discipline,
                          exclude_composite=not a.include_composite,
                          deduplicate_physical=not a.include_duplicate_references)
        if a.details:
            for race in day['races']:
                if str(race['stage']).startswith('SKIPPED'):
                    continue
                r = analyze_race(conn, race_id=race['race_id'],
                                 decision_at=race['decision_at_utc'])
                folder = Path(a.out)/'races'/race['race_id'].replace(':', '_').replace('/', '_')
                write_report(r, folder)
    finally:
        conn.close()
    write_day_report(day, Path(a.out))
    print(json.dumps(day['summary'], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
