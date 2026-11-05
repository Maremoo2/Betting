"""MVP-023A: deterministic, separated research-only M5 dataset partitions.

Reuses M5's source-checked backfill and candidate view. It NEVER builds a
training-ready table from unavailable history or opens the 2025 lockbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .research_lab import digest

SCHEMA = "MVP023A_RESEARCH_DATASET_PARTITION_V1"
SHA = re.compile(r"^[0-9a-f]{64}$")
RID = re.compile(r"^RIKSTOTO:[A-Z0-9]+_NR_(20\d{2}-\d{2}-\d{2}):[1-9]\d*$")
SAFE_FACTS = ("driver", "extra_distance_m")
PROHIBITED = frozenset({
    "label", "labels", "winner", "winning", "place", "placing", "result",
    "km_time", "closing_odds", "win_odds", "market", "payout", "prize", "dividend",
})


def role(day: str) -> str:
    year = int(day[:4])
    if 2015 <= year <= 2022:
        return "DEVELOPMENT_2015_2022"
    if year == 2023:
        return "INTERNAL_VALIDATION_2023"
    if year == 2024:
        return "CHALLENGER_VALIDATION_2024"
    if year == 2025:
        raise ValueError("CANDIDATE_2025_LOCKBOX_MUST_REMAIN_UNOPENED")
    if year == 2026:
        return "EXPOSED_RESEARCH_2026_NOT_BLIND_OOS"
    raise ValueError("OUTSIDE_REGISTERED_HISTORICAL_PERIOD")


def _time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.utcoffset() is not None
    except (ValueError, TypeError):
        return False


def _read_m5(directory: Path) -> tuple[list[dict], dict, str]:
    directory = Path(directory)
    manifest_raw = (directory / "model-readiness.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest.get("schema") != "HBI_RESEARCH_DATASET_V1"
        or manifest.get("model_eligible") != 0
        or not isinstance(manifest.get("per_month"), dict)
        or not isinstance(manifest.get("dataset_sha256"), str)
        or SHA.fullmatch(manifest["dataset_sha256"]) is None
    ):
        raise ValueError("M5_ORIGINAL_DATASET_MANIFEST_INVALID")
    # Must happen before reading even one byte of a potential lockbox dataset.
    if any(str(month).startswith("2025-") for month in manifest["per_month"]):
        raise ValueError("CANDIDATE_2025_LOCKBOX_EXPOSURE_AUDIT_REQUIRED")
    raw = (directory / "dataset.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["dataset_sha256"]:
        raise ValueError("M5_ORIGINAL_DATASET_SHA_MISMATCH")
    rows = [json.loads(line) for line in raw.splitlines() if line]
    return rows, manifest, hashlib.sha256(manifest_raw).hexdigest()


def _research_row(row: dict) -> tuple[dict, dict, str]:
    rid = row.get("race_id")
    match = RID.fullmatch(str(rid))
    day = row.get("date")
    if match is None or day != match.group(1):
        raise ValueError("PHYSICAL_RACE_OR_DATE_CONFLICT")
    partition = role(day)
    if row.get("raceday_key") != rid.split(":")[1]:
        raise ValueError("CANONICAL_RACEDAY_KEY_CONFLICT")
    if row.get("country") not in {"NO", "SE"} or row.get("discipline") != "trot":
        raise ValueError("M5_COUNTRY_OR_DISCIPLINE_OUT_OF_SCOPE")
    if not _time(row.get("event_time")):
        raise ValueError("M5_EVENT_CLOCK_NOT_AUTHENTICATED")
    field = row.get("roster")
    if not isinstance(field, list) or len(field) < 2:
        raise ValueError("FULL_FIELD_ROSTER_UNAVAILABLE")
    numbers = [r.get("selection_id") for r in field if isinstance(r, dict)]
    if len(numbers) != len(field) or any(not isinstance(n, str) or not n for n in numbers) or len(numbers) != len(set(numbers)):
        raise ValueError("DUPLICATE_OR_INVALID_RUNNER_IN_PHYSICAL_RACE")
    if any(type(r.get("scratched")) is not bool for r in field):
        raise ValueError("SCRATCH_STATE_NOT_VERIFIED")
    active = [r for r in field if not r["scratched"]]
    if len(active) < 2:
        raise ValueError("INSUFFICIENT_ACTIVE_FIELD")
    refs = row.get("source_refs")
    if not isinstance(refs, list) or not refs:
        raise ValueError("M5_ORIGINAL_SOURCE_REFERENCES_MISSING")
    for ref in refs:
        if (
            not isinstance(ref, dict)
            or not isinstance(ref.get("body_sha256"), str)
            or SHA.fullmatch(ref["body_sha256"]) is None
            or not isinstance(ref.get("url"), str)
            or not ref["url"].startswith("https://www.rikstoto.no/api/")
            or not _time(ref.get("fetched_at"))
        ):
            raise ValueError("M5_SOURCE_REF_SHA_URI_OR_CLOCK_INVALID")
    model = row.get("model_candidate")
    if (
        not isinstance(model, dict)
        or model.get("schema") != "HBI_RACE_MODEL_CANDIDATE_V1"
        or model.get("race_id") != rid
        or model.get("data_ready") is not False
        or model.get("model_eligible") is not False
    ):
        raise ValueError("M5_MODEL_CANDIDATE_IS_NOT_VERIFIED_BLOCKED_VIEW")
    # M5 source_refs may contain post-race RESULT evidence. Never copy it into
    # a fundamental input. Retain only /racedays/.../starts provenance.
    start_url = "https://www.rikstoto.no/api/racedays/" + row["raceday_key"] + "/starts"
    pre_refs = [
        {k: ref.get(k) for k in ("url", "body_sha256", "fetched_at", "published_at")}
        for ref in refs if ref["url"] == start_url
    ]
    if len(pre_refs) != 1:
        raise ValueError("M5_PRE_RACE_STARTS_SOURCE_NOT_UNIQUE")
    runners = []
    for horse in sorted(active, key=lambda h: h["selection_id"]):
        facts = horse.get("features") or {}
        if not isinstance(facts, dict):
            raise TypeError("M5_FEATURE_OBJECT_NOT_DICT")
        if PROHIBITED.intersection({str(key).lower() for key in facts}):
            raise ValueError("HISTORICAL_RESULT_OR_MARKET_FEATURE_LEAKAGE")
        # Preserve only exact M5 source-bound facts; never copy arbitrary
        # biographical or market values into a research feature sidecar.
        safe = {name: facts.get(name) if name in facts else None for name in SAFE_FACTS}
        for name, fact in safe.items():
            if fact is None:
                continue
            if not isinstance(fact, dict):
                raise TypeError("M5_UNSUPPORTED_FEATURE_OBJECT:" + name)
            if fact.get("value") is not None and (
                fact.get("source_url") != pre_refs[0]["url"]
                or fact.get("source_body_sha256") != pre_refs[0]["body_sha256"]
                or fact.get("source_observed_at") != pre_refs[0]["fetched_at"]
            ):
                raise ValueError("M5_FEATURE_SOURCE_REFERENCE_CONFLICT:" + name)
        if any(name not in (*SAFE_FACTS,) for name in facts):
            raise ValueError("UNREVIEWED_M5_FEATURE_FIELD")
        runners.append({
            "runner_id": horse["selection_id"],
            "provider_registration_observed": horse.get("registration_observed"),
            "independent_identity_attested": False,
            "features": safe, "model_ready": False,
        })
    source_input = {
        "race_id": rid, "date": day, "country": row.get("country"),
        "track": row.get("track"), "discipline": row.get("discipline"),
        "start_at": row.get("event_time"), "partition": partition,
        "active_runner_ids": [h["runner_id"] for h in runners],
        "runners": runners,
        "source_provenance": pre_refs,
        "market_input": None,
        "input_contract": "M5_ORIGINAL_COHORT_RETROSPECTIVE_ONLY",
        "model_eligible": False, "bet_authority": False,
    }
    # Labels stay in a physically separate output file; never part of input SHA.
    label = {
        "race_id": rid, "partition": partition,
        "status": "RETROSPECTIVE_LABEL_ONLY"
        if row.get("authoritative_result_verified") is True else "NOT_VERIFIED",
        "results": row.get("labels", []) if row.get("authoritative_result_verified") is True else [],
        "training_feature_input": False, "bet_authority": False,
    }
    return source_input, label, partition


def build_partitioned_dataset(directory: Path) -> tuple[dict, list[dict], list[dict]]:
    rows, source, source_manifest_sha = _read_m5(directory)
    inputs: list[dict] = []
    labels: list[dict] = []
    partitions: dict[str, list[str]] = {}
    countries = Counter()
    seen = set()
    exclusions = Counter()
    for row in sorted(rows, key=lambda item: str(item.get("race_id"))):
        rid = row.get("race_id")
        if rid in seen:
            raise ValueError("DUPLICATE_PHYSICAL_RACE")
        seen.add(rid)
        input_row, label_row, partition = _research_row(row)
        inputs.append(input_row)
        labels.append(label_row)
        partitions.setdefault(partition, []).append(rid)
        countries[str(row.get("country") or "UNKNOWN")] += 1
        exclusions["HISTORICAL_FEATURE_PIT_CONTRACT_NOT_VERIFIED"] += 1
    for value in partitions.values():
        value.sort()
    manifest = {
        "schema": SCHEMA,
        "research_only": True, "bet_authority": False,
        "source_m5_manifest_sha256": source_manifest_sha,
        "source_m5_dataset_sha256": source["dataset_sha256"],
        "input_dataset_sha256": digest(inputs),
        "label_dataset_sha256": digest(labels),
        "partitions": {name: {
            "race_ids": ids, "count": len(ids), "sha256": digest(ids),
        } for name, ids in sorted(partitions.items())},
        "countries": dict(sorted(countries.items())),
        "races": len(inputs), "active_runners": sum(len(r["runners"]) for r in inputs),
        "model_training_eligible": 0, "benter_fit_eligible": 0,
        "exclusions": dict(sorted(exclusions.items())),
        "label_separated_from_fundamentals": True,
        "market_pre_race_verification": "NOT_AVAILABLE_IN_M5",
        "historical_feature_pit": "NOT_VERIFIED",
        "2025_candidate_lockbox_opened": False,
        "training_performed": False, "model_promotion": False,
        "readiness": "BLOCKED_SOURCE",
    }
    return manifest, inputs, labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest, inputs, labels = build_partitioned_dataset(args.dataset_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, doc in (
        ("manifest.json", manifest),
        ("fundamental-inputs.json", inputs),
        ("retrospective-labels.json", labels),
    ):
        with (args.output_dir / name).open("x", encoding="utf-8") as stream:
            json.dump(doc, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
