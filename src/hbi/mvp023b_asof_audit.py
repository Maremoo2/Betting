"""MVP-023B P1-C: isolate historical event chronology from research as-of evidence.

This is an offline original-envelope replay, never a change to the production
PIT/T-4 gate. A preserved historical event is not proof of publication before
the target cutoff. Synthetic ASOF examples are always TEST_ONLY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rikstoto_crawler.transport import HOST
from rikstoto_crawler.transport import digest as source_digest

SCHEMA = "MVP023B_HISTORICAL_ASOF_RESEARCH_AUDIT_V1"
RID = re.compile(r"^RIKSTOTO:[A-Z0-9]+_NR_(20\d{2}-\d{2}-\d{2}):[1-9]\d*$")
ID = re.compile(r"^(?:DNT_REGISTRATION:[1-9]\d+|ATG_HORSE:[1-9]\d+)$")
SHA = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN = {"market", "odds", "win_odds", "closing_odds",
             "target_result", "target_label", "pwin", "pcol", "payout"}


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        instant = datetime.fromisoformat(value)
    except (ValueError, OverflowError):
        return None
    return instant.astimezone(UTC) if instant.utcoffset() is not None else None


def _read_original(root: Path, member: str, raw_sha: str) -> dict:
    if not isinstance(member, str) or not re.fullmatch(r"raw-results/[0-9a-f]{64}\.json", member):
        raise ValueError("UNSAFE_OR_NONRESULT_ORIGINAL_MEMBER")
    if not isinstance(raw_sha, str) or SHA.fullmatch(raw_sha) is None:
        raise ValueError("ORIGINAL_BYTE_SHA_MISSING")
    target = Path(root)
    if target.is_symlink() or not target.is_dir():
        raise ValueError("ORIGINAL_ARCHIVE_ROOT_UNTRUSTED")
    for step in (target / "raw-results", target / member):
        if step.is_symlink():
            raise ValueError("SYMLINK_ARCHIVE_SOURCE_REFUSED")
    raw = (target / member).read_bytes()
    if len(raw) > 20_000_000 or hashlib.sha256(raw).hexdigest() != raw_sha:
        raise ValueError("ORIGINAL_RESPONSE_BYTES_SHA_CONFLICT")
    envelope = json.loads(raw)
    if (not isinstance(envelope, dict)
            or not isinstance(envelope.get("body"), dict)
            or envelope.get("body_sha256") != source_digest(envelope["body"])
            or not isinstance(envelope.get("path"), str)
            or not envelope["path"].startswith("/results/")
            or envelope.get("url") != HOST + "/api" + envelope["path"]):
        raise ValueError("ORIGINAL_PROVIDER_ENVELOPE_OR_SHA_INVALID")
    return envelope


def assess_one(record: dict, *, root: Path | None = None,
               evidence_mode: str = "TEST_ONLY") -> dict:
    if evidence_mode not in {"TEST_ONLY", "SOURCE_REPLAYED"}:
        raise ValueError("UNREGISTERED_ASOF_EVIDENCE_MODE")
    if not isinstance(record, dict):
        raise TypeError("HISTORICAL_RESEARCH_ONLY_INPUT_REQUIRED")
    if record.get("bet_authority") is not False:
        raise ValueError("HISTORICAL_RESEARCH_ONLY_INPUT_REQUIRED")
    if record.get("model_eligible") is not False:
        raise ValueError("MODEL_OR_PIT_PROMOTION_NOT_ALLOWED")
    if FORBIDDEN & set(record.get("features", {})):
        raise ValueError("MARKET_OR_TARGET_RESULT_LEAKAGE")
    rid = record.get("target_race_id")
    match = RID.fullmatch(str(rid))
    prior_day = record.get("historical_date")
    if match is None or not isinstance(prior_day, str):
        raise ValueError("PHYSICAL_TARGET_OR_HISTORY_DATE_UNVERIFIED")
    # This check precedes any raw-original access.
    if "2025" in (match.group(1)[:4], prior_day[:4]):
        raise ValueError("2025_CANDIDATE_LOCKBOX_ACCESS_FORBIDDEN")
    try:
        target_day = date.fromisoformat(match.group(1))
        historical = date.fromisoformat(prior_day)
    except ValueError as exc:
        raise ValueError("INVALID_OR_UNKNOWN_HISTORICAL_EVENT_DATE") from exc
    if historical >= target_day:
        raise ValueError("FUTURE_OR_SAME_DAY_PERFORMANCE_LEAKAGE")
    stable = record.get("horse_identity")
    if not isinstance(stable, str) or ID.fullmatch(stable) is None:
        raise ValueError("BLOCKED_IDENTITY_NAME_TMP_OR_UNKNOWN")
    if record.get("previous_horse_identity") != stable:
        raise ValueError("CROSS_PROVIDER_IDENTITY_NOT_PROVEN")
    if record.get("source_role") != "PRIOR_OFFICIAL_RESULT":
        raise ValueError("TARGET_LABEL_OR_MARKET_CANNOT_BE_FUNDAMENTAL_INPUT")
    blockers = []
    start = _time(record.get("target_scheduled_start_at_utc"))
    zone = record.get("target_timezone")
    if start is None or zone not in {"Europe/Oslo", "Europe/Stockholm"}:
        blockers.append("TARGET_START_CLOCK_UNKNOWN")
        cutoff = None
    elif start.astimezone(ZoneInfo(zone)).date() != target_day:
        raise ValueError("TARGET_RACEDAY_CLOCK_CONFLICT")
    else:
        cutoff = start - timedelta(minutes=4)
    prior_at = _time(record.get("historical_event_at_utc"))
    if prior_at is not None and cutoff is not None and prior_at >= cutoff:
        raise ValueError("FUTURE_HISTORICAL_EVENT_TIMESTAMP")
    if prior_at is None:
        blockers.append("HISTORICAL_PRIOR_EVENT_CLOCK_UNVERIFIED")
    original = record.get("original_capture")
    observed_at = published_at = None
    if not isinstance(original, dict):
        blockers.append("HISTORICAL_ORIGINAL_CAPTURE_NOT_SUPPLIED")
    elif root is None:
        blockers.append("HISTORICAL_ORIGINAL_BYTES_NOT_REPLAYED")
    else:
        envelope = _read_original(
            root, original.get("member"), original.get("raw_file_sha256"),
        )
        if (
            envelope.get("path") != original.get("provider_path")
            or envelope.get("body_sha256") != original.get("body_sha256")
            or not envelope.get("path", "").endswith("/completeresults")
            or prior_day not in envelope.get("path", "")
        ):
            raise ValueError("HISTORICAL_ORIGINAL_EVENT_OR_SOURCE_CONFLICT")
        observed_at = _time(envelope.get("fetched_at"))
        published_at = _time(original.get("provider_published_at_utc"))
        # Never certify an as-of date solely from a later caller's
        # sidecar: the exact frozen source envelope must corroborate it.
        if (
            original.get("provider_published_at_utc")
            != envelope.get("source_published_at_utc")
        ):
            blockers.append("FIRST_PUBLICATION_NOT_IN_IMMUTABLE_ORIGINAL")
        if envelope.get("version_history_attested") is not True:
            blockers.append("ORIGINAL_CORRECTION_TIMELINE_NOT_SOURCE_ATTESTED")
        if observed_at is None:
            blockers.append("ORIGINAL_ACQUISITION_CLOCK_UNVERIFIED")
        if published_at is None:
            blockers.append("FIRST_PUBLICATION_CLOCK_UNVERIFIED")
        if (observed_at and cutoff and observed_at >= cutoff
                or published_at and cutoff and published_at >= cutoff):
            blockers.append("ORIGINAL_OBSERVED_OR_PUBLISHED_AFTER_CUTOFF")
        # An observed provider result is not sufficient to reconstruct
        # corrections first published at a later time.
        if original.get("immutable_version_timeline_attested") is not True:
            blockers.append("ORIGINAL_CORRECTION_TIMELINE_UNATTESTED")
    identity_at = _time(record.get("identity_proof_observed_at_utc"))
    if identity_at is None:
        blockers.append("STABLE_IDENTITY_NOT_OBSERVED_PRE_CUTOFF")
    elif cutoff and identity_at >= cutoff:
        blockers.append("STABLE_IDENTITY_PROOF_AFTER_CUTOFF")
    if cutoff is None:
        blockers.append("RESEARCH_T4_CUTOFF_NOT_RECONSTRUCTED")
    # Only a test-only complete original/provenance chain can demonstrate
    # the exact logic. Source replay must still remain RESEARCH ONLY.
    asof = not blockers and prior_at is not None and observed_at is not None
    return {
        "target_race_id": rid, "horse_identity": stable,
        "historical_date": prior_day, "source_role": "PRIOR_OFFICIAL_RESULT",
        "research_cutoff_t4_at_utc": cutoff.isoformat() if cutoff else None,
        "evidence_mode": evidence_mode,
        "historical_event_order_verified": True,
        "research_level": ("TEST_ONLY_HISTORICAL_ASOF_VERIFIED"
                           if asof and evidence_mode == "TEST_ONLY"
                           else "HISTORICAL_ASOF_REPLAYED_RESEARCH_ONLY"
                           if asof else "RETROSPECTIVE_PERFORMANCE_RECONSTRUCTION"),
        "historical_asof_source_ready": asof,
        "production_pit_certified": False,
        "model_eligible": False, "bet_authority": False,
        "blockers": sorted(set(blockers)),
    }


def audit(records: list[dict], *, root: Path | None = None,
          evidence_mode: str = "TEST_ONLY") -> dict:
    if not isinstance(records, list):
        raise TypeError("ASOF_RESEARCH_RECORDS_LIST_REQUIRED")
    seen = set()
    results = []
    for record in records:
        key = (record.get("target_race_id"), record.get("horse_identity"),
               record.get("historical_date"), record.get("prior_race_number"))
        if key in seen:
            raise ValueError("DUPLICATE_ORIGINAL_HISTORICAL_START")
        seen.add(key)
        results.append(assess_one(record, root=root, evidence_mode=evidence_mode))
    return {
        "schema": SCHEMA, "evidence_mode": evidence_mode,
        "records": results,
        "retrospective_documented": len(results),
        "historical_asof_source_ready": sum(r["historical_asof_source_ready"] for r in results),
        "production_pit_certified": 0, "model_training_eligible": 0,
        "benter_fit_ready": False, "2025_lockbox_opened": False,
        "bet_authority": False, "training_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_bytes())
    if manifest.get("schema") != "MVP023B_PRIOR_SOURCE_ASOF_INPUT_V1":
        raise ValueError("UNSUPPORTED_ASOF_MANIFEST")
    report = audit(manifest["records"], root=args.source_root,
                   evidence_mode="SOURCE_REPLAYED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        file.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
