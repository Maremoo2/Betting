"""MVP-008C read-only full-field diagnostic: no tests can confer betting authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hbi.mvp008_decision_audit import audit, main


def _frozen():
    rows = []
    for number, p, odd in [(1, .4, 3.0), (2, .6, 2.5)]:
        rows.append({
            "selection_id": str(number), "start_number": number,
            "horse_name": "A" if number == 1 else "B", "scratched": False,
            "champion_p_win": p, "core004_p_win": p,
            "win_odds": odd, "win_odds_provider": "rikstoto",
            "win_odds_observed_at_utc": "2026-11-03T11:15:49+00:00",
            "win_odds_source_uri":
                "https://www.rikstoto.no/api/game/S1_NR_2026-11-03/betdistribution/winodds/1",
        })
    return {
        "schema": "BET_MVP_001_FROZEN_SHADOW_V1",
        "race": {"race_id": "RIKSTOTO:S1_NR_2026-11-03:1",
                 "start_time_utc": "2026-11-03T11:20:00+00:00"},
        "as_of_utc": "2026-11-03T11:15:54+00:00",
        "report_created_at_utc": "2026-11-03T11:15:55+00:00",
        "run_kind": "PROSPECTIVE_ATTEMPT", "source_archive_is_immutable_read_only": True,
        "source_database_sha256": "0" * 64, "model_status": "MODEL_READY",
        "market_status": "MARKET_READY", "bet_authority": False,
        "active_runners": 2, "field_size": 2, "runners": rows,
    }


def _bytes(report):
    return json.dumps(report, sort_keys=True).encode()


def _attest(model, *, status="PIT_NOT_CERTIFIED", sha=None):
    return _bytes({"schema": "PIT_T4_ATTESTATION_INDEX_V1",
                   "pit_certified_count": int(status == "INDEPENDENT_PIT_CERTIFIED"),
                   "results": [{"race_id": model["race"]["race_id"],
                                "pit_status": status,
                                "model_report_sha256":
                                    sha or hashlib.sha256(_bytes(model)).hexdigest(),
                                "blockers": ["UNVERIFIED_SCRATCH_SOURCE"]}]})


def test_complete_frozen_field_reports_fair_market_and_no_bet():
    model = _frozen()
    result = audit(_bytes(model), _attest(model))
    assert result["active_runners"] == 2
    assert result["market_full_field_verified_by_report"] is True
    assert result["attestation"]["matched"] is True
    assert result["frozen_model_original_sha256"] == hashlib.sha256(_bytes(model)).hexdigest()
    assert result["runners"][0]["champion_fair_odds_theoretical"] == pytest.approx(2.5)
    assert result["runners"][0]["normalized_market_p"] == pytest.approx(5/11)
    assert all(r["decision"] == "BLOCKED" and r["stake_nok"] is None for r in result["runners"])
    assert result["v33_evaluator_called"] is False and result["bet_authority"] is False
    assert "FFQ1_FULL_FIELD_REVIEWS_NOT_SUPPLIED" in result["global_blockers"]


@pytest.mark.parametrize("mutate,expected", [
    (lambda x: x["runners"].pop(), "INCOMPLETE_ACTIVE_FULL_FIELD"),
    (lambda x: x["runners"][1].update(selection_id="1"), "DUPLICATE_OR_COLLIDING_START_IDENTITY"),
    (lambda x: x["runners"][1].update(start_number=1), "DUPLICATE_OR_COLLIDING_START_IDENTITY"),
    (lambda x: x["runners"][1].update(scratched=None), "INVALID_FULL_FIELD_ROW"),
    (lambda x: x["runners"][0].update(win_odds=None), "WIN_FULL_FIELD_ODDS_INCOMPLETE"),
    (lambda x: x["runners"][0].update(win_odds=1), "WIN_FULL_FIELD_ODDS_INCOMPLETE"),
    (lambda x: x["runners"][0].update(champion_p_win=0), "CHAMPION_FULL_FIELD_DISTRIBUTION_INVALID"),
    (lambda x: x["runners"][1].update(
        win_odds_observed_at_utc="2026-11-03T11:17:00+00:00"), "WIN_NOT_SINGLE_TIMESTAMP_FIELD"),
    (lambda x: x.update(as_of_utc="2026-11-03T11:21:00+00:00"), "MODEL_ASOF_OR_FREEZE_INVALID"),
    (lambda x: x.update(source_database_sha256="not-a-sha"),
        "MODEL_SOURCE_DATABASE_HASH_MISSING"),
    (lambda x: x.update(bet_authority=True), "UNEXPECTED_MODEL_BET_AUTHORITY"),
    (lambda x: x.update(run_kind="HISTORICAL_REPLAY"), "PROSPECTIVE_MODEL_REQUIRED"),
])
def test_mutated_or_partial_source_contract_blocks_without_stake(mutate, expected):
    model = _frozen()
    mutate(model)
    result = audit(_bytes(model))
    assert expected in result["global_blockers"]
    assert result["v33_evaluator_called"] is False
    assert result["bet_authority"] is False
    assert all(r["decision"] == "BLOCKED" and r["stake_nok"] is None
               for r in result["runners"])


def test_forged_exact_identity_pit_and_ffq_claims_cannot_authorize():
    model = _frozen()
    model.update(identity_matches={"1": {"status": "EXACT", "provider_id": "a"}},
                 pit_status="INDEPENDENT_PIT_CERTIFIED", qualified=True,
                 p_low=.4, p_mid=.4, p_high=.4,
                 minimum_price=2.0, ffq1_review={"market_free": True})
    result = audit(_bytes(model), _attest(model, status="INDEPENDENT_PIT_CERTIFIED"))
    assert result["attestation"]["claimed_status"] == "INDEPENDENT_PIT_CERTIFIED"
    assert result["attestation"]["independently_certified_by_this_audit"] is False
    assert "PIT_LIVE_PROVENANCE_NOT_AUTHENTICATED_BY_ADAPTER" in result["global_blockers"]
    assert "CROSS_PROVIDER_IDENTITY_ORIGINAL_NOT_ATTESTED" in result["global_blockers"]
    assert not result["v33_evaluator_called"] and not result["bet_authority"]


def test_attestation_hash_mismatch_is_explicitly_blocked():
    model = _frozen()
    result = audit(_bytes(model), _attest(model, sha="f" * 64))
    assert "PIT_ATTESTATION_MODEL_HASH_MISMATCH" in result["global_blockers"]
    assert result["attestation"]["matched"] is False


def test_wrong_schema_rejected():
    model = _frozen()
    model["schema"] = "WRONG"
    with pytest.raises(ValueError, match="FROZEN_RESEARCH_MODEL_SCHEMA_REQUIRED"):
        audit(_bytes(model))


def test_cli_creates_new_diagnostic_and_never_overwrites(tmp_path):
    model = _frozen()
    source = tmp_path / "frozen.json"
    source.write_bytes(_bytes(model))
    attestation = tmp_path / "attestation.json"
    attestation.write_bytes(_attest(model))
    target = tmp_path / "audit.json"
    argv = ["--model-report", str(source), "--attestation-index", str(attestation),
            "--output", str(target)]
    assert main(argv) == 0
    output = json.loads(target.read_text())
    assert output["active_runners"] == 2 and output["bet_authority"] is False
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        main(argv)
    assert target.read_bytes() == original


def test_real_eskilstuna_original_archive():
    """The pinned artifact is supplied in read-only downstream jobs, not guessed."""
    import os
    path = os.environ.get("MVP008_ESKILSTUNA_FROZEN_MODEL")
    if not path:
        pytest.skip("live original artifact not attached to this CI job")
    source = Path(path).read_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "4853ed6bc8c7c7063a5898f4b815e552989d29d9b3121372fd338eb0e63f9916"
    )
    report = audit(source)
    assert report["active_runners"] == 12 and report["runners_in_report"] == 12
    assert report["market_full_field_verified_by_report"] is True
    assert all(row["decision"] == "BLOCKED" for row in report["runners"])
