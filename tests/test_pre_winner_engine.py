import json
import zipfile
from copy import deepcopy
from hashlib import sha256

import pytest

from betting.v33 import POLICY_HASH, normalize
from pre_winner.engine import load_input, process, run
from pre_winner.signals import classify


def race(day="2026-01-01", skew=60):
    from datetime import datetime, timedelta
    stamp = f"{day}T12:00:00+00:00"
    colstamp = (datetime.fromisoformat(stamp) - timedelta(seconds=skew)).isoformat()
    key = f"BJ_NR_{day}"
    pool = f"{key}#V4#1"
    runners = {str(n): {"start_number": n, "horse_name": f"Horse {n}", "horse_id": f"ID-{n}",
        "horse_id_stable": True, "scratched": False, "win_odds": odds,
        "place_min": 1.5, "place_max": 2, "win_updated_at": stamp, "place_updated_at": stamp}
        for n, odds in [(1, 2), (2, 4), (3, 10)]}
    shares = {"1": 80, "2": 15, "3": 5}
    return {"schema_version": "RIKSTOTO_PRE_WINNER_ARCHIVE_V2", "policy_hash": POLICY_HASH,
        "race_id": f"RIKSTOTO:{key}:1", "raceday_key": key, "race_number": 1,
        "date": day, "race_start": stamp, "country": "NO", "track": "Bjerke",
        "active_field": list(runners), "runners": runners,
        "pWIN": normalize({n:r["win_odds"] for n,r in runners.items()}, runners, odds=True),
        "turnover": {"V": {"nok": 5000}, "P": {"nok": 4000}},
        "collective_turnover": {pool: {"nok": 10000}},
        "data_quality_flags": [], "snapshot_kind": "HISTORICAL_TERMINAL_ARCHIVE",
        "collective": {pool: {"product": "V4", "leg": 1, "pool_start_race": 1,
            "pool_race_numbers": [1,2,3,4], "raw_shares": shares,
            "pCOL": normalize(shares, runners), "updated_at": colstamp,
            "win_skew_seconds": skew, "contemporaneous": skew <= 60,
            "source": {"url": "https://www.rikstoto.no/api/test", "body_sha256": "a"*64,
                       "fetched_at": stamp}}}}


@pytest.mark.parametrize("pcol,pwin,expected", [
    (.225,.15,"EXTREME_POS"), (.25,.20,"STRONG_POS"), (.175,.15,"MOD_POS"),
    (.10,.20,"EXTREME_NEG"), (.15,.20,"STRONG_NEG"), (.14,.165,"MOD_NEG"),
    (.325,.30,"NONE"), (.01,.02,"NONE"), (.20,.20,"NONE"),
])
def test_frozen_exclusive_and_thresholds(pcol,pwin,expected):
    assert classify(pcol,pwin)["signal"] == expected


@pytest.mark.parametrize("skew,expected", [(60,"PRIMARY"),(61,"SECONDARY"),
    (300,"SECONDARY"),(301,"EXCLUDE_DIAGNOSTIC")])
def test_timing_boundaries(skew,expected):
    rows,qc = process([race(skew=skew)])
    assert qc["accepted_races"] == 1
    assert {r["time_class"] for r in rows} == {expected}


def test_batch_invariance_and_duplicates():
    first = race()
    alone,_ = process([first])
    bulk,qc = process([race("2026-01-08"),first,deepcopy(first),race("2026-01-15")])
    assert [r for r in bulk if r["week"] == "2026-W01"] == alone
    assert qc["duplicate_records_skipped"] == 1
    reordered = deepcopy(first)
    reordered["active_field"].reverse()
    reordered["runners"] = dict(reversed(list(reordered["runners"].items())))
    assert process([reordered])[0] == alone


def test_conflict_quarantines_whole_race():
    original = race()
    conflicting = deepcopy(original)
    conflicting["track"] = "Other"
    rows,qc = process([original,conflicting])
    assert rows == [] and qc["conflicting_races"] == [original["race_id"]]


