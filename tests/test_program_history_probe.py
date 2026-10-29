import hashlib
import json
from unittest.mock import MagicMock

import pytest

from hbi.program_history_probe import allowed, discover_pdf_urls, fetch, verify


class Resp:
    status = 200

    def __init__(self, b, mime):
        self.body = b
        self.headers = {'Content-Type': mime}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.body[:size]


def test_allowlist():
    assert allowed('https://old.travsport.no/pdf/BJ_20261031_Baneprogram.pdf', pdf=True)
    assert not allowed('https://evil.com/pdf/BJ_20261031_Baneprogram.pdf', pdf=True)
    assert not allowed('http://old.travsport.no/pdf/BJ_20261031_Baneprogram.pdf', pdf=True)
    assert not allowed('https://old.travsport.no/pdf/BJ_20261102_Baneprogram.pdf', pdf=True)
    assert not allowed('https://old.travsport.no/pdf/BJ_20261031_Baneprogram.pdf?token=secret', pdf=True)
    assert not allowed('https://old.travsport.no@evil.com/pdf/BJ_20261031_Baneprogram.pdf', pdf=True)


def test_html_link_discovery_only_exact_known_date():
    html = b'<a href="/pdf/BJ_20261031_Baneprogram.pdf">Official</a><a href="https://evil.com/a.pdf">Bad</a><a href="/pdf/BJ_20260127_Baneprogram.pdf">Wrong date</a>'
    links = discover_pdf_urls(html, 'https://old.travsport.no/Sport/Startlister/Bjerke-Travbane/?date=20261031', exact_prefix='BJ_20261031')
    assert links == ['https://old.travsport.no/pdf/BJ_20261031_Baneprogram.pdf']


def test_exact_raw_body_hash_and_file(tmp_path):
    raw = b'%PDF-1.7\nsynthetic bytes'
    op = MagicMock()
    op.open.return_value = Resp(raw, 'application/pdf')
    event, actual = fetch('bjerke_program', 'https://old.travsport.no/pdf/BJ_20261031_Baneprogram.pdf', tmp_path, pdf=True, opener=op)
    assert actual == raw
    assert event.sha256 == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / event.evidence_path).read_bytes() == raw
    assert event.provenance == 'HTTP_CAPTURE_CLOCK_ONLY_NOT_SOURCE_PUBLICATION_TIME'


def test_html_is_not_a_pdf(tmp_path):
    op = MagicMock()
    op.open.return_value = Resp(b'<html>Not found</html>', 'application/pdf')
    event, actual = fetch('bjerke_program', 'https://old.travsport.no/pdf/BJ_20261031_Baneprogram.pdf', tmp_path, pdf=True, opener=op)
    assert actual is None
    assert event.error == 'NOT_PDF_SIGNATURE'
    assert event.sha256 is None


def test_unlisted_urls_are_rejected_without_network(tmp_path):
    with pytest.raises(ValueError, match='URL_NOT_ALLOWLISTED'):
        fetch('bad_url', 'https://example.org/abc', tmp_path, pdf=True)


def test_tampering_detected(tmp_path):
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'raw/ok.body').write_bytes(b'good')
    manifest = {'records': [{'evidence_path': 'raw/ok.body', 'sha256': hashlib.sha256(b'good').hexdigest(), 'label': 'ok'}]}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    assert verify(tmp_path) == []
    (tmp_path / 'raw/ok.body').write_bytes(b'bad')
    assert verify(tmp_path) == ['HASH_MISMATCH:ok']


def test_path_traversal_detected(tmp_path):
    p = tmp_path / 'manifest.json'
    p.write_text(json.dumps({'records': [{'evidence_path': '../outside.body', 'sha256': 'a'*64, 'label': 'bad'}]}))
    assert verify(tmp_path) == ['MISSING_OR_ESCAPED_FILE:bad']
