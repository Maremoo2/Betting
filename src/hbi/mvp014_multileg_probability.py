"""MVP-014: research-only independent multi-leg coverage from ORIGINAL model bytes.

No pool pricing, no EV, no ticket construction, no PIT/BET promotion.
The race/product/leg mapping must be independently verified by callers.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

MODEL_SCHEMA = "BET_MVP_001_FROZEN_SHADOW_V1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("MISSING_FROZEN_CLOCK")
    try:
        time = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_FROZEN_CLOCK") from exc
    if time.utcoffset() is None:
        raise ValueError("NAIVE_FROZEN_CLOCK")
    return time.astimezone(UTC)


def _validated_original(raw: bytes, expected_sha256: str) -> tuple[str, dict[str, dict[str, float]]]:
    if (not isinstance(raw, bytes) or not raw
            or not isinstance(expected_sha256, str)
            or SHA256.fullmatch(expected_sha256) is None
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise ValueError("MODEL_ORIGINAL_BYTES_OR_SHA256_UNVERIFIED")
    try:
        model = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("MODEL_ORIGINAL_NOT_JSON") from exc
    if not isinstance(model, dict) or model.get("schema") != MODEL_SCHEMA:
        raise ValueError("FROZEN_MODEL_SCHEMA_INVALID")
    if (model.get("run_kind") != "PROSPECTIVE_ATTEMPT"
            or model.get("model_status") != "MODEL_READY"
            or model.get("source_archive_is_immutable_read_only") is not True
            or model.get("bet_authority") is not False):
        raise ValueError("FROZEN_MODEL_NOT_ELIGIBLE")
    race = model.get("race")
    if not isinstance(race, dict) or not isinstance(race.get("race_id"), str) or not race["race_id"]:
        raise ValueError("PHYSICAL_RACE_ID_MISSING")
    if not (
        _utc(model.get("as_of_utc"))
        <= _utc(model.get("report_created_at_utc"))
        <= _utc(race.get("start_time_utc")) - timedelta(minutes=4)
    ):
        raise ValueError("MODEL_FREEZE_AFTER_CONSERVATIVE_T4")
    runners = model.get("runners")
    if (not isinstance(runners, list) or len(runners) != model.get("field_size")
            or len(runners) < 2):
        raise ValueError("MODEL_FULL_FIELD_INVALID")
    if any(
        not isinstance(r, dict) or type(r.get("scratched")) is not bool
        or type(r.get("start_number")) is not int
        or not isinstance(r.get("selection_id"), str) or not r["selection_id"]
        for r in runners
    ):
        raise ValueError("MODEL_RUNNER_IDENTITY_INVALID")
    if (len({r["selection_id"] for r in runners}) != len(runners)
            or len({r["start_number"] for r in runners}) != len(runners)):
        raise ValueError("MODEL_RUNNER_IDENTITY_COLLISION")
    active = [r for r in runners if not r["scratched"]]
    if len(active) < 2 or len(active) != model.get("active_runners"):
        raise ValueError("MODEL_ACTIVE_FULL_FIELD_INVALID")
    vectors: dict[str, dict[str, float]] = {}
    for name, key in (("champion", "champion_p_win"), ("core004", "core004_p_win")):
        vector: dict[str, float] = {}
        for row in active:
            p = row.get(key)
            if type(p) not in (float, int) or not math.isfinite(p) or not 0 < p < 1:
                raise ValueError("MODEL_ACTIVE_PROBABILITIES_INVALID")
            vector[row["selection_id"]] = float(p)
        if not math.isclose(math.fsum(vector.values()), 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError("MODEL_ACTIVE_PROBABILITIES_NOT_NORMALIZED")
        vectors[name] = vector
    return race["race_id"], vectors


def independent_system_coverage(
    frozen_legs: list[dict],
    *,
    model_name: str = "champion",
    expected_legs: int | None = None,
) -> dict:
    """Exact system hit probability ONLY under an explicit independence assumption.

    Each leg requires {original_model_bytes, original_model_sha256, selections}.
    Selection IDs are race-local. No market or payout is read or inferred.
    """
    if model_name not in ("champion", "core004"):
        raise ValueError("UNKNOWN_FROZEN_PROBABILITY_MODEL")
    if (not isinstance(frozen_legs, list) or len(frozen_legs) < 2
            or (expected_legs is not None and (
                type(expected_legs) is not int or expected_legs < 2
                or len(frozen_legs) != expected_legs
            ))):
        raise ValueError("INCOMPLETE_OR_INVALID_LEG_COUNT")
    seen: set[str] = set()
    coverage = []
    counts = []
    hashes = []
    for item in frozen_legs:
        if not isinstance(item, dict):
            raise TypeError("LEG_FORMAT_INVALID")
        sha = item.get("original_model_sha256")
        race_id, vectors = _validated_original(item.get("original_model_bytes"), sha)
        if race_id in seen:
            raise ValueError("DUPLICATE_PHYSICAL_RACE_IN_LEGS")
        seen.add(race_id)
        picks = item.get("selections")
        if (not isinstance(picks, list) or not picks
                or any(not isinstance(p, str) or not p for p in picks)
                or len(picks) != len(set(picks))
                or any(p not in vectors[model_name] for p in picks)):
            raise ValueError("UNKNOWN_SCRATCHED_OR_DUPLICATE_SELECTION")
        selected_probability = math.fsum(vectors[model_name][p] for p in picks)
        coverage.append({"race_id": race_id, "selection_count": len(picks),
                         "selected_probability": selected_probability,
                         "source_model_sha256": sha})
        hashes.append(sha)
        counts.append(len(picks))
    return {
        "schema": "MVP014_INDEPENDENT_MULTILEG_COVERAGE_RESEARCH_V1",
        "research_only": True,
        "model_name": model_name,
        "physical_race_count": len(seen),
        "unique_rows": math.prod(counts),
        "probability_all_winners_covered_if_independent": math.prod(
            x["selected_probability"] for x in coverage
        ),
        "legs": coverage,
        "independence_assumption": "ASSUMED_NOT_VALIDATED",
        "pool_identity_verified": False,
        "collective_combination_price": None,
        "jackpot_adjustment": None,
        "system_ev": None,
        "estimated_payout": None,
        "pit_certification_performed": False,
        "bet_authority": False,
        "ticket": None,
        "stake_nok": None,
    }


def independent_combination_probability(
    frozen_legs: list[dict], *, model_name: str = "champion",
    expected_legs: int | None = None,
) -> dict:
    """A single winner combination is a one-selection-per-leg system."""
    result = independent_system_coverage(
        frozen_legs, model_name=model_name, expected_legs=expected_legs
    )
    if result["unique_rows"] != 1:
        raise ValueError("NOT_A_SINGLE_WINNER_COMBINATION")
    return result
