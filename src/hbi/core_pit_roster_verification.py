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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .source_identity import is_generic_horse_identity

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
        if not isinstance(parsed, dict) or parsed.get('success') is not True:
            return None, 'STARTLIST_RESPONSE_NOT_SUCCESSFUL'
        result = parsed.get('result')
        if not isinstance(result, dict):
            return None, 'INVALID_STARTS_ENVELOPE'
        items = result[str(race_no)]
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
        if is_generic_horse_identity(name):
            return None, 'PLACEHOLDER_ROSTER_HORSE_IDENTITY'
        # The race key and each participant's original row number must both
        # identify this exact race, not a stale or accidentally joined leg.
        if type(item.get('raceNumber')) is not int or item['raceNumber'] != race_no:
            return None, 'STARTLIST_ROW_RACE_NUMBER_MISMATCH'
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
    for row in rows:
        value = row[internal]
        # Fundamental features require a real, timezone-aware as-of clock.
        # A missing feature clock cannot be inferred from fetch observation.
        if table == 'runner_fundamental_snapshots' and not value:
            return [],ts
        if value and (parse_time(value) is None or parse_time(value)>cutoff):
            return [],ts
    return rows,ts


def good_fundamentals(rows, active, roster):
    by={str(r['selection_id']):r for r in rows}
    if len(by)!=len(rows) or set(by)!=set(roster):
        # Require each source-roster member, including scratched rows, to match.
        return False
    for key, record in roster.items():
        # An unknown or non-boolean snapshot scratch state is not evidence
        # that a horse was active at T-4. SQLite stores booleans as 0/1.
        observed_scratch = by[key]['scratched']
        if type(observed_scratch) is not int or observed_scratch not in (0, 1):
            return False
        if bool(observed_scratch) != record['scratched']:
            return False
    for key in active:
        row=by[key];starts=row['history_total_starts'];wins=row['history_total_wins']
        if row['full_field_history_complete']!=1 or not row['source_uri'] or row['scratched'] not in (0,None):
            return False
        if type(starts) is not int or type(wins) is not int or starts<0 or not 0<=wins<=starts:
            return False
    return True


def good_market(rows, active, roster):
    """Require exact archived WIN membership, including scratched selections.

    A valid negative-price sentinel for a scratched horse is never proof that
    a previously unknown/off-roster selection belongs in the physical race.
    """
    seen=set();price={}
    for row in rows:
        key=str(row['selection_key'])
        if key in seen or key not in roster:
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
    return seen == set(roster) and set(price)==active


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
    # One physical race cannot silently inherit whichever of multiple
    # incompatible provider race-day identities happens to sort first.
    distinct_keys = {ref['provider_raceday_key'] for ref in refs}
    if len(distinct_keys) != 1 or not next(iter(distinct_keys)):
        return {'race_id': race_id, 'status': 'BLOCKED',
                'raw_input_ready_at_cutoff': False, 'pit_certified': False,
                'blockers': ['AMBIGUOUS_RIKSTOTO_RACEDAY_REFERENCE']}
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
    # Retrospectively linked race identity is not an as-of identity. A later
    # duplicate reference does not invalidate one genuinely observed pre-T-4.
    reference_known_at_cutoff = any(
        (stamp := parse_time(row['discovered_at_utc'])) is not None and stamp <= cutoff
        for row in refs
    )
    if not reference_known_at_cutoff:
        reasons.append('NO_PRE_CUTOFF_RACE_REFERENCE')
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
        market_ready=good_market(market,roster['active'],roster['all'])
        if not fund_ready:reasons.append('INCOMPLETE_FUNDAMENTAL_ASOF_FIELD')
        if not market_ready:reasons.append('INCOMPLETE_WIN_ASOF_FIELD')
    canonical_agreement=None
    if roster:
        mutable=conn.execute('SELECT selection_id,scratched,horse_name FROM runners WHERE race_id=?',(race_id,)).fetchall()
        # A mutable NULL/invalid scratch is not evidence of an active runner;
        # duplicates must not silently collapse in a dict comprehension.
        mutable_well_formed = (
            len(mutable) == len(roster['all'])
            and all(
                type(row['scratched']) is int and row['scratched'] in (0, 1)
                and isinstance(row['horse_name'], str) and row['horse_name'].strip()
                and row['selection_id'] is not None
                for row in mutable
            )
        )
        curr = {
            str(row['selection_id']): {
                'scratched': bool(row['scratched']), 'name': row['horse_name']
            }
            for row in mutable
        } if mutable_well_formed else {}
        canonical_agreement = (
            mutable_well_formed
            and len(curr) == len(mutable)
            and curr == {
                k: {'scratched': v['scratched'], 'name': v['name']}
                for k, v in roster['all'].items()
            }
        )
        if not canonical_agreement:reasons.append('MUTABLE_ROSTER_DIFFERS_FROM_RAW')
    raw_ready=bool(roster and identity_ok and fund_ready and market_ready and canonical_agreement
                   and reference_known_at_cutoff and not invalid_historical_clock and not conflicting_revisions)
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
            'race_reference_known_at_cutoff':reference_known_at_cutoff,
            'raw_starts_reconstructed':bool(roster),'raw_active_count':len(roster['active']) if roster else None,
            'identity_matched_at_source_time':identity_ok,'fundamental_complete_at_cutoff':fund_ready,
            'win_market_complete_at_cutoff':market_ready,'mutable_roster_agrees_now':canonical_agreement,
            'raw_input_ready_at_cutoff':raw_ready,
            'pit_certified':False,'source_publication_proven':False,
            'blockers':sorted(set(reasons)),'source_snapshots':source_info,
            'status':'SOURCE_OBSERVED_UNATTESTED' if raw_ready else 'BLOCKED'}


