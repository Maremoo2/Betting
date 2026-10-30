"""Make a tiny read-only research fixture from a previously archived SQLite database.

Exports only the historical races explicitly requested and their stored data, not outcomes.
This is a convenience for reproducible CORE-001 tests, not a validated source provenance.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

TABLES = ('races', 'runners', 'runner_fundamental_snapshots',
          'provider_market_snapshots', 'fundamental_model_runs')


def extract_fixture(source: Path, destination: Path, race_ids: list[str]) -> dict[str,int]:
    if not race_ids:
        raise ValueError('At least one race_id is required')
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f'file:{source.resolve().as_posix()}?mode=ro&immutable=1',uri=True)
    dst = sqlite3.connect(destination)
    stats={}
    try:
        dst.execute('pragma foreign_keys=off')
        for table in TABLES:
            record=src.execute('select sql from sqlite_master where type=? and name=?',('table',table)).fetchone()
            if not record:raise ValueError(f'Missing {table}')
            dst.execute(record[0])
            count=0
            for race in race_ids:
                if table == 'provider_market_snapshots':
                    start_row=src.execute('select start_time_utc from races where race_id=?',(race,)).fetchone()
                    if start_row:
                        start=datetime.fromisoformat(start_row[0])
                        earliest=(start-timedelta(minutes=30)).isoformat()
                        rows=src.execute(
                            'select * from provider_market_snapshots where race_id=? and product=? and observed_at_utc>=? and observed_at_utc<?',
                            (race,'V',earliest,start_row[0])).fetchall()
                    else:
                        rows=[]
                else:
                    rows=src.execute(f'select * from {table} where race_id=?',(race,)).fetchall()
                if rows:
                    marks=','.join('?' for _ in rows[0])
                    dst.executemany(f'insert into {table} values({marks})',rows)
                    count+=len(rows)
            stats[table]=count
        dst.commit()
        if dst.execute('pragma integrity_check').fetchone()[0]!='ok':
            raise ValueError('Fixture integrity_check failed')
    except BaseException:
        dst.close();destination.unlink(missing_ok=True);raise
    else:
        src.close();dst.close()
    return stats


def main(argv:list[str]|None=None)->None:
    p=argparse.ArgumentParser()
    p.add_argument('--db',required=True);p.add_argument('--out',required=True)
    p.add_argument('--race-id',action='append',required=True)
    a=p.parse_args(argv)
    print(extract_fixture(Path(a.db),Path(a.out),a.race_id))

if __name__=='__main__':main()
