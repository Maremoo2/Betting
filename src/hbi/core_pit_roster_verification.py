"""Independent, read-only CORE-003 PIT evidence quality audit.

Uses *retained provider payloads*, not a mutable runners table, to reconstruct
selection membership at the earliest of archived canonical and source-stated
scheduled off-times. Neither a fetch-completed timestamp nor source-stated
schedule proves original publication time or actual off-time. This tool NEVER
claims training/OOS/BET authority. It never persists SQLite changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

TOLERANCE = timedelta(minutes=4)


def parse_time(value):
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return result.astimezone(UTC) if result.utcoffset() is not None else None


def latest_asof(conn, query, params, cutoff):
    """Choose latest unambiguous observed source cohort, never arbitrary tie order.

    Conflicting payload bodies sharing the exact same observed instant are unsafe
    even if one happens to be returned first by SQLite; fail closed instead.
    Identical duplicate captures may be represented by the same payload body.
    """
    candidates = []
    for row in conn.execute(query, params):
        observed = parse_time(row['observed_at_utc'])
        if observed is not None and observed <= cutoff:
            candidates.append((observed, row))
    if not candidates:
        return None
    highest = max(observed for observed, _ in candidates)
    latest = [row for observed, row in candidates if observed == highest]
    if len({row['payload_json'] for row in latest}) > 1:
        raise AmbiguousSourceSnapshot('CONFLICTING_SAME_INSTANT_SOURCE_PAYLOAD')
    return min(latest, key=lambda row: str(row['payload_id']))


class AmbiguousSourceSnapshot(ValueError):
    """An observed-time tie has conflicting primary source contents."""



def source_rows(conn, provider, category, raceday, race_no):
    return conn.execute(
        "SELECT observed_at_utc, payload_json, source_uri, payload_id FROM provider_payloads "
        "WHERE provider=? AND category=? AND provider_raceday_key=? AND race_number=?",
        (provider, category, raceday, race_no),
    ).fetchall()


def parse_rikstoto_roster(raw, race_no, raceday):
    """Full-field membership, scratch and source names as observed, not identity promotion."""
    if raw is None:
        return None, 'NO_PRE_CUTOFF_RIKSTOTO_STARTS'
    try:
        parsed = json.loads(raw)
        items = parsed['result'][str(race_no)]
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        return None, 'INVALID_STARTS_ENVELOPE'
    if not isinstance(items, list) or len(items) < 2:
        return None, 'INCOMPLETE_STARTS_FIELD'
    roster = {}
    for item in items:
        if not isinstance(item, dict):
            return None, 'MALFORMED_START_ROW'
        sid = item.get('startNumber')
        name = item.get('horseName')
        scratch = item.get('isScratched')
        if type(sid) is not int or sid < 1 or not isinstance(name, str) or not name.strip() or type(scratch) is not bool:
            return None, 'MALFORMED_START_ROW'
        if item.get('raceKey') != f'{raceday}#{race_no}':
            return None, 'RACE_KEY_MISMATCH'
        key = str(sid)
        if key in roster:
            return None, 'DUPLICATE_START_NUMBER'
        roster[key] = {'name':name.strip(), 'scratched':scratch,
                       'reg':item.get('horseRegistrationNumber')}
    active = {key for key, item in roster.items() if not item['scratched']}
    if len(active) < 2:
        return None, 'INSUFFICIENT_ACTIVE_STARTS'
    return {'all':roster,'active':active}, None


def parse_atg_identity(payload, active, source_names):
    if not isinstance(payload, dict) or payload.get('passed') is not True or payload.get('probe_only') is not False:
        return False, 'ATG_FULL_FIELD_GATE_NOT_PASSED'
    rows = payload.get('runners')
    if not isinstance(rows, list):
        return False, 'ATG_RUNNERS_MISSING'
    identity = {}
    for row in rows:
        if not isinstance(row, dict):
            return False, 'ATG_RUNNER_MALFORMED'
        key = str(row.get('selection_id'))
        if key in identity:
            return False, 'ATG_DUPLICATE_ID'
        identity[key] = row
    listed = payload.get('active_selections')
    if not isinstance(listed, list) or {str(x) for x in listed} != active or len(listed)!=len(active):
        return False, 'ATG_ACTIVE_SET_MISMATCH'
    if set(identity) != active or payload.get('active_runners') != len(active) or payload.get('matched_complete_runners') != len(active):
        return False, 'ATG_IDENTITY_FIELD_MISMATCH'
    stable_provider_ids = []
    for key in active:
        row = identity[key]
        if row.get('horse_name') != source_names[key]['name']:
            return False, 'ATG_HORSE_NAME_MISMATCH'
        if row.get('schema_ok') is not True or not row.get('provider_horse_id') or row.get('reason') is not None:
            return False, 'ATG_IDENTITY_UNVERIFIED'
        if row.get('match_method') not in {'EXACT_REGISTRATION', 'UNIQUE_NAME_AND_PROGRAM_NUMBER'}:
            return False, 'ATG_MATCH_METHOD_UNVERIFIED'
        raw_id = row['provider_horse_id']
        if type(raw_id) is int and raw_id > 0:
            stable_provider_ids.append(str(raw_id))
        elif isinstance(raw_id, str) and raw_id.strip() and raw_id.strip().isdigit() and int(raw_id.strip()) > 0:
            stable_provider_ids.append(str(int(raw_id.strip())))
        else:
            return False, 'ATG_PROVIDER_HORSE_ID_NOT_STABLE'
    if len(stable_provider_ids) != len(set(stable_provider_ids)):
        return False, 'ATG_DUPLICATED_PROVIDER_HORSE_ID'
    return True, None


def latest_cohort(conn, table, race_id, cutoff, product=None):
    if table not in {'runner_fundamental_snapshots','provider_market_snapshots'}:
        raise ValueError('Unknown snapshot table')
    product_clause = " AND product='V'" if product else ''
    times = conn.execute('SELECT DISTINCT observed_at_utc FROM '+table+' WHERE race_id=?'+product_clause,(race_id,)).fetchall()
    eligible = [(parse_time(r[0]),r[0]) for r in times]
    eligible = [x for x in eligible if x[0] is not None and x[0]<=cutoff]
    if not eligible:
        return [],None
    ts = max(eligible,key=lambda x:x[0])[1]
    rows = conn.execute('SELECT * FROM '+table+' WHERE race_id=?'+product_clause+' AND observed_at_utc=?',(race_id,ts)).fetchall()
    internal = 'feature_as_of_utc' if table == 'runner_fundamental_snapshots' else 'provider_updated_at_utc'
    if any(row[internal] and (parse_time(row[internal]) is None or parse_time(row[internal])>cutoff) for row in rows):
        return [],ts
    return rows,ts


def good_fundamentals(rows, active, roster):
    by={str(r['selection_id']):r for r in rows}
    if len(by)!=len(rows) or set(by)!=set(roster):
        # Require each source-roster member, including scratched rows, to match.
        return False
    for key, record in roster.items():
        if bool(by[key]['scratched']) != bool(record['scratched']):
            return False
    for key in active:
        row=by[key];starts=row['history_total_starts'];wins=row['history_total_wins']
        if row['full_field_history_complete']!=1 or not row['source_uri'] or row['scratched'] not in (0,None):
            return False
        if type(starts) is not int or type(wins) is not int or starts<0 or not 0<=wins<=starts:
            return False
    return True


def good_market(rows, active):
    seen=set();price={}
    for row in rows:
        key=str(row['selection_key'])
        if key in seen:
            return False
        seen.add(key)
        try: v=float(row['odds_decimal'])
        except (TypeError, ValueError, OverflowError):return False
        if not math.isfinite(v):return False
        if key in active:
            if v <=1:return False
            price[key]=v
        elif v != -0.02:  # Explicit archived Rikstoto unpriced marker only
            return False
    return set(price)==active


def audit_race(conn, race_id, *, asof):
    asof=parse_time(asof) if isinstance(asof,str) else asof
    if asof is None:
        raise ValueError('Aware asof required')
    race=conn.execute('SELECT * FROM races WHERE race_id=?',(race_id,)).fetchone()
    if race is None:
        raise ValueError('Unknown race_id')
    refs=conn.execute("SELECT * FROM provider_race_refs WHERE race_id=? AND provider='rikstoto' ORDER BY discovered_at_utc",(race_id,)).fetchall()
    canonical=parse_time(race['start_time_utc'])
    if canonical is None or not refs:
        return {'race_id':race_id,'status':'BLOCKED','blockers':['NO_CANONICAL_CLOCK_OR_REF'],'pit_certified':False}
    ref=refs[0];key=ref['provider_raceday_key'];rn=int(race['race_no'])
    db_cut=canonical-TOLERANCE
    if db_cut>asof:
        return {'race_id':race_id,'status':'FUTURE','blockers':['TMINUS4_NOT_OBSERVED'],'pit_certified':False}
    # Chronological source candidate: as-of canonical T-4, not merely closest after start.
    try:
        source_atg=latest_asof(conn,
        'SELECT observed_at_utc,payload_json,source_uri,payload_id FROM provider_payloads '
        "WHERE provider='atg' AND category='FULL_FIELD_ONLY_V1' AND provider_raceday_key=? AND race_number=?",
        (race_id,rn),min(db_cut,asof))
    except AmbiguousSourceSnapshot:
        return {'race_id': race_id, 'status': 'BLOCKED', 'pit_certified': False,
                'raw_input_ready_at_cutoff': False,
                'blockers': ['CONFLICTING_SAME_INSTANT_ATG_CLOCK_SOURCE']}
    # A later source refresh cannot extend T-4 past the first *retained*
    # independently reported race clock. Compare the full archived source
    # history observed by canonical T-4, not merely its latest snapshot.
    historic_clocks = []
    invalid_historical_clock = False
    observed_payloads = {}
    for candidate in source_rows(conn, 'atg', 'FULL_FIELD_ONLY_V1', race_id, rn):
        instant = parse_time(candidate['observed_at_utc'])
        if instant is None or instant > min(db_cut, asof):
            continue
        observed_payloads.setdefault(instant.isoformat(), set()).add(
            hashlib.sha256(str(candidate['payload_json']).encode()).hexdigest()
        )
        try:
            payload = json.loads(candidate['payload_json'])
            time = parse_time(payload.get('race_start_utc')) if isinstance(payload, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            time = None
        if time is None:
            invalid_historical_clock = True
        else:
            historic_clocks.append(time)
    conflicting_revisions = any(len(values) > 1 for values in observed_payloads.values())
    reasons=[];atg_payload={};atg_clock=None
    if invalid_historical_clock:reasons.append('INVALID_RETAINED_ATG_RACE_CLOCK')
    if conflicting_revisions:reasons.append('CONFLICTING_RETAINED_ATG_CLOCK_SNAPSHOTS')
    if source_atg is None: reasons.append('NO_PRE_DB_T4_ATG_CLOCK_SOURCE')
    else:
        try:atg_payload=json.loads(source_atg['payload_json'])
        except (TypeError,ValueError):reasons.append('INVALID_ATG_PAYLOAD')
        atg_clock=parse_time(atg_payload.get('race_start_utc')) if isinstance(atg_payload,dict) else None
        if atg_clock is None:reasons.append('ATG_RACE_CLOCK_MISSING')
    earliest_clock = min(historic_clocks) if historic_clocks else None
    anchor=min(canonical,earliest_clock) if earliest_clock else canonical
    cutoff=anchor-TOLERANCE
    try:
        source_starts=latest_asof(conn,
        'SELECT observed_at_utc,payload_json,source_uri,payload_id FROM provider_payloads '
        "WHERE provider='rikstoto' AND category='RACEDAY_STARTS' AND provider_raceday_key=? AND race_number=?",
        (key,rn),min(cutoff,asof))
    except AmbiguousSourceSnapshot:
        return {'race_id': race_id, 'status': 'BLOCKED', 'pit_certified': False,
                'raw_input_ready_at_cutoff': False,
                'blockers': ['CONFLICTING_SAME_INSTANT_RAW_STARTS']}
    try:
        source_atg_strict=latest_asof(conn,
        'SELECT observed_at_utc,payload_json,source_uri,payload_id FROM provider_payloads '
        "WHERE provider='atg' AND category='FULL_FIELD_ONLY_V1' AND provider_raceday_key=? AND race_number=?",
        (race_id,rn),min(cutoff,asof))
    except AmbiguousSourceSnapshot:
        return {'race_id': race_id, 'status': 'BLOCKED', 'pit_certified': False,
                'raw_input_ready_at_cutoff': False,
                'blockers': ['CONFLICTING_SAME_INSTANT_ATG_IDENTITY']}
    roster,roster_err=parse_rikstoto_roster(source_starts['payload_json'] if source_starts else None,rn,key)
    if roster_err:reasons.append(roster_err)
    source_info={}
    for label,row in [('rikstoto_starts',source_starts),('atg_history',source_atg_strict)]:
        source_info[label]={'observed_at_utc':row['observed_at_utc'] if row else None,
                            'payload_sha256':hashlib.sha256(row['payload_json'].encode()).hexdigest() if row else None,
                            'source_uri':row['source_uri'] if row else None}
    identity_ok=False
    if roster:
        if source_atg_strict is None:reasons.append('NO_PRE_CUTOFF_ATG_HISTORY')
        else:
            try:identity_payload=json.loads(source_atg_strict['payload_json'])
            except (TypeError,ValueError): identity_payload={}
            identity_ok,err=parse_atg_identity(identity_payload,roster['active'],roster['all'])
            if err:reasons.append(err)
    fundamentals,_ft=latest_cohort(conn,'runner_fundamental_snapshots',race_id,cutoff)
    market,_mt=latest_cohort(conn,'provider_market_snapshots',race_id,cutoff,product='V')
    if not roster:
        reasons.append('NO_RECONSTRUCTED_ACTIVE_FIELD')
        fund_ready=market_ready=False
    else:
        fund_ready=good_fundamentals(fundamentals,roster['active'],roster['all'])
        market_ready=good_market(market,roster['active'])
        if not fund_ready:reasons.append('INCOMPLETE_FUNDAMENTAL_ASOF_FIELD')
        if not market_ready:reasons.append('INCOMPLETE_WIN_ASOF_FIELD')
    canonical_agreement=None
    if roster:
        mutable=conn.execute('SELECT selection_id,scratched,horse_name FROM runners WHERE race_id=?',(race_id,)).fetchall()
        curr={str(row['selection_id']):{'scratched':bool(row['scratched']),'name':row['horse_name']} for row in mutable}
        canonical_agreement=curr=={k:{'scratched':v['scratched'],'name':v['name']} for k,v in roster['all'].items()}
        if not canonical_agreement:reasons.append('MUTABLE_ROSTER_DIFFERS_FROM_RAW')
    raw_ready=bool(roster and identity_ok and fund_ready and market_ready and canonical_agreement and not invalid_historical_clock and not conflicting_revisions)
    # Publishing/source clock provenance isn't demonstrated by FETCH_COMPLETED timestamp.
    return {'race_id':race_id,'country':race['country'],'track':race['track'],
            'start_database_utc':canonical.isoformat(),
            'start_atg_reported_utc':atg_clock.isoformat() if atg_clock else None,
            'earliest_retained_atg_clock_utc':earliest_clock.isoformat() if earliest_clock else None,
            'retained_atg_clock_count':len(historic_clocks),
            'retained_atg_clock_invalid':invalid_historical_clock,
            'retained_atg_same_instant_conflict':conflicting_revisions,
            'clock_disagreement_seconds':(canonical-earliest_clock).total_seconds() if earliest_clock else None,
            'conservative_cutoff_utc':cutoff.isoformat(),
            'raw_starts_reconstructed':bool(roster),'raw_active_count':len(roster['active']) if roster else None,
            'identity_matched_at_source_time':identity_ok,'fundamental_complete_at_cutoff':fund_ready,
            'win_market_complete_at_cutoff':market_ready,'mutable_roster_agrees_now':canonical_agreement,
            'raw_input_ready_at_cutoff':raw_ready,
            'pit_certified':False,'source_publication_proven':False,
            'blockers':sorted(set(reasons)),'source_snapshots':source_info,
            'status':'SOURCE_OBSERVED_UNATTESTED' if raw_ready else 'BLOCKED'}


def audit_file(db_path, race_ids, *, asof):
    if len(race_ids) != len(set(race_ids)):
        raise ValueError('Duplicate race IDs in denominator/cohort')
    if not race_ids:
        raise ValueError('No race IDs: NO_EVIDENCE, cannot report an assessed card')
    if parse_time(asof) is None:
        raise ValueError('Aware asof required')
    if not db_path.is_file():raise FileNotFoundError(db_path)
    uri='file:'+quote(str(db_path.resolve()))+'?mode=ro&immutable=1'
    conn=sqlite3.connect(uri,uri=True);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    try:
        rows=[audit_race(conn,race_id,asof=asof) for race_id in race_ids]
    finally:conn.close()
    return {'schema':'CORE003_PIT_SOURCE_AUDIT_V1','asof_utc':asof,'read_only':True,
            'authority':'SOURCE_RESEARCH_ONLY_NO_PWIN_EV_OR_BET',
            'total':len(rows),'raw_ready':sum(r.get('raw_input_ready_at_cutoff',False) for r in rows),
            'pit_certified':0,'clock_conflicts':sum(bool(r.get('clock_disagreement_seconds')) for r in rows),
            'blocker_counts':dict(Counter(e for r in rows for e in r['blockers'])),'races':rows}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',required=True,type=Path);p.add_argument('--race-ids',required=True,type=Path)
    p.add_argument('--asof',required=True);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();races=json.loads(args.race_ids.read_text())
    ids=races if isinstance(races,list) and all(isinstance(i,str) for i in races) else [r['race_id'] for r in races]
    report=audit_file(args.db,ids,asof=args.asof)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='races'},indent=2))

if __name__=='__main__':main()
