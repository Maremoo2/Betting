"""MVP009 workflow-side original-only diagnostic publishing tests."""
import hashlib
import json
from pathlib import Path

import pytest

from hbi.mvp009_auto_decision_audit import generate, main


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _frozen(race_id="RIKSTOTO:S1_NR_2026-11-03:1"):
    rows = [{"selection_id": str(i), "start_number": i, "horse_name": f"Horse {i}",
             "scratched": False, "champion_p_win": p, "core004_p_win": p,
             "win_odds": odd, "win_odds_provider": "rikstoto",
             "win_odds_observed_at_utc": "2026-11-03T11:15:49+00:00",
             "win_odds_source_uri": "https://www.rikstoto.no/api/game/winodds"}
            for i, p, odd in [(1, .4, 3.0), (2, .6, 2.5)]]
    return {"schema": "BET_MVP_001_FROZEN_SHADOW_V1", "run_kind": "PROSPECTIVE_ATTEMPT",
            "race": {"race_id": race_id, "start_time_utc": "2026-11-03T11:20:00+00:00"},
            "as_of_utc": "2026-11-03T11:15:54+00:00",
            "report_created_at_utc": "2026-11-03T11:15:55+00:00",
            "source_archive_is_immutable_read_only": True,
            "source_database_sha256": "0" * 64,
            "model_status": "MODEL_READY", "market_status": "MARKET_READY",
            "bet_authority": False, "active_runners": 2, "field_size": 2, "runners": rows}


def fixture(tmp_path, *, count=1):
    root = tmp_path / "bet-mvp-shadow"
    root.mkdir()
    rows = []
    for i in range(1, count + 1):
        race_id = f"RIKSTOTO:S1_NR_2026-11-03:{i}"
        folder = root / f"race-{i:03d}"
        folder.mkdir()
        raw = (json.dumps(_frozen(race_id), sort_keys=True) + "\n").encode()
        (folder / "shadow.json").write_bytes(raw)
        rows.append({"race_id": race_id, "directory": f"bet-mvp-shadow/race-{i:03d}",
                     "report_sha256": _sha(raw)})
    source = root / "cohort-index.json"
    source.write_text(json.dumps({"schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1",
                                  "processed": rows, "bet_authority": False}))
    att = tmp_path / "pit003a-attestations" / "index.json"
    att.parent.mkdir()
    att.write_text(json.dumps({"schema": "PIT_T4_ATTESTATION_INDEX_V1",
                               "results": [{"race_id": r["race_id"],
                                            "pit_status": "PIT_NOT_CERTIFIED",
                                            "model_report_sha256": r["report_sha256"],
                                            "blockers": ["UNVERIFIED_SCRATCH_SOURCE"]}
                                           for r in rows[:1]]}))
    return source, att


def test_live_contract_one_model_attestation_and_readonly_inputs(tmp_path):
    cohort, att = fixture(tmp_path)
    before = {p: _sha(p.read_bytes()) for p in (cohort, att, cohort.parent / "race-001/shadow.json")}
    result = generate(cohort_index=cohort, attestation_index=att, output_dir=tmp_path / "out")
    assert result["model_reports_expected"] == 1
    assert result["model_reports_diagnosed"] == 1
    assert result["errors"] == []
    row = result["records"][0]
    assert row["attestation_matched"] is True
    assert row["active"] == 2 and row["market_full_field"] is True
    report = json.loads((tmp_path / "out" / row["diagnostic_path"]).read_text())
    assert {r["decision"] for r in report["runners"]} == {"BLOCKED"}
    assert "UNVERIFIED_SCRATCH_SOURCE" in report["global_blockers"]
    assert report["v33_evaluator_called"] is False
    assert report["bet_authority"] is False
    assert all(r["stake_nok"] is None for r in report["runners"])
    assert before == {p: _sha(p.read_bytes()) for p in before}
    assert result["attestation_index_original_sha256"] == _sha(att.read_bytes())


