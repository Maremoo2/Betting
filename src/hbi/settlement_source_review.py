"""Independent, no-write evidence contract for official Winner settlement.

Does not settle a ticket, write P&L, make a refund assumption or submit a bet.
It mirrors conservative preconditions in src/hbi/nightly.py, with separate
source-authenticity gate and explicit reasons to investigate provider retries.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def positive_number(value):
    try:
        if value is None or isinstance(value,bool):return None
        n=float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError,TypeError,OverflowError):return None


def assess_winner_settlement(*, ticket, complete, raceday, cached_winner=None, source_attested=False):
    response={'schema':'WIN_SETTLEMENT_EVIDENCE_REVIEW_V1','read_only':True,
              'ticket_id':ticket.get('ticket_id'), 'decision_status':ticket.get('status'),
              'source_attested':bool(source_attested), 'eligible_for_bookkeeping':False,
              'structurally_settlement_ready':False,
              'reasons':[],'winning_result':None,'gross_return_recommendation':None}
    reasons=response['reasons']
    if ticket.get('product')!='V':reasons.append('UNSUPPORTED_PRODUCT')
    try:
        chosen=json.loads(ticket.get('selections_json') or 'null')
    except (TypeError,ValueError,json.JSONDecodeError):chosen=None
    if not isinstance(chosen,list) or len(chosen)!=1:
        reasons.append('INVALID_SELECTIONS');return response
    selection=str(chosen[0]);response['selected']=selection
    if not isinstance(complete,dict) or not isinstance(raceday,dict):
        reasons.append('MISSING_ORIGINAL_OFFICIAL_SOURCE_PAYLOADS');return response
    if complete.get('isComplete') is not True:
        reasons.append('OFFICIAL_RESULT_NOT_COMPLETE');return response
    rows=complete.get('results')
    if not isinstance(rows,list) or not rows:
        reasons.append('OFFICIAL_RUNNER_RESULT_ROWS_MISSING');return response
    places={}
    for row in rows:
        if not isinstance(row,dict) or row.get('startNumber') is None or row.get('place') is None:
            reasons.append('AMBIGUOUS_OFFICIAL_ROW');return response
        key=str(row['startNumber'])
        place=row['place']
        if type(place) is not int or place<0 or key in places:
            reasons.append('DUPLICATE_OR_INVALID_FINISH');return response
        places[key]=(place,row)
    if selection not in places:
        reasons.append('TICKET_SELECTION_ABSENT_FROM_OFFICIAL_FIELD');return response
    winners=[k for k,(place,_) in places.items() if place==1]
    if len(winners)!=1:
        reasons.append('OFFICIAL_WINNER_AMBIGUOUS');return response
    winner=winners[0]
    response['winning_result']=winner
    if cached_winner is not None and str(cached_winner)!=winner:
        reasons.append('CACHED_WINNER_DISAGREES_WITH_RAW_SOURCE');return response
    finish,selrow=places[selection]
    if finish==0 and not (selrow.get('kmTime')=='Dsk' and positive_number(selrow.get('odds')) is not None):
        reasons.append('ZERO_FINISH_NOT_PROVEN_DISQUALIFIED_PARTICIPANT');return response
    day_key=ticket.get('provider_raceday_key')
    race_number=ticket.get('race_number')
    if day_key is None or race_number is None:
        reasons.append('MISSING_RACEDAY_OR_RACE_NUMBER');return response
    try:
        payout=raceday['finalOdds']['winOdds'][str(race_number)][winner]
        if payout.get('payoutStatus')!='Dividends' or positive_number(payout.get('odds')) is None:
            reasons.append('WINNING_DIVIDEND_NOT_CONFIRMED');return response
    except (KeyError,TypeError,AttributeError):
        reasons.append('WINNING_DIVIDEND_MISSING');return response
    if finish==1:
        response['gross_return_recommendation']='STAKE_TIMES_VERIFIED_WIN_DIVIDEND'
    else:
        response['gross_return_recommendation']='ZERO_IF_OFFICIAL_SOURCES_ATTESTED'
    if not source_attested:
        reasons.append('SOURCE_AUTHENTICITY_AND_FETCH_TIME_UNATTESTED');return response
    # Even a structurally valid supplied payload never grants accounting authority.
    response['structurally_settlement_ready']=True
    return response


def audit_archived_ticket_only(ticket, archived_sources):
    """Definitively blocked absent original official result+dividend source payloads."""
    category={r.get('category') for r in archived_sources}
    return {'schema':'WIN_SETTLEMENT_ARCHIVE_EVIDENCE_V1','ticket_id':ticket.get('ticket_id'),
            'read_only':True,'eligible_for_bookkeeping':False,
            'primary_complete_result_archived':'OFFICIAL_COMPLETE_RESULTS' in category,
            'primary_dividend_archived':'OFFICIAL_RACEDAY_RESULTS' in category,
            'status':'BLOCKED_NO_PRIMARY_SETTLEMENT_PAYLOADS'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--ticket-json',type=Path,required=True)
    p.add_argument('--complete-json',type=Path);p.add_argument('--raceday-json',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();ticket=json.loads(a.ticket_json.read_text());complete=json.loads(a.complete_json.read_text()) if a.complete_json else None
    raceday=json.loads(a.raceday_json.read_text()) if a.raceday_json else None
    report=assess_winner_settlement(ticket=ticket,complete=complete,raceday=raceday)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
