"""DEV-009 negative regressions; synthetic official result fixtures never grant PIT/BET."""
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from hbi.prospective_outcome_scorecard import evaluate_archive
from hbi.providers.rikstoto import OriginalBytesFetchResult


RID = "RIKSTOTO:S1_NR_2026-11-03:8"
START = "2026-11-03T13:00:00+00:00"


class FakeOfficial:
    def __init__(self, complete=None, raceday=None, *, failed=None, observation=None):
        self.complete = complete or {
            "success": True, "result": {
                "isComplete": True,
                "results": [
                    {"startNumber": 1, "place": 1, "horseName": "Alpha"},
                    {"startNumber": 2, "place": 2, "horseName": "Beta"},
                ],
            },
        }
        self.raceday = raceday or {
            "success": True, "result": {
                "finalOdds": {"winOdds": {"8": {"1": {
                    "payoutStatus": "Dividends", "odds": 2.4,
                }}}},
            },
        }
        self.failed = failed
        self.observation = observation or datetime(2026, 11, 3, 13, 20, tzinfo=UTC)
        self.calls = []

    def _fetch(self, path, *, retain_raw_body=False):
        self.calls.append((path, retain_raw_body))
        role = "complete" if "completeresults" in path else "raceday"
        data = self.complete if role == "complete" else self.raceday
        raw = json.dumps(data, sort_keys=True).encode("utf-8")
        return OriginalBytesFetchResult(
            url="https://www.rikstoto.no/api" + path, payload=data,
            success=self.failed != role,
            status_code=503 if self.failed == role else 200,
            latency_ms=1, error="HTTP 503" if self.failed == role else None,
            raw_body=raw, response_body_sha256=hashlib.sha256(raw).hexdigest(),
            response_completed_at=self.observation,
            http_etag='"source-revision-1"',
        )


def archive(tmp_path, *, no_core=False, second=False, race_id=RID):
    root = tmp_path / "models"
    root.mkdir()
    rows = []
    for i in range(1, (3 if second else 2)):
        sub = root / f"{i:011d}"
        sub.mkdir()
        report_dir = sub / "race-001"
        report_dir.mkdir()
        rid = race_id if i == 1 else "RIKSTOTO:S1_NR_2026-11-03:9"
        model = {
            "schema": "BET_MVP_001_FROZEN_SHADOW_V1",
            "run_kind": "PROSPECTIVE_ATTEMPT", "bet_authority": False,
            "model_status": "MODEL_READY", "market_status": "MARKET_READY",
            "source_archive_is_immutable_read_only": True,
            "source_database_sha256": "a" * 64,
            "as_of_utc": "2026-11-03T12:54:00+00:00",
            "report_created_at_utc": "2026-11-03T12:55:00+00:00",
            "race": {"race_id": rid, "race_no": 8 if i == 1 else 9,
                     "start_time_utc": START},
            "active_runners": 2, "field_size": 2,
            "runners": [
                {"selection_id": "1", "start_number": 1, "horse_name": "Alpha",
                 "scratched": False, "champion_p_win": .4, "core004_p_win": .5,
                 "win_odds": 2.5, "win_odds_provider": "rikstoto",
                 "win_odds_observed_at_utc": "2026-11-03T12:53:00+00:00"},
                {"selection_id": "2", "start_number": 2, "horse_name": "Beta",
                 "scratched": False, "champion_p_win": .6,
                 "core004_p_win": None if no_core else .5,
                 "win_odds": 1.7, "win_odds_provider": "rikstoto",
                 "win_odds_observed_at_utc": "2026-11-03T12:53:00+00:00"},
            ],
        }
        raw = json.dumps(model, sort_keys=True).encode()
        (report_dir / "shadow.json").write_bytes(raw)
        index = {
            "schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1",
            "bet_authority": False,
            "processed": [{"race_id": rid, "directory": "bet-mvp-shadow/race-001",
                           "report_sha256": hashlib.sha256(raw).hexdigest()}],
        }
        (sub / "cohort-index.json").write_text(json.dumps(index))
        rows.append((sub, model))
    return root, rows


