"""MVP-008C: read-only bridge from frozen HBI research to V3.3 gate diagnostics.

This is *not* a V3.3 input adapter, an identity attestor or an authority grant.
No unverified JSON can trigger betting.v33.evaluate, paper stakes or writes to state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .probability import fair_odds, normalize_market_odds

SCHEMA = "MVP008C_READONLY_DECISION_AUDIT_V1"
MODEL_SCHEMA = "BET_MVP_001_FROZEN_SHADOW_V1"


def _time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.utcoffset() is not None else None


def _prob(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    return value if math.isfinite(value) and 0 < value <= 1 else None


def _odds(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    return value if math.isfinite(value) and value > 1 else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _attestation(index: dict[str, Any] | None, race_id: str, model_sha: str) -> dict:
    """Correlate an artifact, NEVER independently authenticate its provenance."""
    if index is None:
        return {"matched": False, "claimed_status": None, "blockers": ["PIT_ATTESTATION_MISSING"]}
    if index.get("schema") != "PIT_T4_ATTESTATION_INDEX_V1":
        return {"matched": False, "claimed_status": None, "blockers": ["PIT_ATTESTATION_SCHEMA_MISMATCH"]}
    rows = index.get("results")
    if not isinstance(rows, list):
        return {"matched": False, "claimed_status": None, "blockers": ["PIT_ATTESTATION_RESULTS_MISSING"]}
    same = [x for x in rows if isinstance(x, dict) and x.get("race_id") == race_id]
    if len(same) != 1:
        return {"matched": False, "claimed_status": None, "blockers": ["PIT_ATTESTATION_RACE_NOT_UNIQUE"]}
    row = same[0]
    if row.get("model_report_sha256") != model_sha:
        return {"matched": False, "claimed_status": row.get("pit_status"),
                "blockers": ["PIT_ATTESTATION_MODEL_HASH_MISMATCH"]}
    return {"matched": True, "claimed_status": row.get("pit_status"),
            "blockers": list(row.get("blockers") or []),
            "independently_certified_by_this_audit": False}


def audit(model_raw: bytes, attestation_raw: bytes | None = None) -> dict[str, Any]:
    """Inspect an existing frozen report and independent attestation index, without writes.

    Passing a JSON object claiming exact identity, PIT or calibration is never enough:
    this tool has no source authentication or FFQ-1 provenance verifier. Therefore
    it never supplies a fabricated qualified payload to the frozen V3.3 evaluator.
    """
    model = json.loads(model_raw)
    if not isinstance(model, dict) or model.get("schema") != MODEL_SCHEMA:
        raise ValueError("FROZEN_RESEARCH_MODEL_SCHEMA_REQUIRED")
    raw_rows = model.get("runners")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("FROZEN_RESEARCH_FULL_FIELD_REQUIRED")
    race = model.get("race") or {}
    race_id = race.get("race_id")
    if not isinstance(race_id, str) or not race_id:
        raise ValueError("PHYSICAL_RACE_ID_REQUIRED")
    asof, freeze, start = (_time(model.get("as_of_utc")),
                           _time(model.get("report_created_at_utc")),
                           _time(race.get("start_time_utc")))
    global_blocks = set()
    if asof is None or freeze is None or start is None or not asof <= freeze < start:
        global_blocks.add("MODEL_ASOF_OR_FREEZE_INVALID")
    if model.get("run_kind") != "PROSPECTIVE_ATTEMPT":
        global_blocks.add("PROSPECTIVE_MODEL_REQUIRED")
    if model.get("source_archive_is_immutable_read_only") is not True:
        global_blocks.add("ORIGINAL_SOURCE_PROVENANCE_NOT_VERIFIED")
    database_sha = model.get("source_database_sha256")
    if (not isinstance(database_sha, str) or len(database_sha) != 64
            or any(v not in "0123456789abcdef" for v in database_sha)):
        global_blocks.add("MODEL_SOURCE_DATABASE_HASH_MISSING")
    if model.get("model_status") != "MODEL_READY":
        global_blocks.add("MODEL_NOT_READY")
    if model.get("market_status") != "MARKET_READY":
        global_blocks.add("WIN_MARKET_NOT_READY")
    if model.get("bet_authority") is not False:
        global_blocks.add("UNEXPECTED_MODEL_BET_AUTHORITY")

    raw_numbers, active, records = [], [], []
    for row in raw_rows:
        if not isinstance(row, dict):
            global_blocks.add("INVALID_FULL_FIELD_ROW")
            continue
        selection = row.get("selection_id")
        number = row.get("start_number")
        scratch = row.get("scratched")
        if (not isinstance(selection, str) or not selection or type(number) is not int
                or number < 1 or type(scratch) is not bool or not row.get("horse_name")):
            global_blocks.add("INVALID_FULL_FIELD_ROW")
        raw_numbers.append((repr(selection), repr(number)))
        if scratch is False:
            active.append(row)
        records.append(row)
    if (len(raw_numbers) != len(set(raw_numbers))
            or len({r[0] for r in raw_numbers}) != len(raw_numbers)
            or len({r[1] for r in raw_numbers}) != len(raw_numbers)):
        global_blocks.add("DUPLICATE_OR_COLLIDING_START_IDENTITY")
    if (len(active) != model.get("active_runners")
            or len(records) != model.get("field_size") or len(active) < 2):
        global_blocks.add("INCOMPLETE_ACTIVE_FULL_FIELD")

    win, champ, core, win_clock = {}, {}, {}, set()
    for row in active:
        sid = row.get("selection_id")
        if sid in win:
            global_blocks.add("DUPLICATE_OR_COLLIDING_START_IDENTITY")
        win[sid] = _odds(row.get("win_odds"))
        champ[sid] = _prob(row.get("champion_p_win"))
        core[sid] = _prob(row.get("core004_p_win"))
        win_clock.add(row.get("win_odds_observed_at_utc"))
        if not row.get("win_odds_source_uri") or row.get("win_odds_provider") != "rikstoto":
            global_blocks.add("WIN_ORIGINAL_SOURCE_REFERENCE_MISSING")
    if len(win_clock) != 1 or None in win_clock:
        global_blocks.add("WIN_NOT_SINGLE_TIMESTAMP_FIELD")
    observed = _time(next(iter(win_clock))) if len(win_clock) == 1 else None
    if observed is None or asof is None or not observed <= asof:
        global_blocks.add("WIN_OBSERVATION_NOT_BEFORE_MODEL_ASOF")
    if (any(v is None for v in champ.values()) or len(champ) != len(active)
            or not math.isclose(sum(v for v in champ.values() if v is not None),
                                1.0, abs_tol=1e-9)):
        global_blocks.add("CHAMPION_FULL_FIELD_DISTRIBUTION_INVALID")
    if (any(v is None for v in core.values()) or len(core) != len(active)
            or not math.isclose(sum(v for v in core.values() if v is not None),
                                1.0, abs_tol=1e-9)):
        global_blocks.add("CORE004_FULL_FIELD_DISTRIBUTION_INVALID")
    if any(v is None for v in win.values()) or len(win) != len(active):
        global_blocks.add("WIN_FULL_FIELD_ODDS_INCOMPLETE")
    market_p = (normalize_market_odds(win)
                if not global_blocks and all(v is not None for v in win.values()) else {})

    attestation = None
    if attestation_raw is not None:
        attestation = json.loads(attestation_raw)
        if not isinstance(attestation, dict):
            raise ValueError("PIT_ATTESTATION_INDEX_OBJECT_REQUIRED")
    matched_attestation = _attestation(attestation, race_id, _sha(model_raw))
    if (not matched_attestation["matched"]
            or matched_attestation["claimed_status"] != "INDEPENDENT_PIT_CERTIFIED"):
        global_blocks.add("PIT_NOT_CERTIFIED")
    # Even a forged/copy-pasted 'certified' flag is never independent evidence.
    global_blocks.add("PIT_LIVE_PROVENANCE_NOT_AUTHENTICATED_BY_ADAPTER")
    global_blocks.add("CROSS_PROVIDER_IDENTITY_ORIGINAL_NOT_ATTESTED")
    global_blocks.add("CALIBRATED_PWIN_INTERVALS_NOT_SUPPLIED")
    global_blocks.add("FFQ1_FULL_FIELD_REVIEWS_NOT_SUPPLIED")
    global_blocks.add("V33_MINIMUM_PRICES_NOT_SUPPLIED")
    global_blocks.add("V33_PREREGISTERED_BATCH_NOT_SUPPLIED")
    global_blocks.update(matched_attestation["blockers"])

    details = []
    for row in records:
        sid = row.get("selection_id")
        is_active = row.get("scratched") is False
        p = champ.get(sid) if is_active else None
        odds = win.get(sid) if is_active else None
        detail_blocks = set(global_blocks)
        if is_active and p is None:
            detail_blocks.add("CHAMPION_PWIN_MISSING")
        if is_active and odds is None:
            detail_blocks.add("WIN_ODDS_MISSING")
        if row.get("scratched") is True:
            detail_blocks.add("SCRATCHED_NOT_AN_ACTIVE_WIN_CASE")
        elif not is_active:
            detail_blocks.add("UNKNOWN_SCRATCH_STATE")
        details.append({
            "selection_id": sid, "start_number": row.get("start_number"),
            "horse_name": row.get("horse_name"), "active": is_active,
            "champion_p_win": p,
            "champion_fair_odds_theoretical": fair_odds(p) if p is not None else None,
            "core004_p_win_research_only": core.get(sid) if is_active else None,
            "win_odds_observed": odds,
            "win_observed_at_utc": row.get("win_odds_observed_at_utc") if is_active else None,
            "win_source_uri": row.get("win_odds_source_uri") if is_active else None,
            "normalized_market_p": market_p.get(sid),
            "champion_uncalibrated_ev_diagnostic": (
                p * odds - 1 if p is not None and odds is not None else None),
            "decision": "PASS_NOT_ACTIVE" if row.get("scratched") is True else "BLOCKED",
            "missing_contracts": sorted(detail_blocks),
            "stake_nok": None,
            "bet_authority": False,
        })
    return {
        "schema": SCHEMA, "mode": "READ_ONLY_RESEARCH_DIAGNOSTIC",
        "race_id": race_id, "as_of_utc": model.get("as_of_utc"),
        "report_created_at_utc": model.get("report_created_at_utc"),
        "race_start_utc": race.get("start_time_utc"),
        "frozen_model_original_sha256": _sha(model_raw),
        "source_database_sha256": database_sha,
        "attestation_index_sha256": _sha(attestation_raw) if attestation_raw is not None else None,
        "attestation": matched_attestation,
        "active_runners": len(active), "runners_in_report": len(records),
        "market_full_field_verified_by_report": bool(market_p),
        "global_blockers": sorted(global_blocks), "runners": details,
        "v33_evaluator_called": False, "v33_qualified": False,
        "execution": "NONE", "bet_authority": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-report", type=Path, required=True)
    parser.add_argument("--attestation-index", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit(args.model_report.read_bytes(),
                   args.attestation_index.read_bytes() if args.attestation_index else None)
    output = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is None:
        print(output, end="")
    else:
        # Never overwrite frozen diagnostics or any existing path.
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
