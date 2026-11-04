"""MVP-018 original-result scratched rows must match *already frozen* scratches.

No late result can alter pre-T4 field or model probabilities. Negative cases
protect the original strict official full-field/source identity contract.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.prospective_outcome_scorecard import _market, _official_winner, clock
from hbi.evaluation import log_loss

BASELINE_SCORECARD_SHA = "a7cc16d026ea08e0042dc4d6c5c2d75d3212bfd5fb00203dbbbbc36455f11d2b"
MODEL_ARTIFACTS = {
    "RIKSTOTO:S2_NR_2026-11-02:1": (41488067799, 13162906690, "6"),
    "RIKSTOTO:S2_NR_2026-11-02:2": (41492573978, 13164543152, "5"),
    "RIKSTOTO:S2_NR_2026-11-02:4": (41499820309, 13168417335, "1"),
    "RIKSTOTO:S2_NR_2026-11-03:9": (41708503913, 13267816642, "5"),
}


def _case():
    roster = [
        {"start_number": 1, "selection_id": "1", "horse_name": "Alpha",
         "scratched": False},
        {"start_number": 2, "selection_id": "2", "horse_name": "Beta",
         "scratched": False},
        {"start_number": 3, "selection_id": "3", "horse_name": "Gamma",
         "scratched": True},
    ]
    complete = {
        "isComplete": True,
        "results": [
            {"startNumber": 1, "place": 1, "horseName": "Alpha", "kmTime": "14,5"},
            {"startNumber": 2, "place": 2, "horseName": "Beta", "kmTime": "14,6"},
            {"startNumber": 3, "place": 0, "horseName": "Gamma", "kmTime": "Str"},
        ],
    }
    raceday = {"finalOdds": {"winOdds": {"8": {
        "1": {"payoutStatus": "Dividends", "odds": 2.0}
    }}}}
    return roster, complete, raceday


def _verify(roster, complete, raceday):
    return _official_winner(
        complete, raceday, active=[r for r in roster if not r["scratched"]],
        frozen_roster=roster, race_no=8,
    )


def test_explicit_originally_scratched_row_not_counted_as_active():
    roster, complete, raceday = _case()
    assert _verify(roster, complete, raceday) == ("1", None)
    assert [r["scratched"] for r in roster] == [False, False, True]


def test_official_may_omit_an_originally_scratched_row():
    roster, complete, raceday = _case()
    complete["results"] = complete["results"][:2]
    assert _verify(roster, complete, raceday) == ("1", None)


@pytest.mark.parametrize(("mutation", "expected"), [
    ("late_scratch", "OFFICIAL_LATE_SCRATCH_NOT_FROZEN"),
    ("scratched_non_str", "OFFICIAL_FROZEN_SCRATCH_RESULT_CONFLICT"),
    ("scratched_nonzero", "OFFICIAL_FROZEN_SCRATCH_RESULT_CONFLICT"),
    ("scratched_missing_name", "OFFICIAL_FROZEN_SCRATCH_NAME_MISSING"),
    ("scratched_name_changed", "OFFICIAL_FROZEN_RUNNER_NAME_DISAGREES"),
    ("extra_runner", "OFFICIAL_ACTIVE_FIELD_MISMATCH"),
    ("missing_active", "OFFICIAL_ACTIVE_FIELD_MISMATCH"),
    ("duplicate", "OFFICIAL_DUPLICATE_RUNNER"),
    ("scratched_now_active", "OFFICIAL_ACTIVE_FIELD_MISMATCH"),
])
def test_official_scratch_source_conflicts_remain_blocked(mutation, expected):
    roster, complete, raceday = _case()
    if mutation == "late_scratch":
        complete["results"][0]["place"] = 0
        complete["results"][0]["kmTime"] = "Str"
    elif mutation == "scratched_non_str":
        complete["results"][2]["kmTime"] = "g"
    elif mutation == "scratched_nonzero":
        complete["results"][2]["place"] = 3
    elif mutation == "scratched_missing_name":
        complete["results"][2]["horseName"] = ""
    elif mutation == "scratched_name_changed":
        complete["results"][2]["horseName"] = "Different"
    elif mutation == "extra_runner":
        complete["results"].append({
            "startNumber": 4, "place": 0, "horseName": "Extra", "kmTime": "Str"
        })
    elif mutation == "missing_active":
        complete["results"].pop(1)
    elif mutation == "duplicate":
        complete["results"].append(complete["results"][0].copy())
    elif mutation == "scratched_now_active":
        roster[-1]["scratched"] = False
    _, reason = _verify(roster, complete, raceday)
    assert reason == expected


def test_invalid_frozen_duplicate_identity_rejected():
    roster, complete, raceday = _case()
    roster[-1]["start_number"] = 2
    _, reason = _verify(roster, complete, raceday)
    assert reason == "OFFICIAL_FROZEN_FULL_ROSTER_INVALID"


def test_four_sha_pinned_immutable_model_and_official_origins():
    root = os.getenv("MVP018_ORIGINAL_SCRATCH_REPLAY_ROOT")
    if not root:
        pytest.skip("Four immutable original model/official archives only in CI")
    home = Path(root)
    score_raw = (home / "scorecard/index.json").read_bytes()
    assert hashlib.sha256(score_raw).hexdigest() == BASELINE_SCORECARD_SHA
    scorecard = json.loads(score_raw)
    records = {r["race_id"]: r for r in scorecard["records"]}
    for race_id, (run_id, artifact_id, winner_expected) in MODEL_ARTIFACTS.items():
        record = records[race_id]
        assert record["reasons"] == ["OFFICIAL_ACTIVE_FIELD_MISMATCH"]
        model_root = home / f"models/{run_id}"
        index_bytes = (model_root / "cohort-index.json").read_bytes()
        model_index = json.loads(index_bytes)
        candidates = []
        for item in model_index["processed"]:
            path = model_root / Path(item["directory"]).name / "shadow.json"
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == item["report_sha256"]
            if item["race_id"] == race_id:
                candidates.append(raw)
        assert len(candidates) == 1
        original_model_sha = hashlib.sha256(candidates[0]).hexdigest()
        assert original_model_sha == record["source_model_original_sha256"]
        frozen = json.loads(candidates[0])
        assert frozen["model_status"] == "MODEL_READY"
        assert frozen["bet_authority"] is False
        active = [r for r in frozen["runners"] if not r["scratched"]]
        official_dir = home / ("scorecard/official-"
                               + hashlib.sha256(race_id.encode()).hexdigest()[:16])
        bodies = {}
        for receipt in record["original_result_receipts"]:
            role = receipt["role"]
            raw = (official_dir / f"{role}.raw.json").read_bytes()
            assert hashlib.sha256(raw).hexdigest() == receipt["raw_sha256"]
            assert receipt["source_uri"].endswith((
                "completeresults" if role == "complete" else "raceresults"
            ))
            bodies[role] = json.loads(raw)["result"]
        assert set(bodies) == {"complete", "raceday"}
        official_complete = bodies["complete"]
        assert official_complete["isComplete"] is True
        frozen_scratches = {
            int(r["start_number"]) for r in frozen["runners"] if r["scratched"]
        }
        official_scratch_rows = [
            row for row in official_complete["results"]
            if row["place"] == 0 and row.get("kmTime") == "Str"
        ]
        assert frozen_scratches == {int(r["startNumber"]) for r in official_scratch_rows}
        winner, reason = _official_winner(
            official_complete, bodies["raceday"], active=active,
            frozen_roster=frozen["runners"], race_no=int(race_id.split(":")[-1]),
        )
        assert reason is None and winner == winner_expected, (
            race_id, reason, winner, artifact_id
        )
        assert all(r.get("champion_p_win") is not None for r in active)
        assert all(r.get("core004_p_win") is not None for r in active)
        assert _market(active, clock(frozen["as_of_utc"])) is not None
        p = {r["selection_id"]: r["champion_p_win"] for r in active}
        assert log_loss(p, winner) >= 0
        assert not frozen.get("frozen_outcome")
