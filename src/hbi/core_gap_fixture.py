"""Enrich a CORE-002 compact day fixture with source-*timestamp* metadata.

No provider payload JSON, identities beyond already existing CORE-002 data, or
settlement information is copied. Used for reproducible CORE-003 gap forensics.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

def build_gap_fixture(archived_db: Path, core002_fixture: Path, output: Path,
                      *, race_date: str) -> dict[str,int]:
    if output.exists():raise FileExistsError(output)
    if not archived_db.is_file() or not core002_fixture.is_file():raise FileNotFoundError('source db missing')
    output.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(core002_fixture,output)
    source=sqlite3.connect(f'file:{archived_db.resolve().as_posix()}?mode=ro&immutable=1',uri=True)
    source.row_factory=sqlite3.Row
    dst=sqlite3.connect(output)
    try:
        dst.executescript('''
           create table provider_race_refs (
             race_id text, provider text,provider_raceday_key text,race_number integer);
           create table provider_payloads (
             provider text,category text,provider_raceday_key text,race_number integer,
             observed_at_utc text);
           create index ix_core3_payload on provider_payloads(category,provider_raceday_key,race_number);
        ''')
        dates={x[0] for x in dst.execute('select distinct race_date from races')}
        if dates!={race_date}:raise ValueError('CORE-002 fixture date does not match requested race_date')
        ids={x[0] for x in dst.execute('select race_id from races')}
        refs=[r for r in source.execute('select race_id,provider,provider_raceday_key,race_number from provider_race_refs')
              if r['race_id'] in ids]
        dst.executemany('insert into provider_race_refs values (?,?,?,?)',
                        [tuple(r) for r in refs])
        ref_keys={r['provider_raceday_key'] for r in refs}
        meta=[]
        for r in source.execute('''select provider,category,provider_raceday_key,race_number,observed_at_utc
                                   from provider_payloads where category in
                                   ('RACEDAY_STARTS','FULL_FIELD_ONLY_V1')'''):
            if (r['category']=='RACEDAY_STARTS' and r['provider_raceday_key'] in ref_keys) or (
                r['category']=='FULL_FIELD_ONLY_V1' and r['provider_raceday_key'] in ids):
                meta.append(tuple(r))
        dst.executemany('insert into provider_payloads values (?,?,?,?,?)',meta)
        dst.commit()
        assert dst.execute('pragma integrity_check').fetchone()[0]=='ok'
        result={'races':len(ids),'provider_race_refs':len(refs),'provider_payload_timestamps':len(meta)}
    except BaseException:
        dst.close();output.unlink(missing_ok=True);raise
    finally:source.close()
    dst.close()
    return result


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser()
    p.add_argument('--archive',required=True);p.add_argument('--core002',required=True)
    p.add_argument('--out',required=True);p.add_argument('--date',required=True)
    args=p.parse_args(argv)
    print(build_gap_fixture(Path(args.archive),Path(args.core002),Path(args.out),race_date=args.date))
    return 0

if __name__=='__main__':raise SystemExit(main())
