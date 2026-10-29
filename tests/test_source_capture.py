import hashlib
import json
from typing import ClassVar
from unittest.mock import Mock

import pytest

from hbi.source_capture import (
    _atg_starts,
    _starts,
    allowed_url,
    fetch_original,
    resolve_atg,
    verify,
)


class Response:
    status=200
    headers: ClassVar[dict[str, str]] = {'Date':'Thu, 29 Oct 2026 13:00:00 GMT', 'Content-Type':'application/json'}
    def __init__(self,body): self.body=body
    def read(self,n): return self.body[:n]
    def __enter__(self): return self
    def __exit__(self,*args):return False


@pytest.mark.parametrize('url,expected',[
('https://www.rikstoto.no/api/racedays/',True),
('https://www.rikstoto.no/api/racedays/MO_NR_2026-11-01/starts',True),
('https://www.rikstoto.no/api/game/program/MO_NR_2026-11-01/V',True),
('https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-01_80_2',True),
('https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/2026-11-01?headToHeadEnabled=true',True),
('http://www.rikstoto.no/api/racedays/',False),
('https://www.rikstoto.no.evil.com/api/racedays/',False),
('https://www.rikstoto.no/api/transfer/funds',False),
('https://www.rikstoto.no/api/racedays/../../secret',False),
('https://www.rikstoto.no/api/racedays/?auth=abc',False),
('https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-01_80_3',False),
])
def test_allowlist(url,expected):assert allowed_url(url) == expected


def test_raw_sha_keeps_whitespace(tmp_path):
    body=b' {"a":  1} \n'
    opener=Mock();opener.open.return_value=Response(body)
    ev,payload=fetch_original('racedays','https://www.rikstoto.no/api/racedays/',tmp_path,opener)
    assert payload=={'a':1}
    assert ev.original_body_sha256==hashlib.sha256(body).hexdigest()
    assert (tmp_path/ev.body_path).read_bytes()==body
    assert ev.replayable_raw_body_in_artifact


def test_verify_tamper_detection(tmp_path):
    body=b'{"result":[]}'
    opener=Mock();opener.open.return_value=Response(body)
    ev,_=fetch_original('racedays','https://www.rikstoto.no/api/racedays/',tmp_path,opener)
    (tmp_path/'manifest.json').write_text(json.dumps({'records':[ev.__dict__]}))
    assert verify(tmp_path)==[]
    (tmp_path/ev.body_path).write_bytes(b'changed')
    assert verify(tmp_path)==['SHA256_MISMATCH:racedays']


def test_atg_unique_exact_race():
    p={'tracks':[{'countryCode':'NO','sport':'trot','name':'Momarken','races':[{'number':2,'id':'2026-11-01_80_2','startTime':'2026-11-01T19:15:00+01:00'}]}]}
    from datetime import UTC, datetime
    assert resolve_atg(p,'Momarken',2,datetime(2026,11,1,18,15,tzinfo=UTC),date='2026-11-01')[0]=='2026-11-01_80_2'
    assert resolve_atg(p,'Bjerke',2,datetime(2026,11,1,18,15,tzinfo=UTC),date='2026-11-01')[0] is None
    assert resolve_atg(p,'Momarken',2,datetime(2026,11,1,16,15,tzinfo=UTC),date='2026-11-01')[0] is None


def test_unverified_history_not_overclaimed():
    assert _starts({'result':{'2':[{'startNumber':3}]}},2)==[{'startNumber':3}]
    assert _atg_starts({'races':[{'starts':[{'horse':{'id':123}}]}]})==[{'horse':{'id':123}}]
    assert _atg_starts({'races':[{},{}]}) == []
