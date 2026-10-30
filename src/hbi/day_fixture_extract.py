"""Extract only the input snapshots relevant to CORE-002's T-minus-day replay.

A source DB can be hundreds of MB; the fixture contains start/runner records and
latest eligible pre-cutoff input cohorts only. No results or settlement tables.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .day_core_review import _latest_cohort, _valid_date

TABLES = ('races', 'runners', 'runner_fundamental_snapshots',
          'provider_market_snapshots', 'fundamental_model_runs')


def extract_day_fixture(source: Path, destination: Path, race_date: str,
                        *, cutoff_minutes: float = 4., track: str | None = None) -> dict[str, int]:
    _valid_date(race_date)
    if not 0 < cutoff_minutes <= 120:
        raise ValueError('Invalid cutoff_minutes')
    if destination.exists():
        raise FileExistsError(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f'file:{source.resolve().as_posix()}?mode=ro&immutable=1', uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(destination)
    counts: dict[str, int] = {}
    try:
        dst.execute('pragma foreign_keys=off')
        rows = src.execute('select * from races where race_date=?' +
                           (' and track=?' if track is not None else ''),
                           (race_date, track) if track is not None else (race_date,)).fetchall()
        if not rows:
            raise ValueError('No races found')
        for table in TABLES:
            schema = src.execute('select sql from sqlite_master where type=? and name=?',
                                 ('table', table)).fetchone()
            if schema is None or not schema[0]:
                raise ValueError(f'Missing table {table}')
            dst.execute(schema[0])
            counts[table] = 0
        for race in rows:
            race_id = race['race_id']
            start = datetime.fromisoformat(race['start_time_utc'])
            cutoff = (start - timedelta(minutes=cutoff_minutes)).isoformat()
            payloads = {
                'races': [race],
                'runners': src.execute('select * from runners where race_id=?', (race_id,)).fetchall(),
                'runner_fundamental_snapshots': _latest_cohort(src, race_id, 'runner_fundamental_snapshots', cutoff),
                'provider_market_snapshots': _latest_cohort(src, race_id, 'provider_market_snapshots', cutoff),
                'fundamental_model_runs': src.execute(
                    'select * from fundamental_model_runs where race_id=? and created_at_utc<=?',
                    (race_id, cutoff),
                ).fetchall(),
            }
            for table, records in payloads.items():
                if not records:
                    continue
                example = records[0]
                # Records from _latest_cohort are dicts; other rows are sqlite3.Row.
                if isinstance(example, dict):
                    columns = list(example)
                    values = [tuple(rec[k] for k in columns) for rec in records]
                else:
                    columns = list(example.keys())
                    values = [tuple(rec) for rec in records]
                col_sql = ','.join('"'+k+'"' for k in columns)
                placeholders = ','.join('?' for _ in columns)
                dst.executemany(f'insert into "{table}" ({col_sql}) values ({placeholders})', values)
                counts[table] += len(records)
        dst.commit()
        if dst.execute('pragma integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Fixture integrity check failed')
    except BaseException:
        dst.close()
        destination.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    dst.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='CORE-002 reproducible day fixture')
    p.add_argument('--db', required=True)
    p.add_argument('--date', required=True)
    p.add_argument('--track')
    p.add_argument('--out', required=True)
    p.add_argument('--cutoff-minutes', type=float, default=4.)
    a = p.parse_args(argv)
    print(extract_day_fixture(Path(a.db), Path(a.out), a.date,
                              cutoff_minutes=a.cutoff_minutes, track=a.track))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
