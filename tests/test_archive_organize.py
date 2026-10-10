import json
from zipfile import ZipFile

import pytest

from rikstoto_crawler.organize import organize
from rikstoto_crawler.transport import digest, write_json


def test_year_packages_only_include_committed_days_and_keep_stages_separate(tmp_path):
    source, output = tmp_path / 'source', tmp_path / 'years'
    races = [{'race_id': 'fixture', 'pWIN': {'1': 1.0}}]
    pre = {'stage': 'MARKET_ONLY', 'races': races, 'sha256': digest(races)}
    write_json(source / 'inventory/2015-06.json', {'body': {'result': [
        {'raceDayKey': 'BJ_NR_2015-06-01'}, {'raceDayKey': 'BJ_NR_2015-06-02'}]}})
    write_json(source / 'market-days/2015-06-01.json', pre)
    write_json(source / 'market-days/2015-06-02.json', pre)
    post = {'stage': 'RESULTS', 'pre_sha256': pre['sha256'], 'outcomes': [{'winner': 1}],
            'summary': {'counts': {'WIN_ONLY': 1}}}
    write_json(source / 'result-days/2015-06-01.json', post)
    original = (source / 'market-days/2015-06-01.json').read_bytes()
    result = organize(source, output)
    assert result['years'][0]['days_completed'] == 1
    assert result['years'][0]['missing_discovered_dates'] == ['2015-06-02']
    assert not (output / '2015/PRE/2015-06-02.json').exists()
    with ZipFile(output / '2015/weekly/2015-W23-PRE.zip') as archive:
        assert 'outcomes' not in json.loads(archive.read('2015-06-01.json'))
        assert archive.testzip() is None
    organize(source, output)
    assert (source / 'market-days/2015-06-01.json').read_bytes() == original
    write_json(source / 'result-days/2015-06-02.json', post)
    result = organize(source, output)
    assert result['years'][0]['status'] == 'DISCOVERED_DAYS_COLLECTED_QC_REQUIRED'
    assert result['years'][0]['training_ready'] is False
    with ZipFile(output / '2015/weekly/2015-W23-PRE.zip') as archive:
        assert len(json.loads(archive.read('MANIFEST.json'))['days']) == 2
    (output / '2015/PRE/2015-06-01.json').write_text('{}')
    with pytest.raises(ValueError, match='differs'):
        organize(source, output)


def test_organizer_rejects_overlapping_output(tmp_path):
    with pytest.raises(ValueError, match='separate'):
        organize(tmp_path, tmp_path / 'years')
