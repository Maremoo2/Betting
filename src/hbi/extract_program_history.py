"""DATA-005X, conservative bounded extraction of per-horse DNT program form rows.

No use as official individual identity or model/PIT admission. The program's short
DD/MM dates omit year; inferred ISO date is labelled an inference and must be
crosschecked against authoritative dated race results.
"""
from __future__ import annotations

import csv
import hashlib
import re
from datetime import date
from pathlib import Path

import fitz

DATE_TOKEN = re.compile(r"^(?P<day>\d{1,2})/(?P<month>\d{1,2})-(?P<racepart>[0-9A-Za-z]+)/[0-9A-Za-z]+$")
# PDF layout verified by visual comparison on 29 Oct 2026 for these two pages.
COLUMNS = {
    'driver': (225, 289),
    'track_code': (289, 308),
    'date_program_code': (308, 355),
    'distance_m': (355, 376),
    'finish_raw': (376, 384),
    'km_time_raw': (384, 418),
    'program_pr_column_raw': (418, 433),
    'program_odds_column_raw': (433, 447),
}


def name_anchor(page: fitz.Page, horse: str) -> fitz.Rect:
    matches = [r for r in page.search_for(horse.upper()) if 69 < r.x0 < 75 and r.height < 13]
    if len(matches) != 1:
        raise ValueError(f'NAME_ANCHOR_AMBIGUOUS:{horse}:{len(matches)}')
    return matches[0]


def infer_dates_backward(raw_dates: list[str], program_date: date) -> list[dict]:
    """Calendar-only backward inference, not proof of the actual historical race date."""
    parsed = []
    for token in raw_dates:
        m = DATE_TOKEN.fullmatch(token)
        if not m:
            raise ValueError(f'INVALID_DATE_TOKEN:{token}')
        d, mo = int(m['day']), int(m['month'])
        if not 1 <= mo <= 12 or not 1 <= d <= 31:
            raise ValueError('INVALID_DAY_MONTH')
        parsed.append((d, mo))
    last = program_date
    tentative = [None] * len(parsed)
    for i in range(len(parsed) - 1, -1, -1):
        day, mo = parsed[i]
        year = last.year
        while True:
            try:
                curr = date(year, mo, day)
            except ValueError as exc:
                raise ValueError(f'INVALID_DATE:{day}/{mo}') from exc
            if curr <= last:
                break
            year -= 1
            if year < program_date.year - 6:
                raise ValueError('TOO_OLD_OR_UNSORTED_HISTORY')
        tentative[i] = {'year_inferred_iso': curr.isoformat(), 'year_inferred_not_attested': True}
        last = curr
    return tentative


def extract(page: fitz.Page, horse_names: list[str], race_id: str, program_date: date, pdf_sha256: str) -> list[dict]:
    anchors = sorted(((name_anchor(page, horse), horse) for horse in horse_names), key=lambda pair: pair[0].y0)
    if [name for _, name in anchors] != horse_names:
        raise ValueError('HORSE_NAME_ORDER_NOT_EQUAL_CANONICAL_FIELD')
    if len(anchors) != len(horse_names) or len({a.y0 for a, _ in anchors}) != len(anchors):
        raise ValueError('HORSE_FIELD_INCOMPLETE_OR_DUPLICATE_ANCHORS')
    words = page.get_text('words')
    result = []
    for k, (anchor, horse) in enumerate(anchors):
        boundary = anchors[k + 1][0].y0 - 8 if k + 1 < len(anchors) else page.rect.height - 18
        # History rows are the small text to the RIGHT, strictly below the horse's heading.
        relevant = [w for w in words if anchor.y0 + 7 <= w[1] < boundary and 225 <= w[0] < 448]
        date_words = [w for w in relevant if 308 <= w[0] < 355 and DATE_TOKEN.fullmatch(w[4])]
        date_words.sort(key=lambda w: w[1])
        if len(date_words) != 5:
            raise ValueError(f'REQUIRE_FIVE_VISIBLE_FORM_ROWS:{horse}:{len(date_words)}')
        dates = infer_dates_backward([w[4] for w in date_words], program_date)
        for i, date_word in enumerate(date_words):
            matched = [w for w in relevant if abs(w[1] - date_word[1]) < 1.35]
            columns: dict[str, str] = {}
            for column, (low, high) in COLUMNS.items():
                parts = sorted((w for w in matched if low <= w[0] < high), key=lambda w: w[0])
                columns[column] = ' '.join(w[4] for w in parts)
            if columns['date_program_code'] != date_word[4]:
                raise ValueError(f'HISTORY_COLUMN_MISALIGNMENT:{horse}:{i}')
            if not re.fullmatch(r'\d{3,4}', columns['distance_m']):
                raise ValueError(f'INVALID_DISTANCE:{horse}:{i}:{columns["distance_m"]}')
            result.append({
                'race_id': race_id, 'race_number': 2,
                'current_start_number': k + 1, 'horse_name': horse,
                'form_row_order_oldest_to_newest': i + 1,
                'pdf_program_date': program_date.isoformat(),
                'source_pdf_sha256': pdf_sha256, 'source_page': 2,
                **columns, **dates[i],
                'exact_horse_identity_attested': False,
                'historic_result_independently_verified': False,
                'history_candidate_not_model_eligible': True,
            })
    return result


