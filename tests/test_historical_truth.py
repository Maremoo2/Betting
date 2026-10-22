"""Source-verified results and negative mutations of the genuine archived envelopes."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hbi.date_overview import DailyArchive, inspect_race
from hbi.fundamental_view import analyze_race
from hbi.historical_truth import HistoricalTruth, attach_history
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
ARCHIVE = ROOT / "tests/fixtures/rikstoto-2026-10-20.zip"
SHA = "a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e"
TRUTH = ROOT / "tests/fixtures/rikstoto-historical-truth.json"
TRUTH_SHA = "8086ec016e8e4f9cda7d9ad36abe44df1e09e3c2e387a9ed6c612fa61a0f8953"


def context():
    archive = DailyArchive(ARCHIVE, SHA, "2026-10-20")
    doc = archive.data["races"][0]
    starts = archive.read("meetings/BJ_NR_2026-10-20/starts.json")
    entry, _ = inspect_race(archive, doc, archive.manifest["meetings"][0], starts)
    entry["source_entry_id"] = f"{SHA}:races:0"
    entry["fundamental_analysis"] = analyze_race(archive, doc, entry, starts)
    return archive, doc, entry


def truth_copy(tmp_path, mutate):
    from rikstoto_crawler.transport import digest
    bundle = json.loads(TRUTH.read_bytes())
    mutate(bundle)
    for s in bundle["sources"]:
        s["body_sha256"] = digest(s["body"])
    path = tmp_path / "mutated.json"
    raw = json.dumps(bundle).encode()
    path.write_bytes(raw)
    return HistoricalTruth(path, hashlib.sha256(raw).hexdigest())


def link(truth, horse_index=0, prior_index=4):
    _, doc, entry = context()
    horse = entry["fundamental_analysis"]["horses"][horse_index]
    return truth.link(horse, doc["entrants"][horse_index]["past_starts"][prior_index],
                      entry["fundamental_analysis"]["cutoff"], "2026-10-20")


def test_actual_cli_result_view_and_readiness(tmp_path):
    output = tmp_path / "m4"
    result = subprocess.run([sys.executable, "-m", "hbi.cli", "overview", "--date", "2026-10-20",
        "--archive", str(ARCHIVE), "--sha256", SHA, "--fundamental",
        "--results-archive", str(TRUTH), "--results-sha256", TRUTH_SHA,
        "--output", str(output)], cwd=ROOT, capture_output=True, text=True, check=True)
    report = json.loads((output / "overview.json").read_text())
    readiness = json.loads((output / "model-readiness.json").read_text())
    assert readiness == report["historical_truth"]
    assert readiness["counts"] == {
        "total_unique_observations": 1440, "source_occurrences": 1440,
        "horse_identity_verified": 375, "historical_race_identity_verified": 6,
        "authoritative_result_verified": 6, "pit_verified": 0, "model_eligible": 0,
        "by_status": {"SOURCE_EXCERPT_ONLY": 1065, "IDENTITY_VERIFIED": 369,
                      "RESULT_VERIFIED": 6, "PIT_VERIFIED": 0, "MODEL_ELIGIBLE": 0,
                      "CONFLICT": 0, "UNRESOLVED": 0}}
    assert sum(readiness["counts"]["by_status"].values()) == len(readiness["observations"])
    assert "RIKSTOTO:JA_NR_2026-07-03:10; plass=4" in result.stdout
    assert "originalkode=0; tid=dg a" in result.stdout and "tid=br a" in result.stdout
    assert report["counts"]["fully_analyzed"] == 0 and len(report["races"]) == 55
    first = report["races"][0]
    assert len(first["fundamental_analysis"]["horses"]) == 12
    catalog = {r["observation_id"]: r for r in readiness["observations"]}
    for h in first["fundamental_analysis"]["horses"]:
        assert len(h["historical_results"]) == 5
        assert h["historical_coverage"]["unique_observations"] == 5
        assert all(not catalog[i]["model_eligible"] for i in h["historical_results"])
    assert first["betting_runtime"]["report"]["allowed"] is False
    store = SQLiteStore(output / "hbi.sqlite")
    for table in ["predictions", "outcomes", "decisions", "market_snapshots"]:
        assert store.count(table) == 0


def test_real_independent_result_identity_and_source_pointer():
    truth = HistoricalTruth(TRUTH, TRUTH_SHA)
    row = link(truth)
    assert row["authoritative_result_verified"]
    assert row["verified_registration"] == "578001020160396"
    assert row["historical_race_id"] == "RIKSTOTO:JA_NR_2026-07-03:10"
    assert row["result"]["placing"] == 4 and row["result"]["km_time_raw"] == "29,8"
    assert row["result"]["distance_m"] == 2120
    source = truth.sources[row["source_refs"][-1]["path"]]
    value = source["body"]
    for token in row["result"]["json_pointer"].split("/")[1:]:
        value = value[int(token)] if isinstance(value, list) else value[token]
    assert value["horseRegistrationNumber"] == row["verified_registration"]
    assert value["place"] == row["result"]["placing"]
    assert not row["pit_verified"] and not row["model_eligible"]
    assert "RESULT_ACQUIRED_AFTER_ANALYSIS_CUTOFF" in row["reasons"]
    winner = link(truth, 10, 3)
    assert winner["result"]["status"] == "WINNER" and winner["result"]["placing"] == 1


@pytest.mark.parametrize("horse,index,code", [(0, 3, "dg a"), (1, 4, "32,5 g"), (2, 4, "br a")])
def test_real_zero_gallop_dq_nonfinish_codes_remain_uninterpreted(horse, index, code):
    row = link(HistoricalTruth(TRUTH, TRUTH_SHA), horse, index)
    assert row["result"]["km_time_raw"] == code
    assert row["result"]["placing"] is None and row["result"]["place_raw"] == 0
    assert row["result"]["status"] == "UNRESOLVED_CODE"
    assert all(row["result"][k] is None for k in ["gallop", "disqualified", "did_not_finish"])
    assert not row["model_eligible"]


@pytest.mark.parametrize("change", ["wrong_id", "wrong_name", "partial_field", "duplicate_id", "incomplete"])
def test_result_identity_or_full_field_contradictions_rejected(tmp_path, change):
    def mutate(bundle):
        s = next(s for s in bundle["sources"] if s["path"].endswith("/10/completeresults"))
        r = s["body"]["result"]
        if change == "wrong_id":
            r["results"][3]["horseRegistrationNumber"] = "WRONG"
        elif change == "wrong_name":
            r["results"][3]["horseName"] = "OTHER"
        elif change == "partial_field":
            r["results"].pop()
        elif change == "duplicate_id":
            r["results"][0]["horseRegistrationNumber"] = r["results"][3]["horseRegistrationNumber"]
        else:
            r["isComplete"] = False
    row = link(truth_copy(tmp_path, mutate))
    assert not row["authoritative_result_verified"] and row["result"] is None
    assert not row["model_eligible"] and any("REJECTED" in r for r in row["reasons"])


def test_duplicate_official_race_is_ambiguous(tmp_path):
    def mutate(b):
        s = next(s for s in b["sources"] if s["path"].endswith("2026-07-03/list"))
        g = s["body"]["result"][0]
        m = next(m for m in g["raceDays"] if m["raceDay"] == "JA_NR_2026-07-03")
        g["raceDays"].append(copy.deepcopy(m))
    row = link(truth_copy(tmp_path, mutate))
    assert row["status"] == "CONFLICT" and row["result"] is None


@pytest.mark.parametrize("day", [None, "2026-10-20", "2026-10-21", "bad"])
def test_future_or_undated_excerpts_never_result_features(day):
    _, doc, entry = context()
    prior = copy.deepcopy(doc["entrants"][0]["past_starts"][4])
    prior["date"] = day
    row = HistoricalTruth(TRUTH, TRUTH_SHA).link(entry["fundamental_analysis"]["horses"][0],
                                               prior, entry["fundamental_analysis"]["cutoff"], "2026-10-20")
    assert row["status"] == "UNRESOLVED" and row["source_excerpt"] is None
    assert not row["authoritative_result_verified"] and not row["model_eligible"]


def test_deduplicate_same_start_and_conflict_divergent_excerpt():
    archive, doc, entry = context()
    # Existing real observation repeated in a mutation; never inflates source truth.
    doc["entrants"][0]["past_starts"].append(copy.deepcopy(doc["entrants"][0]["past_starts"][4]))
    archive.data["races"] = [doc]
    report = {"races": [entry]}
    attach_history(report, archive, HistoricalTruth(TRUTH, TRUTH_SHA))
    assert report["historical_truth"]["counts"]["total_unique_observations"] == 60
    assert report["historical_truth"]["counts"]["source_occurrences"] == 61
    assert report["historical_truth"]["counts"]["authoritative_result_verified"] == 6
    doc["entrants"][0]["past_starts"][-1]["raw_text"] += " DIFFERENT"
    attach_history(report, archive, HistoricalTruth(TRUTH, TRUTH_SHA))
    assert report["historical_truth"]["counts"]["by_status"]["CONFLICT"] == 1
    assert report["historical_truth"]["counts"]["authoritative_result_verified"] == 5


@pytest.mark.parametrize("change,error", [
    ("wrong_host", "UNTRUSTED_HISTORY_SOURCE"),
    ("duplicate_source", "DUPLICATE_OR_UNTRUSTED_HISTORY_SOURCE"),
    ("naive_time", "UNKNOWN_SOURCE_TIMEZONE"),
    ("wrong_list_date", "HISTORY_LIST_DATE_MISMATCH"),
])
def test_source_integrity_rejections(tmp_path, change, error):
    def mutate(b):
        s = b["sources"][0]
        if change == "wrong_host":
            s["url"] = "https://example.org/api" + s["path"]
        elif change == "duplicate_source":
            b["sources"].append(copy.deepcopy(s))
        elif change == "naive_time":
            s["fetched_at"] = "2026-10-21T12:00:00"
        else:
            s["body"]["result"][0]["date"] = "2027-01-01T00:00:00"
    with pytest.raises(ValueError, match=error):
        truth_copy(tmp_path, mutate)


def test_hash_and_body_tampering_rejected(tmp_path):
    with pytest.raises(ValueError, match="HISTORY_ARCHIVE_SHA256_MISMATCH"):
        HistoricalTruth(TRUTH, "0" * 64)
    bundle = json.loads(TRUTH.read_bytes())
    bundle["sources"][0]["body"]["result"] = []
    raw = json.dumps(bundle).encode()
    p = tmp_path / "tampered.json"
    p.write_bytes(raw)
    with pytest.raises(ValueError, match="HISTORY_BODY_HASH_MISMATCH"):
        HistoricalTruth(p, hashlib.sha256(raw).hexdigest())


def test_unproven_publication_claims_and_market_columns_cannot_enable_features(tmp_path):
    def mutate(b):
        for s in b["sources"]:
            s["fetched_at"] = "2026-10-19T05:00:00+00:00"
            s["published_at"] = "2026-10-19T04:00:00+00:00"  # Unverified invented test field.
            if s["path"].endswith("completeresults"):
                s["body"]["result"]["publishedAt"] = "2026-10-19T04:00:00+00:00"
                for r in s["body"]["result"]["results"]:
                    r["odds"] = 999999
    row = link(truth_copy(tmp_path, mutate))
    real = link(HistoricalTruth(TRUTH, TRUTH_SHA))
    assert row["result"] == real["result"]
    assert not row["pit_verified"] and not row["model_eligible"]
    assert "HISTORICAL_PUBLICATION_TIME_NOT_DOCUMENTED" in row["reasons"]
    assert all(s["published_at"] is None for s in row["source_refs"])


@pytest.mark.parametrize("extra", [[], ["--results-sha256", TRUTH_SHA]])
def test_bad_cli_contract_fails_before_import(tmp_path, extra):
    output = tmp_path / "bad"
    result = subprocess.run([sys.executable, "-m", "hbi.cli", "overview", "--date", "2026-10-20",
        "--archive", str(ARCHIVE), "--sha256", SHA, "--results-archive", str(TRUTH),
        "--output", str(output), *extra], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "HISTORICAL_RESULTS_REQUIRE_FUNDAMENTAL_AND_CHECKSUM" in result.stdout
    assert not output.exists()


def test_m3_facts_and_quotes_unchanged_when_truth_attached():
    archive, doc, entry = context()
    archive.data["races"] = [doc]
    before = copy.deepcopy(entry["fundamental_analysis"]["horses"])
    attach_history({"races": [entry]}, archive, HistoricalTruth(TRUTH, TRUTH_SHA))
    for old, new in zip(before, entry["fundamental_analysis"]["horses"], strict=True):
        assert old["facts"] == new["facts"] and old["history"] == new["history"]
        assert old["identity"] == new["identity"]


@pytest.mark.parametrize("time", ["1.29,8", "1:29.8", "P", None])
def test_unsupported_time_formats_are_not_normalized_or_training_features(tmp_path, time):
    def mutate(b):
        s = next(s for s in b["sources"] if s["path"].endswith("/10/completeresults"))
        s["body"]["result"]["results"][3]["kmTime"] = time
    row = link(truth_copy(tmp_path, mutate))
    assert row["result"]["km_time_raw"] == time
    assert "RESULT_CODE_OR_TIME_SEMANTICS_UNRESOLVED" in row["reasons"]
    assert not row["model_eligible"]


@pytest.mark.parametrize("status", ["UNRESOLVED", "CONFLICT"])
def test_target_identity_never_promoted_by_a_name_or_number(status):
    _, doc, entry = context()
    horse = entry["fundamental_analysis"]["horses"][0]
    horse["identity"]["status"] = status
    row = HistoricalTruth(TRUTH, TRUTH_SHA).link(horse, doc["entrants"][0]["past_starts"][4],
                                               entry["fundamental_analysis"]["cutoff"], "2026-10-20")
    assert not row["horse_identity_verified"]
    assert row["result"] is None and not row["authoritative_result_verified"]
    assert not row["model_eligible"]


def test_readiness_serialization_reproducible_across_hash_seeds():
    program = """
import json, runpy
from hbi.historical_truth import HistoricalTruth, attach_history
suite = runpy.run_path('tests/test_historical_truth.py')
archive, doc, entry = suite['context']()
archive.data['races'] = [doc]
report = {'races': [entry]}
attach_history(report, archive, HistoricalTruth(suite['TRUTH'], suite['TRUTH_SHA']))
print(json.dumps(report, ensure_ascii=False))
"""
    outputs = [subprocess.run([sys.executable, '-c', program], cwd=ROOT,
        env={**os.environ, 'PYTHONHASHSEED': seed}, capture_output=True,
        text=True, check=True).stdout for seed in ('1', '2')]
    assert outputs[0] == outputs[1]
