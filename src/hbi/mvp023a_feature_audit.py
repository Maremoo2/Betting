"""MVP-023A: audit M5 historical feature provenance, no training or lockbox access.

Consumes the existing hbi.backfill dataset JSONL and its SHA-pinned manifest.
No source fetching, model fitting, betting decision, or label-to-feature conversion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .research_lab import digest

SCHEMA = "MVP023A_HISTORICAL_FEATURE_AUDIT_V1"
SHA = re.compile(r"^[0-9a-f]{64}$")
FIELDS = {
    "driver": "driver",
    "extra_distance_m": "extra_distance_m",
    "trainer": "trainer",
    "last_3_starts": "last_3_starts",
    "last_5_starts": "last_5_starts",
    "last_10_starts": "last_10_starts",
    "normalized_km_time": "normalized_km_time",
    "opponent_strength": "opponent_strength",
    "distance_record": "distance_record",
    "start_method": "start_method",
    "post_position": "post_position",
    "gallop_rate": "gallop_rate",
    "dq_rate": "dq_rate",
    "days_since_last_start": "days_since_last_start",
    "race_class": "race_class",
    "track_context": "track_context",
}
LEAKAGE = {
    "result", "results", "labels", "placing", "place", "winner",
    "win_odds", "closing_odds", "market_probability", "pwin", "pcol",
    "payout", "dividend", "prize", "final_odds", "future_result",
}
STATES = (
    "PIT_VERIFIED", "RETROSPECTIVE_ONLY", "UNVERIFIED_TIME",
    "UNVERIFIED_IDENTITY", "UNSUPPORTED", "MISSING",
)


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.utcoffset() is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _classify(fact: object, runner: dict, race: dict, refs: set[tuple]) -> tuple[str, str]:
    if fact is None:
        return "MISSING", "ORIGINAL_FEATURE_NOT_PRESENT"
    if not isinstance(fact, dict):
        return "UNSUPPORTED", "FEATURE_NOT_SOURCE_OBJECT"
    value = fact.get("value")
    if value is None or value in ("UNKNOWN", "NOT_REPORTED"):
        return "MISSING", "FEATURE_VALUE_NOT_AVAILABLE"
    sha = fact.get("source_body_sha256")
    uri = fact.get("source_url")
    observed = fact.get("source_observed_at")
    if (
        not isinstance(sha, str) or SHA.fullmatch(sha) is None
        or not isinstance(uri, str) or not uri.startswith("https://www.rikstoto.no/api/")
        or (uri, sha, observed) not in refs
    ):
        return "UNSUPPORTED", "SOURCE_SHA_OR_REFERENCE_NOT_ATTESTED"
    event_time = _instant(race.get("event_time"))
    observed_time = _instant(observed)
    if event_time is None or observed_time is None:
        return "UNVERIFIED_TIME", "ORIGINAL_EVENT_OR_OBSERVATION_CLOCK_UNKNOWN"
    if observed_time >= event_time:
        return "RETROSPECTIVE_ONLY", "SOURCE_OBSERVED_AT_OR_AFTER_EVENT"
    if (
        not isinstance(runner.get("registration_observed"), str)
        or runner["registration_observed"].upper().startswith(
            ("TMP", "TEMP", "UNKNOWN", "ATG:", "ATG_", "ATG-", "NAME:")
        )
        or runner.get("identity_status") != "IDENTITY_VERIFIED"
        or race.get("independent_identity_attested") is not True
    ):
        return "UNVERIFIED_IDENTITY", "INDEPENDENT_HORSE_IDENTITY_NOT_PROVEN"
    feature_event = _instant(fact.get("event_at"))
    published = _instant(fact.get("published_at"))
    if (
        feature_event is None or published is None
        or feature_event >= event_time or published >= event_time
        or observed_time >= event_time
    ):
        return "UNVERIFIED_TIME", "FEATURE_EVENT_OR_PUBLICATION_NOT_PIT_ATTESTED"
    # A backfill dataset is not itself the raw original. Even apparently
    # complete timestamps cannot authorize PIT without a separate original
    # source-byte replay and a reviewed historical feature contract.
    return "UNVERIFIED_TIME", "RAW_HISTORICAL_FEATURE_ORIGINAL_NOT_REPLAYED"


def audit_feature_dataset(directory: Path) -> dict:
    directory = Path(directory)
    manifest = json.loads((directory / "model-readiness.json").read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "HBI_RESEARCH_DATASET_V1"
        or manifest.get("model_eligible") != 0
        or not isinstance(manifest.get("dataset_sha256"), str)
        or SHA.fullmatch(manifest["dataset_sha256"]) is None
    ):
        raise ValueError("M5_RESEARCH_MANIFEST_CONTRACT_INVALID")
    months = manifest.get("per_month")
    if not isinstance(months, dict):
        raise TypeError("M5_MONTHLY_SCOPE_MISSING")
    # Do this BEFORE reading dataset.jsonl; 2025 is a candidate lockbox and
    # neither its labels nor source outcomes may be opened for this audit.
    if any(str(month).startswith("2025-") for month in months):
        raise ValueError("CANDIDATE_2025_LOCKBOX_EXPOSURE_AUDIT_REQUIRED")
    raw = (directory / "dataset.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["dataset_sha256"]:
        raise ValueError("M5_DATASET_ORIGINAL_SHA_MISMATCH")
    records = []
    seen = set()
    counts = {name: Counter() for name in FIELDS}
    slices: dict[str, dict[str, Counter]] = {
        "by_year": defaultdict(Counter),
        "by_country": defaultdict(Counter),
    }
    for line in raw.splitlines():
        if not line:
            continue
        row = json.loads(line)
        rid = row.get("race_id")
        if not isinstance(rid, str) or not rid.startswith("RIKSTOTO:") or rid in seen:
            raise ValueError("M5_PHYSICAL_RACE_ID_DUPLICATE_OR_INVALID")
        seen.add(rid)
        day = row.get("date")
        if not isinstance(day, str) or not re.fullmatch(r"20(?:1[5-9]|2[0-6])-\d{2}-\d{2}", day):
            raise ValueError("M5_INVALID_HISTORICAL_DATE")
        if day.startswith("2025-"):
            raise ValueError("CANDIDATE_2025_LOCKBOX_SCOPE_CONFLICT")
        country = row.get("country") or "UNKNOWN"
        field = row.get("roster")
        if not isinstance(field, list):
            raise TypeError("M5_ROSTER_NOT_LIST")
        identities = [h.get("selection_id") for h in field if isinstance(h, dict)]
        if len(identities) != len(field) or len(set(identities)) != len(identities):
            raise ValueError("M5_DUPLICATE_OR_MISSING_RUNNERS")
        if any(type(h.get("scratched")) is not bool for h in field):
            raise ValueError("M5_SCRATCH_STATE_UNVERIFIED")
        active = [h for h in field if h["scratched"] is False]
        refs = row.get("source_refs") or []
        if not isinstance(refs, list):
            raise TypeError("M5_INVALID_SOURCE_RECEIPTS")
        source_set = {
            (r.get("url"), r.get("body_sha256"), r.get("fetched_at"))
            for r in refs if isinstance(r, dict)
        }
        if len(source_set) != len(refs):
            raise ValueError("M5_SOURCE_RECEIPTS_DUPLICATED_OR_MALFORMED")
        states_by_feature = {}
        for feature in FIELDS:
            observed = Counter()
            reasons = Counter()
            for runner in active:
                facts = runner.get("features") or {}
                if not isinstance(facts, dict):
                    raise TypeError("M5_FEATURE_OBJECT_INVALID")
                if LEAKAGE.intersection({str(k).lower() for k in facts}):
                    raise ValueError("OUTCOME_OR_MARKET_LEAKAGE_IN_FUNDAMENTAL_FEATURES")
                status, reason = _classify(facts.get(feature), runner, row, source_set)
                observed[status] += 1
                reasons[reason] += 1
            counts[feature].update(observed)
            states_by_feature[feature] = {
                "active_runners": len(active), "status_counts": dict(sorted(observed.items())),
                "primary_reason": reasons.most_common(1)[0][0] if reasons else "NO_ACTIVE_RUNNERS",
                "pit_qualified_runners": observed["PIT_VERIFIED"],
            }
        year = day[:4]
        for kind, name in (("by_year", year), ("by_country", country)):
            slices[kind][name]["races"] += 1
            slices[kind][name]["active_runners"] += len(active)
        records.append({
            "race_id": rid, "date": day, "country": country,
            "active_runners": len(active), "features": states_by_feature,
            "fundamental_training_eligible": False, "bet_authority": False,
            "reason": "HISTORICAL_FEATURE_ORIGINAL_PIT_CONTRACT_NOT_VALIDATED",
        })
    return {
        "schema": SCHEMA, "research_only": True, "bet_authority": False,
        "source_manifest_sha256": hashlib.sha256(
            (directory / "model-readiness.json").read_bytes()
        ).hexdigest(),
        "source_dataset_sha256": manifest["dataset_sha256"],
        "dataset_role_policy": "2015-2022_DEV_2023_INTERNAL_2024_LATE_2025_LOCKBOX_WITHHELD_2026_EXPOSED",
        "physical_races": len(records),
        "feature_count": len(FIELDS),
        "features": {k: {
            "source": "M5_ROSTER_FEATURES",
            "original_field": "roster[*].features." + k,
            "eligible_runners": v["PIT_VERIFIED"],
            "status_counts": dict(sorted(v.items())),
            "denominator_active_runners": sum(v.values()),
            "research_status": "PIT_VERIFIED" if v["PIT_VERIFIED"] else "PARTIAL_OR_BLOCKED",
        } for k, v in sorted(counts.items())},
        "by_year": {k: dict(v) for k, v in sorted(slices["by_year"].items())},
        "by_country": {k: dict(v) for k, v in sorted(slices["by_country"].items())},
        "by_race": records,
        "feature_audit_sha256": digest(records),
        "training_ready_races": 0,
        "benter_ready": False,
        "lockbox_2025_opened": False,
        "training_performed": False,
        "limitations": [
            "M5 features are not authenticated raw pre-race source-byte replays.",
            "Labels and retrospective odds are excluded from all feature evaluations.",
            "2025 results are not opened; exposure audit required.",
            "Feature availability and independent ID crosswalk are not established.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit_feature_dataset(args.dataset_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
