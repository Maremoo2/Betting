"""Fail-closed official Romme result parser (no model, no bets)."""
import json
import runpy
from pathlib import Path

import pytest

mod = runpy.run_path(str(
    Path(__file__).resolve().parents[1]
    / "scripts/romme_official_result_snapshot_readonly.py"
))
winner = mod["original_winner"]


def test_one_complete_winner():
    raw = json.dumps({"success": True, "result": {
        "isComplete": True, "results": [
            {"place": 1, "startNumber": 6, "horseName": "Nunchita"},
            {"place": 2, "startNumber": 11, "horseName": "Snowqueen"},
        ],
    }}).encode()
    assert winner(raw, 7)["winner_number"] == 6


@pytest.mark.parametrize("body,error", [
    ({"isComplete": False, "results": []}, "OFFICIAL_RESULT_INCOMPLETE"),
    ({"isComplete": True, "results": []}, "OFFICIAL_RESULT_ROWS_MISSING"),
    ({"isComplete": True, "results": [
        {"place": 1, "startNumber": 6},
        {"place": 1, "startNumber": 11},
    ]}, "OFFICIAL_WINNER_NOT_UNIQUE"),
    ({"isComplete": True, "results": [
        {"place": 1, "startNumber": 6},
        {"place": 2, "startNumber": 6},
    ]}, "OFFICIAL_START_NUMBER_CONFLICT"),
])
def test_incomplete_or_ambiguous_results_refused(body, error):
    raw = json.dumps({"success": True, "result": body}).encode()
    with pytest.raises(ValueError, match=error):
        winner(raw, 7)


def test_fixed_scope():
    assert len(mod["PATHS"]) == 9
    assert all("S1_NR_2026-11-06" in p for p in mod["PATHS"])
    assert all("/results/" in p or "/game/prizepayout/" in p for p in mod["PATHS"])