def run(tmp_path, **kwargs):
    root, rows = archive(tmp_path, **{k: v for k, v in kwargs.items()
                                     if k in ("no_core", "second", "race_id")})
    official = kwargs.get("official") or FakeOfficial()
    result = evaluate_archive(
        models_root=root, output_dir=tmp_path / "scorecard",
        fetch_official=kwargs.get("fetch_official", True), client=official,
        now=kwargs.get("now", datetime(2026, 11, 3, 14, tzinfo=UTC)),
        attestation_index=kwargs.get("attestation_index"),
    )
    return root, rows, official, result


def test_valid_synthetic_original_pair_no_pit_no_bet(tmp_path):
    root, rows, official, result = run(tmp_path)
    assert result["counts"]["paired_champion_core004"] == 1
    assert result["counts"]["pit_certified_paired"] == 0
    assert result["counts"]["official_results_verified"] == 1
    assert result["status"] == "EVALUABLE_RESEARCH_ONLY"
    assert result["bet_authority"] is False and result["no_model_promotion"] is True
    assert result["calibration"]["bins"] is None
    rec = result["records"][0]
    assert rec["cohort"] == "PROSPECTIVE_NOT_PIT_CERTIFIED"
    assert rec["winner_selection_id"] == "1"
    assert rec["winner_identity_scope"].startswith("OFFICIAL_IN_RACE")
    assert rec["score"]["core004_log_loss"] > 0
    assert rec["score"]["champion_log_loss"] > 0
    assert len(rec["original_result_receipts"]) == 2
    assert all(r["raw_sha256"] and r["observed_at_utc"] and r["http_etag"]
               for r in rec["original_result_receipts"])
    for receipt in rec["original_result_receipts"]:
        from pathlib import Path
        raw = Path(receipt["raw_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == receipt["raw_sha256"]
    assert all(r[1] is True for r in official.calls)
    assert (root / "00000000001/race-001/shadow.json").read_bytes() == json.dumps(
        rows[0][1], sort_keys=True
    ).encode()


def test_missing_results_not_evaluable(tmp_path):
    _, _, _, result = run(tmp_path, official=FakeOfficial(failed="complete"))
    assert result["counts"]["paired_champion_core004"] == 0
    assert "OFFICIAL_GET_OR_RAW_HASH_FAILED" in result["records"][0]["reasons"]
    assert result["bet_authority"] is False


def test_incomplete_official_field(tmp_path):
    complete = {"success": True, "result": {
        "isComplete": True, "results": [{"startNumber": 1, "place": 1}],
    }}
    _, _, _, result = run(tmp_path, official=FakeOfficial(complete=complete))
    assert "OFFICIAL_ACTIVE_FIELD_MISMATCH" in result["records"][0]["reasons"]
    assert result["metrics"] is None


def test_incomplete_official_finish(tmp_path):
    complete = {"success": True, "result": {"isComplete": False, "results": []}}
    _, _, _, result = run(tmp_path, official=FakeOfficial(complete=complete))
    assert "OFFICIAL_FINISH_NOT_COMPLETE" in result["records"][0]["reasons"]


def test_wrong_physical_race_id(tmp_path):
    _, _, _, result = run(tmp_path, race_id="WRONG:ID:8")
    assert "PHYSICAL_RACE_ID_INVALID" in result["records"][0]["reasons"]
    assert result["counts"]["official_results_verified"] == 0


def test_winner_name_or_dividend_disagrees(tmp_path):
    complete = {"success": True, "result": {"isComplete": True, "results": [
        {"startNumber": 1, "place": 1, "horseName": "Not Alpha"},
        {"startNumber": 2, "place": 2, "horseName": "Beta"},
    ]}}
    _, _, _, result = run(tmp_path, official=FakeOfficial(complete=complete))
    assert "OFFICIAL_FROZEN_RUNNER_NAME_DISAGREES" in result["records"][0]["reasons"]
    day = {"success": True, "result": {"finalOdds": {"winOdds": {
        "8": {"2": {"payoutStatus": "Dividends", "odds": 4.5}},
    }}}}
    alt = tmp_path / "alt"
    alt.mkdir()
    _, _, _, second = run(alt, official=FakeOfficial(raceday=day))
    assert "OFFICIAL_WINNER_DIVIDEND_MISSING" in second["records"][0]["reasons"]


def test_wrong_model_original_sha(tmp_path):
    root, _ = archive(tmp_path)
    index_path = root / "00000000001/cohort-index.json"
    ix = json.loads(index_path.read_text())
    ix["processed"][0]["report_sha256"] = "f" * 64
    index_path.write_text(json.dumps(ix))
    report = evaluate_archive(models_root=root, output_dir=tmp_path / "out",
                              fetch_official=False)
    assert report["counts"]["physical_races"] == 0
    assert report["archive_errors"][0]["reason"] == "FROZEN_MODEL_SHA256_MISMATCH"
    assert report["bet_authority"] is False


def test_post_race_outcome_does_not_modify_model(tmp_path):
    root, _ = archive(tmp_path)
    original_path = root / "00000000001/race-001/shadow.json"
    before = hashlib.sha256(original_path.read_bytes()).hexdigest()
    result = evaluate_archive(models_root=root, output_dir=tmp_path / "out",
                              fetch_official=True, client=FakeOfficial(
                                  observation=datetime(2026, 11, 3, 13, 59, tzinfo=UTC)),
                              now=datetime(2026, 11, 3, 14, tzinfo=UTC))
    assert result["records"][0]["status"] == "EVALUABLE_RESEARCH_ONLY"
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == before


def test_official_response_before_start_rejected(tmp_path):
    _, _, _, result = run(tmp_path, official=FakeOfficial(
        observation=datetime(2026, 11, 3, 12, 59, tzinfo=UTC)))
    assert "OFFICIAL_RESULT_OBSERVED_BEFORE_START" in result["records"][0]["reasons"]
    assert result["counts"]["official_results_verified"] == 0


def test_no_core004_and_no_score(tmp_path):
    _, _, official, result = run(tmp_path, no_core=True)
    assert "CORE004_FULL_FIELD_INVALID" in result["records"][0]["reasons"]
    assert result["metrics"] is None and official.calls == []


def test_duplicate_physical_race_only_counted_once(tmp_path):
    root, _ = archive(tmp_path)
    import shutil
    shutil.copytree(root / "00000000001", root / "00000000003")
    report = evaluate_archive(models_root=root, output_dir=tmp_path / "out",
                              fetch_official=True, client=FakeOfficial(),
                              now=datetime(2026, 11, 3, 14, tzinfo=UTC))
    assert report["counts"]["physical_races"] == 1
    assert report["counts"]["paired_champion_core004"] == 1


def test_pit_status_not_inferred_from_model_flag(tmp_path):
    root, rows = archive(tmp_path)
    rows[0][1]["pit_status"] = "INDEPENDENT_PIT_CERTIFIED"
    model_path = root / "00000000001/race-001/shadow.json"
    raw = json.dumps(rows[0][1], sort_keys=True).encode()
    model_path.write_bytes(raw)
    ix = root / "00000000001/cohort-index.json"
    data = json.loads(ix.read_text())
    data["processed"][0]["report_sha256"] = hashlib.sha256(raw).hexdigest()
    ix.write_text(json.dumps(data))
    report = evaluate_archive(models_root=root, output_dir=tmp_path / "out",
                              fetch_official=True, client=FakeOfficial(),
                              now=datetime(2026, 11, 3, 14, tzinfo=UTC))
    assert report["counts"]["pit_certified_paired"] == 0
    assert report["bet_authority"] is False


def test_new_output_cannot_overwrite(tmp_path):
    root, _ = archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileExistsError):
        evaluate_archive(models_root=root, output_dir=out)


def test_real_eskilstuna_frozen_original_if_supplied(tmp_path):
    import os
    root = os.getenv("DEV009_AUTHENTIC_ARCHIVE_ROOT")
    if not root:
        pytest.skip("Separate authenticated frozen GitHub model artifact not mounted")
    result = evaluate_archive(
        models_root=__import__("pathlib").Path(root),
        output_dir=tmp_path / "authentic",
        fetch_official=False,
    )
    assert result["counts"]["physical_races"] >= 1
    assert result["counts"]["paired_champion_core004"] == 0
    assert result["bet_authority"] is False
    matching = [r for r in result["records"] if r["race_id"]
                == "RIKSTOTO:S1_NR_2026-11-03:8"]
    assert len(matching) == 1
    assert matching[0]["active_runners"] == 12
    assert matching[0]["complete_active_field"] is True
    assert matching[0]["source_model_original_sha256"] == (
        "f04dd8f19254764114739009383371e3367c445c917c8fac5b08cf085e814a6d"
    )
