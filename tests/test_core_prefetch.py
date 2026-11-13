import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest

from hbi.core_prefetch import SCHEMA, execute_prefetch, plan_prefetch

NOW=datetime(2026,10,30,12,0,tzinfo=UTC)
START=(NOW+timedelta(minutes=8)).isoformat()
RID='RIKSTOTO:T1_NR_2026-10-30:1'


def make_db():
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
    c.executescript('''
      create table races (race_id text,track text,race_no int,discipline text,
                          start_time_utc text,race_date text,country text default 'UNKNOWN');
      create table provider_race_refs (provider text, race_id text,
                          provider_raceday_key text,race_number int);
      create table runners (race_id text,selection_id text,horse_name text,
                            scratched int,post_position int,driver_or_jockey text,trainer text);
      create table runner_fundamental_snapshots (
                          race_id text,selection_id text,observed_at_utc text,
                          feature_as_of_utc text,history_total_starts int,
                          history_total_wins int,source_uri text,full_field_history_complete int,
                          scratched int,horse_name text,post_position int,driver_or_jockey text,data_quality text);
      create table provider_market_snapshots (
                          race_id text,product text,selection_key text,
                          observed_at_utc text,provider_updated_at_utc text,odds_decimal real);
    ''')
    add_race(c)
    return c


def add_race(c, *, rid=RID, start=START, track='Testbane', no=1, roster=True, country='trot', nation='UNKNOWN'):
    c.execute('insert into races values (?,?,?,?,?,?,?)',
              (rid,track,no,country,start,'2026-10-30',nation))
    c.execute('insert into provider_race_refs values (?,?,?,?)',
              ('rikstoto',rid,'T1_NR_2026-10-30',no))
    if roster:
        for n in (1,2,3):
            c.execute('insert into runners values (?,?,?,?,?,?,?)',
                      (rid,str(n),f'Named Runner {n}',0,n,'Driver','Trainer'))
    c.commit()


def fundamental(c, *, rid=RID, now=NOW, complete=True, one_missing=False):
    for n in ((1,2) if one_missing else (1,2,3)):
        c.execute('insert into runner_fundamental_snapshots values (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (rid,str(n),now.isoformat(),now.isoformat(),10,n,
                   'https://example.test/source',int(complete),0,f'Named Runner {n}',n,'Driver','FULL_FIELD_HISTORY_ATG'))
    c.commit()


def market(c, *, rid=RID, now=NOW, include=(1,2,3), odds=4.):
    for n in include:
        c.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',
                  (rid,'V',str(n),now.isoformat(),None,odds))
    c.commit()


def actions(plan): return [t['action'] for t in plan['tasks']]


def test_missing_inputs_create_two_tasks():
    p=plan_prefetch(make_db(),now=NOW.isoformat())
    assert p['schema_version']==SCHEMA
    assert p['races_considered']==1
    assert actions(p)==['COLLECT_FUNDAMENTALS','COLLECT_WIN_MARKET']
    assert p['reason_counts']=={'MISSING_HORSE_HISTORY':1,'MISSING_OR_INCOMPLETE_WIN_MARKET':1}


def test_missing_roster_action():
    c=make_db();c.execute('delete from runners')
    p=plan_prefetch(c,now=NOW.isoformat());assert p['tasks'][0]['reason']=='MISSING_STARTLIST'


def test_persisted_history_removes_fund_task():
    c=make_db();fundamental(c)
    assert actions(plan_prefetch(c,now=NOW.isoformat()))==['COLLECT_WIN_MARKET']


def test_complete_market_removes_market_task():
    c=make_db();market(c)
    assert actions(plan_prefetch(c,now=NOW.isoformat()))==['COLLECT_FUNDAMENTALS']


def test_complete_field_no_tasks():
    c=make_db();fundamental(c);market(c)
    assert plan_prefetch(c,now=NOW.isoformat())['tasks']==[]


def test_partial_fund_retries():
    c=make_db();fundamental(c,one_missing=True)
    assert plan_prefetch(c,now=NOW.isoformat())['tasks'][0]['reason']=='INCOMPLETE_FULL_FIELD_HISTORY'