@dataclass(frozen=True)
class VerifiedCollectorEvidence:
    """Created only after replaying an authenticated original Collector artifact."""

    race_id: str
    archive_sha256: str
    github_run_id: int
    source_repository: str
    observed_at_utc: str
    original_bytes_sha256_verified: bool
    full_field_pdf_startlist_reconciled: bool
    origin_authenticated_independently: bool
    version_identical_to_t4: bool


def attest_t4_receipt(
    receipt: dict, *, receipt_dir: Path,
    model_report: dict | None, model_raw: bytes | None,
    collector_archive: VerifiedCollectorEvidence | dict | None = None,
    provenance_mode: str = "LIVE",
) -> dict:
    """Independent model-free source/time check plus frozen report hash binding.

    No dictionary assertion alone grants live certification. Independently
    authenticated Collector artifacts must be verified before being admitted.
    Offline tests may establish a positive CONTRACT_PASS, never live authority.
    """
    if provenance_mode not in {"LIVE", "TEST_ONLY"}:
        raise ValueError("INVALID_PROVENANCE_MODE")
    if provenance_mode == "LIVE" and not isinstance(collector_archive, VerifiedCollectorEvidence):
        collector_origin_wired = False
    else:
        collector_origin_wired = isinstance(collector_archive, VerifiedCollectorEvidence)
    if isinstance(collector_archive, VerifiedCollectorEvidence):
        collector_archive = asdict(collector_archive)
    blocks: set[str] = set(receipt.get("blockers", []))
    if not isinstance(receipt, dict) or receipt.get("schema") != "PIT_T4_SOURCE_RECEIPT_V1":
        raise ValueError("UNRECOGNIZED_T4_RECEIPT")
    t4 = parse_time(receipt.get("t_minus_4_utc"))
    start = parse_time(receipt.get("canonical_start_utc"))
    race_id = receipt.get("race_id")
    if t4 is None or start is None or not isinstance(race_id, str):
        blocks.add("INVALID_OR_MISSING_RACE_CLOCK")
    if start is not None and t4 is not None and start <= t4:
        blocks.add("INVALID_T4_START_ORDER")
    evidence = []
    for role in ("racedays", "starts", "scratched"):
        row = receipt.get("sources", {}).get(role)
        if not isinstance(row, dict):
            blocks.add("INCOMPLETE_T4_SOURCE_SET")
            continue
        request = parse_time(row.get("request_started_at_utc"))
        observed = parse_time(row.get("source_observed_at_utc"))
        received = parse_time(row.get("collector_received_at_utc"))
        raw_name = row.get("raw_path")
        if not isinstance(raw_name, str) or raw_name != role + ".raw.json":
            blocks.add("ORIGINAL_RAW_ARCHIVE_UNAVAILABLE")
            continue
        raw_path = receipt_dir / raw_name
        if raw_path.is_symlink() or not raw_path.is_file():
            blocks.add("ORIGINAL_RAW_ARCHIVE_UNAVAILABLE")
            continue
        raw_bytes = raw_path.read_bytes()
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        if actual_hash != row.get("raw_sha256"):
            blocks.add("ORIGINAL_RAW_HASH_MISMATCH")
        if (request is None or observed is None or received is None
                or t4 is None or not request <= observed <= received < t4):
            blocks.add("INVALID_OR_POST_CUTOFF_SOURCE_CLOCK")
        if row.get("http_status") != 200:
            blocks.add("SOURCE_HTTP_NOT_SUCCESSFUL")
        evidence.append({
            "role": role, "source_uri": row.get("source_uri"),
            "sha256": actual_hash, "observed_at_utc": row.get("source_observed_at_utc"),
            "received_at_utc": row.get("collector_received_at_utc"),
        })
        # HTTP Date, fetch completion, and Last-Modified are not original
        # first-publication evidence. Never substitute any one for another.
        published = parse_time(row.get("source_published_at_utc"))
        if published is not None and (observed is None or published > observed):
            blocks.add("INVALID_PUBLICATION_CLOCK")
    roster = receipt.get("runners")
    if not isinstance(roster, list) or len(roster) < 2:
        blocks.add("INCOMPLETE_ACTIVE_FIELD")
        roster = []
    nums = [r.get("start_number") for r in roster if isinstance(r, dict)]
    regs = [r.get("registration_number") for r in roster if isinstance(r, dict)]
    if (len(nums) != len(roster) or len(set(nums)) != len(nums)
            or any(type(n) is not int or n <= 0 for n in nums)):
        blocks.add("DUPLICATED_OR_INVALID_START_NUMBERS")
    if (len(regs) != len(roster) or len(set(regs)) != len(regs)
            or any(not isinstance(r, str) or not r.strip()
                   or r.upper().startswith(("TMP", "TEMP", "UNKNOWN"))
                   for r in regs)):
        blocks.add("STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED")
    if any(not isinstance(row, dict) or type(row.get("scratched")) is not bool
           for row in roster):
        blocks.add("UNKNOWN_SCRATCH_STATE")
    active = [row for row in roster if isinstance(row, dict) and row.get("scratched") is False]
    if len(active) < 2:
        blocks.add("INCOMPLETE_ACTIVE_FIELD")

    model_digest = hashlib.sha256(model_raw).hexdigest() if model_raw is not None else None
    if model_report is None or model_raw is None:
        blocks.add("FROZEN_MODEL_REPORT_NOT_AVAILABLE")
    else:
        if model_report.get("race", {}).get("race_id") != race_id:
            blocks.add("MODEL_RACE_ID_MISMATCH")
        asof = parse_time(model_report.get("as_of_utc"))
        freeze = parse_time(model_report.get("report_created_at_utc"))
        if (asof is None or freeze is None or t4 is None
                or not asof <= freeze <= t4):
            blocks.add("MODEL_ASOF_OR_FREEZE_AFTER_T4")
        if model_report.get("model_status") != "MODEL_READY":
            blocks.add("FROZEN_MODEL_NOT_READY")
        if model_report.get("bet_authority") is not False:
            blocks.add("MODEL_BET_AUTHORITY_NOT_FALSE")
        model_roster = {
            str(row.get("start_number")): (
                str(row.get("horse_name")), bool(row.get("scratched"))
            )
            for row in model_report.get("runners", [])
        }
        source_roster = {
            str(row.get("start_number")): (
                str(row.get("horse_name")), row.get("scratched")
            )
            for row in roster if isinstance(row, dict)
        }
        if model_roster != source_roster or len(model_roster) != len(roster):
            blocks.add("MODEL_ROSTER_NOT_T4_MATCHED")
        if not (model_report.get("champion_p_sum") is not None
                and model_report.get("core004_p_sum") is not None
                and abs(model_report["champion_p_sum"] - 1) <= 1e-9
                and abs(model_report["core004_p_sum"] - 1) <= 1e-9):
            blocks.add("INCOMPLETE_MODEL_FULL_FIELD_PROBABILITIES")
        if model_report.get("run_kind") != "PROSPECTIVE_ATTEMPT":
            blocks.add("MODEL_NOT_PROSPECTIVE")
        for runner in model_report.get("runners", []):
            if runner.get("scratched"):
                continue
            if not runner.get("history_source_uri"):
                blocks.add("MODEL_HISTORY_SOURCE_MISSING")

    # A distinct original Collector archive must be authenticated and replayed
    # against the actual source bytes. A caller-provided boolean is not proof.
    if collector_archive is None:
        blocks.add("COLLECTOR_ARCHIVE_UNAVAILABLE")
    elif not isinstance(collector_archive, dict) or (
            collector_archive.get("original_bytes_sha256_verified") is not True
            or collector_archive.get("full_field_pdf_startlist_reconciled") is not True
            or collector_archive.get("race_id") != race_id
            or parse_time(collector_archive.get("observed_at_utc")) is None
            or t4 is None
            or parse_time(collector_archive["observed_at_utc"]) >= t4):
        blocks.add("INDEPENDENT_COLLECTOR_ARCHIVE_NOT_VERIFIED")
    # Source publication proof is NOT established by source timestamps that
    # derive from our own GET. An independent original version is an acceptable
    # alternative only after externally authenticated source provenance.
    if not (isinstance(collector_archive, dict)
            and collector_archive.get("origin_authenticated_independently") is True
            and collector_archive.get("version_identical_to_t4") is True):
        blocks.add("INDEPENDENT_SOURCE_PUBLICATION_UNATTESTED")
    # Remove only diagnostic placeholders from capture, never a real failure.
    if isinstance(collector_archive, dict):
        if ("COLLECTOR_ARCHIVE_NOT_CORROBORATED" in blocks
                and collector_archive.get("original_bytes_sha256_verified") is True
                and collector_archive.get("full_field_pdf_startlist_reconciled") is True):
            blocks.discard("COLLECTOR_ARCHIVE_NOT_CORROBORATED")
        if ("SOURCE_PUBLICATION_UNATTESTED" in blocks
                and collector_archive.get("origin_authenticated_independently") is True
                and collector_archive.get("version_identical_to_t4") is True):
            blocks.discard("SOURCE_PUBLICATION_UNATTESTED")
    # A purported LIVE Collector attestation supplied as an arbitrary JSON
    # dictionary must never be trusted. Require a separate authenticated
    # GitHub artifact verifier entrypoint, which is deliberately not in this
    # first read-only sidecar integration.
    if provenance_mode == "LIVE" and not collector_origin_wired:
        blocks.add("INDEPENDENT_COLLECTOR_ORIGIN_GATE_NOT_WIRED")
    contract_pass = not blocks
    if provenance_mode == "TEST_ONLY" and contract_pass:
        status = "TEST_ONLY_CONTRACT_PASS"
    else:
        status = "PIT_NOT_CERTIFIED"
    return {
        "schema": "PIT_T4_ATTESTATION_V1", "race_id": race_id,
        "status": status, "pit_status": status,
        "source_observed_before_t4": (
            len(evidence) == 3 and not any(
                b in blocks for b in (
                    "INVALID_OR_POST_CUTOFF_SOURCE_CLOCK",
                    "ORIGINAL_RAW_HASH_MISMATCH", "INCOMPLETE_T4_SOURCE_SET",
                    "RESPONSE_AFTER_T4", "MISSED_T4"
                )
            )
        ),
        "independent_pit_certified": False,
        "blockers": sorted(blocks), "sources": evidence,
        "model_report_sha256": model_digest,
        "model_report_frozen_at_utc": (
            model_report.get("report_created_at_utc") if model_report else None
        ),
        "t_minus_4_utc": receipt.get("t_minus_4_utc"),
        "source_published_at_utc": receipt.get("source_published_at_utc"),
        "mode": provenance_mode, "bet_authority": False,
        "research_only": True,
    }


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
