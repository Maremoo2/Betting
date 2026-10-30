"""DATA-005Y stage 3: no valid-looking CSV on incomplete/ambiguous capture."""

from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path

import pytest

from hbi.extract_program_history import audit_exit_code, verify_and_export_probe


@pytest.fixture
def copied_real_source(tmp_path: Path) -> Path:
    raw = os.environ.get('HBI_DNT_PROBE_DIR')
    if not raw:
        pytest.skip('Source archive not supplied; do not simulate original-PDF acceptance')
    root = tmp_path / 'copied-sources'
    shutil.copytree(Path(raw), root)
    return root


def test_corrupt_pdf_does_not_leave_partial_csv(copied_real_source: Path) -> None:
    root = copied_real_source
    good = verify_and_export_probe(root)
    assert good['row_count'] == 120 and audit_exit_code(good) == 0
    candidate = root / 'candidate_form_rows.csv'
    assert candidate.exists()
    pdf = root / 'raw/bjerke_20261031_program_0.body'
    pdf.write_bytes(pdf.read_bytes() + b'FAKE_CORRUPTION')
    failed = verify_and_export_probe(root)
    assert failed['row_count'] == 60 and audit_exit_code(failed) == 1
    assert not candidate.exists(), 'unsafe 60-row CSV escaped from failed extraction'


def test_timezone_naive_capture_is_rejected(copied_real_source: Path) -> None:
    root = copied_real_source
    manifest_path = root / 'manifest.json'
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    for record in data['records']:
        if record['label'] == 'bjerke_20261031_program_0':
            record['completed_at_utc'] = '2026-10-29T13:43:10'
    manifest_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    report = verify_and_export_probe(root)
    assert audit_exit_code(report) == 1
    assert any('CAPTURE_TIMEZONE_MISSING' in reason for reason in report['issues'])
    assert not (root / 'candidate_form_rows.csv').exists()


def test_duplicate_manifest_labels_are_rejected(copied_real_source: Path) -> None:
    root = copied_real_source
    manifest_path = root / 'manifest.json'
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    data['records'].append(dict(data['records'][0]))
    manifest_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    report = verify_and_export_probe(root)
    assert audit_exit_code(report) == 1
    assert 'DUPLICATE_RECORD_LABEL' in report['issues']
    assert not (root / 'candidate_form_rows.csv').exists()


def test_csv_write_interruption_leaves_no_partial_candidate(
    copied_real_source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copied_real_source

    def interrupt_export(*args: object, **kwargs: object) -> None:
        raise OSError('synthetic disk write interruption')

    monkeypatch.setattr(csv.DictWriter, 'writerows', interrupt_export)
    with pytest.raises(OSError, match='synthetic disk write interruption'):
        verify_and_export_probe(root)
    assert not (root / 'candidate_form_rows.csv').exists()
    assert not (root / '.candidate_form_rows.csv.tmp').exists()
