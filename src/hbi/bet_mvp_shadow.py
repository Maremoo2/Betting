"""BET-MVP-001: join existing CORE-001 Champion and CORE-004 research outputs.

Read-only source database; no collection, no outcome lookup, no model fitting,
no decision persistence, no BET/staking authority. Intended to be added to the
existing hbi package and run against a *separate* archived/collector database.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .core_multifactor_research import MODEL_ID as CORE004_ID
from .core_multifactor_research import analyze_multifactor
from .core_shadow_pilot import _atg_history_source_diagnostic
from .race_core_review import MODEL_VERSION as CHAMPION_ID
from .race_core_review import analyze_race

SCHEMA = "BET_MVP_001_FROZEN_SHADOW_V1"
PINNED_UPSTREAM = "deec4e240293f43261d368c546faa6437f912472"
NO_BET_AUTHORITY = "RESEARCH_ONLY_NEVER_BET"

# Keep market acquisition separate from the two market-free model distributions.
# These are existing source/price failure codes, not new betting thresholds.
MARKET_BLOCKER_CODES = frozenset({
    "INVALID_WIN_MARKET_CLOCK", "DUPLICATE_WIN_MARKET_IN_COHORT",
    "NO_WIN_MARKET_SNAPSHOT_BEFORE_AS_OF", "WIN_MARKET_ROSTER_ID_MISMATCH",
    "DUPLICATE_MARKET_SELECTIONS", "NO_WIN_MARKET_AS_OF",
    "MARKET_FIELD_MISMATCH", "MARKET_HAS_UNKNOWN_SELECTION",
    "MISSING_OR_INVALID_ACTIVE_WIN_ODDS", "MARKET_PROBABILITY_SUM_NOT_ONE",
})


def aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("AS_OF_MUST_HAVE_UTC_OFFSET")
    return parsed.astimezone(UTC)


def read_rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


def sha256(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            dig.update(block)
    return dig.hexdigest()


def source_checks(conn: sqlite3.Connection, race_id: str, as_of: datetime) -> dict[str, Any]:
    """Independent instant-based cross-check, never promotes archived PIT."""
    roster = read_rows(conn, "SELECT selection_id,horse_name,post_position,scratched FROM runners WHERE race_id=?", (race_id,))
    fundamental = read_rows(conn, "SELECT * FROM runner_fundamental_snapshots WHERE race_id=?", (race_id,))
    markets = read_rows(conn, "SELECT selection_key,observed_at_utc,provider_updated_at_utc,odds_decimal,source_uri,provider FROM provider_market_snapshots WHERE race_id=? AND product='V'", (race_id,))
    blocks: set[str] = set()
    if len(roster) < 2:
        blocks.add("NO_COMPLETE_CANONICAL_ROSTER")
    if len({str(x['selection_id']) for x in roster}) != len(roster):
        blocks.add("DUPLICATE_CANONICAL_RUNNER")
    observed: list[tuple[datetime, dict[str, Any]]] = []
    invalid_fund_clocks = False
    for row in fundamental:
        try:
            t = aware(str(row['observed_at_utc']))
        except (ValueError, TypeError):
            invalid_fund_clocks = True
            continue
        if t <= as_of:
            observed.append((t, row))
    if invalid_fund_clocks:
        blocks.add("INVALID_FUNDAMENTAL_OBSERVATION_CLOCK")
    latest = max((t for t, _ in observed), default=None)
    fund_cohort = [r for t,r in observed if t == latest] if latest else []
    if not fund_cohort:
        blocks.add("NO_FUNDAMENTAL_SNAPSHOT_BEFORE_AS_OF")
    if len({str(r['selection_id']) for r in fund_cohort}) != len(fund_cohort):
        blocks.add("DUPLICATE_FUNDAMENTAL_IN_COHORT")
    if {str(r['selection_id']) for r in fund_cohort} != {str(r['selection_id']) for r in roster}:
        blocks.add("FUNDAMENTAL_ROSTER_ID_MISMATCH")
    roster_by = {str(r['selection_id']): r for r in roster}
    for row in fund_cohort:
        sid = str(row['selection_id'])
        try:
            feature_at = aware(str(row['feature_as_of_utc']))
            if feature_at > as_of:
                blocks.add("FEATURE_CLOCK_AFTER_ANALYSIS_AS_OF")
        except (ValueError, TypeError):
            blocks.add("INVALID_FEATURE_CLOCK")
        if sid in roster_by and bool(row['scratched']) != bool(roster_by[sid]['scratched']):
            blocks.add("SCRATCH_COHORT_MISMATCH")
        if not row['source_uri'] or row['full_field_history_complete'] != 1:
            blocks.add("UNVERIFIED_RUNNER_HISTORY")
    market_observed: list[tuple[datetime,dict[str,Any]]] = []
    invalid_market_clocks = False
    for row in markets:
        try:
            t = aware(str(row['observed_at_utc']))
            upd = aware(str(row['provider_updated_at_utc'])) if row['provider_updated_at_utc'] else None
        except (ValueError, TypeError):
            invalid_market_clocks = True
            continue
        if t <= as_of and (upd is None or upd <= as_of):
            market_observed.append((t,row))
    if invalid_market_clocks:
        blocks.add("INVALID_WIN_MARKET_CLOCK")
    mt = max((t for t,_ in market_observed),default=None)
    market_cohort = [row for t,row in market_observed if t == mt] if mt else []
    if len({str(r['selection_key']) for r in market_cohort}) != len(market_cohort):
        blocks.add("DUPLICATE_WIN_MARKET_IN_COHORT")
    if not market_cohort:
        blocks.add("NO_WIN_MARKET_SNAPSHOT_BEFORE_AS_OF")
    elif {str(r['selection_key']) for r in market_cohort} != set(roster_by):
        blocks.add("WIN_MARKET_ROSTER_ID_MISMATCH")
    return {
        "source_blocks": sorted(blocks),
        "fundamental_observed_at_utc": latest.isoformat() if latest else None,
        "market_observed_at_utc": mt.isoformat() if mt else None,
        "fundamental_rows_in_cohort": len(fund_cohort),
        "market_rows_in_cohort": len(market_cohort),
        "full_field_roster_count": len(roster),
        "source_uri_by_selection": {str(r['selection_id']):r['source_uri'] for r in fund_cohort},
        "market_uri_by_selection": {str(r['selection_key']):r['source_uri'] for r in market_cohort},
        "market_provider_by_selection": {str(r['selection_key']):r['provider'] for r in market_cohort},
        "market_odds_by_selection": {str(r['selection_key']):r['odds_decimal'] for r in market_cohort},
        "archival_observation_only": True,
        "independent_provider_publication_time_proven": False,
        "pit_certified": False,
    }


def _safe_call(label: str, fn, **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(**kwargs)
    except (sqlite3.Error, ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as e:
        return {"status":"BLOCKED", "exception_code":f"{label}_EXECUTION_ERROR", "exception_detail":f"{type(e).__name__}: {e}"}


def analyze(conn: sqlite3.Connection, *, race_id: str, as_of: str, archive_sha: str | None,
            run_kind: str = "ARCHIVED_REPLAY",
            source_report: dict[str, Any] | None = None,
            source_report_sha256: str | None = None) -> dict[str, Any]:
    cutoff = aware(as_of)
    race = read_rows(conn, "SELECT * FROM races WHERE race_id=?", (race_id,))
    if len(race) != 1:
        raise ValueError("RACE_ID_NOT_UNIQUELY_PRESENT_IN_DATABASE")
    race = race[0]
    start = aware(str(race['start_time_utc']))
    analysis_started_at = datetime.now(UTC)
    if run_kind == 'PROSPECTIVE_ATTEMPT':
        if analysis_started_at >= start:
            raise ValueError('PROSPECTIVE_FREEZE_AFTER_RECORDED_START')
        if cutoff > analysis_started_at:
            raise ValueError('PROSPECTIVE_AS_OF_IN_FUTURE')
    timestamp_blocks: set[str] = set()
    if cutoff >= start:
        timestamp_blocks.add("NOT_BEFORE_RECORDED_RACE_START")
    audit = source_checks(conn, race_id, cutoff)
    # Reuse the existing CORE-003 source diagnostic. Explicitly rejected ATG
    # full-field evidence is a veto, never a positive source attestation.
    atg = _atg_history_source_diagnostic(
        conn, race_id=race_id, cutoff=min(cutoff, start-timedelta(minutes=4))
    )
    audit['atg_full_field_diagnostic'] = atg
    champion = _safe_call("CHAMPION", analyze_race, db=conn, race_id=race_id, decision_at=as_of)
    candidate = _safe_call("CORE004", analyze_multifactor, conn=conn, race_id=race_id, as_of=as_of)
    model_calculated_at = datetime.now(UTC)
    if run_kind == 'PROSPECTIVE_ATTEMPT' and model_calculated_at >= start:
        raise ValueError('PROSPECTIVE_MODEL_FINISHED_AFTER_RECORDED_START')
    champion_rows = {str(r['selection_id']):r for r in champion.get('runner_rows', [])}
    candidate_rows = {str(r['selection_id']):r for r in candidate.get('runners', [])}
    roster = read_rows(conn, "SELECT * FROM runners WHERE race_id=? ORDER BY post_position,selection_id", (race_id,))
    ids = set(champion_rows) | set(candidate_rows) | {str(r['selection_id']) for r in roster}
    numbers = lambda sid: (0,int(sid)) if sid.isdecimal() else (1,sid)
    source_blocks = set(audit['source_blocks']) | timestamp_blocks
    if atg is not None and atg.get('full_field_gate_passed') is not True:
        source_blocks.add('ATG_FULL_FIELD_SOURCE_EXPLICITLY_REJECTED')
        source_blocks.update(str(reason) for reason in atg.get('source_reasons', []))
    source_blocks.update(champion.get('blocks', []))
    source_blocks.update(candidate.get('blocked_reasons', []))
    for model,res in (("CHAMPION",champion),("CORE004",candidate)):
        if res.get('exception_code'):
            source_blocks.add(res['exception_code'])
    champ_ready = champion.get('fundamental_ready_for_research') is True
    core_ready = candidate.get('status') == 'CANDIDATE_READY_UNCALIBRATED'
    market_ready = champion.get('win_market_complete') is True
    collection_evidence: dict[str, Any] | None = None
    if source_report is not None:
        cohort = source_report.get('races_in_fixed_cohort', [])
        if not isinstance(cohort, list) or race_id not in cohort:
            source_blocks.add('CORE003_REPORT_RACE_NOT_IN_FIXED_COHORT')
        try:
            capture_start = aware(str(source_report['started_at_utc']))
            capture_finish = aware(str(source_report['finished_at_utc']))
            if capture_start > capture_finish:
                source_blocks.add('CORE003_CAPTURE_CLOCK_INVERTED')
            if capture_finish > cutoff:
                source_blocks.add('CORE003_CAPTURE_FINISHED_AFTER_ANALYSIS_AS_OF')
        except (ValueError, TypeError, KeyError):
            source_blocks.add('CORE003_CAPTURE_CLOCK_INVALID')
        collection_evidence = {
            'schema_version': source_report.get('schema_version'),
            'sha256': source_report_sha256,
            'started_at_utc': source_report.get('started_at_utc'),
            'finished_at_utc': source_report.get('finished_at_utc'),
            'race_in_fixed_cohort': race_id in cohort if isinstance(cohort, list) else False,
            'independent_pit_certified': False,
        }
    # An invalid or unverified fundamental source prevents declaring a model
    # ready even when a raw mathematical probability vector can be calculated.
    market_blocks = {b for b in source_blocks if b in MARKET_BLOCKER_CODES}
    model_blocks = source_blocks - market_blocks
    model_ready = champ_ready and core_ready and not model_blocks
    model_status = ('MODEL_READY' if model_ready else 'MODEL_PARTIAL'
                    if champ_ready != core_ready else 'MODEL_BLOCKED')
    market_ready = market_ready and not market_blocks
    market_status = 'MARKET_READY' if market_ready else 'MARKET_BLOCKED'
    # A calculation may be displayed without conferring admission or wagering authority.
    analysis_status = ("RESEARCH_READY" if champ_ready and core_ready and market_ready and not source_blocks
                       else "SOURCE_BLOCKED")
    rows = []
    for sid in sorted(ids,key=numbers):
        r = next((r for r in roster if str(r['selection_id']) == sid), {})
        ch=champion_rows.get(sid,{})
        co=candidate_rows.get(sid,{})
        scratch=bool(r.get('scratched',ch.get('scratched',False)))
        pc=ch.get('p_win') if champ_ready and not scratch else None
        pm=co.get('p_candidate') if core_ready and not scratch else None
        odds=ch.get('available_odds') if market_ready and not scratch else None
        marketp=ch.get('normalized_market_p') if market_ready and not scratch else None
        is_blocked=bool(source_blocks) or not champ_ready or not market_ready or not core_ready
        row_status = ('PASS' if scratch else 'BLOCKED' if is_blocked else ch.get('status','PASS'))
        # Preserve CORE-004's no-EV / no-WATCH rule. Any WATCH arises only
        # from the unchanged Champion preliminary price threshold.
        rows.append({
            'selection_id':sid, 'start_number':r.get('post_position'), 'horse_name':r.get('horse_name') or ch.get('horse_name'),
            'scratched':scratch,'historical_starts':ch.get('history_total_starts'), 'historical_wins':ch.get('history_total_wins'),
            'history_source_uri':audit['source_uri_by_selection'].get(sid),
            'history_source_quality':ch.get('history_source_quality'),
            'champion_p_win':pc, 'core004_p_win':pm,
            'core004_minus_champion_pp':(pm-pc)*100 if pm is not None and pc is not None else None,
            'champion_fair_odds':1/pc if pc else None,
            'core004_fair_odds_research_only':1/pm if pm else None,
            'win_odds':odds,'win_odds_observed_at_utc':audit['market_observed_at_utc'] if odds else None,
            'win_odds_source_uri':audit['market_uri_by_selection'].get(sid) if odds else None,
            'win_odds_provider':audit['market_provider_by_selection'].get(sid) if odds else None,
            'normalized_market_p':marketp,
            'champion_theoretical_ev_uncalibrated':(pc*odds-1) if pc is not None and odds is not None else None,
            'research_status':row_status,
            'model_status':'NOT_APPLICABLE_SCRATCHED' if scratch else model_status,
            'market_status':'NOT_APPLICABLE_SCRATCHED' if scratch else market_status,
            'pit_status':'PIT_NOT_CERTIFIED',
            'blocker_codes':sorted(source_blocks) if row_status=='BLOCKED' else [],
            'bet_authority':False,
        })
    active = [r for r in rows if not r['scratched']]
    champ_values=[r['champion_p_win'] for r in active if r['champion_p_win'] is not None]
    core_values=[r['core004_p_win'] for r in active if r['core004_p_win'] is not None]
    mark_values=[r['normalized_market_p'] for r in active if r['normalized_market_p'] is not None]
    # Never claim a complete field when probabilities are not on ALL active runners.
    probability_blocks=[]
    for label,values in (("CHAMPION",champ_values),("CORE004",core_values),("MARKET",mark_values)):
        if len(values)==len(active) and active and abs(math.fsum(values)-1)>1e-9:
            probability_blocks.append(f"{label}_PROBABILITY_SUM_NOT_ONE")
    if probability_blocks:
        analysis_status="SOURCE_BLOCKED"
        source_blocks.update(probability_blocks)
        for r in rows:
            if not r['scratched']:
                r['research_status']='BLOCKED'
                r['blocker_codes']=sorted(source_blocks)
        market_blocks.update(b for b in probability_blocks if b in MARKET_BLOCKER_CODES)
        model_blocks.update(b for b in probability_blocks if b not in MARKET_BLOCKER_CODES)
        if model_blocks:
            model_status = 'MODEL_BLOCKED'
        if market_blocks:
            market_status = 'MARKET_BLOCKED'
        for r in rows:
            if not r['scratched']:
                r['model_status'] = model_status
                r['market_status'] = market_status
    report_created_at = datetime.now(UTC)
    if run_kind == 'PROSPECTIVE_ATTEMPT' and report_created_at >= start:
        raise ValueError('PROSPECTIVE_FREEZE_AFTER_RECORDED_START')
    return {
        'schema':SCHEMA,'run_kind':run_kind,
        'analysis_started_at_utc':analysis_started_at.isoformat(),
        'model_calculated_at_utc':model_calculated_at.isoformat(),
        'report_created_at_utc':report_created_at.isoformat(),
        'race':{k:race.get(k) for k in ('race_id','race_date','track','country','race_no','start_time_utc','discipline','distance_m','start_method')},
        'as_of_utc':cutoff.isoformat(),'minutes_before_recorded_start':(start-cutoff).total_seconds()/60,
        'source_database_sha256':archive_sha,'source_archive_is_immutable_read_only':True,
        'collector_source_evidence':collection_evidence,
        'source_audit':{k:v for k,v in audit.items() if not k.endswith('_by_selection')},
        'source_attestation':(
            'PROSPECTIVE_CORE003_CAPTURE_RECORDED_PIT_NOT_CERTIFIED'
            if run_kind == 'PROSPECTIVE_ATTEMPT' and collection_evidence
            and not any(code.startswith('CORE003_') for code in source_blocks)
            else 'PROSPECTIVE_LOCAL_FREEZE_CAPTURE_NOT_ATTESTED_PIT_NOT_CERTIFIED'
            if run_kind == 'PROSPECTIVE_ATTEMPT'
            else 'ARCHIVED_BEFORE_START_NOT_INDEPENDENT_PIT'),
        'model_versions':{'champion':CHAMPION_ID,'core004':CORE004_ID},
        'model_configuration':'ORIGINAL_UPSTREAM_UNCHANGED',
        'model_diagnostics':{'champion':{'ready':champ_ready,'blocks':champion.get('blocks',[]),'error':champion.get('exception_code')},
                             'core004':{'ready':core_ready,'blocks':candidate.get('blocked_reasons',[]),'error':candidate.get('exception_code'),
                                        'weights':candidate.get('weights_unfitted_illustrative')}},
        'analysis_status':analysis_status,
        'model_status':model_status,'market_status':market_status,
        'pit_status':'PIT_NOT_CERTIFIED','bet_authority':False,
        'status_dimensions':{'model':model_status,'market':market_status,
                             'pit':'PIT_NOT_CERTIFIED','bet':'NOT_ELIGIBLE_FOR_REAL_BETTING'},
        'model_blockers':sorted(model_blocks),'market_blockers':sorted(market_blocks),
        'source_blocks':sorted(source_blocks),'active_runners':len(active),'field_size':len(rows),
        'champion_p_sum':math.fsum(champ_values) if len(champ_values)==len(active) and active else None,
        'core004_p_sum':math.fsum(core_values) if len(core_values)==len(active) and active else None,
        'normalized_market_p_sum':math.fsum(mark_values) if len(mark_values)==len(active) and active else None,
        'runners':rows,
        'result_join_key':{'race_id':race_id,'race_date':race.get('race_date'),'race_no':race.get('race_no')},
        'frozen_outcome':None,
        'p0_backlog':{'skive_settlement':'BLOCKED','canonical_v1_audit':'FAIL','source_semantics':'BLOCKED'},
        'git_ref_pinned_upstream':PINNED_UPSTREAM,'git_sha_of_current_workspace':git_head(),
    }


def git_head() -> str | None:
    try:
        return subprocess.run(['git','-C',str(Path(__file__).resolve().parents[2]),'rev-parse','HEAD'],check=True,capture_output=True,text=True,timeout=3).stdout.strip()
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
        return None


def select_next_race(conn: sqlite3.Connection, as_of: datetime, horizon_minutes: int = 1440) -> dict[str, Any] | None:
    races = read_rows(conn, "SELECT race_id,track,race_no,start_time_utc,discipline FROM races WHERE lower(discipline)='trot' ORDER BY start_time_utc,race_id")
    eligible=[]
    for race in races:
        try:
            when=aware(str(race['start_time_utc']))
        except ValueError:
            continue
        if as_of < when <= as_of+timedelta(minutes=horizon_minutes) and ':X1_NR_' not in str(race['race_id']):
            eligible.append((when,race))
    return min(eligible,key=lambda x:(x[0],x[1]['race_id']))[1] if eligible else None


def fmt(value: Any, scale: float = 1.0) -> str:
    return '—' if value is None else f"{value*scale:.4f}"


def markdown_report(report: dict[str,Any]) -> str:
    race=report['race']
    lines=[f"# BET-MVP-001 – {race['track']} løp {race['race_no']} ({race['race_date']})",'',
           f"**Status:** {report['analysis_status']} · **Modell:** {report.get('model_status','UKJENT')} · **Marked:** {report.get('market_status','UKJENT')} · **PIT:** {report['pit_status']} · **BET:** NEI",'',
           f"Arkivert start: `{race['start_time_utc']}` · Analyse: `{report['as_of_utc']}` · Løp: `{race['race_id']}`",'',
           f"Modell beregnet: `{report.get('model_calculated_at_utc')}` · Rapport frosset: `{report.get('report_created_at_utc')}`",'',
           f"Champion: `{report['model_versions']['champion']}` · CORE-004: `{report['model_versions']['core004']}`",'',
           f"Aktive: {report['active_runners']} av {report['field_size']} · Champion-sum: {fmt(report['champion_p_sum'],100)} % · CORE-004-sum: {fmt(report['core004_p_sum'],100)} %",'',
           '## Samlet felt',
           '| # | Hest | Strøket | Starter/seire | Champion % | CORE-004 % | Δ pp | Fair Champion | WIN-odds | Marked % | EV Champion % | Status |',
           '|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for x in report['runners']:
        hist=f"{x['historical_starts']}/{x['historical_wins']}" if x['historical_starts'] is not None else '—'
        lines.append(f"| {x['start_number'] if x['start_number'] is not None else x['selection_id']} | {str(x['horse_name'] or '—').replace('|','/')} | {'Ja' if x['scratched'] else 'Nei'} | {hist} | {fmt(x['champion_p_win'],100)} | {fmt(x['core004_p_win'],100)} | {fmt(x['core004_minus_champion_pp'])} | {fmt(x['champion_fair_odds'])} | {fmt(x['win_odds'])} | {fmt(x['normalized_market_p'],100)} | {fmt(x['champion_theoretical_ev_uncalibrated'],100)} | {x['research_status']} |")
    lines+=['','## Kilde- og tidsaudit',f"- Original SQLite SHA-256: `{report['source_database_sha256']}`",
            f"- Fundamental observation: `{report['source_audit']['fundamental_observed_at_utc']}`",
            f"- WIN observation: `{report['source_audit']['market_observed_at_utc']}`",
            f"- CORE-003 kildekvittering SHA-256: `{(report.get('collector_source_evidence') or {}).get('sha256')}`",
            f"- Modellblokkeringer: {', '.join(report.get('model_blockers',[])) or 'ingen'}",
            f"- Markedsblokkeringer: {', '.join(report.get('market_blockers',[])) or 'ingen'}",
            '- Originale observasjonstider dokumenterer ikke uavhengig kildepublisering/PIT.',
            f"- Blokkeringer: {', '.join(report['source_blocks']) or 'Ingen kildeblokkeringer for lokal forskning'}",
            '- CORE-004-vektene er illustrative, ikke kalibrert. CORE-004 beregner ingen WATCH eller EV.',
            '- WIN-odds er observerte tote-odds, ikke garantert oppnåelig pris.',
            '- Resultater er ikke innlest; rapporten er frossen og klar for senere separat evaluering.',
            '- Skive-oppgjør, V1-replay og uavhengig kildegodkjenning er ikke lukket.',
            '','## Individuelle kildereferanser']
    for x in report['runners']:
        lines.append(f"- {x['selection_id']} {x['horse_name']}: historikk `{x['history_source_uri'] or 'MANGLER'}`; WIN `{x['win_odds_source_uri'] or 'MANGLER'}`; tidsstempel `{x['win_odds_observed_at_utc'] or 'MANGLER'}`")
    return '\n'.join(lines)+'\n'


def write_frozen(report:dict[str,Any],folder:Path)->dict[str,str]:
    if folder.exists():
        raise FileExistsError('FROZEN_SHADOW_OUTPUT_DIRECTORY_EXISTS_NO_OVERWRITE')
    folder.mkdir(parents=True,exist_ok=False)
    targets={k:folder/k for k in ('shadow.json','shadow.md','runners.csv')}
    with targets['shadow.json'].open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')
    with targets['shadow.md'].open('x',encoding='utf-8') as f:
        f.write(markdown_report(report))
    fields=['selection_id','start_number','horse_name','scratched','historical_starts','historical_wins','history_source_uri','champion_p_win','core004_p_win','core004_minus_champion_pp','champion_fair_odds','core004_fair_odds_research_only','win_odds','win_odds_observed_at_utc','normalized_market_p','champion_theoretical_ev_uncalibrated','research_status','model_status','market_status','pit_status','blocker_codes']
    with targets['runners.csv'].open('x',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        wr.writeheader()
        wr.writerows({**r,'blocker_codes':';'.join(r['blocker_codes'])} for r in report['runners'])
    return {name:sha256(p) for name,p in targets.items()}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Frozen read-only CORE-001 + CORE-004 shadow analysis; NO BET')
    p.add_argument('--db',type=Path,required=True)
    p.add_argument('--race-id',help='Exact canonical HBI race_id, else discover next upcoming')
    p.add_argument('--as-of',required=True,help='Aware ISO datetime, frozen before race start')
    p.add_argument('--out',type=Path,required=True,help='Fresh directory, never overwrite')
    p.add_argument('--horizon-minutes',type=int,default=1440)
    p.add_argument('--source-report',type=Path,help='Unmodified optional CORE-003 source report JSON')
    p.add_argument('--run-kind',choices=['ARCHIVED_REPLAY','PROSPECTIVE_ATTEMPT'],default='ARCHIVED_REPLAY')
    args=p.parse_args(argv)
    if not args.db.is_file():
        p.error('SOURCE_DB_NOT_FOUND')
    if args.source_report is not None and not args.source_report.is_file():
        p.error('CORE003_SOURCE_REPORT_NOT_FOUND')
    if args.out.resolve()==args.db.resolve():
        p.error('OUTPUT_CANNOT_OVERWRITE_SOURCE_DB')
    cutoff=aware(args.as_of)
    uri='file:'+quote(str(args.db.resolve()))+'?mode=ro&immutable=1'
    try:
        source_report = (json.loads(args.source_report.read_text(encoding='utf-8'))
                         if args.source_report is not None else None)
    except (OSError, ValueError) as exc:
        p.error(f'CORE003_SOURCE_REPORT_INVALID: {exc}')
    if source_report is not None and not isinstance(source_report, dict):
        p.error('CORE003_SOURCE_REPORT_MUST_BE_OBJECT')
    with sqlite3.connect(uri,uri=True) as conn:
        conn.row_factory=sqlite3.Row
        selected=({'race_id':args.race_id} if args.race_id else select_next_race(conn,cutoff,args.horizon_minutes))
        if not selected:
            p.error('NO_UPCOMING_CANONICAL_RACE_IN_ARCHIVE')
        report=analyze(conn,race_id=str(selected['race_id']),as_of=cutoff.isoformat(),archive_sha=sha256(args.db),run_kind=args.run_kind,
                       source_report=source_report,
                       source_report_sha256=sha256(args.source_report) if args.source_report is not None else None)
    hashes=write_frozen(report,args.out)
    print(json.dumps({'race_id':report['race']['race_id'],'status':report['analysis_status'],'active':report['active_runners'],
                      'model_status':report['model_status'],'market_status':report['market_status'],
                      'champion_sum':report['champion_p_sum'],'core004_sum':report['core004_p_sum'],
                      'watch':sum(r['research_status']=='WATCH' for r in report['runners']),
                      'blocked':sum(r['research_status']=='BLOCKED' for r in report['runners']),
                      'output_sha256':hashes,'bet_authority':False},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
