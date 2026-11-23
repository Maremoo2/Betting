"""TEST_ONLY fixture checks for PREWATCH-004B3; not sports model validation."""
from copy import deepcopy

import pytest

from hbi.prewatch004b3_flexible_pilot import evaluate, NOT_ESTIMABLE


def fixture():
    ctx = {"race_id": "R:1", "source_run_id": "collector-original",
           "pit_certified": False, "bet_authorized": False,
           "runners": [
               {"selection_id": "1", "scratched": False, "source_history_count": 4,
                "research_source_extractions": [{}, {}, {}, {}],
                "model_eligible": False, "pit_eligible": False, "bet_authorized": False},
               {"selection_id": "2", "scratched": False, "source_history_count": 1,
                "research_source_extractions": [{}],
                "model_eligible": False, "pit_eligible": False, "bet_authorized": False},
               {"selection_id": "3", "scratched": True, "source_history_count": 0,
                "research_source_extractions": [],
                "model_eligible": False, "pit_eligible": False, "bet_authorized": False}]}
    id_report = {"schema": "PREWATCH004B2_DAY_IDENTITY_COVERAGE_V1",
                 "source_run_id": "collector-original", "source_original_archive_sha256": "a"*64,
                 "physical_races": 1, "active_runners": 2, "listed_runners": 3,
                 "model_eligible": False, "bet_authorized": False,
                 "horse_observations": [
                     {"race_id": "R:1", "selection_id": str(i),
                      "identity_status": "IDENTITY_UNRESOLVED",
                      "pit_status": "PIT_UNPROVEN", "model_eligible": False}
                     for i in (1, 2)]}
    return [ctx], id_report


def test_partial_pdf_rows_are_not_qualified_bets():
    contexts, ids = fixture()
    a = evaluate(contexts, ids)
    assert a["research_pdf_row_tiers"] == {
        "pdf_raw_ge1": 2, "pdf_raw_ge3": 1,
        "pdf_raw_ge5": 0, "pdf_raw_ge10": 0}
    assert a["strict"]["model_eligible_horses"] == 0
    assert a["flexible"]["model_eligible_horses"] == 0
    assert a["comparison"]["p_win"] == NOT_ESTIMABLE
    assert a["comparison"]["bet_candidates"] == NOT_ESTIMABLE
    assert a["research_bets_issued"] == 0 and a["bet_authorized"] is False
    assert evaluate(contexts, ids) == a


@pytest.mark.parametrize("change,error", [
    ("wrong_identity", "FULL_FIELD"),
    ("duplicate_runner", "DUPLICATE_ACTIVE"),
    ("fake_pit", "UNATTESTED_IDENTITY"),
    ("fake_approval", "UNAUTHORIZED_FEATURE"),
    ("wrong_source", "DAY_COUNTS"),
    ("fake_bet", "SOURCE_AUTHORITY"),
    ("wrong_history", "SOURCE_HISTORY"),
])
def test_adversarial_changes_fail_closed(change, error):
    contexts, ids = fixture()
    c, r = contexts[0], contexts[0]["runners"][0]
    if change == "wrong_identity":
        ids["horse_observations"][0]["selection_id"] = "9"
    elif change == "duplicate_runner":
        c["runners"][1]["selection_id"] = "1"
    elif change == "fake_pit":
        ids["horse_observations"][0]["pit_status"] = "PIT_VERIFIED"
    elif change == "fake_approval":
        r["model_eligible"] = True
    elif change == "wrong_source":
        ids["source_run_id"] = "unrelated"
    elif change == "fake_bet":
        c["bet_authorized"] = True
    elif change == "wrong_history":
        r["source_history_count"] = 5
    with pytest.raises(ValueError, match=error):
        evaluate(contexts, ids)


def test_missing_and_colliding_race():
    contexts, ids = fixture()
    with pytest.raises(ValueError, match="DUPLICATE_OR_EMPTY"):
        evaluate([], ids)
    with pytest.raises(ValueError, match="DUPLICATE_OR_EMPTY"):
        evaluate(contexts + deepcopy(contexts), ids)
