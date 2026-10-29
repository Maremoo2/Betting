"""DATA-005X, bounded official DNT race-program discovery and historical evidence.

Research-only, no model/betting authority. A PDF is not official until its source
host, content bytes and SHA-256 are verified. All retrieval timestamps are collector
observations, NOT attested PDF publication time or PIT-valid model cutoffs.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 6_000_000
OFFICIAL_HOST = 'old.travsport.no'
TARGETS = {
    'bjerke_20261031': ('BJ_20261031', 'https://old.travsport.no/Sport/Startlister/Bjerke-Travbane/?date=20261031'),
    'momarken_20261101': ('MO_20261101', 'https://old.travsport.no/Travbane-mal5/Sport/Innmelding-Startlister-Travbanen/?date=20261101'),
    'positive_control_bjerke_20260127': ('BJ_20260127', None),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError('REDIRECT_BLOCKED')


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.extend(v for k, v in attrs if k == 'href' and isinstance(v, str))


def allowed(url: str, *, pdf: bool) -> bool:
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.hostname != OFFICIAL_HOST or p.port not in (None, 443):
            return False
        if p.username or p.password or p.fragment:
            return False
        if pdf:
            return not p.query and bool(re.fullmatch(r'/pdf/(BJ_20261031|MO_20261101|BJ_20260127)_Baneprogram\.pdf', p.path))
        return bool(re.fullmatch(r'/(Sport/Startlister/Bjerke-Travbane/|Travbane-mal5/Sport/Innmelding-Startlister-Travbanen/)', p.path)) and p.query in ('date=20261031', 'date=20261101')
    except ValueError:
        return False


@dataclass(frozen=True)
class Probe:
    label: str
    url: str
    started_at_utc: str
    completed_at_utc: str
    status: int | None
    sha256: str | None
    bytes_count: int
    kind: str
    evidence_path: str | None
    error: str | None
    content_type: str | None
    provenance: str = 'HTTP_CAPTURE_CLOCK_ONLY_NOT_SOURCE_PUBLICATION_TIME'


def fetch(label: str, url: str, out: Path, *, pdf: bool, opener=None) -> tuple[Probe, bytes | None]:
    if not allowed(url, pdf=pdf):
        raise ValueError('URL_NOT_ALLOWLISTED')
    if not re.fullmatch('[a-z0-9_]{4,60}', label):
        raise ValueError('INVALID_LABEL')
    opener = opener or urllib.request.build_opener(NoRedirect())
    started = datetime.now(UTC).isoformat()
    body = None
    status = None
    content_type = None
    err = None
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/pdf' if pdf else 'text/html', 'User-Agent': 'HBI-PIT-Research/0.1'}, method='GET')
        with opener.open(req, timeout=12) as resp:
            status = resp.status
            content_type = str(resp.headers.get('Content-Type') or '')[:160]
            raw = resp.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                err = 'MAX_SIZE_EXCEEDED'
            elif pdf and not raw.startswith(b'%PDF-'):
                err = 'NOT_PDF_SIGNATURE'
            elif not pdf and b'<' not in raw:
                err = 'NOT_HTML_SIGNATURE'
            else:
                body = raw
    except urllib.error.HTTPError as exc:
        status = exc.code
        err = f'HTTP_{status}'
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        err = type(exc).__name__
    completed = datetime.now(UTC).isoformat()
    digest = hashlib.sha256(body).hexdigest() if body is not None else None
    p = f'raw/{label}.body' if digest else None
    if body is not None:
        dest = out / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
    return Probe(label, url, started, completed, status, digest, len(body or b''), 'OFFICIAL_DNT_PDF' if pdf else 'OFFICIAL_DNT_STARTLIST_HTML', p, err, content_type), body


def discover_pdf_urls(html: bytes, base_url: str, *, exact_prefix: str) -> list[str]:
    parser = Anchors()
    parser.feed(html.decode('utf-8', errors='replace'))
    candidates = {urljoin(base_url, href) for href in parser.hrefs}
    match = f'/pdf/{exact_prefix}_Baneprogram.pdf'
    return sorted(u for u in candidates if allowed(u, pdf=True) and urlsplit(u).path == match)


def summarize_pdf_text(body: bytes, horse_names: list[str]) -> dict:
    """PDF text-only diagnostics. Does NOT parse or certify individual form rows."""
    try:
        import fitz
        doc = fitz.open(stream=body, filetype='pdf')
        chunks = [page.get_text('text') for page in doc]
        pages = len(doc)
    except (ImportError, RuntimeError, ValueError):
        return {'pdf_readable': False, 'name_candidates': {}, 'complete_history_certified': False}
    normalized = [' '.join(p.casefold().split()) for p in chunks]
    occurrences = {name: [i + 1 for i, text in enumerate(normalized) if ' '.join(name.casefold().split()) in text] for name in horse_names}
    return {'pdf_readable': True, 'pages': pages, 'name_candidates': occurrences, 'formrader_title_visible': any('5 siste starter' in t for t in normalized), 'complete_history_certified': False}


def capture(out: Path, horse_names_by_track: dict[str, list[str]] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    records = []
    pdf_findings = {}
    for label, (prefix, listing) in TARGETS.items():
        candidates = {f'https://{OFFICIAL_HOST}/pdf/{prefix}_Baneprogram.pdf'}
        if listing is not None:
            ev, html = fetch(f'{label}_startlist', listing, out, pdf=False)
            records.append(asdict(ev))
            if html:
                candidates.update(discover_pdf_urls(html, listing, exact_prefix=prefix))
        for index, url in enumerate(sorted(candidates)):
            ev, body = fetch(f'{label}_program_{index}', url, out, pdf=True)
            records.append(asdict(ev))
            if body:
                prefix_name = label.split('_')[0]
                pdf_findings[label] = summarize_pdf_text(body, (horse_names_by_track or {}).get(prefix_name, []))
        pdf_findings.setdefault(label, {'pdf_readable': False, 'status': 'PDF_MISSING_OR_INACCESSIBLE', 'complete_history_certified': False})
    manifest = {'schema': 'DATA005X_OFFICIAL_DNT_PROGRAM_PROBE_V1', 'captured_at_utc': datetime.now(UTC).isoformat(), 'records': records, 'pdf_findings': pdf_findings, 'research_only': True, 'pit_model_eligible': False, 'stable_horse_ids_verified': False, 'full_history_certified': False, 'bet_authorized': False}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    return manifest


def verify(out: Path) -> list[str]:
    data = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    errors = []
    for r in data['records']:
        if r['evidence_path']:
            p = (out / r['evidence_path']).resolve()
            if not p.is_relative_to(out.resolve()) or not p.is_file():
                errors.append('MISSING_OR_ESCAPED_FILE:' + r['label'])
            elif hashlib.sha256(p.read_bytes()).hexdigest() != r['sha256']:
                errors.append('HASH_MISMATCH:' + r['label'])
    return errors


if __name__ == '__main__':
    import os
    import sys
    out = Path(os.getenv('HBI_PROGRAM_PROBE_DIR', 'history-program-probe'))
    result = capture(out)
    errs = verify(out)
    print(json.dumps({'records': len(result['records']), 'statuses': [(r['label'], r['status'], r['error']) for r in result['records']], 'pdf_findings': result['pdf_findings'], 'errors': errs}, indent=2))
    sys.exit(int(bool(errs)))