def test_unverified_history_retries():
    c=make_db();fundamental(c,complete=False)
    assert plan_prefetch(c,now=NOW.isoformat())['tasks'][0]['reason']=='INCOMPLETE_FULL_FIELD_HISTORY'


def test_old_complete_then_new_partial_retries():
    c=make_db();fundamental(c,now=NOW-timedelta(minutes=10))
    fundamental(c,now=NOW,one_missing=True)
    assert plan_prefetch(c,now=NOW.isoformat())['tasks'][0]['reason']=='INCOMPLETE_FULL_FIELD_HISTORY'


def test_future_snapshots_never_count():
    c=make_db();future=NOW+timedelta(minutes=3)
    fundamental(c,now=future);market(c,now=future)
    assert len(plan_prefetch(c,now=NOW.isoformat())['tasks'])==2


def test_market_partial_triggers_refresh():
    c=make_db();fundamental(c);market(c,include=(1,2))
    assert actions(plan_prefetch(c,now=NOW.isoformat()))==['COLLECT_WIN_MARKET']


def test_scratched_invalid_market_quote_ignored():
    c=make_db();c.execute('update runners set scratched=1 where selection_id="3"')
    # fund scratch corresponding
    for n in (1,2,3):
        c.execute('insert into runner_fundamental_snapshots values (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (RID,str(n),NOW.isoformat(),NOW.isoformat(),10,n,'source',1,int(n==3),f'Named Runner {n}',n,'D','Q'))
    market(c,odds=4.)
    c.execute('update provider_market_snapshots set odds_decimal=null where selection_key="3"')
    assert plan_prefetch(c,now=NOW.isoformat())['tasks']==[]


def test_unknown_roster_scratch_never_suppresses_source_fetch():
    c = make_db()
    fundamental(c); market(c)
    c.execute("UPDATE runners SET scratched=NULL WHERE selection_id='2'")
    p = plan_prefetch(c, now=NOW.isoformat())
    assert actions(p) == ['COLLECT_FUNDAMENTALS', 'COLLECT_WIN_MARKET']
    assert p['tasks'][0]['reason'] == 'UNVERIFIED_ROSTER_SCRATCH_OR_ID'


def test_conflicting_fundamental_scratch_retries_source():
    c = make_db()
    fundamental(c); market(c)
    c.execute("UPDATE runner_fundamental_snapshots SET scratched=1 WHERE selection_id='2'")
    p = plan_prefetch(c, now=NOW.isoformat())
    assert actions(p) == ['COLLECT_FUNDAMENTALS']
    assert p['tasks'][0]['reason'] == 'INCOMPLETE_FULL_FIELD_HISTORY'


def test_missing_snapshot_scratch_retries_source():
    c = make_db()
    fundamental(c); market(c)
    c.execute("UPDATE runner_fundamental_snapshots SET scratched=NULL WHERE selection_id='1'")
    assert actions(plan_prefetch(c, now=NOW.isoformat())) == ['COLLECT_FUNDAMENTALS']


def test_invalid_history_record_retries_source():
    c = make_db()
    fundamental(c); market(c)
    c.execute("UPDATE runner_fundamental_snapshots SET history_total_wins=11 WHERE selection_id='1'")
    assert actions(plan_prefetch(c, now=NOW.isoformat())) == ['COLLECT_FUNDAMENTALS']


def test_duplicate_roster_id_never_counts_full_field():
    c = make_db()
    fundamental(c); market(c)
    c.execute("INSERT INTO runners SELECT * FROM runners WHERE selection_id='1'")
    p = plan_prefetch(c, now=NOW.isoformat())
    assert actions(p) == ['COLLECT_FUNDAMENTALS', 'COLLECT_WIN_MARKET']
    assert p['tasks'][0]['reason'] == 'UNVERIFIED_ROSTER_SCRATCH_OR_ID'


def test_no_market_fetch_more_than_twelve_minutes_before_start():
    c=make_db();c.execute('update races set start_time_utc=?',((NOW+timedelta(minutes=30)).isoformat(),))
    assert actions(plan_prefetch(c,now=NOW.isoformat()))==['COLLECT_FUNDAMENTALS']


def test_never_prefetch_inside_t4():
    c=make_db();c.execute('update races set start_time_utc=?',((NOW+timedelta(minutes=3)).isoformat(),))
    assert plan_prefetch(c,now=NOW.isoformat())['tasks']==[]


def test_never_prefetch_past_race():
    c=make_db();c.execute('update races set start_time_utc=?',((NOW-timedelta(minutes=3)).isoformat(),))
    assert plan_prefetch(c,now=NOW.isoformat())['tasks']==[]


def test_horizon_omits_too_distant():
    c=make_db();c.execute('update races set start_time_utc=?',((NOW+timedelta(minutes=91)).isoformat(),))
    assert not plan_prefetch(c,now=NOW.isoformat())['tasks']


def test_exclude_other_sport():
    c=make_db();c.execute('update races set discipline="gallop"')
    assert plan_prefetch(c,now=NOW.isoformat())['races_considered']==0


def test_exclude_composite():
    c=make_db();c.execute('update races set track="Testbane/Others"')
    assert not plan_prefetch(c,now=NOW.isoformat())['tasks']


def test_dedupe_likely_duplicate():
    c=make_db();add_race(c,rid='RIKSTOTO:T2_NR_2026-10-30:1',start=START,track='Testbane',no=1)
    assert plan_prefetch(c,now=NOW.isoformat())['races_considered']==1


def test_max_tasks_truncates():
    p=plan_prefetch(make_db(),now=NOW.isoformat(),max_tasks=1)
    assert p['tasks_returned']==1 and p['tasks_available']==2 and p['truncated']
    assert actions(p) == ['COLLECT_FUNDAMENTALS']
    assert [(task['race_id'], task['action']) for task in p['deferred_tasks']] == [
        (RID, 'COLLECT_WIN_MARKET'),
    ]


def test_each_task_rechecks_its_own_start_time():
    db = make_db()
    later_id = "RIKSTOTO:T2_NR_2026-10-30:2"
    later_start = (NOW + timedelta(minutes=20)).isoformat()
    add_race(db, rid=later_id, start=later_start, no=2)
    plan = plan_prefetch(db, now=NOW.isoformat(), market_window_minutes=30)
    assert {task["race_id"]: task["race_start_utc"] for task in plan["tasks"]} == {
        RID: START,
        later_id: later_start,
    }

    class MarketOnly:
        def collect_fundamentals(self, **kwargs):
            assert kwargs["race_id"] == later_id
            return 3, True, "https://example.test/start"

        def collect_market(self, **kwargs):
            assert kwargs["race_id"] == later_id
            return 3, 0

    events = execute_prefetch(plan, MarketOnly(), now=NOW,
                              clock=lambda: NOW + timedelta(minutes=4))
    assert {(event["race_id"], event["status"]) for event in events} == {
        (RID, "TOO_LATE_TO_PREFETCH"),
        (later_id, "FETCHED_NOT_PROVEN_COMPLETE"),
    }


@pytest.mark.parametrize('kwargs',[{'horizon_minutes':1},{'horizon_minutes':float('nan')},
                                   {'lead_minutes':0},{'market_window_minutes':4},
                                   {'max_tasks':0},{'max_tasks':1.2}])
def test_invalid_inputs(kwargs):
    with pytest.raises(ValueError):plan_prefetch(make_db(),now=NOW.isoformat(),**kwargs)


def test_time_zone_required():
    with pytest.raises(ValueError):plan_prefetch(make_db(),now='2026-10-30T12:00:00')


class CollectorStub:
    def __init__(self,c):self.c=c;self.calls=[]
    def collect_fundamentals(self,**kw):
        self.calls.append(('fund',kw));fundamental(self.c,now=kw['observed_at'])
        return 3,True,'https://example.test/start'
    def collect_market(self,**kw):
        self.calls.append(('market',kw));market(self.c,now=kw['observed_at'])
        return 3,0


def test_execute_prefetch_to_complete_cohort():
    c=make_db();p=plan_prefetch(c,now=NOW.isoformat());coll=CollectorStub(c)
    events=execute_prefetch(p,coll,now=NOW,clock=lambda:NOW)
    assert len(events)==2
    assert all(e['status']=='FETCHED_NOT_PROVEN_COMPLETE' for e in events)
    assert len(coll.calls)==2 and coll.calls[1][1]['products']=={'V'}
    assert plan_prefetch(c,now=NOW.isoformat())['tasks']==[]


def test_execute_rechecks_current_time():
    c=make_db();p=plan_prefetch(c,now=NOW.isoformat());coll=CollectorStub(c)
    events=execute_prefetch(p,coll,now=NOW,clock=lambda:NOW+timedelta(minutes=7))
    assert all(x['status']=='TOO_LATE_TO_PREFETCH' for x in events)
    assert coll.calls==[]


def test_execute_provider_failure_does_not_hide():
    class Broken:
        def collect_fundamentals(self,**kw):raise OSError('no network')
        def collect_market(self,**kw):return (0,1)
    events=execute_prefetch(plan_prefetch(make_db(),now=NOW.isoformat()),Broken(),now=NOW,clock=lambda:NOW)
    assert events[0]['status']=='PROVIDER_EXCEPTION' and events[1]['status']=='SOURCE_UNAVAILABLE'


def test_execute_never_calls_unknown_action():
    p=plan_prefetch(make_db(),now=NOW.isoformat());p['tasks'][0]['action']='SPEND_MONEY'
    with pytest.raises(ValueError):execute_prefetch(p,CollectorStub(make_db()),now=NOW,clock=lambda:NOW)


def test_invalid_plan_rejected():
    p=plan_prefetch(make_db(),now=NOW.isoformat());p['schema_version']='FAKE'
    with pytest.raises(ValueError):execute_prefetch(p,CollectorStub(make_db()),now=NOW)


def test_refresh_completed_field_near_start_if_stale():
    c=make_db();fundamental(c,now=NOW);market(c,now=NOW)
    after=NOW+timedelta(minutes=3,seconds=20)
    p=plan_prefetch(c,now=after.isoformat())
    assert actions(p)==['COLLECT_FUNDAMENTALS','COLLECT_WIN_MARKET']
    assert 'REFRESH_VERIFIED_FUNDAMENTALS_NEAR_START' in p['reason_counts']
    assert 'REFRESH_WIN_MARKET_NEAR_START' in p['reason_counts']


def test_not_refresh_complete_cohort_if_still_fresh():
    c=make_db();fundamental(c,now=NOW);market(c,now=NOW)
    p=plan_prefetch(c,now=(NOW+timedelta(minutes=1)).isoformat())
    assert p['tasks']==[]


def test_generic_sql_horse_name_never_suppresses_prefetch():
    c = make_db()
    fundamental(c)
    market(c)
    c.execute("UPDATE runners SET horse_name='Häst 1' WHERE selection_id='1'")
    p = plan_prefetch(c, now=NOW.isoformat())
    assert actions(p) == ["COLLECT_FUNDAMENTALS", "COLLECT_WIN_MARKET"]
    assert p["tasks"][0]["reason"] == "UNRESOLVED_PLACEHOLDER_ROSTER_IDENTITY"


def test_scratched_generic_name_also_blocks_source_readiness():
    c = make_db()
    fundamental(c)
    market(c)
    c.execute("UPDATE runners SET horse_name='Horse 3', scratched=1 WHERE selection_id='3'")
    c.execute("UPDATE runner_fundamental_snapshots SET scratched=1 WHERE selection_id='3'")
    p = plan_prefetch(c, now=NOW.isoformat())
    assert actions(p) == ["COLLECT_FUNDAMENTALS", "COLLECT_WIN_MARKET"]
    assert p["tasks"][0]["reason"] == "UNRESOLVED_PLACEHOLDER_ROSTER_IDENTITY"


def test_non_placeholder_named_horse_remains_eligible_for_source_completion():
    c = make_db()
    fundamental(c)
    market(c)
    c.execute("UPDATE runners SET horse_name='Horse Power 1' WHERE selection_id='1'")
    p = plan_prefetch(c, now=NOW.isoformat())
    assert p["tasks"] == []



@pytest.mark.parametrize(("table", "field", "reason"), [
    ("runner_fundamental_snapshots", "observed_at_utc",
     "INCOMPLETE_FULL_FIELD_HISTORY"),
    ("runner_fundamental_snapshots", "feature_as_of_utc",
     "INCOMPLETE_FULL_FIELD_HISTORY"),
    ("provider_market_snapshots", "observed_at_utc",
     "MISSING_OR_INCOMPLETE_WIN_MARKET"),
    ("provider_market_snapshots", "provider_updated_at_utc",
     "MISSING_OR_INCOMPLETE_WIN_MARKET"),
])
def test_prefetch_never_accepts_lexically_early_but_utc_future_snapshot(
    table, field, reason,
):
    c = make_db()
    fundamental(c)
    market(c)
    future = (NOW + timedelta(minutes=55)).astimezone(
        timezone(timedelta(hours=-1))
    ).isoformat()
    assert future[:13] < NOW.isoformat()[:13]
    c.execute(f"UPDATE {table} SET {field}=?", (future,))
    plan = plan_prefetch(c, now=NOW.isoformat())
    assert reason in plan["reason_counts"]
    assert plan["authority"] == "SHADOW_RESEARCH_ONLY"


@pytest.mark.parametrize(("table", "reason"), [
    ("runner_fundamental_snapshots", "INCOMPLETE_FULL_FIELD_HISTORY"),
    ("provider_market_snapshots", "MISSING_OR_INCOMPLETE_WIN_MARKET"),
])
def test_prefetch_invalid_selected_iso_clock_is_source_refresh_not_exception(
    table, reason,
):
    c = make_db()
    fundamental(c)
    market(c)
    c.execute(f"UPDATE {table} SET observed_at_utc=?",
              ("1999-invalid-source-clock",))
    plan = plan_prefetch(c, now=NOW.isoformat())
    assert reason in plan["reason_counts"]
    assert plan["tasks_returned"] >= 1


def test_prefetch_valid_utc_offset_with_true_past_snapshot_is_accepted():
    c = make_db()
    fundamental(c)
    market(c)
    past = (NOW - timedelta(minutes=5)).astimezone(
        timezone(timedelta(hours=-1))
    ).isoformat()
    c.execute("UPDATE runner_fundamental_snapshots SET observed_at_utc=?, feature_as_of_utc=?",
              (past, past))
    c.execute("UPDATE provider_market_snapshots SET observed_at_utc=?", (past,))
    plan = plan_prefetch(c, now=NOW.isoformat())
    assert "INCOMPLETE_FULL_FIELD_HISTORY" not in plan["reason_counts"]
    assert "MISSING_OR_INCOMPLETE_WIN_MARKET" not in plan["reason_counts"]

def test_nordic_priority_preserves_capacity_and_has_no_country_bias():
    conn = make_db()
    conn.execute("UPDATE races SET country='FR', start_time_utc=?", ((NOW + timedelta(minutes=6)).isoformat(),))
    add_race(conn, rid="NO", track="Biri", nation="NO", start=(NOW + timedelta(minutes=10)).isoformat())
    add_race(conn, rid="SE", track="Kalmar", nation="SE")
    original = plan_prefetch(conn, now=NOW.isoformat(), max_tasks=4)
    ordered = plan_prefetch(conn, now=NOW.isoformat(), max_tasks=4, nordic_first=True)
    assert original["tasks"][0]["race_id"] == RID
    assert [t["race_id"] for t in ordered["tasks"]] == ["SE", "SE", "NO", "NO"]
    assert ordered["tasks_available"] == original["tasks_available"] == 6
    fallback = plan_prefetch(conn, now=NOW.isoformat(), max_tasks=5, nordic_first=True)
    assert fallback["tasks"][-1]["race_id"] == RID


def test_nordic_priority_uses_verified_roster_before_time_within_urgency():
    conn = make_db()
    conn.execute("UPDATE races SET country='NO', start_time_utc=?", ((NOW + timedelta(minutes=6)).isoformat(),))
    conn.execute("DELETE FROM runners")
    add_race(conn, rid="SE", track="Kalmar", nation="SE")
    plan = plan_prefetch(conn, now=NOW.isoformat(), max_tasks=1, nordic_first=True)
    assert plan["tasks"][0]["race_id"] == "SE"