@pytest.mark.parametrize("change", [
    lambda r: r["runners"]["1"].update(win_odds=float("nan")),
    lambda r: r["runners"]["1"].update(scratched=None),
    lambda r: r["runners"]["1"].update(horse_id="ID-2"),
    lambda r: r["collective"][next(iter(r["collective"]))]["raw_shares"].pop("1"),
    lambda r: r["collective"][next(iter(r["collective"]))].update(win_skew_seconds=999),
])
def test_invalid_full_field_fails_closed(change):
    value = race()
    change(value)
    rows,qc = process([value])
    assert not rows and value["race_id"] in qc["rejected_races"]


def add_pool(row,product="V65",skew=None):
    old = next(iter(row["collective"]))
    new = row["raceday_key"] + f"#{product}#1"
    row["collective"][new] = deepcopy(row["collective"][old])
    row["collective"][new]["product"] = product
    row["collective_turnover"][new] = {"nok": 20000}
    if skew is not None:
        other = race(row["date"],skew)
        for name in ("updated_at","win_skew_seconds","contemporaneous"):
            row["collective"][new][name] = next(iter(other["collective"].values()))[name]


def test_dual_pool_same_horse_and_cohort_only():
    row = race()
    add_pool(row)
    obs,_ = process([row])
    first = [r for r in obs if r["horse_no"] == "1"]
    assert all(r["DUAL_POOL_STRONG"] and r["COL_CONSENSUS"] == "POSITIVE" for r in first)
    row = race()
    add_pool(row,skew=301)
    obs,_ = process([row])
    assert not any(r["DUAL_POOL_STRONG"] for r in obs)


def make_zip(path,row,stage="PRE"):
    raw = (json.dumps(row)+"\n").encode()
    hashed = sha256(raw).hexdigest()
    with zipfile.ZipFile(path,"w") as archive:
        archive.writestr("pre.jsonl",raw)
        archive.writestr("MANIFEST.json",json.dumps({"stage":stage,
            "weekly_PRE_sha256":hashed,"files_sha256":{"pre.jsonl":hashed}}))


def test_freeze_no_post_reads_and_no_outcome_outputs(tmp_path):
    source = tmp_path / "PRE.zip"
    value = race()
    value["winner"] = "SECRET_POST_VALUE"
    make_zip(source,value)
    (tmp_path / "post.jsonl").write_text("invalid secret POST")
    original_hash = sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "frozen"
    qc = run([source],output)
    assert not qc["post_read"]
    assert "SECRET_POST_VALUE" not in (output/"PRE_MASTER.csv").read_text()
    assert sha256(source.read_bytes()).hexdigest() == original_hash
    manifest = json.loads((output/"MANIFEST.json").read_text())
    for name, hashed in manifest["files_sha256"].items():
        assert sha256((output/name).read_bytes()).hexdigest() == hashed
    with pytest.raises(ValueError,match="immutable"):
        run([source],output)
    make_zip(source,value,stage="POST")
    with pytest.raises(ValueError,match="POST"):
        load_input(source)


def test_corrupt_hash_rejected(tmp_path):
    path = tmp_path/"PRE.zip"
    make_zip(path,race())
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("pre.jsonl")
        manifest = json.loads(archive.read("MANIFEST.json"))
    manifest["weekly_PRE_sha256"] = "0"*64
    with zipfile.ZipFile(path,"w") as archive:
        archive.writestr("pre.jsonl",raw)
        archive.writestr("MANIFEST.json",json.dumps(manifest))
    with pytest.raises(ValueError,match="hash"):
        load_input(path)


def test_scratched_runner_excluded_from_both_normalizations():
    row = race()
    row["runners"]["3"]["scratched"] = True
    row["active_field"] = ["1", "2"]
    row["pWIN"] = normalize({n: row["runners"][n]["win_odds"] for n in row["active_field"]},
                             row["active_field"], odds=True)
    pool = next(iter(row["collective"].values()))
    pool["raw_shares"].pop("3")
    pool["pCOL"] = normalize(pool["raw_shares"], row["active_field"])
    obs, qc = process([row])
    assert {r["horse_no"] for r in obs} == {"1", "2"}
    assert sum(r["pWIN"] for r in obs) == pytest.approx(1)
    assert sum(r["pCOL"] for r in obs) == pytest.approx(1)
    assert qc["excluded_scratched_runners"] == 1
