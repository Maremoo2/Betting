import json
from zipfile import ZipFile

from hbi.hq_daily_report import model_runners, original_roster, render


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
