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
