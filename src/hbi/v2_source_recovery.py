"""Manual-only source recovery and audits. Never authorizes a V2/PIT forecast."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rikstoto_crawler.capture import field_market
from rikstoto_crawler.extract import keyed

from .benchmark002_shadow import checked_json
from .research_lab import freeze
from .t4_evidence import _aware
from .v2_feature_state import advance, freeze_state, normalize_original


def recover_versions(candidates, roster, *, country):
    """Reject invalid versions first. Two valid conflicting originals still block.

    Roster is fixed before inspecting outcomes. No latest-version preference,
    guessed corrections, or majority vote can settle a real source conflict.
    """
    valid, rejected = {}, []
    for raw, receipt, source_id in candidates:
        try:
            field = normalize_original(raw, receipt, roster, country=country, source_id=source_id)
            valid.setdefault(field["body_sha256"], []).append(field)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            rejected.append({"source_id": source_id, "reason": str(exc)})
    if len(valid) != 1:
        return None, {"status": "SOURCE_DATA_MISSING" if not valid and not rejected else "SOURCE_DATA_INVALID",
                      "reason": "NO_VALID_RESULT_VERSION" if not valid else "MULTIPLE_VALID_RESULT_VERSIONS",
                      "valid_versions": len(valid), "rejected": rejected}
    same = next(iter(valid.values()))
    field = min(same, key=lambda f: (f["observed_at"], f["source_id"]))
    return field, {"status": "RETROSPECTIVE_RECONSTRUCTED", "valid_versions": 1,
                   "duplicate_valid_originals": len(same), "rejected": rejected,
                   "PIT_CERTIFIED": False}


def audit_market(raw, receipt, packet, *, now):
    """Expose all source blockers, including those masked by the first exception.

    Reuse Collector's roster-aware field parser for diagnostics only. Its
    historical local-time conversion cannot grant live timestamp attestation.
    """
    body = checked_json(raw, receipt["sha256"])
    _, meeting, number = packet["race_id"].split(":")
    errors = []
    if (receipt.get("status") != 200 or receipt.get("url") !=
            f"https://www.rikstoto.no/api/game/{meeting}/betdistribution/winodds/{number}"):
        errors.append("SOURCE_OR_RACE_MISMATCH")
    began, completed = _aware(receipt.get("started_at")), _aware(receipt.get("completed_at"))
    if began is None or completed is None or not began <= completed <= now:
        errors.append("CAPTURE_CLOCK_INVALID")
    rows = body.get("result")
    if body.get("success") is not True or not isinstance(rows, list):
        raise ValueError("SOURCE_MARKET_RESPONSE_INVALID")
    roster = {r["selection_id"]: r for r in packet["runners"]}
    active = {n for n, r in roster.items() if not r["scratched"]}
    try:
        quotes = keyed(rows)
    except (ValueError, KeyError, TypeError):
        quotes = {}
        errors.append("DUPLICATE_OR_INVALID_SELECTION")
    structural = field_market(rows, roster, active, ["odds"])
    missing = sorted(active-quotes.keys())
    unknown = sorted(quotes.keys()-roster.keys())
    known_scratched = sorted((quotes.keys() & roster.keys())-active)
    if missing or unknown or structural["status"] != "COMPLETE":
        errors.append("ACTIVE_FIELD_OR_PRICE_INVALID")
    if known_scratched:
        errors.append("STRICT_SHADOW_QUOTE_SET_CONFLICT")
    for n in sorted(active & quotes.keys()):
        updated = _aware(quotes[n].get("lastUpdated"))
        if updated is None:
            errors.append("PROVIDER_CLOCK_NAIVE_OR_MISSING:"+n)
        elif completed is not None and (updated > completed or completed-updated > timedelta(seconds=300)):
            errors.append("PROVIDER_MARKET_STALE_OR_FUTURE:"+n)
    return {"race_id": packet["race_id"], "market_status": "MARKET_CAPTURED_UNVERIFIED",
        "source_sha256": receipt["sha256"], "active_quote_count": len(active & quotes.keys()),
        "active_runners": len(active), "missing_active": missing, "unknown_selections": unknown,
        "known_scratched_quote_selections": known_scratched,
        "existing_collector_structural_audit": structural, "errors": errors,
        "qualified_combination_allowed": False, "PIT_CERTIFIED": False, "BET_AUTHORITY": False}


def load_bundle(path):
    """Read preserved source bytes, not caller-supplied normalized feature events."""
    doc = json.loads(Path(path).read_bytes())
    fields, audits = [], []
    for item in doc["races"]:
        raw = Path(item["roster_file"]).read_bytes()
        roster = checked_json(raw, item["roster_sha256"])["result"][str(item["race_number"])]
        candidates = [(Path(c["raw_file"]).read_bytes(), json.loads(Path(c["receipt_file"]).read_bytes()),
                       c["raw_file"]) for c in item["candidates"]]
        field, audit = recover_versions(candidates, roster, country=item["country"])
        audits.append({"race_id": item["race_id"], **audit})
        if field is not None:
            if field["race_id"] != item["race_id"]:
                raise ValueError("BUNDLE_PHYSICAL_RACE_CONFLICT")
            fields.append(field)
    return fields, audits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--state-sha256", required=True)
    parser.add_argument("--source-bundle", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("OUTPUT_EXISTS_NO_OVERWRITE")
    previous = checked_json(args.state.read_bytes(), args.state_sha256)
    fields, audits = load_bundle(args.source_bundle)
    cutoff = datetime.now(UTC).isoformat()  # Never a caller-backdated live clock.
    state, receipt = advance(args.workspace, previous, fields, cutoff)
    state["known_gaps"] = sorted(set(state["known_gaps"]+["2026_NOT_A_COMPLETE_RESULT_CENSUS"]))
    # This is an observed research state. advance never opens canonical V2.
    args.output.mkdir(parents=True)
    checksum = freeze_state(args.output/"state.json", state)
    freeze(args.output/"receipt.json", {**receipt, "state_sha256": checksum,
        "base_sha256": args.state_sha256, "source_audits": audits, "cutoff_utc": cutoff,
        "source_bundle_sha256": hashlib.sha256(args.source_bundle.read_bytes()).hexdigest(),
        "new_race_ids": sorted(set(state["applied_races"])-set(previous["applied_races"])),
        "PIT_CERTIFIED": False, "BET_AUTHORITY": False, "MANUAL_EXECUTION_ONLY": True})
    print(json.dumps({"state_sha256": checksum, "new_fields": receipt["new_fields"],
                      "PIT_CERTIFIED": False, "MANUAL_EXECUTION_ONLY": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
