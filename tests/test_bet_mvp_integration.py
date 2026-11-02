"""BET-MVP-001 additive status/provenance checks using real, immutable race data."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from hbi.bet_mvp_shadow import analyze, sha256

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path(os.environ.get('BET_MVP_REAL_DB', ''))
PILOT = Path(os.environ.get('BET_MVP_PILOT_DB', ''))
SOURCE = Path(os.environ.get('BET_MVP_CORE003_REPORT', ''))
FROZEN = Path(os.environ['BET_MVP_FROZEN_REPORTS']) if os.getenv('BET_MVP_FROZEN_REPORTS') else None


def connection(path):
    db = sqlite3.connect(f'file:{path.resolve()}?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    return db


@pytest.mark.skipif(not ORIGINAL.is_file(), reason='Original HBI SQLite unavailable')
def test_real_fullfield_statuses_coexist_with_pit_not_certified():
    with connection(ORIGINAL) as db:
        result = analyze(db, race_id='RIKSTOTO:S1_NR_2026-10-17:6',
                         as_of='2026-10-17T13:18:00+00:00', archive_sha=sha256(ORIGINAL))
    assert result['analysis_status'] == 'RESEARCH_READY'
    assert result['status_dimensions'] == {
        'model':'MODEL_READY','market':'MARKET_READY','pit':'PIT_NOT_CERTIFIED',
        'bet':'NOT_ELIGIBLE_FOR_REAL_BETTING',
    }
    assert len(result['runners']) == 15
    assert result['model_blockers'] == []
    assert result['market_blockers'] == []
    assert all(row['model_status'] == 'MODEL_READY' and row['pit_status'] == 'PIT_NOT_CERTIFIED'
               for row in result['runners'])
    assert all(row['bet_authority'] is False for row in result['runners'])


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(), reason='Real CORE003 data unavailable')
def test_real_core003_model_ready_market_blocked_is_not_model_failure():
    evidence = json.loads(SOURCE.read_text())
    with connection(PILOT) as db:
        result = analyze(db, race_id='RIKSTOTO:S1_NR_2026-11-02:1',
                         as_of='2026-11-02T10:21:36+00:00', archive_sha=sha256(PILOT),
                         source_report=evidence, source_report_sha256=sha256(SOURCE))
    assert result['status_dimensions'] == {
        'model':'MODEL_READY','market':'MARKET_BLOCKED','pit':'PIT_NOT_CERTIFIED',
        'bet':'NOT_ELIGIBLE_FOR_REAL_BETTING',
    }
    assert result['analysis_status'] == 'SOURCE_BLOCKED'
    assert result['model_blockers'] == []
    assert 'NO_WIN_MARKET_AS_OF' in result['market_blockers']
    assert result['champion_p_sum'] == pytest.approx(1)
    assert result['core004_p_sum'] == pytest.approx(1)
    assert len(result['runners']) == 10
    assert all(row['research_status'] == 'BLOCKED' and row['model_status'] == 'MODEL_READY'
               and row['market_status'] == 'MARKET_BLOCKED' and row['win_odds'] is None
               for row in result['runners'])
    assert result['collector_source_evidence']['sha256'] == sha256(SOURCE)
    assert result['collector_source_evidence']['finished_at_utc'] == '2026-11-02T10:08:39.302286+00:00'
    assert result['collector_source_evidence']['independent_pit_certified'] is False
    assert (datetime.fromisoformat(result['analysis_started_at_utc'])
            <= datetime.fromisoformat(result['model_calculated_at_utc'])
            <= datetime.fromisoformat(result['report_created_at_utc']))


@pytest.mark.skipif(not ORIGINAL.is_file(), reason='Original HBI SQLite unavailable')
def test_real_skive_partial_model_not_called_fully_ready():
    with connection(ORIGINAL) as db:
        r = analyze(db, race_id='RIKSTOTO:S2_NR_2026-10-30:7',
                    as_of='2026-10-30T16:45:00+00:00', archive_sha=None)
    assert r['model_status'] == 'MODEL_PARTIAL'
    assert r['champion_p_sum'] == pytest.approx(1)
    assert r['core004_p_sum'] is None
    assert 'ASOF_AFTER_EARLIEST_SOURCE_T4' in r['model_blockers']
    assert r['bet_authority'] is False


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(), reason='Original source unavailable')
@pytest.mark.parametrize(('field', 'value', 'blocker'), [
    ('races_in_fixed_cohort', ['WRONG_RACE'], 'CORE003_REPORT_RACE_NOT_IN_FIXED_COHORT'),
    ('finished_at_utc', '2026-11-02T10:21:37+00:00', 'CORE003_CAPTURE_FINISHED_AFTER_ANALYSIS_AS_OF'),
    ('started_at_utc', 'not-an-instant', 'CORE003_CAPTURE_CLOCK_INVALID'),
])
def test_untrusted_core003_report_never_promotes_model(field, value, blocker):
    source = json.loads(SOURCE.read_text())
    source[field] = value
    with connection(PILOT) as db:
        r = analyze(db, race_id='RIKSTOTO:S1_NR_2026-11-02:1',
                    as_of='2026-11-02T10:21:36+00:00', archive_sha=None,
                    source_report=source, source_report_sha256='0'*64)
    assert blocker in r['source_blocks']
    assert r['model_status'] == 'MODEL_BLOCKED'
    assert r['bet_authority'] is False


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(), reason='Real source unavailable')
def test_real_source_cli_writes_frozen_statuses_and_rejects_second_write(tmp_path):
    target = tmp_path / 'new-frozen-report'
    command = [sys.executable, '-m', 'hbi.bet_mvp_shadow',
               '--db', str(PILOT), '--source-report', str(SOURCE),
               '--race-id', 'RIKSTOTO:S1_NR_2026-11-02:1',
               '--as-of', '2026-11-02T10:21:36+00:00', '--out', str(target),
               '--run-kind', 'ARCHIVED_REPLAY']
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
    run = subprocess.run(command, check=False, cwd=ROOT, env=env, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    report = json.loads((target / 'shadow.json').read_text())
    assert report['status_dimensions']['model'] == 'MODEL_READY'
    assert report['status_dimensions']['market'] == 'MARKET_BLOCKED'
    assert 'MODEL_READY' in (target / 'shadow.md').read_text()
    assert 'MARKET_BLOCKED' in (target / 'shadow.md').read_text()
    assert sha256(target / 'shadow.json') == json.loads(run.stdout)['output_sha256']['shadow.json']
    again = subprocess.run(command, check=False, cwd=ROOT, env=env, text=True, capture_output=True)
    assert again.returncode != 0
    assert 'FROZEN_SHADOW_OUTPUT_DIRECTORY_EXISTS_NO_OVERWRITE' in again.stderr


@pytest.mark.skipif(not PILOT.is_file() or not ORIGINAL.is_file() or FROZEN is None,
                    reason='Original frozen reports / SQLite unavailable')
@pytest.mark.parametrize(('source', 'race', 'as_of', 'dirname'), [
    (ORIGINAL, 'RIKSTOTO:S1_NR_2026-10-17:6', '2026-10-17T13:18:00+00:00', 'archived_gavle_final'),
    (ORIGINAL, 'RIKSTOTO:S1_NR_2026-10-20:4', '2026-10-20T11:22:00+00:00', 'archived_scratched_final'),
    (ORIGINAL, 'RIKSTOTO:S2_NR_2026-10-30:7', '2026-10-30T16:45:00+00:00', 'archived_skive_final'),
    (PILOT, 'RIKSTOTO:S1_NR_2026-11-02:1', '2026-11-02T10:21:36+00:00', 'prospective_final_attested'),
])
def test_four_original_frozen_races_have_same_probabilities_and_market(source, race, as_of, dirname):
    old = json.loads((FROZEN / dirname / 'shadow.json').read_text())
    original_sha = hashlib.sha256((FROZEN / dirname / 'shadow.json').read_bytes()).hexdigest()
    with connection(source) as db:
        new = analyze(db, race_id=race, as_of=as_of, archive_sha=sha256(source))
    assert new['field_size'] == old['field_size']
    assert new['active_runners'] == old['active_runners']
    a = {r['selection_id']:r for r in new['runners']}
    for previous in old['runners']:
        updated = a[previous['selection_id']]
        for key in ('scratched','champion_p_win','core004_p_win',
                    'normalized_market_p','win_odds','champion_theoretical_ev_uncalibrated',
                    'core004_minus_champion_pp','historical_starts','historical_wins'):
            assert updated[key] == previous[key], (race, previous['selection_id'], key)
    assert old['champion_p_sum'] == new['champion_p_sum']
    assert old['core004_p_sum'] == new['core004_p_sum']
    assert original_sha == hashlib.sha256((FROZEN / dirname / 'shadow.json').read_bytes()).hexdigest()


@pytest.mark.skipif(FROZEN is None, reason='Original frozen reports unavailable')
def test_two_original_aerjang_freeze_times_and_original_report_bytes_are_preserved():
    snapshots = [("prospective_genuine_frozen", '2026-11-02T10:13:28.941818+00:00', '2026-11-02T10:08:40+00:00'),
                 ("prospective_final_attested", '2026-11-02T10:21:37.216488+00:00', '2026-11-02T10:21:36+00:00')]
    original_sha = []
    for dirname, created, cutoff in snapshots:
        p = FROZEN / dirname / 'shadow.json'
        old = json.loads(p.read_text())
        assert old['report_created_at_utc'] == created
        assert old['as_of_utc'] == cutoff
        assert old['source_database_sha256'] == '9c9a7021d15648db355fb320c51def268e5ffd34dc78ebef1cd95a6f5b7794ef'
        assert old['source_audit']['fundamental_observed_at_utc'] == '2026-11-02T10:08:39.259317+00:00'
        assert old['model_versions']['champion'] == 'FUNDAMENTAL_CHAMPION_V1_1'
        assert old['model_versions']['core004'] == 'CORE_004_EXPLORATORY_MULTIFACTOR_V0_NOT_FITTED'
        assert old.get('model_calculated_at_utc') is None  # never retroactively invent a clock
        original_sha.append(hashlib.sha256(p.read_bytes()).hexdigest())
    assert original_sha == [
        '97a79b8d8344d56340b886811187cd92dd63e718f209e9acf5f11f7f90cf9428',
        'c685b107639d4cdb2a6d4371e5514c8a92f30b51c19998d856c0e6793dbf74f6',
    ]


def _position_fixture(*, race_id="RIKSTOTO:S1_NR_2026-11-02:1",
                      as_of="2026-11-02T10:21:36+00:00",
                      source_at="2026-11-02T10:08:37+00:00",
                      distances=(0, 0, 0, 0, 0, 20, 20, 20, 20, 40),
                      names=None, scratched_ids=()):
    """Synthetic source-shaped fixture with identities from original programs."""
    from hbi.bet_mvp_shadow import aware, verified_program_positions
    if names is None:
        names = ["Arevs Madicken", "Solurstjärn", "Mörten", "Hornnes Odd",
                 "Lykkje Trolla", "Balder Töffen S.K.", "Komnes Hera",
                 "Troll Winther", "Vik Tor", "Remjahn"]
    meeting, race_text = race_id.removeprefix("RIKSTOTO:").rsplit(":", 1)
    race_number = int(race_text)
    roster = [
        {"selection_id": str(i), "horse_name": name, "post_position": i, "scratched": int(i in scratched_ids)}
        for i, name in enumerate(names, 1)
    ]
    starts = [
        {"raceNumber": race_number, "startNumber": i, "horseName": name,
         "isScratched": i in scratched_ids, "extraDistance": distance}
        for i, (name, distance) in enumerate(zip(names, distances), 1)
    ]
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE provider_payloads(
        provider TEXT, category TEXT, provider_raceday_key TEXT,
        observed_at_utc TEXT, payload_json TEXT, source_uri TEXT)""")
    db.execute("INSERT INTO provider_payloads VALUES(?,?,?,?,?,?)", (
        "rikstoto", "RACEDAY_STARTS", meeting, source_at,
        json.dumps({"success": True, "result": {str(race_number): starts}}),
        "https://www.rikstoto.no/api/racedays/" + meeting + "/starts",
    ))
    return db, roster, verified_program_positions, aware(as_of)


