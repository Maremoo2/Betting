from contextlib import contextmanager
from datetime import UTC,datetime,timedelta
from hbi.core_prefetch_worker import run_tick
from test_core_prefetch import NOW, make_db, CollectorStub
import pytest

class StoreStub:
    def __init__(self, conn):self.conn=conn
    @contextmanager
    def connect(self):yield self.conn

class DiscoveringCollector(CollectorStub):
    def discover(self,now):return ['R1']


def test_worker_integrates_before_after():
    conn=make_db()
    store=StoreStub(conn);coll=DiscoveringCollector(conn)
    r=run_tick(store=store,collector=coll,now=NOW,clock=lambda:NOW)
    assert r['discovered']==1
    assert r['tasks_prepared']==2 and r['tasks_attempted']==2
    assert r['tasks_still_needed']==0
    assert r['real_bet_count']==0 and r['model_invocations']==0


def test_worker_discovery_optional():
    conn=make_db();coll=CollectorStub(conn)
    r=run_tick(store=StoreStub(conn),collector=coll,now=NOW,clock=lambda:NOW,discover=False)
    assert r['discovered']==0 and r['tasks_attempted']==2


def test_worker_budget_stops_after_one():
    conn=make_db();coll=DiscoveringCollector(conn)
    r=run_tick(store=StoreStub(conn),collector=coll,now=NOW,clock=lambda:NOW,max_tasks=1)
    assert r['tasks_prepared']==2 and r['tasks_attempted']==1
    assert r['tasks_still_needed']==1


def test_worker_rejects_naive_now():
    with pytest.raises(ValueError):
        run_tick(store=StoreStub(make_db()),collector=DiscoveringCollector(make_db()),
                 now=datetime(2026,10,30,12,0),clock=lambda:NOW)
