"""Fail-closed V3.3.13 Pre-Watch transport for existing Collector reports.

No probability model, EV calculation, Champion mutation or betting authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

SCHEMA = "PREWATCH_SHADOW_HANDOFF_V3313_V1"


def _clock(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("TIMEZONE_AWARE_DECISION_TIME_REQUIRED")
    return stamp


def _sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def build_handoff(
    source: dict, *, decision_time: str,
    model_run: dict | None = None, win_snapshot: dict | None = None,
) -> dict:
    """Represent actual collector_handoff evidence, never infer an EV or BET.

    This consumes collector_handoff.verify_import() output. Even independently
    verified model/market inputs still require the existing betting.v33 review.
    """
    decision_at = _clock(decision_time)
    race_id = source.get("race_id")
    if not isinstance(race_id, str) or not race_id:
        raise ValueError("CANONICAL_RACE_ID_REQUIRED")
    rows = source.get("runners") or []
    if not isinstance(rows, list):
        raise TypeError("RUNNER_ROWS_INVALID")
    selections = [str(row["start_number"]) for row in rows]
    if len(selections) != len(set(selections)):
        raise ValueError("DUPLICATE_START_NUMBER")
    active = [str(row["start_number"]) for row in rows if row.get("scratched") is False]
    provenance = {
        key: value for key, value in (source.get("model_input_sources") or {}).items()
        if key.startswith("collector_")
    }
    blockers = {str(code) for code in source.get("blockers", [])}
    required_hashes = (
        "collector_starts_sha256",
        "collector_program_pdf_sha256",
        "collector_manifest_sha256",
    )
    source_ready = (
        source.get("source_imported_to_sqlite") is True
        and len(active) >= 2
        and all(_sha(provenance.get(key)) for key in required_hashes)
    )
    if not source_ready:
        blockers.add("SOURCE_IMPORT_NOT_VERIFIED")
    model_ready = (
        source.get("model_input_approved") is True
        and source.get("independent_identity_attested") is True
        and model_run is not None
        and model_run.get("shadow_eligible") is True
        and model_run.get("status") == "READY"
        and model_run.get("calibration_verified") is True
    )
    if not model_ready:
        blockers.add("MODEL_INPUT_OR_CALIBRATION_UNVERIFIED")
    market_ready = False
    if win_snapshot is not None:
        try:
            quote_at = _clock(win_snapshot["observed_at"])
            odds = win_snapshot["odds"]
            market_ready = (
                quote_at <= decision_at
                and win_snapshot.get("race_id") == race_id
                and win_snapshot.get("source_verified") is True
                and win_snapshot.get("full_field_verified") is True
                and set(odds) == set(active)
                and all(
                    type(price) in (int, float) and math.isfinite(price) and price > 1
                    for price in odds.values()
                )
            )
        except (KeyError, ValueError, TypeError):
            market_ready = False
    if not market_ready:
        blockers.add("COMPLETE_WIN_MARKET_UNVERIFIED")
    blockers.add("EXISTING_V33_REVIEW_NOT_EXECUTED")
    return {
        "schema": SCHEMA,
        "race_id": race_id,
        "decision_time": decision_at.isoformat(),
        "listed_runners": len(rows),
        "active_field": active,
        "source_status": "SOURCE_READY" if source_ready else "DATA_BLOCKED",
        "fundamental_status": (
            "READY_FOR_ENGINE_REVIEW" if model_ready else "MODEL_UNCALIBRATED"
        ),
        "market_status": "SOURCE_VERIFIED" if market_ready else "MARKET_PENDING",
        "shadow_status": (
            "NEEDS_EXISTING_V33_REVIEW" if model_ready and market_ready
            else "DATA_BLOCKED"
        ),
        "model_version": model_run.get("model_version") if model_run else None,
        "model_calibration_verified": bool(model_ready),
        "probabilities": None,
        "expected_value": None,
        "bet_authorized": False,
        "execution": "SHADOW_ONLY",
        "champion_changed": False,
        "blockers": sorted(blockers),
        "source_checksums": provenance,
    }


def write_once_and_readback(report: dict, target: Path) -> str:
    """Local append-only-by-file transport; no writes to canonical HBI state."""
    target = Path(target)
    raw = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")
    with target.open("xb") as output:
        output.write(raw)
    if target.read_bytes() != raw:
        raise OSError("SHADOW_REPORT_READBACK_CONFLICT")
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    """Convert an existing collector_handoff.run_import report to gated Shadow JSON."""
    import argparse

    parser = argparse.ArgumentParser(description="Read-only Pre-Watch Shadow transport")
    parser.add_argument("--collector-report", type=Path, required=True)
    parser.add_argument("--decision-time", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.collector_report.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or not isinstance(source.get("records"), list):
        raise ValueError("EXISTING_COLLECTOR_REPORT_REQUIRED")
    events = [
        build_handoff(row, decision_time=args.decision_time)
        for row in source["records"]
    ]
    output = {
        "schema": "PREWATCH_SHADOW_BATCH_V3313_V1",
        "source_report_sha256": hashlib.sha256(
            args.collector_report.read_bytes()
        ).hexdigest(),
        "races": events,
        "bet_authorized": False,
        "champion_changed": False,
    }
    write_once_and_readback(output, args.out)


if __name__ == "__main__":
    main()