@pytest.mark.parametrize(("selection","additional"), [
    ("1", 0), ("5", 0), ("6", 20), ("9", 20), ("10", 40),
])
def test_arjang_three_volts_keep_program_number_independent_of_hbi_post_position(selection, additional):
    db, roster, verify, clock = _position_fixture()
    try:
        result = verify(db, race_id="RIKSTOTO:S1_NR_2026-11-02:1",
                        as_of=clock, roster=roster)
    finally:
        db.close()
    assert len(result) == 10
    assert result[selection]["start_number"] == int(selection)
    assert result[selection]["extra_distance_m"] == additional
    assert result[selection]["start_number_observed_at_utc"] == "2026-11-02T10:08:37+00:00"


def test_autostart_program_number_not_inferred_from_post_position():
    # The real Årjäng R2 program is autostart with 12 entrants, #3 scratched.
    # The reconstructed /starts *fixture* is not a fresh original API capture.
    names = ["Whirlwindz", "Zolatin", "Explositj", "Kick the Man",
             "Bara Joe", "One Big Bang", "Chiani Broline", "Surr",
             "Jessie", "Fanny S.I.R.", "Eightpack", "Timber Tile"]
    db, roster, verify, clock = _position_fixture(
        race_id="RIKSTOTO:S1_NR_2026-11-02:2", distances=(0,) * 12,
        names=names, scratched_ids=(3,))
    roster[0]["post_position"] = 7  # an HBI field is NOT a source program number
    try:
        result = verify(db, race_id="RIKSTOTO:S1_NR_2026-11-02:2",
                        as_of=clock, roster=roster)
    finally:
        db.close()
    assert len(result) == 12
    assert result["1"]["start_number"] == 1
    assert result["12"]["start_number"] == 12
    assert all(row["extra_distance_m"] == 0 for row in result.values())
    assert roster[2]["scratched"] == 1
    assert roster[0]["post_position"] == 7


