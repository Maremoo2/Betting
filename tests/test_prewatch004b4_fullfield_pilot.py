"""004B4 TEST_ONLY artificial negative cases, not real PIT or sports evidence."""
from copy import deepcopy

import pytest

from hbi.prewatch004b4_fullfield_pilot import select_race
from test_prewatch004b3_flexible_pilot import fixture


def source_fixture():
    contexts, identities = fixture()
    for race in contexts:
        race["race"] = {"track": "TEST_ONLY", "race_number": 1}
        for runner in race["runners"]:
            for prior in runner["research_source_extractions"]:
                prior.update({
                    "verified_official_result": False,
                    "pit_certified": False,
                    "semantic_status": "UNKNOWN",
                    "raw_sha256": "a" * 64,
                })
    return contexts, identities


def test_entire_field_and_missingness_are_explicit():
    contexts, identity = source_fixture()
    result = select_race(contexts, identity)
    assert result["race_id"] == "R:1"
    assert result["active_count"] == 2
    assert result["listed_count"] == 3
    assert result["scratched_count"] == 1
    assert result["active_raw_ge3"] == 1
    assert result["active_raw_ge5"] == 0
    assert result["p_win"] == "NOT_ESTIMABLE"
    assert result["bet_candidates"] == "NOT_ESTIMABLE"
    assert result["bet_authorized"] is False
    assert len(result["runners"]) == 3
    assert select_race(contexts, identity) == result


def test_deterministic_max_min_selection():
    contexts, identity = source_fixture()
    extra = deepcopy(contexts[0])
    extra["race_id"] = "R:2"
    for r in extra["runners"]:
        if not r["scratched"]:
            r["source_history_count"] = 5
            r["research_source_extractions"] = [{}] * 5
    contexts.append(extra)
    for i in (1, 2):
        identity["horse_observations"].append(
            {**identity["horse_observations"][i - 1], "race_id": "R:2"}
        )
    identity["physical_races"] = 2
    identity["listed_runners"] = 6
    identity["active_runners"] = 4
    assert select_race(contexts, identity)["race_id"] == "R:2"


@pytest.mark.parametrize("mutate", [
    "identity", "pit", "model", "prior", "roster", "source", "bet",
])
def test_mutated_claims_are_rejected(mutate):
    contexts, identity = source_fixture()
    runner = contexts[0]["runners"][0]
    if mutate == "identity":
        identity["horse_observations"][0]["identity_status"] = "ATTESTED"
    elif mutate == "pit":
        identity["horse_observations"][0]["pit_status"] = "PIT_VERIFIED"
    elif mutate == "model":
        runner["model_eligible"] = True
    elif mutate == "prior":
        runner["research_source_extractions"][0]["verified_official_result"] = True
    elif mutate == "roster":
        contexts[0]["runners"][1]["selection_id"] = "1"
    elif mutate == "source":
        contexts[0]["source_run_id"] = "changed"
    elif mutate == "bet":
        contexts[0]["bet_authorized"] = True
    with pytest.raises((ValueError, KeyError)):
        select_race(contexts, identity)
