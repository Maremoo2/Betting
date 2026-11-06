"""TEST_ONLY weekend source mapping / fail-closed research tests, no synthetic BET."""
import runpy
from pathlib import Path

mod = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                         "scripts/weekend_race_intelligence_readonly.py"))
_targets = mod["_targets"]
_pool_legs = mod["_pool_legs"]
_roster = mod["_roster"]
_assess_win = mod["_assess_win"]
_meetings = mod["_meetings"]


def meeting(key="B4_NR_2026-11-07", product="V85", numbers=None):
    numbers = numbers or [5, 6, 7, 8, 9, 10, 11, 12]
    return {
        "raceDayKey": key, "raceDayName": "Bergsåker",
        "countryIsoCode": "SE",
        "pools": [{
            "product": product, "poolKey": "SOURCE_POOL_2026",
            "raceNumber": numbers[0], "raceNumbers": numbers,
            "isMultiTrack": False, "isSecondary": False,
        }],
        "races": [{
            "raceNumber": n, "startTime": "2026-11-07T15:00:00+01:00",
            "startMethod": "Auto", "distance": 1640,
        } for n in numbers],
    }


def test_bergsaaker_all_eight_legs_mapped_to_authoritative_physical_keys():
    source = meeting()
    selected = _targets([source])
    assert len(selected["BERGSAKER_V85"]) == 1
    legs, blockers = _pool_legs(source, "V85")
    assert not blockers and len(legs) == 8
    assert [x["leg"] for x in legs] == list(range(1, 9))
    assert [x["physical_race_id"] for x in legs] == [
        f"RIKSTOTO:B4_NR_2026-11-07:{n}" for n in range(5, 13)
    ]


def test_multitrack_secondary_never_silently_assigned_local_legs():
    source = meeting()
    source["pools"][0]["isMultiTrack"] = True
    assert _pool_legs(source, "V85") == (
        [], ["MULTITRACK_OR_SECONDARY_REQUIRES_CROSS_RACEDAY_SOURCE"]
    )
    source["pools"][0]["isMultiTrack"] = False
    source["pools"][0]["isSecondary"] = True
    assert not _pool_legs(source, "V85")[0]


def test_no_inferred_leg_mapping_when_provider_pool_incomplete():
    source = meeting()
    source["pools"][0]["raceNumbers"][3] = 100
    assert _pool_legs(source, "V85")[1] == ["POOL_RACES_NOT_SUBSET_OF_PHYSICAL_MEETING"]
    source = meeting()
    source["pools"][0]["raceNumbers"] = [5, 5]
    assert _pool_legs(source, "V85")[1] == ["DUPLICATE_OR_INVALID_POOL_RACE_NUMBER"]
    source = meeting()
    source["pools"] = []
    assert _pool_legs(source, "V85")[1] == ["PRODUCT_NOT_FOUND_IN_ORIGINAL_MEETING"]


def test_cross_day_and_name_only_discovery_not_assumed():
    valid = meeting()
    wrong = meeting("B4_NR_2026-11-06")
    assert not _targets([wrong])["BERGSAKER_V85"]
    wrong = meeting()
    wrong["raceDayName"] = "Unrelated Race Course"
    assert not _targets([wrong])["BERGSAKER_V85"]
    assert _targets([valid, valid])["BERGSAKER_V85"] == [valid]


def test_x1_composite_wrapper_must_not_be_counted_as_physical_bergsaker():
    x1 = meeting("X1_NR_2026-11-07", "V4", [1, 2, 3, 4])
    x1["raceDayName"] = "Klosterskogen/Bergsåker"
    x1["trackCode"] = "X1"
    direct = meeting()
    assert _targets([x1, direct])["BERGSAKER_V85"] == [direct]
    assert _targets([x1, direct])["KLOSTERSKOGEN_V75"] == []


def test_nested_discovery_group_from_original_is_supported():
    m = meeting()
    assert _meetings({"result": [{"raceDays": [m]}]}) == [m]
    assert _meetings({"result": [m]}) == [m]
    assert _meetings({"result": "not a list"}) == []


def test_no_unknown_roster_becomes_zero_horses_or_bets():
    assert _roster({}, 5) == ([], ["STARTS_SOURCE_NOT_AVAILABLE"])
    source = {"result": {"5": [
        {"startNumber": 1, "horseRegistrationNumber": "SE123",
         "horseName": "Original Horse", "isScratched": False},
        {"startNumber": 2, "horseRegistrationNumber": "SE999",
         "horseName": "Another Horse", "isScratched": True},
    ]}}
    rows, errors = _roster(source, 5)
    assert not errors
    assert [r["decision"] for r in rows] == ["NOT_EXECUTABLE", "NOT_APPLICABLE"]
    assert all(r["p_win"] is None and r["fair_odds"] is None and
               r["frozen_min_odds"] is None for r in rows)
    source["result"]["5"][1]["horseRegistrationNumber"] = "SE123"
    assert _roster(source, 5)[1] == ["INVALID_OR_DUPLICATE_RUNNER_IDENTITY"]
    source["result"]["5"][1]["horseRegistrationNumber"] = "TMP-non-authoritative"
    temporary, issues = _roster(source, 5)
    assert issues == []
    assert temporary[1]["identity_status"] == "BLOCKED_TMP_NOT_AUTHORITY"
    assert temporary[1]["p_win"] is None and temporary[1]["decision"] == "NOT_APPLICABLE"


def test_unknown_win_not_misrepresented_as_zero_value():
    rows, err = _roster({"result": {"5": [
        {"startNumber": 1, "horseRegistrationNumber": "SE1", "horseName": "A", "isScratched": False},
        {"startNumber": 2, "horseRegistrationNumber": "SE2", "horseName": "B", "isScratched": False},
    ]}}, 5)
    assert not err
    assert _assess_win(None, rows) == "NOT_VERIFIED"
    assert all(r["win_odds"] is None and r["decision"] == "NOT_EXECUTABLE" for r in rows)

def test_unassessed_horse_is_never_model_pass():
    source = {"result": {"5": [
        {"startNumber": 1, "horseRegistrationNumber": "SE1",
         "horseName": "Original Horse", "isScratched": False},
        {"startNumber": 2, "horseRegistrationNumber": "SE2",
         "horseName": "Another Horse", "isScratched": False},
    ]}}
    rows, errors = _roster(source, 5)
    assert not errors
    assert all(r["model_status"] == "NOT_ASSESSED" for r in rows)
    assert all(r["decision"] == "NOT_EXECUTABLE" for r in rows)
    assert all(r["p_win"] is None and r["fair_odds"] is None for r in rows)
