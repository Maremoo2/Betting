"""MERGE-001: strictly non-authoritative DATA-009 -> BENCHMARK-003 schema preview.

This is a *structural* integration check, not a PIT certificate or a scoring
adapter. It deliberately does not return a valid benchmark row to callers.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from hbi.benchmark003_framework import validate
from hbi.data009_prospective_bridge import audit


def preview_handoff(race: dict[str, Any], root: Path, *, race_date: str) -> dict[str, Any]:
    checked = audit(race, root)
    if checked["pit_evidence_status"] != "PIT_UNPROVEN" or checked["evaluation_eligible"] is not False:
        raise ValueError("DATA009_AUTHORITY_ESCALATION_FORBIDDEN")
    if not checked["contract_complete"]:
        return {
            "status": "BLOCKED_SOURCE_AUDIT",
            "blockers": checked["blockers"], "benchmark_eligible": False,
            "pit_evidence_status": "PIT_UNPROVEN", "bet_authority": False,
        }
    model_version = race.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        return {
            "status": "BLOCKED_MODEL_VERSION_UNATTESTED",
            "blockers": ["MODEL_VERSION_MISSING"], "benchmark_eligible": False,
            "pit_evidence_status": "PIT_UNPROVEN", "bet_authority": False,
        }
    date.fromisoformat(race_date)
    candidate = {
        "race_id": race["race_id"], "race_date": race_date,
        "scope": "DECISION_TIME_OBSERVED",
        "pit_evidence_status": "PIT_UNPROVEN",
        "race_start_at": checked["scheduled_start_at"],
        "decision_cutoff": checked["decision_cutoff"],
        "active_field": list(race["active_field"]),
        "probabilities": {
            "SHADOW_MODEL_PREVIEW": dict(race["model_probabilities"]),
            "NORMALIZED_WIN_PREVIEW": dict(checked["normalized_win_probability"]),
        },
        "winner_selection_id": race["winner_selection_id"],
        "market_observed_at": race["sources"]["WIN"]["observed_at"],
        "model_source_observed_at": race["sources"]["MODEL"]["observed_at"],
        "model_version": model_version,
        "source_hash": race["sources"]["WIN"]["source_hash"],
    }
    validate(candidate)
    # A DATA-009 local-byte check does not attest the provider, frozen model
    # or source publication. Never expose a ready-to-score row from this bridge.
    return {
        "status": "SCHEMA_COMPATIBLE_NOT_SCORE_AUTHORIZED",
        "mapped_field_names": sorted(candidate),
        "source_model_version": model_version,
        "missing_for_pit": [
            "INDEPENDENT_PROVIDER_ORIGIN_ATTESTATION",
            "MODEL_FREEZE_AUTHORITY",
            "SOURCE_PUBLICATION_AND_REVISION_PROVENANCE",
            "PIT_CERTIFICATE_AND_APPROVED_COHORT",
        ],
        "benchmark_eligible": False, "pit_evidence_status": "PIT_UNPROVEN",
        "bet_authority": False,
    }