def run(pdf_by_race: dict[str, Path], names_by_race: dict[str, list[str]], out_csv: Path) -> dict:
    rows = []
    for race_id, pdf in pdf_by_race.items():
        doc = fitz.open(pdf)
        raw_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        program_date = date.fromisoformat(race_id.split('_')[2].split(':')[0])
        rows += extract(doc[1], names_by_race[race_id], race_id, program_date, raw_sha)
    with out_csv.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {'rows': len(rows), 'races': len(pdf_by_race), 'horses': len(rows) // 5, 'identity_attested': 0, 'history_independently_verified': 0}


PILOT_FIELDS: dict[str, tuple[str, str, list[str]]] = {
    'momarken_20261101': (
        'RIKSTOTO:MO_NR_2026-11-01:2', '2026-11-01', [
            'SOLØR HANNA', 'STJERNE LIAM', 'BJØNNUM RAPPEN', 'ROS LYNET',
            'STJERNE ORLA', 'MJØLNER JÆRV', 'BYRTING', 'PROPELL', 'TORILAS',
            'HAUGESTAD LALLA', 'BENONI', 'BJØRLI LIZZIE',
        ]
    ),
    'bjerke_20261031': (
        'RIKSTOTO:BJ_NR_2026-10-31:2', '2026-10-31', [
            'HVALSTAD IL', 'KALIDA', 'FINSETH VIND', 'SØYSET NORAH', 'PREKTIG',
            'NELSON HEIDI', 'KOS FRIGGA', 'JERKELD ODINA', 'RY TORA',
            'BJØRLIMINDI (S)', 'ØYGARD STJERNA', 'MYR TØTTA',
        ]
    ),
}


def verify_and_export_probe(root: Path) -> dict:
    """Export a candidate, not verified identity/history, from exact captured PDF bytes.

    Fails closed on missing hash, wrong program count, duplicate/unsorted horse,
    and source capture not before its own published program start.
    """
    import json
    from datetime import UTC, datetime

    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    records = {r['label']: r for r in manifest['records']}
    issues = []
    rows: list[dict] = []
    for label, (race_id, start_date, names) in PILOT_FIELDS.items():
        record = records.get(f'{label}_program_0')
        if not record or record.get('status') != 200 or not record.get('evidence_path'):
            issues.append(f'MISSING_OR_UNVERIFIED_PROGRAM:{label}')
            continue
        path = (root / record['evidence_path']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            issues.append(f'INVALID_OR_MISSING_FILE:{label}')
            continue
        body = path.read_bytes()
        if not body.startswith(b'%PDF-') or hashlib.sha256(body).hexdigest() != record['sha256']:
            issues.append(f'RAW_PDF_SHA256_MISMATCH:{label}')
            continue
        capture = datetime.fromisoformat(record['completed_at_utc']).astimezone(UTC)
        # Source dates are published approximate program times, not certified off-times.
        scheduled = datetime.fromisoformat(
            '2026-11-01T18:15:00+00:00' if label.startswith('momarken')
            else '2026-10-31T12:52:00+00:00'
        )
        if capture >= scheduled:
            issues.append(f'NOT_CAPTURED_BEFORE_PUBLISHED_SCHEDULE:{label}')
            continue
        try:
            doc = fitz.open(stream=body, filetype='pdf')
            if len(doc) < 2:
                raise ValueError('EXPECTED_SECOND_PAGE')
            extracted = extract(doc[1], names, race_id, date.fromisoformat(start_date), record['sha256'])
            for r in extracted:
                r['source_capture_completed_at_utc'] = record['completed_at_utc']
                r['source_observation_level'] = 'DNT_PROGRAM_RAW_PDF_SHA256_VERIFIED_PRESTART'
            rows.extend(extracted)
        except (ValueError, RuntimeError) as exc:
            issues.append(f'PDF_STRUCTURE_MISMATCH:{label}:{exc}')
    if rows:
        with (root / 'candidate_form_rows.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    report = {
        'schema': 'DATA005X_FIVE_FORM_ROWS_V1',
        'row_count': len(rows), 'horses_with_five_rows': len(rows) // 5,
        'expected_rows': 120, 'issues': issues,
        'all_source_pdf_rows_found': len(rows) == 120 and not issues,
        'year_fields_inferred_not_officially_attested': len(rows),
        'independent_individual_ueln_verified': 0,
        'model_eligible': False, 'bet_authorized': False,
        'source_publication_time_attested': False,
        'full_history_certified': False,
        'note': 'Five program form rows are independently sourced; they are not a validated permanent identity link nor an authenticated full individual history.',
    }
    (root / 'form_rows_audit.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding='utf-8'
    )
    return report


def audit_exit_code(report: dict) -> int:
    """An extraction failure must fail CI, not produce a green empty artifact."""
    valid = (
        report.get('all_source_pdf_rows_found') is True
        and report.get('row_count') == 120
        and report.get('horses_with_five_rows') == 24
        and not report.get('issues')
    )
    return 0 if valid else 1


if __name__ == '__main__':
    import json
    import os
    import sys

    report = verify_and_export_probe(Path(os.getenv('HBI_PROGRAM_PROBE_DIR', 'history-program-probe')))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(audit_exit_code(report))
