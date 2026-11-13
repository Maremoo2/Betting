import json
from zipfile import ZipFile

import pytest

from hbi.hq_daily_report import freeze_order, model_runners, original_roster, read_cohort, render
from hbi.prospective_outcome_scorecard import digest


def test_roster_rejects_wrong_physical_race(tmp_path):
    path = tmp_path / "source.zip"
    meeting = "S1_NR_2026-11-13"
    row = {"raceNumber": 2, "raceKey": f"{meeting}#2", "startNumber": 1,
           "isScratched": False, "horseName": "Example"}
    with ZipFile(path, "w") as archive:
        archive.writestr(f"original/meetings/{meeting}/starts.raw.json",
                         json.dumps({"result": {"2": [row], "3": [row]}}))
    with ZipFile(path) as archive:
        assert original_roster(archive, f"RIKSTOTO:{meeting}:2")[0] == [row]
        assert original_roster(archive, f"RIKSTOTO:{meeting}:3") == ([], None)


def test_blocked_model_and_missing_data_render_without_fabrication():
    assert model_runners({"race": {}, "runners": []}) == []
    report = {
        "date": "2026-11-13", "as_of": None, "run": 1,
        "historical": None, "benchmark": None, "archive_run": None,
        "races": [{
            "track": "<Track>", "country": "SE", "number": 1, "start": None,
            "active": None, "scratched": None, "analysis": None, "full_market": False,
            "reasons": ["COLLECTOR_PDF_START_CLOCK_CONFLICT"], "runners": [],
        }],
    }
    _, text, html = render(report)
    assert "NO VALID MODEL" in text and "ukjent aktive" in text
    assert "Programmet og den registrerte starttiden avviker." in text
    assert "COLLECTOR_PDF_START_CLOCK_CONFLICT" not in text
    assert "&lt;Track&gt;" in html and "<Track>" not in html

def test_oslo_time_keeps_seconds_and_handles_dst():
    from hbi.hq_daily_report import clock_label

    assert clock_label("2026-11-13T11:29:30+00:00") == "13.11.2026 12:29:30"
    assert clock_label("2026-07-13T11:29:30+00:00") == "13.07.2026 13:29:30"
    assert clock_label("2026-11-13T11:29:30") == "ukjent"

def research_freeze(*, with_win):
    return {
        "race": {"race_id": "RIKSTOTO:S2_NR_2026-11-13:1",
                 "start_time_utc": "2026-11-13T17:20:00+00:00"},
        "report_created_at_utc": "2026-11-13T17:15:59+00:00",
        "model_calculated_at_utc": "2026-11-13T17:15:58+00:00",
        "as_of_utc": "2026-11-13T17:15:57+00:00",
        "model_status": "MODEL_READY", "run_kind": "PROSPECTIVE_ATTEMPT",
        "source_archive_is_immutable_read_only": True, "bet_authority": False,
        "field_size": 2, "active_runners": 2,
        "runners": [
            {"start_number": n, "selection_id": str(n), "scratched": False,
             "champion_p_win": .5, "core004_p_win": .5, **(
                 {"win_odds": 3.0, "win_odds_provider": "rikstoto",
                  "win_odds_observed_at_utc": "2026-11-13T17:15:50+00:00"}
                 if with_win else {}
             )}
            for n in (1, 2)
        ],
    }


def test_same_freeze_win_beats_earlier_probability_only_freeze():
    older = research_freeze(with_win=False)
    older["report_created_at_utc"] = "2026-11-13T17:10:00+00:00"
    older["as_of_utc"] = "2026-11-13T17:09:00+00:00"
    assert freeze_order((research_freeze(with_win=True), "b")) < freeze_order((older, "a"))


@pytest.mark.parametrize(("frozen", "blocked"), [
    ("2026-11-13T17:15:59+00:00", False),
    ("2026-11-13T17:16:00+00:00", True),
    ("2026-11-13T17:16:01+00:00", True),
    ("2026-11-13T17:15:59", True),
])
def test_cohort_requires_creation_strictly_before_conservative_cutoff(tmp_path, frozen, blocked):
    model = research_freeze(with_win=True)
    model["race"]["start_time_utc"] = "2026-11-13T17:24:00+00:00"
    model["report_created_at_utc"] = frozen
    race_id = model["race"]["race_id"]
    raw = json.dumps(model).encode()
    index = json.dumps({
        "schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1", "bet_authority": False,
        "pit_certified": False, "original_cohort": [race_id],
        "eligible_prestart": [{"race_id": race_id, "start_time_utc": model["race"]["start_time_utc"],
                              "earliest_source_start_utc": "2026-11-13T17:20:00+00:00"}],
        "processed": [{"race_id": race_id, "directory": "bet-mvp-shadow/race-001",
                       "report_sha256": digest(raw)}],
    }).encode()
    path = tmp_path / "cohort.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("cohort-index.json", index)
        archive.writestr("race-001/shadow.json", raw)
    _, originals, blocked_races = read_cohort(path, digest(index))
    assert originals[race_id] == (model, digest(raw))
    assert (race_id in blocked_races) is blocked

