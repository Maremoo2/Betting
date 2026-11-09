from hbi.model003_shadow_research import candidate_features


def rows():
    return [
        {
            "performance_date": f"2026-10-{i:02}",
            "horse_id": "TEST-ONLY-1",
            "official_race_id": f"TEST-RACE-{i}",
            "pit_evidence_status": "PIT_CERTIFIED",
            "result_source_sha256": "a" * 64,
            "km_seconds": 70. + i,
            "gallop": i == 3,
        }
        for i in range(1, 6)
    ]


def test_market_free_candidate_is_only_a_fixture():
    result = candidate_features(
        target_date="2026-11-09", horse_id="TEST-ONLY-1",
        identity_status="VERIFIED_ID", starts=rows(),
    )
    assert result["status"] == "PARTIAL_RESEARCH_FEATURES"
    assert result["features"]["opponent_strength"] is None
    assert result["features"]["recent_gallop_fraction"] == .2
    assert result["bet_authority"] is False


def test_identity_pit_and_future_veto():
    data = rows()
    data[1]["pit_evidence_status"] = "PIT_UNPROVEN"
    data[-1]["performance_date"] = "2026-11-10"
    result = candidate_features(
        target_date="2026-11-09", horse_id="TEST-ONLY-1",
        identity_status="PROVISIONAL_MATCH", starts=data,
    )
    assert {
        "PERMANENT_ID_NOT_VERIFIED", "HISTORICAL_PIT_NOT_CERTIFIED",
        "HISTORICAL_LOOKAHEAD",
    } <= set(result["reasons"])
    assert not result["features"]


def test_identity_collision_and_missing_race():
    data = rows()
    data[1]["horse_id"] = "WRONG"
    data[2]["official_race_id"] = None
    result = candidate_features(
        target_date="2026-11-09", horse_id="TEST-ONLY-1",
        identity_status="VERIFIED_ID", starts=data,
    )
    assert "HISTORICAL_ID_MISMATCH" in result["reasons"]
    assert "HISTORIC_RACE_ID_MISSING" in result["reasons"]