def test_unattested_future_startlist_never_produces_program_numbers():
    db, roster, verify, clock = _position_fixture(
        source_at="2026-11-02T10:21:37+00:00")
    try:
        assert verify(db, race_id="RIKSTOTO:S1_NR_2026-11-02:1",
                      as_of=clock, roster=roster) == {}
    finally:
        db.close()


def test_mismatched_runner_identity_blocks_entire_startlist():
    db, roster, verify, clock = _position_fixture()
    roster[8]["horse_name"] = "Wrong Horse"
    try:
        assert verify(db, race_id="RIKSTOTO:S1_NR_2026-11-02:1",
                      as_of=clock, roster=roster) == {}
    finally:
        db.close()


@pytest.mark.skipif(not PILOT.is_file() or not SOURCE.is_file(),
                    reason="Original CORE-003 sources not available in CI")
def test_real_arjang_start_positions_are_verified_without_volte_inference():
    from hbi.bet_mvp_shadow import aware, markdown_report, verified_program_positions
    with connection(PILOT) as conn:
        result = analyze(conn, race_id="RIKSTOTO:S1_NR_2026-11-02:1",
                         as_of="2026-11-02T10:21:36+00:00", archive_sha=None)
        positions = verified_program_positions(
            conn, race_id="RIKSTOTO:S1_NR_2026-11-02:1",
            as_of=aware("2026-11-02T10:21:36+00:00"),
            roster=[dict(x) for x in conn.execute(
                "SELECT * FROM runners WHERE race_id=?",
                ("RIKSTOTO:S1_NR_2026-11-02:1",))],
        )
    assert len(positions) == 10
    assert [(str(r["start_number"]), r["extra_distance_m"])
            for r in result["runners"]] == [
        (str(i), 0 if i <= 5 else 20 if i <= 9 else 40)
        for i in range(1, 11)]
    assert all(r["volte_position"] is None for r in result["runners"])
    assert all(r["start_number_observed_at_utc"] for r in result["runners"])
    assert all(r["pit_status"] == "PIT_NOT_CERTIFIED" and not r["bet_authority"]
               for r in result["runners"])
    assert "## Startnumre og volteløp" in markdown_report(result)


