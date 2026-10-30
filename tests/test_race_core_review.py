from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hbi.race_core_review import analyze_race, historical_win_prior, write_report

RACE = 'RIKSTOTO:TEST:1'
T0 = '2026-10-28T18:23:05+00:00'
START = '2026-10-28T18:27:00+00:00'
MARKET = '2026-10-28T18:23:00+00:00'


def fixture():
    db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
    db.executescript('''
        create table races(race_id text,race_date text,country text,track text,race_no integer,start_time_utc text,discipline text,distance_m int,start_method text);
        create table runners(race_id text,selection_id text,horse_name text,post_position int,driver_or_jockey text,trainer text,scratched int);
        create table runner_fundamental_snapshots(race_id text,selection_id text,horse_name text,post_position int,driver_or_jockey text,trainer text,scratched int,observed_at_utc text,feature_as_of_utc text,history_total_starts int,history_total_wins int,full_field_history_complete int,source_uri text,data_quality text,current_year_starts int,record_auto text,record_volt text);
        create table provider_market_snapshots(race_id text,selection_key text,product text,odds_decimal real,observed_at_utc text,provider_updated_at_utc text);
    ''')
    db.execute('insert into races values (?,?,?,?,?,?,?,?,?)',(RACE,'2026-10-28','SE','Synthetic',1,START,'trot',2140,'Volt'))
    vals=[('1','Alpha',10,3,False,4.5),('2','Beta',20,2,False,8.0),('3','Gamma',0,0,True,-0.02)]
    for id_,name,starts,wins,scratched,odds in vals:
        db.execute('insert into runners values (?,?,?,?,?,?,?)',(RACE,id_,name,int(id_),'J','T',int(scratched)))
        db.execute('insert into runner_fundamental_snapshots values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (RACE,id_,name,int(id_),'J','T',int(scratched),T0,T0,starts if not scratched else None,wins if not scratched else None,int(not scratched),'https://example.test','FULL_FIELD_HISTORY_ATG',starts,'a','v'))
        db.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',(RACE,id_,'V',odds,MARKET,MARKET))
    db.commit()
    return db


class CoreModelTests(unittest.TestCase):
    def test_existing_v1_formula(self):
        p,k=historical_win_prior([{'selection_id':'1','scratched':False,'history_total_starts':10,'history_total_wins':3},
                                  {'selection_id':'2','scratched':False,'history_total_starts':20,'history_total_wins':0}])
        a=(3+6*0.5)/(10+6);b=(0+6*0.5)/(20+6)
        self.assertAlmostEqual(p['1'],a/(a+b));self.assertAlmostEqual(p['2'],b/(a+b));self.assertEqual(k,2)

    def test_unreported_history_uses_prior_and_counts_unknown(self):
        p,k=historical_win_prior([{'selection_id':'1','scratched':False,'history_total_starts':10,'history_total_wins':2},
                                  {'selection_id':'2','scratched':False,'history_total_starts':None,'history_total_wins':None}])
        self.assertEqual(k,1);self.assertAlmostEqual(sum(p.values()),1)

    def test_corrupt_history_does_not_leak_negative_strength(self):
        for starts,wins in [(-1,0),(4,5),(3,-1),('bad',3)]:
            p,k=historical_win_prior([{'selection_id':'1','scratched':False,'history_total_starts':starts,'history_total_wins':wins},
                                      {'selection_id':'2','scratched':False,'history_total_starts':1,'history_total_wins':1}])
            self.assertEqual(k,1);self.assertTrue(all(math.isfinite(x) and x>0 for x in p.values()))

    def test_one_active_returns_no_probs(self):
        self.assertEqual(historical_win_prior([{'selection_id':'1','scratched':False}]),({},0))


class CoreEndToEndTests(unittest.TestCase):
    def setUp(self):self.db=fixture()
    def tearDown(self):self.db.close()
    def report(self,t=T0):return analyze_race(self.db,race_id=RACE,decision_at=t)
    def test_complete_field(self):
        r=self.report();self.assertTrue(r['model_ready_for_research'])
        self.assertEqual(len(r['runner_rows']),3);self.assertEqual(r['active_runners'],2)
        self.assertEqual(r['known_history_runners'],2)
        self.assertAlmostEqual(r['probability_sum'],1)
        self.assertEqual(sum(x['status']=='PASS' for x in r['runner_rows'] if x['scratched']),1)
        self.assertTrue(all(x['p_win'] is not None for x in r['runner_rows'] if not x['scratched']))
        self.assertTrue(all(x['status'] != 'BET' for x in r['runner_rows']))
    def test_fair_and_ev_and_minimum_price(self):
        r=self.report();x=r['runner_rows'][0]
        self.assertAlmostEqual(x['fair_odds'],1/x['p_win'])
        self.assertAlmostEqual(x['minimum_watch_odds'],1.1025/x['p_win'])
        self.assertAlmostEqual(x['theoretical_ev'],x['p_win']*x['available_odds']-1)
    def test_normalized_market_probabilities_sum(self):
        r=self.report();self.assertAlmostEqual(sum(x['normalized_market_p'] or 0 for x in r['runner_rows']),1)
    def test_no_future_information_at_earlier_cutoff(self):
        r=self.report('2026-10-28T18:22:00+00:00');self.assertFalse(r['model_ready_for_research'])
        self.assertIn('NO_FUNDAMENTAL_COHORT_AS_OF',r['blocks'])
        self.assertTrue(all(x['status']=='PASS' for x in r['runner_rows']))
        self.assertTrue(all(x['p_win'] is None for x in r['runner_rows']))
    def test_not_before_start(self):
        r=self.report(START);self.assertIn('NOT_BEFORE_RECORDED_START',r['blocks'])
        self.assertEqual(sum(x['status']=='WATCH' for x in r['runner_rows']),0)
    def test_market_cohort_missing_runner(self):
        self.db.execute('delete from provider_market_snapshots where selection_key=?',('2',))
        r=self.report();self.assertIn('MARKET_FIELD_MISMATCH',r['blocks'])
        self.assertEqual(sum(x['status']=='WATCH' for x in r['runner_rows']),0)
    def test_market_missing_preserves_independent_fundamental_p(self):
        self.db.execute('delete from provider_market_snapshots')
        r=self.report();self.assertFalse(r['model_ready_for_research'])
        self.assertTrue(r['fundamental_ready_for_research'])
        self.assertAlmostEqual(r['probability_sum'],1.0)
        self.assertEqual(sum(x['p_win'] is not None for x in r['runner_rows']),2)
        self.assertTrue(all(x['status']=='PASS' for x in r['runner_rows']))

    def test_fundamental_cohort_missing_runner(self):
        self.db.execute('delete from runner_fundamental_snapshots where selection_id=?',('2',))
        r=self.report();self.assertIn('FUNDAMENTAL_FIELD_MISMATCH',r['blocks'])
        self.assertTrue(all(x['p_win'] is None for x in r['runner_rows']))
    def test_history_shortfall_blocks(self):
        self.db.execute('update runner_fundamental_snapshots set history_total_starts=null,history_total_wins=null where selection_id=?',('2',))
        r=self.report();self.assertIn('LOW_HISTORY_COVERAGE',r['blocks'])
    def test_missing_history_source_blocks(self):
        self.db.execute('update runner_fundamental_snapshots set source_uri=null where selection_id=?',('1',))
        r=self.report();self.assertIn('FULL_FIELD_HISTORY_NOT_VERIFIED',r['blocks'])
    def test_invalid_active_odds_blocks(self):
        for odds in [0,-0.02,1, None]:
            self.db.execute('update provider_market_snapshots set odds_decimal=? where selection_key=?',(odds,'1'))
            r=self.report();self.assertIn('MISSING_OR_INVALID_ACTIVE_WIN_ODDS',r['blocks'])
    def test_future_provider_updated_timestamp_not_used(self):
        self.db.execute('update provider_market_snapshots set provider_updated_at_utc=?',('2026-10-28T18:25:00+00:00',))
        r=self.report();self.assertIn('NO_WIN_MARKET_AS_OF',r['blocks'])
    def test_roster_scratch_conflict_blocks(self):
        self.db.execute('update runners set scratched=0 where selection_id=?',('3',))
        r=self.report();self.assertIn('ROSTER_SCRATCH_DISAGREEMENT',r['blocks'])
    def test_later_partial_cohort_not_downgraded(self):
        t='2026-10-28T18:23:06+00:00'
        self.db.execute('update runner_fundamental_snapshots set observed_at_utc=? where selection_id=?',(t,'1'))
        r=self.report(t);self.assertIn('FUNDAMENTAL_FIELD_MISMATCH',r['blocks'])
    def test_duplicate_market_runner_blocks(self):
        self.db.execute('insert into provider_market_snapshots values (?,?,?,?,?,?)',(RACE,'1','V',8.8,MARKET,MARKET))
        r=self.report();self.assertIn('DUPLICATE_MARKET_SELECTIONS',r['blocks'])
    def test_missing_distance_marked_not_assumed(self):
        self.db.execute('update races set distance_m=null')
        r=self.report();self.assertTrue(r['model_ready_for_research'])
        self.assertEqual(r['feature_coverage']['distance_m_present'],0)
    def test_select_custom_price_margin(self):
        r=analyze_race(self.db,race_id=RACE,decision_at=T0,edge_target=0.1,safety_margin=0.1)
        x=r['runner_rows'][0];self.assertAlmostEqual(x['minimum_watch_odds'],x['fair_odds']*1.21)
    def test_margin_invalid(self):
        with self.assertRaises(ValueError):analyze_race(self.db,race_id=RACE,decision_at=T0,edge_target=-0.1)
    def test_unknown_race(self):
        with self.assertRaises(ValueError):analyze_race(self.db,race_id='not there',decision_at=T0)
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):self.report('2026-10-28T18:23:05')
    def test_report_writes_three_files(self):
        r=self.report()
        with tempfile.TemporaryDirectory() as tmp:
            write_report(r,Path(tmp));self.assertEqual(len(list(Path(tmp).iterdir())),3)
            self.assertEqual(len(json.loads((Path(tmp)/'race_core.json').read_text())['runner_rows']),3)
            self.assertIn('Alpha',(Path(tmp)/'race_core.md').read_text())