def test_atg_calendar_keeps_unmatched_physical_race_in_its_own_namespace():
    from datetime import date

    from hbi.hq_daily_report import calendar_only_races

    day = date(2026, 11, 13)
    race = {"id": "2026-11-13_11_2", "number": 2,
            "status": "results", "startTime": "2026-11-13T18:12:44"}
    calendar = {"date": day.isoformat(), "tracks": [
        {"id": 11, "name": "Boden", "countryCode": "SE", "sport": "trot", "races": [race]},
        {"id": 20, "name": "Ponny", "countryCode": "SE", "sport": "pony", "races": [race]},
    ]}
    rows = calendar_only_races(calendar, day, [])
    assert len(rows) == 1
    assert rows[0]["race_id"] == "ATG:2026-11-13_11_2"
    assert rows[0]["start"] is None
    assert rows[0]["calendar_status"] == "results"
    assert rows[0]["analysis"] is None
    assert calendar_only_races(calendar, day, [
        {"track": "Boden", "country": "SE", "number": 2},
    ]) == []
    with pytest.raises(ValueError, match="ATG_CALENDAR_RACE_ID_MISMATCH"):
        calendar_only_races({**calendar, "tracks": [
            {**calendar["tracks"][0], "races": [{**race, "id": "2026-11-18_11_2"}]},
        ]}, day, [])

def test_atg_result_preserves_atg_identity_and_has_no_score(tmp_path):
    from hbi.hq_daily_report import official_atg_observation
    from hbi.providers.atg import AtgClient

    rid = "2026-11-13_11_2"
    original = json.dumps({"id": f"vinnare_{rid}", "races": [{
        "id": rid, "number": "2", "date": "2026-11-13", "sport": "trot",
        "track": {"id": 11, "name": "Boden", "countryCode": "SE"},
        "status": "results", "startTime": "2026-11-13T18:13:00",
        "scheduledStartTime": "2026-11-13T18:08:00", "result": {"scratchings": [2]},
        "pools": {"vinnare": {"result": {"winners": [{"number": 1}]}}},
        "starts": [
            {"id": f"{rid}_1", "number": "1", "horse": {"name": "Runner One"}, "result": {"place": 1}},
            {"id": f"{rid}_2", "number": "2", "horse": {"name": "Runner Two"}},
        ],
    }]}).encode()
    (tmp_path / "game.raw.json").write_bytes(original)
    (tmp_path / "game.receipt.json").write_text(json.dumps({
        "source_uri": f"{AtgClient.GAME_API}/vinnare_{rid}", "http_status": 200,
        "observed_at_utc": "2026-11-13T17:18:00+00:00", "sha256": digest(original),
    }))
    race = {"race_id": f"ATG:{rid}", "track": "Boden", "country": "SE", "number": 2}
    result = official_atg_observation(race, tmp_path)
    assert result["winner"] == {"number": 1, "name": "Runner One"}
    assert result["scratches"] == ["Runner Two"]
    assert result["score_blocker"] == "NO_FROZEN_MODEL"
    assert result["scores"] is None
    with pytest.raises(ValueError, match="ATG_OFFICIAL_RESULT_ID_MISMATCH"):
        official_atg_observation({**race, "number": 1}, tmp_path)


def test_atg_sorlandet_alias_does_not_duplicate_norwegian_programme():
    from datetime import date

    from hbi.hq_daily_report import calendar_only_races

    day = date(2026, 11, 12)
    calendar = {"date": day.isoformat(), "tracks": [{
        "id": 99, "name": "Sörlandet", "countryCode": "NO", "sport": "trot",
        "races": [{"id": "2026-11-12_99_1", "number": 1}],
    }]}
    assert calendar_only_races(calendar, day, [
        {"track": "Sørlandet", "country": "NO", "number": 1},
    ]) == []
