"""Real M4 regression cohort; native packaging below is a test adapter, not backfill evidence."""
import copy
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from hbi.backfill import feature, run_batch
from hbi.historical_truth import HistoricalTruth
from hbi.storage import SQLiteStore
from rikstoto_crawler.transport import digest

ROOT = Path(__file__).parents[1]
TRUTH = ROOT / "tests/fixtures/rikstoto-historical-truth.json"
SHA = "8086ec016e8e4f9cda7d9ad36abe44df1e09e3c2e387a9ed6c612fa61a0f8953"


def manifest(tmp_path, specs=None):
    doc = {"schema": "HBI_BACKFILL_INPUT_V1", "cohort": "M4_REGRESSION_ONLY",
           "archives": specs if specs is not None else [{"path": str(TRUTH), "format": "M4_TRUTH_REGRESSION_ONLY", "sha256": SHA}]}
    p = tmp_path / "inputs.json"
    p.write_text(json.dumps(doc))
    return p


def dataset(output):
    return [json.loads(line) for line in (output / "dataset.jsonl").read_text().splitlines()]


def test_real_m4_regression_batch_and_label_feature_separation(tmp_path):
    out = tmp_path / "dataset"
    report = run_batch(manifest(tmp_path), out)
    assert report["cohort"] == "M4_REGRESSION_ONLY" and report["terminal_status"] == "M5_PARTIAL"
    assert report["races"] == report["imported_races"] == 39
    assert report["imported_runners"] == 393
    assert report["provenance_payloads"] == 39
    assert sum(m["result_label_rows"] for m in report["per_month"].values()) == 41
    assert sum(m["result_verified_races"] for m in report["per_month"].values()) == 4
    assert set(report["per_month"]) == {"2026-06", "2026-07", "2026-09", "2026-10"}
    assert all(m["feature_pit_verified_runners"] == m["model_eligible"] == 0 for m in report["per_month"].values())
    rows = dataset(out)
    assert all(not r["model_eligible"] for r in rows)
    store = SQLiteStore(out / "research.sqlite")
    for table in ["outcomes", "market_snapshots", "predictions", "decisions"]:
        assert store.count(table) == 0
    for r in rows:
        for h in r["roster"]:
            assert set(h["features"]) == {"driver", "extra_distance_m"}
            assert all(f["published_at"] is None for f in h["features"].values())
        for label in r["labels"]:
            assert label["role"] == "RETROSPECTIVE_LABEL_ONLY"
            # Late acquisition does not reject an otherwise authoritative retrospective label.
            assert label["fetched_at"][:10] > r["date"]
    assert report["dataset_sha256"] == hashlib.sha256((out / "dataset.jsonl").read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        run_batch(manifest(tmp_path), out)


def test_same_m4_cohort_links_equal_the_baseline(tmp_path):
    out = tmp_path / "data"
    run_batch(manifest(tmp_path), out)
    index = {(r["race_id"], l["registration"]): l for r in dataset(out) for l in r["labels"]}
    truth = HistoricalTruth(TRUTH, SHA)
    for race in truth.races:
        rid = f"RIKSTOTO:{race['key']}:{race['number']}"
        active = {r["horseRegistrationNumber"] for r in race["rows"] if r["isScratched"] is False}
        for row in race["result"]["results"]:
            if row["horseRegistrationNumber"] not in active:
                continue
            label = index[(rid, row["horseRegistrationNumber"])]
            assert label["place_raw"] == row["place"] and label["km_time_raw"] == row["kmTime"]


def test_cross_archive_deduplication_preserves_counts_and_provenance(tmp_path):
    spec = {"path": str(TRUTH), "format": "M4_TRUTH_REGRESSION_ONLY", "sha256": SHA}
    report = run_batch(manifest(tmp_path, [spec, spec]), tmp_path / "dedup")
    assert report["races"] == 39 and report["imported_runners"] == 393
    assert sum(m["result_label_rows"] for m in report["per_month"].values()) == 41
    record = next(r for r in dataset(tmp_path / "dedup") if r["authoritative_result_verified"])
    assert len(record["source_refs"]) >= 6


def mutated_spec(tmp_path, mutate):
    b = json.loads(TRUTH.read_bytes())
    mutate(b)
    for s in b["sources"]:
        s["body_sha256"] = digest(s["body"])
    raw = json.dumps(b).encode()
    p = tmp_path / "mutation.json"
    p.write_bytes(raw)
    return {"path": str(p), "format": "M4_TRUTH_REGRESSION_ONLY", "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.mark.parametrize("change", ["id", "name", "duplicate", "incomplete", "partial"])
def test_negative_result_identity_or_field(tmp_path, change):
    def mutate(b):
        s = next(s for s in b["sources"] if s["path"].endswith("/10/completeresults"))
        r = s["body"]["result"]
        if change == "id":
            r["results"][3]["horseRegistrationNumber"] = "OTHER"
        elif change == "name":
            r["results"][3]["horseName"] = "OTHER"
        elif change == "duplicate":
            r["results"].append(copy.deepcopy(r["results"][0]))
        elif change == "incomplete":
            r["isComplete"] = False
        else:
            r["results"].pop()
    report = run_batch(manifest(tmp_path, [mutated_spec(tmp_path, mutate)]), tmp_path / "data")
    row = next(r for r in dataset(tmp_path / "data") if r["race_id"] == "RIKSTOTO:JA_NR_2026-07-03:10")
    assert not row["labels"] and not row["authoritative_result_verified"]
    assert report["model_eligible"] == 0


def test_conflicting_source_revisions_not_first_or_last_wins(tmp_path):
    def mutate(b):
        s = next(s for s in b["sources"] if s["path"].endswith("/10/completeresults"))
        s["body"]["result"]["results"][3]["place"] = 3
    spec = mutated_spec(tmp_path, mutate)
    original = {"path": str(TRUTH), "format": "M4_TRUTH_REGRESSION_ONLY", "sha256": SHA}
    report = run_batch(manifest(tmp_path, [original, spec]), tmp_path / "data")
    row = next(r for r in dataset(tmp_path / "data") if r["race_id"] == "RIKSTOTO:JA_NR_2026-07-03:10")
    assert row["status"] == "CONFLICT" and row["labels"] == []
    assert report["conflicting_source_paths"] and report["conflicting_sources"]


def test_empty_backfill_is_not_a_success(tmp_path):
    report = run_batch(manifest(tmp_path, []), tmp_path / "empty")
    assert report["terminal_status"] == "M5_BLOCKED" and report["imported_races"] == 0
    assert dataset(tmp_path / "empty") == []


@pytest.mark.parametrize("observed,status", [("2026-07-03T10:00:00+00:00", "PIT_VERIFIED"),
                                             ("2026-10-21T10:00:00+00:00", "UNRESOLVED"),
                                             ("2026-07-03T18:00:00+00:00", "UNRESOLVED")])
def test_feature_availability_is_not_result_label_fetch_time(observed, status):
    source = {"fetched_at": observed, "published_at": "2015-01-01T00:00:00Z",
              "url": "https://www.rikstoto.no/api/racedays/JA_NR_2026-07-03/starts", "body_sha256": "test"}
    f = feature("driver", source, "2026-07-03T18:00:00+00:00")
    assert f["status"] == status and f["published_at"] is None


def native_archive(tmp_path):
    """Test packaging of genuine M4 values into the documented native cache shape.

    This is not an original monthly backfill archive and never demonstrates M5 acceptance.
    """
    b = json.loads(TRUTH.read_bytes())
    path = tmp_path / "native-adapter-test.zip"
    with zipfile.ZipFile(path, "w") as z:
        for i, s in enumerate(b["sources"]):
            if s["path"].endswith("/list"):
                # Test-only native census shape, with original authoritative keys/metadata.
                meetings = [{**m, "raceDayKey": m["raceDay"]} for g in s["body"]["result"] for m in g["raceDays"]]
                day = s["path"].split("/")[-2]
                s = copy.deepcopy(s)
                s["path"] = f"/racedays/dates/{day}/{day}"
                s["url"] = "https://www.rikstoto.no/api" + s["path"]
                s["body"]["result"] = meetings
                s["body_sha256"] = digest(s["body"])
            part = "raw-results" if s["path"].endswith("completeresults") else "raw-markets"
            z.writestr(f"month/{part}/{i}.json", json.dumps(s))
    return {"path": str(path), "format": "CRAWLER_NATIVE_ZIP", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_native_cache_adapter_contract_without_new_crawling(tmp_path):
    spec = native_archive(tmp_path)
    report = run_batch(manifest(tmp_path, [spec]), tmp_path / "native")
    assert report["races"] == 39 and sum(m["result_label_rows"] for m in report["per_month"].values()) == 41
    assert report["terminal_status"] == "M5_PARTIAL"  # Test adapter is not backfill evidence.


def test_corrupt_checksum_rejected_before_db(tmp_path):
    spec = {"path": str(TRUTH), "format": "M4_TRUTH_REGRESSION_ONLY", "sha256": "0" * 64}
    with pytest.raises(ValueError, match="BACKFILL_ARCHIVE_SHA256_MISMATCH"):
        run_batch(manifest(tmp_path, [spec]), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_cross_race_same_registration_conflicting_names_is_quarantined(tmp_path):
    def mutate(b):
        starts = next(s for s in b["sources"] if s["path"] == "/racedays/JA_NR_2026-07-03/starts")
        target = next(r for r in starts["body"]["result"]["10"] if r["horseName"].lower() == "mio nova")
        target["horseName"] = "OTHER NAME"
        results = next(s for s in b["sources"] if s["path"].endswith("/10/completeresults"))
        next(r for r in results["body"]["result"]["results"] if r["horseRegistrationNumber"] == target["horseRegistrationNumber"])["horseName"] = "OTHER NAME"
    run_batch(manifest(tmp_path, [mutated_spec(tmp_path, mutate)]), tmp_path / "data")
    records = dataset(tmp_path / "data")
    related = [r for r in records if any(h["registration_observed"] == "578001020160396" for h in r["roster"])]
    assert len(related) >= 2 and all(r["status"] == "CONFLICT" and not r["labels"] for r in related)
    assert all("CROSS_ARCHIVE_HORSE_IDENTITY_NAME_CONFLICT" in r["reasons"] for r in related)


def test_inventory_conflicting_revisions_cannot_drop_or_accept_races(tmp_path):
    def mutate(b):
        source = next(s for s in b["sources"] if s["path"].endswith("2026-07-03/list"))
        m = next(m for m in source["body"]["result"][0]["raceDays"] if m["raceDay"] == "JA_NR_2026-07-03")
        m["races"][0]["startTime"] = "2026-07-03T10:00:00"
    changed = mutated_spec(tmp_path, mutate)
    original = {"path": str(TRUTH), "format": "M4_TRUTH_REGRESSION_ONLY", "sha256": SHA}
    run_batch(manifest(tmp_path, [original, changed]), tmp_path / "data")
    rows = [r for r in dataset(tmp_path / "data") if r["month"] == "2026-07"]
    assert len(rows) == 13 and all(r["status"] == "CONFLICT" and not r["imported"] for r in rows)


def test_native_pre_freeze_and_post_binding_are_not_trusted_blindly(tmp_path):
    spec = native_archive(tmp_path)
    with zipfile.ZipFile(spec["path"], "a") as z:
        z.writestr("month/market-days/2026-07-03.json", json.dumps({"stage": "MARKET_ONLY", "races": [], "sha256": "wrong"}))
    spec["sha256"] = hashlib.sha256(Path(spec["path"]).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="BACKFILL_PRE_FREEZE_MISMATCH"):
        run_batch(manifest(tmp_path, [spec]), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("case", ["post_binding", "unsafe_path", "market_only"])
def test_native_insufficient_or_unsafe_package_rejected(tmp_path, case):
    p = tmp_path / "bad.zip"
    with zipfile.ZipFile(p, "w") as z:
        if case == "unsafe_path":
            z.writestr("../escape.json", "{}")
        elif case == "post_binding":
            z.writestr("result-days/2020-01-01.json", json.dumps({"stage": "RESULTS", "pre_sha256": "missing"}))
        else:
            z.writestr("MANIFEST.json", json.dumps({"stage": "MARKET_ONLY"}))
    spec = {"path": str(p), "format": "CRAWLER_NATIVE_ZIP", "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    with pytest.raises(ValueError):
        run_batch(manifest(tmp_path, [spec]), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_reproducible_dataset_from_same_manifest(tmp_path):
    inputs = manifest(tmp_path)
    first = run_batch(inputs, tmp_path / "one")
    second = run_batch(inputs, tmp_path / "two")
    assert first == second
    assert (tmp_path / "one/dataset.jsonl").read_bytes() == (tmp_path / "two/dataset.jsonl").read_bytes()


def test_empty_batch_cli_exits_blocked_not_green_noop(tmp_path):
    inputs = manifest(tmp_path, [])
    result = subprocess.run([sys.executable, '-m', 'hbi.cli', 'backfill', '--manifest', str(inputs),
        '--output', str(tmp_path / 'blocked')], capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert json.loads(result.stdout)['terminal_status'] == 'M5_BLOCKED'


def test_native_composite_meeting_cannot_be_imported_as_independent(tmp_path):
    from hbi.backfill import make_record
    original = json.loads(TRUTH.read_bytes())['sources']
    # Adapt genuine envelopes for a deliberately invalid composite metadata case.
    sources = {s['path']: {'source': s, 'refs': []} for s in original}
    meeting = next(m for s in original if s['path'].endswith('2026-07-03/list')
                   for g in s['body']['result'] for m in g['raceDays'] if m['raceDay'] == 'JA_NR_2026-07-03')
    meeting['isMultiTrack'] = True
    meta = next(r for r in meeting['races'] if r['raceNumber'] == 10)
    row = make_record('JA_NR_2026-07-03', meta, meeting, sources, set())
    assert not row['full_field_identity_verified'] and not row['labels']
    assert 'COMPOSITE_MEETING_NOT_INDEPENDENT' in row['reasons']
