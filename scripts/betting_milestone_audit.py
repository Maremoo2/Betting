"""Evidence-only audit over archived HBI SQLite. Does not write to SQLite.

No model/market blending, EV, wagers, or historical reconciliation authority.
Run with --db /path/data/hbi.sqlite --output-dir /path/out --as-of UTC.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from urllib.parse import quote

DEFAULT_END = datetime(2026, 10, 30, 14, 49, 42, tzinfo=UTC)
PRIOR_STARTS = 6
SENTINEL = -0.02  # Explicitly observed in archived Rikstoto snapshots; do not assume for other codes.
P0_RACES = {
    'RIKSTOTO:S2_NR_2026-10-09:5',
    'RIKSTOTO:MO_NR_2026-10-17:10',
    'RIKSTOTO:S4_NR_2026-10-21:9',
    'RIKSTOTO:S2_NR_2026-10-22:5',
    'RIKSTOTO:S3_NR_2026-10-25:11',
}
TICKET = 'a55a504a-bc34-487d-aced-75326dcb2b59'


def stamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None
    return t.astimezone(UTC) if t.utcoffset() is not None else None


def db_open(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = 'file:' + quote(str(path.resolve())) + '?mode=ro&immutable=1'
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as file:
        for b in iter(lambda: file.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def dicts(conn, query, args=()):
    return [dict(x) for x in conn.execute(query, args)]


def latest_cohort(conn, table, rid, cutoff, product=None):
    if table == 'runner_fundamental_snapshots':
        extra, args = '', (rid,)
    elif table == 'provider_market_snapshots':
        extra, args = " AND product='V'", (rid,)
    else:
        raise ValueError('Unsupported table')
    # Choose latest eligible coherent observed-time cohort (do not mix individual horses).
    times = conn.execute('SELECT DISTINCT observed_at_utc FROM '+table+' WHERE race_id=?'+extra,
                         args).fetchall()
    eligible = [x[0] for x in times if (t := stamp(x[0])) is not None and t <= cutoff]
    if not eligible:
        return [], None
    selected = max(eligible, key=lambda x: stamp(x))
    rows = dicts(conn, 'SELECT * FROM '+table+' WHERE race_id=?'+extra+' AND observed_at_utc=?',
                 (rid, selected))
    # Future source-internal timestamps block the whole cohort; do not cherry-pick rows.
    col = 'feature_as_of_utc' if table == 'runner_fundamental_snapshots' else 'provider_updated_at_utc'
    if any(x[col] and ((u := stamp(x[col])) is None or u > cutoff) for x in rows):
        return [], selected
    return rows, selected


def active_market_cohort(rows, active):
    """Strictly align priced active selections. Only exact unpriced -0.02 off-field rows allowed.

    Does not prove actual scratches; only reconstructs frozen selection-set or
    current archived roster selection-set without independently attesting it.
    """
    ids = [str(x['selection_key']) for x in rows]
    if len(ids) != len(set(ids)):
        return None, 'DUPLICATE_SELECTION'
    prices = {}
    sentinels = []
    for row in rows:
        key = str(row['selection_key'])
        raw = row['odds_decimal']
        try:
            price = float(raw)
        except (ValueError, TypeError):
            return None, 'UNKNOWN_ODDS_VALUE'
        if not math.isfinite(price):
            return None, 'NONFINITE_ODDS'
        if key in active:
            if price <= 1:
                return None, 'INVALID_ACTIVE_PRICE'
            prices[key] = price
        elif price == SENTINEL:
            sentinels.append(key)
        else:
            return None, 'EXTRA_PRICE_OR_UNKNOWN_MARKER'
    if not active or set(prices) != set(active):
        return None, 'MISSING_ACTIVE_PRICE'
    return {'odds': prices, 'excluded_unpriced_keys': sorted(sentinels)}, None


def norm_odds(odds):
    inv = {k: 1 / v for k, v in odds.items()}
    z = sum(inv.values())
    return {k: v / z for k, v in inv.items()}


def champion_baseline(fund, active):
    """Same 6-start empirical Bayes equation as CORE-001; research evidence only."""
    if len(active) < 2:
        return None
    by = {str(x['selection_id']): x for x in fund}
    if len(by) != len(fund) or not set(active).issubset(by):
        return None
    n = len(active)
    strength = {}
    for sid in active:
        row = by[sid]
        starts, wins = row['history_total_starts'], row['history_total_wins']
        if (row['full_field_history_complete'] != 1 or not row['source_uri']
            or type(starts) is not int or type(wins) is not int
            or starts < 0 or not 0 <= wins <= starts):
            return None
        strength[sid] = (wins + PRIOR_STARTS / n) / (starts + PRIOR_STARTS)
    total = sum(strength.values())
    return {k: v / total for k, v in strength.items()}


def _parse_distribution(raw):
    try:
        data = json.loads(raw)
        p = {str(k): float(v) for k, v in data.items()}
        if len(p) < 2 or any(not 0 < v < 1 or not math.isfinite(v) for v in p.values()) or abs(sum(p.values())-1)>1e-6:
            return None
        return p
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def raw_source_status(conn, *, race_id, cutoff, race_no, raceday_key):
    """Actual retained provider payload observation times, never a provider-availability claim."""
    configs=(('RACEDAY_STARTS','rikstoto',raceday_key),
             ('FULL_FIELD_ONLY_V1','atg',race_id))
    out={}
    for category,provider,key in configs:
        timestamps=[stamp(x[0]) for x in conn.execute(
            'SELECT observed_at_utc FROM provider_payloads WHERE provider=? AND category=? '
            'AND provider_raceday_key=? AND race_number=?',
            (provider,category,key,race_no))]
        valid=sorted(t for t in timestamps if t is not None)
        pre=[t for t in valid if t<=cutoff]
        out[category]={'retained_events':len(timestamps),
                       'pre_t4_events':len(pre),
                       'latest_pre_t4_observed_utc':pre[-1].isoformat() if pre else None,
                       'status':'OBSERVED_BEFORE_T4' if pre else
                           ('FIRST_OBSERVED_ONLY_AFTER_T4' if valid else 'NO_RETAINED_PAYLOAD')}
    return out


def audit_card(conn, dates, as_of):
    day_rows=[]; race_rows=[]; examples=[]
    for day in dates:
        races=dicts(conn,"SELECT * FROM races WHERE race_date=? AND lower(discipline)='trot' AND instr(track,'/')=0 ORDER BY start_time_utc,race_id",(day,))
        selected=[]; duplicate_ids=[]
        # Research-only physical identity heuristic; do not relabel providers.
        for race in races:
            st=stamp(race['start_time_utc'])
            if st is None: continue
            same=next((x for x in selected if x['track']==race['track'] and x['race_no']==race['race_no'] and abs((stamp(x['start_time_utc'])-st).total_seconds())<=600),None)
            if same: duplicate_ids.append(race['race_id']);continue
            selected.append(race)
        counters=Counter()
        for race in selected:
            start=stamp(race['start_time_utc']);cutoff=start-timedelta(minutes=4)
            if cutoff>as_of:
                counters['future_t4_not_observed']+=1
                continue
            counters['eligible_races']+=1
            rid=race['race_id']
            roster=dicts(conn,'SELECT selection_id,scratched,horse_name FROM runners WHERE race_id=?',(rid,))
            active={str(x['selection_id']) for x in roster if not bool(x['scratched'])}
            if not active:
                counters['no_archived_roster']+=1
            else: counters['has_archived_roster']+=1
            ref=conn.execute("SELECT provider_raceday_key FROM provider_race_refs "
                             "WHERE race_id=? AND provider='rikstoto' LIMIT 1",(rid,)).fetchone()
            raw=raw_source_status(conn,race_id=rid,cutoff=cutoff,race_no=race['race_no'],
                                  raceday_key=ref[0] if ref else None) if ref else None
            if raw:
                for category,rec in raw.items():
                    key='starts' if category=='RACEDAY_STARTS' else 'history'
                    counters[key+'_'+rec['status'].lower()]+=1
            f,ft=latest_cohort(conn,'runner_fundamental_snapshots',rid,cutoff)
            m,mt=latest_cohort(conn,'provider_market_snapshots',rid,cutoff)
            fids=[str(x['selection_id']) for x in f]
            fdict={str(x['selection_id']):x for x in f}
            valid_f=bool(active and len(fids)==len(set(fids)) and set(active).issubset(fdict) and
                all(fdict[s]['full_field_history_complete']==1 and fdict[s]['history_total_starts'] is not None and
                    fdict[s]['history_total_wins'] is not None and fdict[s]['source_uri'] for s in active))
            if valid_f: counters['full_history_t4']+=1
            else: counters['no_full_history_t4']+=1
            mk, why=active_market_cohort(m,active)
            valid_m=mk is not None
            if valid_m: counters['full_win_market_t4']+=1
            else:counters['no_full_win_market_t4']+=1
            if valid_f and valid_m:counters['both_t4']+=1
            p=champion_baseline(f,active) if valid_f else None
            if p is not None and valid_m and len(active)>=2:
                pm=norm_odds(mk['odds'])
                examples.append({'date':day,'race_id':rid,'race_number':race['race_no'],'track':race['track'],
                                 'country':race['country'],'start_time_utc':start.isoformat(),
                                 'cutoff_utc':cutoff.isoformat(), 'fundamentals_observed_utc':ft,
                                 'market_observed_utc':mt, 'active_current_roster_count':len(active),
                                 'champion_pwin':p,'market_p':pm,
                                 'horse_name':{str(x['selection_id']):x['horse_name'] for x in roster if str(x['selection_id']) in active},
                                 'odds':mk['odds'],'roster_pit_attested':False,'betting_authority':False})
            race_rows.append({'date':day,'race_id':rid,'country':race['country'],'track':race['track'],
                              'race_no':race['race_no'],'cutoff_utc':cutoff.isoformat(),
                              'archived_active_roster':len(active),'fundamentals_utc':ft,'win_market_utc':mt,
                              'fund_complete_t4':valid_f,'win_complete_t4':valid_m,
                              'both_t4':valid_f and valid_m,'market_blocker':why or '',
                              'roster_pit_attested':False,
                              'raw_starts_observation_status':raw['RACEDAY_STARTS']['status'] if raw else 'NO_RIKSTOTO_REF',
                              'raw_history_observation_status':raw['FULL_FIELD_ONLY_V1']['status'] if raw else 'NO_RIKSTOTO_REF'})
        day_rows.append({'date':day,'total_trot_non_composite_records':len(races),
                         'duplicate_race_ids_by_heuristic':duplicate_ids,
                         'physically_distinct_heuristic':len(selected),**dict(counters),
                         'scope':'archived_utc_Tminus4_no_roster_PIT_attestation'})
    return day_rows,race_rows,examples


def audit_core004_feature_readiness(conn, examples):
    """Inspect actual market-free career features; never learn coefficients."""
    results=[]
    for example in examples:
        rid=example['race_id']
        cutoff=stamp(example['cutoff_utc'])
        fund,ft=latest_cohort(conn,'runner_fundamental_snapshots',rid,cutoff)
        by={str(x['selection_id']):x for x in fund}
        active=set(example['champion_pwin'])
        reasons=[]
        for sid in active:
            r=by.get(sid, {})
            vals=[r.get(k) for k in ('history_total_starts','history_total_wins',
                                    'history_total_seconds','history_total_thirds',
                                    'history_total_earnings')]
            if not all(v is not None for v in vals):
                reasons.append('MISSING_CAREER_FEATURES');continue
            starts,wins,seconds,thirds,earnings=vals
            if not (all(type(v) is int and v >= 0 for v in vals[:4])
                    and type(earnings) in (int,float) and math.isfinite(float(earnings))
                    and earnings >= 0 and wins+seconds+thirds<=starts):
                reasons.append('INVALID_CAREER_FEATURES')
        results.append({'date':example['date'],'race_id':rid,'active_runners':len(active),
                        'snapshot_utc':ft,
                        'lifetime_core004_factors_valid':not reasons,
                        'reasons':sorted(set(reasons)),
                        'recent_five_form_verified':False,
                        'driver_distance_class_effects_verified':False,
                        'roster_pit_attested':False,'model_coefficients_trained':False,
                        'promotion_or_bet_eligible':False})
    valid=sum(z['lifetime_core004_factors_valid'] for z in results)
    return {'scope':'archived CORE-001 fullfield examples; PIT not attested',
            'races_with_lifetime_feature_coverage':valid,'tested_races':len(results),
            'races_with_pit_verified_recent_form':0,
            'can_fit_validated_multifactor':False,'races':results}


def audit_replay(conn):
    out=[]
    for rid in sorted(P0_RACES):
        data=dicts(conn,'SELECT d.*,p.market_odds_json,p.recorded_at_utc FROM shadow_decision_runs d JOIN decision_provenance p ON d.decision_run_id=p.decision_run_id WHERE d.race_id=?',(rid,))
        if len(data)!=1: out.append({'race_id':rid,'status':'MISSING_OR_AMBIGUOUS'});continue
        d=data[0];pmarket=_parse_distribution(d['market_probabilities_json'])
        if not pmarket:out.append({'race_id':rid,'status':'BAD_FROZEN_MARKET'});continue
        original=dicts(conn,"SELECT selection_key,odds_decimal FROM provider_market_snapshots WHERE race_id=? AND product=? AND observed_at_utc=?",(rid,d['product'],d['source_market_observed_at_utc']))
        m,error=active_market_cohort(original,set(pmarket))
        normalized=norm_odds(m['odds']) if m else None
        max_source_p_delta=max(abs(normalized[k]-pmarket[k]) for k in pmarket) if normalized else None
        prov=json.loads(d['market_odds_json'])
        prov_norm=norm_odds(prov) if set(prov)==set(pmarket) and all(float(x)>1 for x in prov.values()) else None
        max_prov_p_delta=max(abs(prov_norm[k]-pmarket[k]) for k in pmarket) if prov_norm else None
        record_at=stamp(d['recorded_at_utc']);first_at=stamp(d['created_at_utc'])
        out.append({'race_id':rid,'decision_run_id':d['decision_run_id'],'decision_status':d['decision_status'],
                    'tickets':d['ticket_count'],'source_observed_utc':d['source_market_observed_at_utc'],
                    'provenance_recorded_utc':d['recorded_at_utc'],
                    'provenance_delay_minutes':round((record_at-first_at).total_seconds()/60,3) if record_at and first_at else None,
                    'source_market_keys':len(m['odds']) if m else 0,
                    'excluded_unpriced_original_keys':m['excluded_unpriced_keys'] if m else [],
                    'source_market_error':error,'source_market_max_abs_delta':max_source_p_delta,
                    'attached_provenance_max_abs_delta':max_prov_p_delta,
                    'classification':'SOURCE_RECONSTRUCTED_LEGACY_ATTACHMENT_MISMATCH' if
                        max_source_p_delta is not None and max_source_p_delta<=1e-12 and
                        max_prov_p_delta is not None and max_prov_p_delta>1e-12 else 'NOT_RECONCILED',
                    'changes_frozen_decision':False})
    return out


def audit_settlement(conn):
    row=conn.execute('SELECT * FROM shadow_tickets WHERE ticket_id=?',(TICKET,)).fetchone()
    if row is None:return {'ticket_id':TICKET,'status':'MISSING'}
    d=dict(row);race=conn.execute('SELECT * FROM races WHERE race_id=?',(d['race_id'],)).fetchone()
    outcome=conn.execute('SELECT * FROM outcomes WHERE race_id=?',(d['race_id'],)).fetchone()
    # Stored provider_payloads only include starts/full-field and contender; there is
    # no retained primary complete_results/raceresults for adjudication.
    evidence=dicts(conn,'SELECT provider,category,COUNT(*) n FROM provider_payloads WHERE provider_raceday_key=? GROUP BY provider,category',(d['provider_raceday_key'],))
    return {'ticket_id':TICKET,'race_id':d['race_id'],'product':d['product'],'status':d['status'],
            'selections_json':d['selections_json'],'stake_nok':d['stake_nok'],
            'start_utc':race['start_time_utc'] if race else None,
            'cached_winner':outcome['winner_selection_id'] if outcome else None,
            'outcome_present':bool(outcome),
            'provider_payload_categories_for_raceday':evidence,
            'complete_result_isComplete_proven':False,'participant_finish_proven_by_official_payload':False,
            'winning_dividend_status_proven_by_official_payload':False,
            'action':'BLOCKED_READ_ONLY_NO_SETTLEMENT','authorized_booked_return_nok':None}


def audit_paired(conn, as_of):
    """Retrospective descriptive only: assess frozen pre-race distributions with outcomes.

    Does not use closing quotes for prediction, does not fit parameters, and does not
    promote a Challenger. One earliest eligible frozen decision per physical race.
    """
    rows=dicts(conn,'SELECT d.*,o.winner_selection_id,o.settled_at_utc FROM shadow_decision_runs d JOIN outcomes o USING(race_id) ORDER BY d.race_id,d.created_at_utc')
    used=set();fail=Counter();out=[]
    for r in rows:
        rid=r['race_id']
        if rid in used: continue
        decision=stamp(r['created_at_utc']);race_start=stamp(r['race_start_time_utc']);source=stamp(r['source_market_observed_at_utc'])
        if (not all((decision,race_start,source)) or not (source<=decision<race_start)
                or decision>as_of or stamp(r['settled_at_utc']) is None
                or stamp(r['settled_at_utc'])>as_of):
            fail['BAD_FROZEN_TIMING']+=1;continue
        dists={n:_parse_distribution(r[col]) for n,col in [('fundamental','fundamental_probabilities_json'),('market','market_probabilities_json'),('combined','combined_probabilities_json')]}
        if any(x is None for x in dists.values()) or not (set(dists['fundamental'])==set(dists['market'])==set(dists['combined'])):
            fail['NO_COMPARABLE_DISTRIBUTIONS']+=1;continue
        winner=str(r['winner_selection_id']);
        if winner not in dists['fundamental']:
            fail['WINNER_NOT_IN_FROZEN_FIELD']+=1;continue
        used.add(rid); scores={}
        for label,p in dists.items():
            scores[label+'_logloss']=-math.log(p[winner]);scores[label+'_brier']=sum((v-(k==winner))**2 for k,v in p.items())
            scores[label+'_winner_p']=p[winner]
        out.append({'race_id':rid,'race_day':race_start.date().isoformat(),'country':rid.split(':')[0],
                    'winner':winner,'selection_count':len(dists['market']),
                    'decision_time':r['created_at_utc'],'status':r['decision_status'],**scores})
    cols=['fundamental','market','combined']
    metrics={'races':len(out),'denominator_candidate_rows':len(rows),'distinct_races_scored':len(used),
             'excluded_reasons_count_by_decision':dict(fail),
             'mean_logloss':{m:mean(x[m+'_logloss'] for x in out) if out else None for m in cols},
             'mean_brier':{m:mean(x[m+'_brier'] for x in out) if out else None for m in cols},
             'first_decision_day':min((x['race_day'] for x in out),default=None),
             'last_decision_day':max((x['race_day'] for x in out),default=None),
             'provenance_warning':'legacy 5 mismatch cases are not dropped or reclassified by this outcome-only report',
             'evidence_level':'RETROSPECTIVE_DESCRIPTIVE_NOT_PRE_REGISTERED_OOS',
             'market_used_in_combined':True,'betting_authority':False}
    if out:
        # Exploratory uncertainty, block-resampled by race day to avoid pretending
        # dozens of races from one card are independent. Not a preregistered test.
        days = sorted({r['race_day'] for r in out})
        by_day = {day: [r for r in out if r['race_day']==day] for day in days}
        rng = random.Random(20261030)
        sampled=[]
        for _ in range(1500):
            draws = [by_day[days[rng.randrange(len(days))]] for _ in days]
            subset = [r for block in draws for r in block]
            sampled.append(sum(r['combined_logloss']-r['market_logloss'] for r in subset)/len(subset))
        sampled.sort()
        metrics['paired_combined_minus_market_logloss_dayblock_bootstrap_95pct'] = [
            sampled[int(.025 * (len(sampled)-1))], sampled[int(.975 * (len(sampled)-1))]
        ]
        metrics['day_blocks'] = len(days)
        metrics['bootstrap_replicates'] = 1500
        metrics['bootstrap_interpretation']='Exploratory resampling; not preregistered OOS proof or promotion test'
        metrics['paired_market_minus_fundamental_mean_logloss']=mean(x['market_logloss']-x['fundamental_logloss'] for x in out)
        metrics['paired_combined_minus_market_mean_logloss']=mean(x['combined_logloss']-x['market_logloss'] for x in out)
    return metrics,out


def as_json(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')


def as_csv(path, rows):
    if not rows:return
    cols=list(rows[0])
    with path.open('w',newline='',encoding='utf-8') as file:
        w=csv.DictWriter(file,fieldnames=cols);w.writeheader();w.writerows(rows)


def run(db_path,output_dir,as_of=DEFAULT_END,dates=None):
    db_path=Path(db_path);output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    checksum_before=sha256(db_path)
    dates=dates or ['2026-10-27','2026-10-28','2026-10-29','2026-10-30']
    with db_open(db_path) as conn:
        days,races,examples=audit_card(conn,dates,as_of)
        replay=audit_replay(conn)
        core004=audit_core004_feature_readiness(conn,examples)
        settlement=audit_settlement(conn)
        evaluation,paired=audit_paired(conn,as_of)
    checksum_after=sha256(db_path)
    if checksum_before!=checksum_after:raise AssertionError('Source DB mutated during audit')
    # All user-facing structured files are explicit: no fake success for uncovered races.
    as_json(output_dir/'day_coverage.json',{'schema':'CORE_EVIDENCE_CARD_AUDIT_V1','as_of_utc':as_of.isoformat(),
                                            'source_db_sha256':checksum_before,'days':days})
    as_csv(output_dir/'race_coverage.csv',races)
    as_json(output_dir/'eligible_full_field_examples.json',examples)
    as_json(output_dir/'p0_replay_original_source.json',replay)
    as_json(output_dir/'core004_feature_readiness.json',core004)
    as_json(output_dir/'p0_settlement_source_gate.json',settlement)
    as_json(output_dir/'p1_retrospective_metrics.json',evaluation)
    as_csv(output_dir/'p1_matched_frozen_decisions.csv',paired)
    manifest={'db_bytes':db_path.stat().st_size,'db_sha256_before':checksum_before,
              'db_sha256_after':checksum_after,'source_read_only':True,'as_of_utc':as_of.isoformat(),
              'output_files':{p.name:sha256(p) for p in sorted(output_dir.iterdir())
                              if p.name in {'day_coverage.json','race_coverage.csv','eligible_full_field_examples.json',
                                            'p0_replay_original_source.json','p0_settlement_source_gate.json',
                                            'core004_feature_readiness.json','p1_retrospective_metrics.json',
                                            'p1_matched_frozen_decisions.csv'}}}
    as_json(output_dir/'manifest.json',manifest)
    return {'days':days,'replay':replay,'settlement':settlement,'paired':evaluation,'manifest':manifest,
            'example_count':len(examples),'core004':core004}


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--as-of',default=DEFAULT_END.isoformat())
    p.add_argument('--days',nargs='+',default=['2026-10-27','2026-10-28','2026-10-29','2026-10-30'])
    a=p.parse_args()
    result=run(a.db,a.output_dir,stamp(a.as_of),a.days)
    print(json.dumps({'day_summary':result['days'],'full_field_examples':result['example_count'],
                      'replay_reconstructed':sum(x['classification']=='SOURCE_RECONSTRUCTED_LEGACY_ATTACHMENT_MISMATCH' for x in result['replay'] if 'classification' in x),
                      'settlement':result['settlement']['action'],
                      'paired_races':result['paired']['races'],
                      'source_unchanged':result['manifest']['db_sha256_before']==result['manifest']['db_sha256_after']},indent=2))

if __name__=='__main__':main()