def test_multiple_models_includes_unmatched_receipt(tmp_path):
    cohort, att = fixture(tmp_path, count=2)
    result = generate(cohort_index=cohort, attestation_index=att, output_dir=tmp_path / "out")
    assert result["model_reports_diagnosed"] == 2
    assert [r["attestation_matched"] for r in result["records"]] == [True, False]
    assert all(r["status"] == "BLOCKED" for r in result["records"])


def test_missing_attestation_emits_diagnostic_but_cannot_promote(tmp_path):
    cohort, att = fixture(tmp_path)
    att.unlink()
    result = generate(cohort_index=cohort, attestation_index=att, output_dir=tmp_path / "out")
    assert result["model_reports_diagnosed"] == 1
    assert result["errors"][0]["reason"] == "PIT_ATTESTATION_INDEX_UNAVAILABLE_OR_INVALID"
    report = json.loads((tmp_path / "out/race-001.json").read_text())
    assert "PIT_ATTESTATION_MISSING" in report["attestation"]["blockers"]
    assert report["bet_authority"] is False


@pytest.mark.parametrize("mutate", ["wrong_hash", "wrong_race", "unsafe_path", "duplicate"])
def test_wrong_original_cohort_never_promotes(tmp_path, mutate):
    cohort, att = fixture(tmp_path)
    ix = json.loads(cohort.read_text())
    if mutate == "wrong_hash":
        ix["processed"][0]["report_sha256"] = "f" * 64
    elif mutate == "wrong_race":
        ix["processed"][0]["race_id"] = "RIKSTOTO:S1_NR_2026-11-03:9"
    elif mutate == "unsafe_path":
        ix["processed"][0]["directory"] = "../../outside/race-001"
    else:
        ix["processed"].append(ix["processed"][0])
    cohort.write_text(json.dumps(ix))
    result = generate(cohort_index=cohort, attestation_index=att, output_dir=tmp_path / "out")
    assert result["errors"]
    assert result["model_reports_diagnosed"] < result["model_reports_expected"] or mutate == "duplicate"
    assert result["bet_authority"] is False


def test_no_cohort_and_no_overwrite(tmp_path):
    cohort = tmp_path / "bet-mvp-shadow/cohort-index.json"
    att = tmp_path / "pit003a-attestations/index.json"
    output = tmp_path / "out"
    result = generate(cohort_index=cohort, attestation_index=att, output_dir=output)
    assert result["model_reports_expected"] == 0 and result["model_reports_diagnosed"] == 0
    assert len(result["errors"]) == 2
    with pytest.raises(FileExistsError):
        generate(cohort_index=cohort, attestation_index=att, output_dir=output)


def test_cli_summary_and_zero_bet(tmp_path, capsys):
    cohort, att = fixture(tmp_path)
    main(["--cohort-index", str(cohort), "--attestation-index", str(att),
          "--output-dir", str(tmp_path / "out")])
    summary = json.loads(capsys.readouterr().out)
    assert summary["diagnosed"] == 1 and summary["bet_authority"] is False


def test_real_eskilstuna_artifacts_when_available(tmp_path):
    import os
    root = os.environ.get("MVP009_ESKILSTUNA_ARCHIVE_ROOT")
    if root is None:
        pytest.skip("No separate authenticated archival artifact mounted")
    path = Path(root)
    cohort = path / "bet-mvp-shadow/cohort-index.json"
    att = path / "pit003a-attestations/index.json"
    result = generate(cohort_index=cohort, attestation_index=att, output_dir=tmp_path / "out")
    assert result["errors"] == []
    assert result["model_reports_expected"] == 2
    assert result["model_reports_diagnosed"] == 2
    eskilstuna = [r for r in result["records"] if r["race_id"] == "RIKSTOTO:S1_NR_2026-11-03:1"]
    assert len(eskilstuna) == 1 and eskilstuna[0]["active"] == 12
    assert eskilstuna[0]["attestation_matched"] is True
    assert eskilstuna[0]["frozen_model_original_sha256"] == "4853ed6bc8c7c7063a5898f4b815e552989d29d9b3121372fd338eb0e63f9916"
    assert all(r["bet_authority"] is False for r in result["records"])