def test_original_arjang_fundamental_excerpt_replays_actual_model_modules():
    """Use the ten archived ATG numeric rows from ORIGINAL pilot SHA

    9c9a7021d15648db355fb320c51def268e5ffd34dc78ebef1cd95a6f5b7794ef.
    This excerpt tests the untouched original Python model entrypoints in CI.
    It is NOT a replacement for the original receipts or a PIT attestation.
    """
    from hbi.core_multifactor_research import analyze_multifactor
    from hbi.race_core_review import analyze_race

    field = [
        ("Arevs Madicken", 65, 2, 4, 4, 23889600, 0),
        ("Solurstjärn", 62, 1, 3, 4, 25502400, 0),
        ("Mörten", 59, 1, 2, 1, 18465000, 0),
        ("Hornnes Odd", 32, 6, 6, 1, 25546300, 0),
        ("Lykkje Trolla", 22, 3, 4, 2, 23125200, 0),
        ("Balder Töffen S.K.", 107, 5, 6, 6, 36639600, 20),
        ("Komnes Hera", 64, 5, 7, 3, 31439400, 20),
        ("Troll Winther", 39, 5, 6, 5, 29288500, 20),
        ("Vik Tor", 39, 6, 5, 5, 29144700, 20),
        ("Remjahn", 13, 10, 0, 1, 47690300, 40),
    ]
    race = "RIKSTOTO:S1_NR_2026-11-02:1"
    seen = "2026-11-02T10:08:39.259317+00:00"
    cutoff = "2026-11-02T10:21:36+00:00"
    atg_url = "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-02_31_1"
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        db.execute("""INSERT INTO races(
            race_id,race_date,country,track,race_no,start_time_utc,
            discipline,start_method,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)""",
                   (race, "2026-11-02", "SE", "Årjäng", 1,
                    "2026-11-02T11:20:00+00:00", "trot", "Volt",
                    "2026-10-30T11:41:04.234358+00:00"))
        for number, (name, starts, wins, seconds, thirds, earnings, extra) in enumerate(field, 1):
            db.execute("""INSERT INTO runners(
                race_id,selection_id,horse_name,post_position,scratched)
                VALUES(?,?,?,?,?)""", (race, str(number), name, number, 0))
            db.execute("""INSERT INTO runner_fundamental_snapshots(
                snapshot_id,race_id,selection_id,observed_at_utc,
                feature_as_of_utc,source_uri,horse_name,post_position,extra_distance_m,
                history_total_starts,history_total_wins,history_total_seconds,
                history_total_thirds,history_total_earnings,scratched,data_quality,
                full_field_history_complete)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       ("EXCERPT-ORIGINAL-" + str(number), race, str(number), seen,
                        seen, atg_url, name, number, extra, starts, wins,
                        seconds, thirds, float(earnings), 0, "FULL_FIELD_HISTORY_ATG", 1))
        champion = analyze_race(db, race_id=race, decision_at=cutoff)
        core004 = analyze_multifactor(db, race_id=race, as_of=cutoff)
    actual_champion = {r["selection_id"]: r["p_win"]
                       for r in champion["runner_rows"]}
    actual_core = {r["selection_id"]: r["p_candidate"]
                   for r in core004["runners"]}
    # Archived frozen report: percentages rounded to FOUR decimal places.
    frozen_champion = [
        2.7215, 1.7486, 1.8293, 12.9077, 9.5551,
        3.6830, 5.9454, 9.2484, 10.8999, 41.4612,
    ]
    frozen_core = [
        1.6996, 1.0769, 1.0091, 11.0648, 8.2069,
        2.3805, 4.2257, 8.0567, 9.4886, 52.7912,
    ]
    assert core004["status"] == "CANDIDATE_READY_UNCALIBRATED"
    assert len(actual_champion) == len(actual_core) == 10
    for number in range(1, 11):
        sid = str(number)
        assert actual_champion[sid] == pytest.approx(
            frozen_champion[number - 1] / 100, abs=5e-7)
        assert actual_core[sid] == pytest.approx(
            frozen_core[number - 1] / 100, abs=5e-7)
    assert sum(actual_champion.values()) == pytest.approx(1.0)
    assert sum(actual_core.values()) == pytest.approx(1.0)
    assert "NO_WIN_MARKET_AS_OF" in champion["blocks"]
    assert core004["bet_count"] == 0


def test_core003_shadow_workflow_preserves_fixed_cohort_and_blocked_races():
    """Contract: the full unchanged CORE-003 cohort is processed or accounted for.

    The selector itself has behavioral fixture regressions in
    tests/test_bet_mvp_shadow.py; do not pin obsolete inline Python text.
    """
    workflow = (ROOT / ".github" / "workflows" /
                "core-003-shadow-pilot.yml").read_text(encoding="utf-8")
    from hbi.bet_mvp_shadow import select_fixed_cohort_races

    assert callable(select_fixed_cohort_races)
    assert "selection = select_fixed_cohort_races(connection, source_report, as_of)" in workflow
    assert "for number, entry in enumerate(selection['eligible'], start=1):" in workflow
    assert "'original_cohort': selection['original_cohort']" in workflow
    assert "'not_processed': selection['not_processed']" in workflow
    assert "'processed': []" in workflow
    assert "'report_sha256': sha256(destination / 'shadow.json')" in workflow
    assert "'model_status': report['model_status']" in workflow
    assert "'market_status': report['market_status']" in workflow
    assert "'pit_status': report['pit_status']" in workflow
    assert "'bet_authority': False" in workflow
    assert "--run-kind', 'PROSPECTIVE_ATTEMPT'" in workflow
    assert "min(upcoming" not in workflow
