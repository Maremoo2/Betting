"""TEST_ONLY synthetic protocol tests; genuine archive integration is separate."""
import copy
import json
import math
from pathlib import Path

import pytest

from hbi.backfill import run_batch
from hbi.date_overview import DailyArchive
from hbi.model_protocol import audit, score, splits
from hbi.swedish_identity import biography, resolve

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures"
PROGRAM_SHA = "a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e"
ATG_SHA = "a053ce855c230c8e10450dfcecca3447873718512269bfc2b132c2d66f84745c"


def test_real_sweden_identity_integration():
    archive = DailyArchive(FIXTURES / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    result = resolve(archive, FIXTURES / "atg-se-2026-10-20-identity.zip", ATG_SHA)
    assert result["races"] == 19 and result["horses"] == 208
    assert result["status_counts"] == {"IDENTITY_VERIFIED": 196, "UNRESOLVED": 12}
    assert result["original_stable_registrations"] == 0
    assert all(not h["pre_race_availability_verified"] for h in result["links"])
    assert not result["provider_admission_changed"] and result["model_eligible"] == 0
    # Genuine monté metadata is retained as a conflict, not coerced to trot.
    assert all(h["provider_identity"] is None for h in result["links"] if h["race_number"] == 5 and h["raceday_key"].startswith("S2"))


@pytest.mark.parametrize("mutation", ["name_collision", "parentage", "missing_bio"])
def test_test_only_identity_negative(mutation):
    archive = DailyArchive(FIXTURES / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    archive.data = copy.deepcopy(archive.data)
    doc = next(d for d in archive.data["races"] if d["race"]["meeting_id"].startswith("S1") and d["race"]["race_number"] == 1)
    if mutation == "name_collision":
        doc["entrants"][0]["name"] = doc["entrants"][1]["name"]
    else:
        doc["entrants"][0]["identity_text"] = "" if mutation == "missing_bio" else "9-års brun v e Wrong - Parent e Other"
    result = resolve(archive, FIXTURES / "atg-se-2026-10-20-identity.zip", ATG_SHA)
    assert result["status_counts"]["IDENTITY_VERIFIED"] < 196


def test_test_only_biography_no_fuzzy_guess():
    assert biography("unknown") is None
    assert biography("3-års brun v e Sire - Dam e Grandsire") == (3, "gelding", "sire", "dam")


def test_test_only_splits_and_scores():
    protocol = json.loads((ROOT / "examples/model-protocol.json").read_text())
    assert list(splits(protocol)) == ["train", "validation", "test"]
    protocol["validation"][0] = "2023-12-31"
    with pytest.raises(ValueError, match="CHRONOLOGICAL"):
        splits(protocol)
    # TEST_ONLY fabricated predictions; no empirical model claim.
    result = score({"TEST_ONLY_NO": {"a": .75, "b": .25}}, {"TEST_ONLY_NO": (["a", "b"], "a")})
    assert result["log_loss"] == pytest.approx(-math.log(.75))
    assert result["brier_sum_per_race"] == pytest.approx(.125)
    assert result["uniform_baseline"]["brier_sum_per_race"] == .5


@pytest.mark.parametrize("probabilities", [{"a": .7}, {"a": .8, "b": .8}, {"a": float("nan"), "b": 0}, {"a": True, "b": 0}, {"a": -1, "b": 2}])
def test_test_only_invalid_predictions(probabilities):
    with pytest.raises(ValueError, match="FULL_FIELD"):
        score({"TEST_ONLY": probabilities}, {"TEST_ONLY": (["a", "b"], "a")})


def test_real_m5_candidate_audit_and_tampering(tmp_path):
    output = tmp_path / "research"
    run_batch(ROOT / "examples/backfill/m4-regression.json", output)
    report = audit(output, ROOT / "examples/model-protocol.json")
    assert report["races"] == 39 and report["data_ready"] == 0
    assert report["metrics"] is None and not report["training_performed"]
    rows = [json.loads(line) for line in (output / "dataset.jsonl").read_text().splitlines()]
    assert all("labels" not in r["model_candidate"]["inputs"][0] for r in rows)
    assert all(not r["model_candidate"]["data_ready"] for r in rows)
    with (output / "dataset.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="HASH"):
        audit(output, ROOT / "examples/model-protocol.json")


def test_test_only_feature_pit_and_label_leakage(tmp_path):
    from hbi.model_dataset import candidate

    output = tmp_path / "research"
    run_batch(ROOT / "examples/backfill/m4-regression.json", output)
    row = json.loads((output / "dataset.jsonl").read_text().splitlines()[0])
    row = copy.deepcopy(row)  # TEST_ONLY mutation of an existing contract.
    horse = row["roster"][0]
    horse["features"]["driver"]["status"] = "PIT_VERIFIED"
    horse["features"]["driver"]["source_observed_at"] = "1900-01-01T00:00:00+00:00"
    horse["features"]["winning_place"] = {"value": 1, "status": "PIT_VERIFIED"}
    view = candidate(row)
    assert not view["inputs"][0]["features"]["driver"]["pit_verified"]
    assert any("UNAPPROVED_FEATURE" in r for r in view["exclusion_reasons"])
    assert not view["data_ready"]


def test_test_only_duplicate_races_rejected(tmp_path):
    import hashlib

    output = tmp_path / "research"
    run_batch(ROOT / "examples/backfill/m4-regression.json", output)
    path = output / "dataset.jsonl"
    data = path.read_bytes()
    path.write_bytes(data + data.splitlines(keepends=True)[0])
    manifest_path = output / "model-readiness.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["dataset_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="DUPLICATE_RACE"):
        audit(output, ROOT / "examples/model-protocol.json")
