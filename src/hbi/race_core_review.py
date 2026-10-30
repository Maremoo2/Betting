"""Read-only full-field WIN research report from an archived HBI SQLite database.

CORE-001 deliberately REUSES the frozen FUNDAMENTAL_CHAMPION_V1_1 formula.
It does not modify Champion, calibration, frozen rules or live wagering.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

MODEL_VERSION = "FUNDAMENTAL_CHAMPION_V1_1"
PRIOR_STARTS = 6.0
MIN_HISTORY_COVERAGE = 0.80
# Research-only thresholds, not authorised betting gates.
EDGE_TARGET = 0.05
SAFETY_MARGIN = 0.05


def _utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError(f"Naive UTC timestamp: {value}")
    return dt


def _rows(db: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(sql, args)]


def _cohort(db: sqlite3.Connection, table: str, race_id: str, decision_at: str,
            *, product: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
    # An entire snapshot cohort is used: never silently mix runner snapshots across times.
    if table == 'runner_fundamental_snapshots':
        key = 'observed_at_utc'
        where = 'race_id=? and observed_at_utc<=? and feature_as_of_utc<=?'
        args = (race_id, decision_at, decision_at)
    elif table == 'provider_market_snapshots':
        key = 'observed_at_utc'
        where = "race_id=? and product=? and observed_at_utc<=? and (provider_updated_at_utc is null or provider_updated_at_utc<=?)"
        args = (race_id, product, decision_at, decision_at)
    else:
        raise ValueError('Unsupported table')
    times = _rows(db, f"select distinct {key} t from {table} where {where} order by {key} desc", args)
    for item in times:
        t = item['t']
        if table == 'runner_fundamental_snapshots':
            records = _rows(db, f"select * from {table} where race_id=? and observed_at_utc=? and feature_as_of_utc<=?",
                            (race_id, t, decision_at))
        else:
            records = _rows(db, f"select * from {table} where race_id=? and product=? and observed_at_utc=? and (provider_updated_at_utc is null or provider_updated_at_utc<=?)",
                            (race_id, product, t, decision_at))
        # Highest available cohort is returned even if partial. Never cherry-pick an older
        # cohort to create a falsely complete report after a newer partial update.
        return records, t
    return [], None


def historical_win_prior(entries: list[dict[str, Any]]) -> tuple[dict[str, float], int]:
    """Exact equation from existing Champion V1.1; no market features enter p(win)."""
    active = [r for r in entries if not bool(r.get('scratched'))]
    if len(active) < 2:
        return {}, 0
    prior = 1 / len(active)
    strength: dict[str, float] = {}
    known = 0
    for r in active:
        starts, wins = r.get('history_total_starts'), r.get('history_total_wins')
        try:
            starts, wins = int(starts), int(wins)
            valid = starts >= 0 and 0 <= wins <= starts
        except (ValueError, TypeError):
            valid = False
        if valid:
            known += 1
            s = (wins + PRIOR_STARTS * prior) / (starts + PRIOR_STARTS)
        else:
            s = prior
        strength[str(r['selection_id'])] = s if math.isfinite(s) and s > 0 else prior
    z = sum(strength.values())
    return {i: s/z for i, s in strength.items()}, known


def _number(selection: str) -> tuple[int, str]:
    return (int(selection), selection) if selection.isdigit() else (10**9, selection)


def analyze_race(db: sqlite3.Connection, *, race_id: str, decision_at: str,
                 edge_target: float = EDGE_TARGET, safety_margin: float = SAFETY_MARGIN) -> dict[str, Any]:
    """Compute read-only as-of field report. Never issues actionable BET decisions."""
    if not 0 <= edge_target < 1 or not 0 <= safety_margin < 1:
        raise ValueError('edge_target and safety_margin must be in [0,1)')
    cutoff = _utc(decision_at)
    races = _rows(db, 'select * from races where race_id=?', (race_id,))
    if not races:
        raise ValueError(f'Unknown race: {race_id}')
    race = races[0]
    start = _utc(race['start_time_utc'])
    # ISO representation normalised to database offsets, for consistent lexicographic filtering.
    canonical_cutoff = cutoff.astimezone(start.tzinfo).isoformat()
    roster = _rows(db, 'select selection_id,horse_name,post_position,driver_or_jockey,trainer,scratched from runners where race_id=?', (race_id,))
    fund, ft = _cohort(db, 'runner_fundamental_snapshots', race_id, canonical_cutoff)
    odds, mt = _cohort(db, 'provider_market_snapshots', race_id, canonical_cutoff, product='V')
    roster_ids = {str(r['selection_id']) for r in roster}
    f_by = {str(r['selection_id']): r for r in fund}
    m_by = {str(r['selection_key']): r for r in odds}
    problems: list[str] = []
    if cutoff >= start:
        problems.append('NOT_BEFORE_RECORDED_START')
    if not roster_ids:
        problems.append('NO_CANONICAL_ROSTER')
    if len(f_by) != len(fund):
        problems.append('DUPLICATE_FUNDAMENTAL_SELECTIONS')
    if len(m_by) != len(odds):
        problems.append('DUPLICATE_MARKET_SELECTIONS')
    if not ft:
        problems.append('NO_FUNDAMENTAL_COHORT_AS_OF')
    elif set(f_by) != roster_ids:
        problems.append('FUNDAMENTAL_FIELD_MISMATCH')
    if not mt:
        problems.append('NO_WIN_MARKET_AS_OF')
    elif set(m_by) != roster_ids:
        problems.append('MARKET_FIELD_MISMATCH')
    if ft and _utc(ft) > cutoff or mt and _utc(mt) > cutoff:
        problems.append('SOURCE_FROM_FUTURE')
    if ft and any(_utc(r['feature_as_of_utc']) > cutoff for r in fund):
        problems.append('FEATURE_AS_OF_AFTER_DECISION')
    if ft and any(bool(r['scratched']) != bool(next((o['scratched'] for o in roster if o['selection_id']==r['selection_id']), False)) for r in fund):
        problems.append('ROSTER_SCRATCH_DISAGREEMENT')
    if roster_ids and any(s not in roster_ids for s in m_by):
        problems.append('MARKET_HAS_UNKNOWN_SELECTION')

    active = [r for r in fund if not bool(r['scratched'])]
    probs, known = historical_win_prior(fund)
    if len(active) < 2:
        problems.append('INSUFFICIENT_ACTIVE_FIELD')
    if active and known / len(active) < MIN_HISTORY_COVERAGE:
        problems.append('LOW_HISTORY_COVERAGE')
    if any(not r.get('full_field_history_complete') or not r.get('source_uri')
           for r in active):
        problems.append('FULL_FIELD_HISTORY_NOT_VERIFIED')
    active_ids = set(probs)
    if len(active_ids) != len(active):
        problems.append('MODEL_SELECTION_DUPLICATES')
    if any(s not in m_by or m_by[s]['odds_decimal'] is None or
           not math.isfinite(float(m_by[s]['odds_decimal'])) or float(m_by[s]['odds_decimal']) <= 1
           for s in active_ids):
        problems.append('MISSING_OR_INVALID_ACTIVE_WIN_ODDS')
    # Information may be incomplete even with all snapshots (distance/form etc.).
    # This is the narrow Champion v1.1 baseline, NOT an all-factor handicapping model.
    market_codes = {
        'DUPLICATE_MARKET_SELECTIONS', 'NO_WIN_MARKET_AS_OF',
        'MARKET_FIELD_MISMATCH', 'MARKET_HAS_UNKNOWN_SELECTION',
        'MISSING_OR_INVALID_ACTIVE_WIN_ODDS',
    }
    fundamental_ready = bool(probs) and not any(p not in market_codes for p in problems)
    market_ready = not any(p in market_codes for p in problems)
    model_ready = fundamental_ready and market_ready

    runner_by = {str(x['selection_id']): x for x in roster}
    all_ids = sorted(roster_ids | set(f_by) | set(m_by), key=_number)
    entries = []
    for selection in all_ids:
        f, market, rr = f_by.get(selection), m_by.get(selection), runner_by.get(selection)
        scratched = bool(f['scratched']) if f else (bool(rr['scratched']) if rr else False)
        p = probs.get(selection) if f and not scratched and fundamental_ready else None
        available = (float(market['odds_decimal']) if market and market['odds_decimal'] is not None
                     and not scratched else None)
        fair = 1 / p if p is not None and p > 0 else None
        # Require both edge and a separate model-error margin, each applied on the fair price.
        min_quote = fair * (1 + edge_target) * (1 + safety_margin) if fair else None
        ev = p * available - 1 if p is not None and available is not None and available > 1 else None
        if scratched:
            status, why = 'PASS', 'SCRATCHED'
        elif not fundamental_ready:
            status, why = 'PASS', 'INCOMPLETE_OR_UNVERIFIED_FUNDAMENTALS'
        elif not market_ready:
            status, why = 'PASS', 'INCOMPLETE_WIN_MARKET'
        elif available is None or available <= 1:
            status, why = 'PASS', 'NO_VALID_WIN_PRICE'
        elif available >= min_quote:
            status, why = 'WATCH', 'PRICE_EXCEEDS_UNCALIBRATED_BASELINE_MINIMUM'
        else:
            status, why = 'PASS', 'PRICE_BELOW_RESEARCH_MINIMUM'
        entries.append({
            'selection_id': selection,
            'horse_name': (f or rr or {}).get('horse_name'),
            'post_position': (f or rr or {}).get('post_position'),
            'driver_or_jockey': (f or rr or {}).get('driver_or_jockey'),
            'scratched': scratched,
            'history_total_starts': None if not f else f.get('history_total_starts'),
            'history_total_wins': None if not f else f.get('history_total_wins'),
            'history_source_quality': None if not f else f.get('data_quality'),
            'p_win': p,
            'fair_odds': fair,
            'minimum_watch_odds': min_quote,
            'available_odds': available,
            'theoretical_ev': ev,
            'status': status, 'reason': why,
        })
    valid_market = {s: float(m_by[s]['odds_decimal']) for s in active_ids
                    if s in m_by and m_by[s].get('odds_decimal') is not None
                    and float(m_by[s]['odds_decimal']) > 1}
    implied = {s:1/o for s,o in valid_market.items()}
    total_implied = sum(implied.values())
    market_p = {s: v/total_implied for s,v in implied.items()} if len(valid_market)==len(active_ids) and total_implied else {}
    for entry in entries:
        entry['normalized_market_p'] = market_p.get(entry['selection_id'])
    feature_counts = {
        'known_history_active': known,
        'total_active': len(active),
        'distance_m_present': int(race['distance_m'] is not None),
        'start_method_present': int(bool(race['start_method'])),
        'post_position_active': sum(r.get('post_position') is not None for r in active),
        'driver_active': sum(bool(r.get('driver_or_jockey')) for r in active),
        'trainer_active': sum(bool(r.get('trainer')) for r in active),
        'current_year_starts_active': sum(r.get('current_year_starts') is not None for r in active),
        'record_auto_active': sum(bool(r.get('record_auto')) for r in active),
        'record_volt_active': sum(bool(r.get('record_volt')) for r in active),
    }
    return {
        'race': {k: race[k] for k in ('race_id','race_date','country','track','race_no','start_time_utc','discipline','distance_m','start_method')},
        'decision_at_utc': canonical_cutoff,
        'minutes_before_recorded_start': (start - cutoff).total_seconds()/60,
        'model_version': MODEL_VERSION,
        'model_scope': 'HISTORICAL_WIN_RATE_ONLY; UNVALIDATED_SHADOW; NO_REAL_BETS',
        'fundamental_observed_at_utc': ft, 'market_observed_at_utc': mt,
        'field_size': len(all_ids), 'active_runners': len(active),
        'known_history_runners': known,
        'feature_coverage': feature_counts,
        'probability_sum': sum(p for p in (x['p_win'] for x in entries) if p is not None),
        'theoretical_market_implied_sum': total_implied,
        'fundamental_ready_for_research': fundamental_ready,
        'win_market_complete': market_ready,
        'model_ready_for_research': model_ready,
        'blocks': sorted(set(problems)),
        'decision_authority': 'RESEARCH_ONLY_NO_BET',
        'runner_rows': entries,
        'caveats': [
            'Source timestamps are archived observations, not independently proven publication times.',
            'Canonical runner roster and recorded start were reconstructed from an archival mutable database.',
            'FUNDAMENTAL_CHAMPION_V1_1 uses only historical win rates; it does not price form, distance, driver, class or pace.',
            'Displayed EV is model-implied only; the model has not been prospectively calibrated.',
            'WIN totalisator odds can change and are not guaranteed executable prices.',
        ],
    }


def write_report(report: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'race_core.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    fields = ['selection_id','horse_name','scratched','history_total_starts','history_total_wins',
              'p_win','fair_odds','minimum_watch_odds','available_odds','theoretical_ev',
              'normalized_market_p','status','reason']
    with (folder/'race_core.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(report['runner_rows'])
    r=report['race']
    lines=[f"# CORE-001 – {r['track']} løp {r['race_no']} ({r['race_date']})",'',
           f"**Arkivert start:** {r['start_time_utc']} | **Beslutningsklokke:** {report['decision_at_utc']}",
           f"**Felt:** {report['field_size']} registrert, {report['active_runners']} aktive | **Modell:** {report['model_version']}",
           f"**Status:** {'RESEARCH-ONLY (full feltkohort)' if report['model_ready_for_research'] else 'PASS – BLOCKED'}",'',
           'p(win) er kun historisk seiersrate med Champion V1.1 shrinkage. Minsteodds er **eksperimentell WATCH-grense**, ikke autorisert BET-grense.',
           '', '| # | Hest | Starter/seire | p(win) | Fair | WATCH fra | Vinnerodds | Modell-EV | Status |',
           '|---:|---|---:|---:|---:|---:|---:|---:|---|']
    def fmt(v:float|None, factor:float=1, suffix:str='')->str:
        return '–' if v is None else f'{v*factor:.2f}{suffix}'
    for x in report['runner_rows']:
        hist = f"{x['history_total_starts']}/{x['history_total_wins']}" if x['history_total_starts'] is not None else '–'
        lines.append(f"| {x['selection_id']} | {x['horse_name'] or '–'}{' (strøket)' if x['scratched'] else ''} | {hist} | {fmt(x['p_win'],100,'%')} | {fmt(x['fair_odds'])} | {fmt(x['minimum_watch_odds'])} | {fmt(x['available_odds'])} | {fmt(x['theoretical_ev'],100,'%')} | {x['status']} |")
    lines+=['',f"**Fundamentalt kildeobservert:** {report['fundamental_observed_at_utc']} | **Marked observert:** {report['market_observed_at_utc']}",
            f"**p(win)-sum:** {report['probability_sum']:.9f} | **Blokkeringer:** {', '.join(report['blocks']) or 'ingen for smal baseline'}",'',
            '## Begrensninger']+[f'- {c}' for c in report['caveats']]
    (folder/'race_core.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description='CORE-001 read-only full-field WIN review')
    parser.add_argument('--db',required=True)
    parser.add_argument('--race-id',required=True)
    parser.add_argument('--as-of',required=True,help='ISO timestamp with explicit UTC offset')
    parser.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    p=Path(args.db).resolve()
    if not p.is_file():
        parser.error('Database path does not exist')
    connection=sqlite3.connect(f'file:{p.as_posix()}?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    try: report=analyze_race(connection,race_id=args.race_id,decision_at=args.as_of)
    finally: connection.close()
    write_report(report,Path(args.out))
    print(json.dumps({'race_id':args.race_id,'runners':report['field_size'],
                      'active':report['active_runners'],'status':'RESEARCH_ONLY' if report['model_ready_for_research'] else 'BLOCKED',
                      'watch':sum(x['status']=='WATCH' for x in report['runner_rows']),
                      'report_path':str(Path(args.out)/'race_core.md')},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
