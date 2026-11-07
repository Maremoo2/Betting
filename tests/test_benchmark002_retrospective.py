from datetime import date

import numpy as np
import pytest

from hbi import benchmark002_retrospective as bench


def make_field(day, winner):
    rid = f"RIKSTOTO:AA_NR_{day}:1"
    rows = [
        {"race_id": rid, "race_date": day, "horse_id": horse, "start_number": str(i),
         "source_url": "https://example.test/result", "track": "AA", "country": "NO",
         "identity_status": "EXACT_SOURCE_NATIVE_REGISTRATION", "availability_evidence": [],
         "record_eligible": True, "scratched": False, "result_version": "a",
         "source_body_hash": "a", "race_time": {"value": 70 + i}, "gallop_status": None,
         "dead_heat": False, "winner": i == winner}
        for i, horse in enumerate(("h1", "h2"), 1)
    ]
    return rows, {"race_id": rid, "day": day, "horse_ids": ["h1", "h2"], "track": "AA"}


def test_own_and_future_outcome_are_not_features(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "purse_proxy", lambda root, row: 9.1)
    past, first = make_field("2019-01-01", 1)
    today, target = make_field("2019-01-02", 1)
    races, _, _ = bench.build_races(tmp_path, past + today, [first, target])
    today[0]["winner"], today[1]["winner"] = False, True
    today[0]["race_time"]["value"] = 99
    changed, _, _ = bench.build_races(tmp_path, past + today, [first, target])
    assert changed[1]["x"] == races[1]["x"]
    assert changed[1]["winner"] != races[1]["winner"]
    assert changed[1]["x"][0][7] > changed[1]["x"][1][7]


def test_full_field_failure_and_missing_vintage(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "purse_proxy", lambda root, row: pytest.fail("Incomplete field"))
    rows, target = make_field("2019-01-01", 1)
    assert bench.admission(rows[0])[0] == "RETROSPECTIVE_ONLY"
    rows[0]["availability_evidence"] = [{"verified": True}]
    assert bench.admission(rows[0])[0] == "PIT_UNPROVEN"
    races, _, diagnostics = bench.build_races(tmp_path, rows[:1], [target])
    assert races == []
    assert diagnostics["FULL_FIELD_REJECTED"] == 1


def test_regularized_fit_is_deterministic_and_normalized():
    row = {"x": [[1.0], [0.0], [-1.0]], "winner": 0}
    beta = bench.fit([row] * 3, (0,))
    assert np.array_equal(beta, bench.fit([row] * 3, (0,)))
    p = bench.predict(row, (0,), beta)
    assert p.sum() == pytest.approx(1)
    assert 1 > p[0] > p[1] > p[2] > 0


def test_lockbox_and_non_archive_source_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="Outside retrospective scope"):
        bench.historical_day("2025-01-01")
    with pytest.raises(ValueError, match="Outside source allowlist"):
        bench.purse_proxy(tmp_path, {"source_id": "2025/opaque.json"})
    assert bench.historical_day("2024-12-31") == date(2024, 12, 31)
