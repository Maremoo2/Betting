"""Proof that official Winner settlement gate does not guess losses or payout."""
import json
from pathlib import Path

import pytest
from hbi.settlement_source_review import assess_winner_settlement, audit_archived_ticket_only

T={'ticket_id':'test-paper','provider_raceday_key':'S4_NR_2026-10-14','race_number':6,
   'product':'V','status':'SHADOW_BET','selections_json':'["8"]'}
COMPLETE={'isComplete':True,'results':[
  {'startNumber':5,'place':1,'kmTime':'1.15'}, {'startNumber':8,'place':9,'kmTime':'1.20'}]}
DAY={'finalOdds':{'winOdds':{'6':{'5':{'payoutStatus':'Dividends','odds':4.82}}}}}


def check(**updates):
    args=dict(ticket=T,complete=COMPLETE,raceday=DAY,cached_winner='5',source_attested=True)
    args.update(updates)
    return assess_winner_settlement(**args)


def test_confirmed_official_loss_eligible_only_with_attested_sources():
    r=check()
    assert r['structurally_settlement_ready'] and not r['eligible_for_bookkeeping'] and r['gross_return_recommendation']=='ZERO_IF_OFFICIAL_SOURCES_ATTESTED'


def test_normal_online_read_or_unverified_payload_never_authorizes_accounting():
    r=check(source_attested=False)
    assert not r['eligible_for_bookkeeping']
    assert 'SOURCE_AUTHENTICITY_AND_FETCH_TIME_UNATTESTED' in r['reasons']


def test_missing_official_payloads_preserve_pending_status():
    assert 'MISSING_ORIGINAL_OFFICIAL_SOURCE_PAYLOADS' in check(complete=None)['reasons']
    assert 'MISSING_ORIGINAL_OFFICIAL_SOURCE_PAYLOADS' in check(raceday=None)['reasons']


def test_official_incomplete_result_blocks_even_with_winner():
    assert 'OFFICIAL_RESULT_NOT_COMPLETE' in check(complete={**COMPLETE,'isComplete':False})['reasons']


def test_ambiguous_zero_place_not_forced_to_loss():
    c={'isComplete':True,'results':[COMPLETE['results'][0],{'startNumber':8,'place':0,'kmTime':'Str','odds':0}]}
    assert 'ZERO_FINISH_NOT_PROVEN_DISQUALIFIED_PARTICIPANT' in check(complete=c)['reasons']


def test_dsk_positive_participation_is_a_loss():
    c={'isComplete':True,'results':[COMPLETE['results'][0],{'startNumber':8,'place':0,'kmTime':'Dsk','odds':18}]}
    assert check(complete=c)['structurally_settlement_ready']


def test_dsk_zero_odds_cannot_settle():
    c={'isComplete':True,'results':[COMPLETE['results'][0],{'startNumber':8,'place':0,'kmTime':'Dsk','odds':0}]}
    assert not check(complete=c)['eligible_for_bookkeeping']


def test_winner_dividend_pending_blocks():
    d={'finalOdds':{'winOdds':{'6':{'5':{'payoutStatus':'Pending','odds':4.82}}}}}
    assert 'WINNING_DIVIDEND_NOT_CONFIRMED' in check(raceday=d)['reasons']


def test_official_winner_disagrees_with_local_outcome_blocks():
    assert 'CACHED_WINNER_DISAGREES_WITH_RAW_SOURCE' in check(cached_winner='6')['reasons']


def test_missing_selection_never_counts_as_loss():
    c={'isComplete':True,'results':[COMPLETE['results'][0]]}
    assert 'TICKET_SELECTION_ABSENT_FROM_OFFICIAL_FIELD' in check(complete=c)['reasons']


def test_duplicate_or_invalid_result_blocks():
    c={'isComplete':True,'results':[COMPLETE['results'][0],COMPLETE['results'][0],COMPLETE['results'][1]]}
    assert 'DUPLICATE_OR_INVALID_FINISH' in check(complete=c)['reasons']


def test_winning_ticket_is_not_assigned_zero_gross():
    t=dict(T,selections_json='["5"]')
    r=check(ticket=t)
    assert r['gross_return_recommendation']=='STAKE_TIMES_VERIFIED_WIN_DIVIDEND'


def test_no_primary_payload_categories_means_no_settlement():
    r=audit_archived_ticket_only(T,[{'category':'RACEDAY_STARTS'},{'category':'CONTENDER_GATE_V2_1'}])
    assert r['status']=='BLOCKED_NO_PRIMARY_SETTLEMENT_PAYLOADS'
