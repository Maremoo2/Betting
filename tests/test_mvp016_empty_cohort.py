"""MVP-016: CORE-003 no-op source is not a broken original or a race.

Synthetic cases exercise the contract; optional GitHub-original case is called
by PR CI with a downloaded SHA-checked prospective no-op index.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hbi.prospective_outcome_scorecard import read_archived_models

SCHEMA = "BET_MVP_002_FIXED_COHORT_INDEX_V1"
ORIGINAL_NOOP_SHA = "ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0"


def _write(root: Path, run: str, value: dict) -> None:
    folder = root / run
    folder.mkdir(parents=True)
    (folder / "cohort-index.json").write_text(json.dumps(value), encoding="utf-8")


def _noop() -> dict:
    return {
        "schema": SCHEMA, "bet_authority": False,
        "original_cohort": [], "processed": [], "not_processed": [],
    }


def test_valid_empty_cohort_is_zero_races_and_not_an_archive_error(tmp_path):
    _write(tmp_path, "001", _noop())
    models, errors, cohort = read_archived_models(tmp_path)
    assert (models, errors, cohort) == ([], [], [])


def test_one_valid_noop_does_not_erase_real_frozen_denominator(tmp_path):
    _write(tmp_path, "001", _noop())
    race_id = "RIKSTOTO:S1_NR_2026-11-03:8"
    _write(tmp_path, "002", {
        "schema": SCHEMA, "bet_authority": False, "original_cohort": [race_id],
        "processed": [], "not_processed": [{"race_id": race_id, "reason": "SOURCE_BLOCKED"}],
    })
    models, errors, cohort = read_archived_models(tmp_path)
    assert models == [] and errors == [] and cohort == [race_id]


@pytest.mark.parametrize("invalid", [
    {"processed": [{"race_id": "RIKSTOTO:TEST:1", "directory": "bet-mvp-shadow/race-001"}]},
    {"not_processed": [{"race_id": "RIKSTOTO:TEST:1", "reason": "MODEL_BLOCKED"}]},
    {"not_processed": None},
    {"original_cohort": ["RIKSTOTO:TEST:1", "RIKSTOTO:TEST:1"]},
    {"bet_authority": True},
    {"schema": "UNKNOWN"},
])
def test_conflicting_or_untrusted_empty_cohort_remains_fail_closed(tmp_path, invalid):
    _write(tmp_path, "001", {**_noop(), **invalid})
    models, errors, cohort = read_archived_models(tmp_path)
    assert models == []
    assert errors
    assert cohort == []


def test_genuine_nov04_original_empty_cohort_no_error_or_phantom_race(tmp_path):
    original_root = os.environ.get("MVP016_EMPTY_COHORT_ORIGINAL_ROOT")
    if not original_root:
        pytest.skip("Original GitHub model artifact is only in the CI replay")
    path = Path(original_root) / "cohort-index.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_NOOP_SHA
    model = json.loads(raw)
    assert model["schema"] == SCHEMA
    assert model["bet_authority"] is False
    assert model["original_cohort"] == model["processed"] == model["not_processed"] == []
    models, errors, cohort = read_archived_models(Path(original_root))
    assert (models, errors, cohort) == ([], [], [])