class RealArchivedRaceTests(unittest.TestCase):
    def test_historical_champion_probability_exact(self):
        path=os.environ.get('HBI_ARCHIVE_20261028')
        if not path or not Path(path).exists():self.skipTest('Set HBI_ARCHIVE_20261028')
        db=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
        try:
            race_id='RIKSTOTO:S2_NR_2026-10-28:4'
            r=analyze_race(db,race_id=race_id,decision_at='2026-10-28T18:23:05.413188+00:00')
            self.assertTrue(r['model_ready_for_research'])
            self.assertEqual(len(r['runner_rows']),12)
            self.assertEqual(r['active_runners'],11)
            self.assertAlmostEqual(r['probability_sum'],1)
            original=json.loads(db.execute('select probabilities_json from fundamental_model_runs where race_id=?',(race_id,)).fetchone()[0])
            actual={row['selection_id']:row['p_win'] for row in r['runner_rows'] if row['p_win'] is not None}
            self.assertEqual(original,actual)
            self.assertEqual(sum(row['status']=='WATCH' for row in r['runner_rows']),7)
        finally:db.close()

    def test_other_historical_race_is_blocked_at_t_minus_four(self):
        path=os.environ.get('HBI_ARCHIVE_20261028')
        if not path or not Path(path).exists():self.skipTest('Set HBI_ARCHIVE_20261028')
        db=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro&immutable=1',uri=True)
        db.row_factory=sqlite3.Row
        try:
            race='RIKSTOTO:S2_NR_2026-10-28:6'
            early=analyze_race(db,race_id=race,decision_at='2026-10-28T19:12:00+00:00')
            late=analyze_race(db,race_id=race,decision_at='2026-10-28T19:15:26.713600+00:00')
            self.assertFalse(early['model_ready_for_research'])
            self.assertTrue(late['model_ready_for_research'])
            self.assertEqual(late['active_runners'],15)
            self.assertEqual(sum(x['status']=='WATCH' for x in early['runner_rows']),0)
        finally:db.close()

    def test_historical_missing_roster_is_blocked(self):
        path=os.environ.get('HBI_ARCHIVE_20261028')
        if not path or not Path(path).exists():self.skipTest('Set HBI_ARCHIVE_20261028')
        db=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro&immutable=1',uri=True)
        db.row_factory=sqlite3.Row
        try:
            r=analyze_race(db,race_id='RIKSTOTO:S2_NR_2026-10-28:1',decision_at='2026-10-28T17:11:00+00:00')
            self.assertFalse(r['model_ready_for_research'])
            self.assertIn('NO_CANONICAL_ROSTER',r['blocks'])
        finally:db.close()


if __name__=='__main__':unittest.main()
