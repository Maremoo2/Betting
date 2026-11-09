import hashlib

from hbi.data009_prospective_bridge import audit


def sample(tmp_path):
    race_id = "R:2026-11-09:1"
    roles = {}
    for role in ("PROGRAM", "ROSTER", "WIN", "MODEL", "RESULT", "SETTLEMENT"):
        p = tmp_path / (role + ".json")
        raw = role.encode()
        p.write_bytes(raw)
        roles[role] = {
            "race_id": race_id,
            "observed_at": (
                "2026-11-09T20:15:00Z"
                if role in ("RESULT", "SETTLEMENT")
                else "2026-11-09T19:55:00Z"
            ),
            "source_hash": hashlib.sha256(raw).hexdigest(),
            "member": p.name,
        }
    return {
        "race_id": race_id,
        "scheduled_start_at": "2026-11-09T20:00:00Z",
        "decision_cutoff": "2026-11-09T19:56:00Z",
        "sources": roles,
        "active_field": ["1", "2"],
        "model_probabilities": {"1": .6, "2": .4},
        "win_odds": {"1": 2., "2": 3.},
        "scratches_independently_verified": True,
        "actual_start_independently_verified": True,
        "source_publication_or_asof_attested": True,
        "provider_identity_verified": True,
        "winner_selection_id": "1",
    }


def test_synthetic_source_contract_cannot_certify_pit(tmp_path):
    result = audit(sample(tmp_path), tmp_path)
    assert result["contract_complete"] is True
    assert result["evaluation_eligible"] is False
    assert result["pit_evidence_status"] == "PIT_UNPROVEN"
    assert result["bet_authority"] is False
    assert abs(result["normalized_win_probability"]["1"] - .6) < 1e-12


def test_mutated_body_and_late_price_fail(tmp_path):
    row = sample(tmp_path)
    (tmp_path / "WIN.json").write_bytes(b"wrong")
    assert "WIN:SOURCE_BYTES_SHA_CONFLICT" in audit(row, tmp_path)["blockers"]
    row = sample(tmp_path)
    row["sources"]["WIN"]["observed_at"] = "2026-11-09T19:59:00Z"
    assert "WIN:SOURCE_OBSERVED_AFTER_CUTOFF" in audit(row, tmp_path)["blockers"]


def test_roster_missing_win_and_wrong_winner_block(tmp_path):
    row = sample(tmp_path)
    row["win_odds"].pop("2")
    row["sources"]["ROSTER"]["race_id"] = "WRONG"
    row["winner_selection_id"] = "3"
    errors = audit(row, tmp_path)["blockers"]
    assert "WIN_FIELD_INCOMPLETE" in errors
    assert "ROSTER:SOURCE_RACE_ID_MISMATCH" in errors
    assert "OFFICIAL_WINNER_NOT_IN_ACTIVE_FIELD" in errors


def test_cutoff_scratch_and_missing_provenance(tmp_path):
    row = sample(tmp_path)
    row["decision_cutoff"] = "2026-11-09T19:55:00Z"
    row["scratches_independently_verified"] = False
    row["sources"]["MODEL"]["member"] = "../escape"
    errors = audit(row, tmp_path)["blockers"]
    assert "NOT_T_MINUS_FOUR" in errors
    assert "SCRATCHES_UNVERIFIED" in errors
    assert "MODEL:SOURCE_MEMBER_INVALID" in errors
