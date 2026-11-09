"""Ensure the accelerated research interface cannot silently acquire betting authority."""

import json
from pathlib import Path


def test_canonical_contract_explicit_fields_and_no_bet():
    root = Path(__file__).resolve().parents[1]
    contract = json.loads((root / "docs" / "ACCELERATION_001_COMMON_CONTRACT.json").read_text())
    fields = set(contract["required"])
    assert len(fields) == 14
    assert {"race_id", "source_hash", "decision_cutoff", "pit_evidence_status"} <= fields
    assert contract["bet_authority"] is False
    assert contract["auto_merge"] is False
    assert len(contract["scope_categories"]) == 4
