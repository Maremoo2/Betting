"""PREWATCH-004B2: source-gated original history binding (NO MODEL / NO BET).

Reuses existing HBI identity and historical official-original validators.
Without an independently reviewed registry receipt + ATG result originals
observed before the declared cutoff, current horses remain UNRESOLVED.
This is not an ATG client, PDF parser, new provider, or model.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .historical_intelligence_v2 import history_coverage, verified_past_race
from .horse_identity import ModelIdentityEvidence, resolve_model_identity
from .prewatch004_pack import _write_once, digest
from .prewatch004b_features import make_feature_day_packs, validate_context_for_draft

SCHEMA = "PREWATCH004B2_ORIGINAL_HISTORY_BINDING_V1"
DAY_SCHEMA = "PREWATCH004B2_DAY_IDENTITY_COVERAGE_V1"
UNKNOWN = "UNKNOWN"
PIT_UNPROVEN = "PIT_UNPROVEN"
MARKET_KEYS = frozenset({
    "odds", "win_odds", "v_percent", "market_probability",
    "expected_value", "stake", "bet", "closing_odds",
})


def utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("PREWATCH004B2_AWARE_UTC_REQUIRED")
    point = datetime.fromisoformat(value)
    if point.utcoffset() is None:
        raise ValueError("PREWATCH004B2_NAIVE_CLOCK_FORBIDDEN")
    return point.astimezone(UTC)


def feature(
    value: Any = UNKNOWN, *, n: int = 0, refs: tuple[str, ...] = (),
    status: str = "UNKNOWN", reason: str = "NOT_IN_ATTESTED_ORIGINAL",
) -> dict[str, Any]:
    if status not in ("VERIFIED", "PARTIAL", "UNKNOWN", "BLOCKED"):
        raise ValueError("PREWATCH004B2_INVALID_STATUS")
    if type(n) is not int or n < 0:
        raise ValueError("PREWATCH004B2_INVALID_DENOMINATOR")
    return {
        "value": value, "status": status, "denominator": n,
        "source_ids": list(refs), "reason": reason,
        "pit_status": PIT_UNPROVEN,
        "model_eligible": False, "bet_authorized": False,
    }


def aggregate_official_history(
    results: list[dict[str, Any]], *, horse_id: int, cutoff_utc: str,
    history_index_complete: bool = False,
) -> dict[str, Any]:
    """Aggregate only verified *individual originals*, never negative by silence.

    The results are already returned from historical_intelligence_v2.
    Even a valid observed-original evidence chain is not production PIT.
    """
    if type(horse_id) is not int or horse_id <= 0:
        raise ValueError("PREWATCH004B2_HORSE_ID_MISSING")
    cutoff = utc(cutoff_utc)
    admitted = []
    seen = set()
    for item in results:
        if not isinstance(item, dict) or item.get("horse_id") != horse_id:
            raise ValueError("PREWATCH004B2_HISTORY_IDENTITY_CONFLICT")
        uri = item.get("source_uri")
        if not isinstance(uri, str) or not uri:
            raise ValueError("PREWATCH004B2_SOURCE_ID_REQUIRED")
        if uri in seen:
            raise ValueError("PREWATCH004B2_DUPLICATE_PRIOR_RACE")
        seen.add(uri)
        if (item.get("pit_certified") is not False
                or item.get("bet_authority") is not False):
            raise ValueError("PREWATCH004B2_UNREVIEWED_PIT_OR_BET_PROMOTION")
        observed = utc(item["source_observed_at_utc"])
        published_raw = item.get("source_published_at_utc")
        if observed >= cutoff or (
            published_raw is not None and utc(published_raw) >= cutoff
        ):
            raise ValueError("PREWATCH004B2_POST_CUTOFF_ORIGINAL")
        if item.get("status") == "VERIFIED":
            fields = item.get("fields")
            if not isinstance(fields, dict) or not all(
                k in fields for k in ("race_date", "placing", "gallop", "disqualified")
            ):
                raise ValueError("PREWATCH004B2_OFFICIAL_RESULT_FIELDS_MISSING")
            from datetime import date

            if date.fromisoformat(fields["race_date"]) >= cutoff.date():
                raise ValueError("PREWATCH004B2_FUTURE_OR_SAME_DAY_HISTORY")
            admitted.append(item)

    # Reuse the existing conservative history-completeness contract.
    coverage = history_coverage(
        results, current_horse_id=horse_id,
        current_model_cutoff_utc=cutoff.isoformat(),
        original_history_index_complete=history_index_complete,
    )
    if coverage["verified_historical_results"] != len(admitted):
        raise ValueError("PREWATCH004B2_HISTORY_COVERAGE_MISMATCH")
    ordered = sorted(
        admitted, key=lambda x: (x["fields"]["race_date"], x["source_uri"]), reverse=True
    )
    references = tuple(r["source_uri"] for r in ordered)
    placing = [
        r for r in ordered if type(r["fields"]["placing"]) is int
        and r["fields"]["placing"] >= 1
    ]
    values: dict[str, dict[str, Any]] = {
        "observed_verified_prior_starts": feature(
            len(ordered), n=len(ordered), refs=references,
            status="VERIFIED" if ordered else "UNKNOWN",
            reason="INDEPENDENT_OFFICIAL_PRIOR_RESULTS_OBSERVED_NOT_COMPLETE_INDEX",
        ),
        "latest_observed_verified_start_date": feature(
            ordered[0]["fields"]["race_date"] if ordered else UNKNOWN,
            n=1 if ordered else 0, refs=references[:1],
            status="VERIFIED" if ordered else "UNKNOWN",
            reason="LATEST_OBSERVED_NOT_PROVEN_LATEST_ACTUAL",
        ),
    }

    def rate(key: str, subset: list[dict[str, Any]], predicate) -> None:
        refs = tuple(r["source_uri"] for r in subset)
        values[key] = feature(
            sum(bool(predicate(r)) for r in subset) / len(subset) if subset else UNKNOWN,
            n=len(subset), refs=refs,
            status="VERIFIED" if subset else "UNKNOWN",
            reason="OBSERVED_VERIFIED_RESULTS_ONLY_NOT_CAREER_RATE",
        )

    rate("observed_win_rate", placing, lambda r: r["fields"]["placing"] == 1)
    rate("observed_top3_rate", placing, lambda r: r["fields"]["placing"] <= 3)
    for signal in ("gallop", "disqualified"):
        subset = [
            r for r in ordered if type(r["fields"][signal]) is bool
        ]
        rate(f"observed_{signal}_rate", subset, lambda r, k=signal: r["fields"][k])

    method_counts: dict[str, int] = {}
    distance_counts: dict[str, int] = {}
    for entry in ordered:
        row = entry["fields"]
        distance = row.get("distance_m")
        method = row.get("start_method")
        if type(distance) is int and 300 <= distance <= 9999:
            name = str(distance)
            distance_counts[name] = distance_counts.get(name, 0) + 1
        if method in ("AUTO", "VOLT"):
            method_counts[method] = method_counts.get(method, 0) + 1
    for key, counts in (
        ("observed_distance_counts_m", distance_counts),
        ("observed_start_method_counts", method_counts),
    ):
        values[key] = feature(
            dict(sorted(counts.items())) if counts else UNKNOWN,
            n=sum(counts.values()), refs=references,
            status="VERIFIED" if counts else "UNKNOWN",
            reason="OFFICIAL_ORIGINAL_CONTEXT_ONLY_NO_COMPARABILITY_INFERRED",
        )

    for last_n in (3, 5, 10):
        allowed = (history_index_complete and len(ordered) >= 3) if last_n == 3 else (
            coverage[f"last_{last_n}"] == "VERIFIED"
        )
        subset = ordered[:last_n] if allowed else []
        values[f"last_{last_n}_complete_results"] = feature(
            [
                {"source_uri": r["source_uri"],
                 "race_date": r["fields"]["race_date"],
                 "placing": r["fields"]["placing"]}
                for r in subset
            ] if allowed else UNKNOWN,
            n=len(subset), refs=tuple(r["source_uri"] for r in subset),
            status="VERIFIED" if allowed else "UNKNOWN",
            reason="COMPLETE_ORIGINAL_INDEX_ATTESTED" if allowed
            else "INCOMPLETE_OR_UNATTESTED_HISTORY_INDEX",
        )

    return {
        "status": "PARTIAL_RESEARCH_ONLY" if ordered else "UNKNOWN",
        "verified_individual_originals": len(ordered),
        "history_index_complete_attested": history_index_complete,
        "history_coverage": coverage,
        "features": values,
        "pit_status": PIT_UNPROVEN,
        "model_eligible": False,
        "bet_authorized": False,
    }


def bind_target_horse(
    source_pack: dict[str, Any], context: dict[str, Any], *,
    selection_id: str, cutoff_utc: str,
    current_atg: dict[str, Any] | None = None,
    identity_row: dict[str, Any] | None = None,
    identities: tuple[ModelIdentityEvidence, ...] = (),
    historical_originals: tuple[dict[str, Any], ...] = (),
    history_index_complete: bool = False,
) -> dict[str, Any]:
    """Exact source+identity+PIT admission, always research-only.

    The configured reviewed receipt set is currently empty: no name or ATG
    horseId alone can create a successful permanent cross-provider binding.
    """
    validate_context_for_draft(source_pack, context)
    cutoff = utc(cutoff_utc)
    start = utc(source_pack["race"]["start_time_utc"])
    observed = utc(source_pack["source"]["observed_at_utc"])
    if not observed < cutoff < start:
        raise ValueError("PREWATCH004B2_SOURCE_OR_CUTOFF_NOT_PRESTART")
    if type(selection_id) is not str or not selection_id.isdecimal():
        raise ValueError("PREWATCH004B2_INVALID_SELECTION_ID")
    rows = [r for r in context["runners"] if r["selection_id"] == selection_id]
    if len(rows) != 1:
        raise ValueError("PREWATCH004B2_TARGET_SELECTION_NOT_UNIQUE")
    runner = rows[0]
    if runner["scratched"]:
        return {
            "schema": SCHEMA, "race_id": source_pack["race_id"], "selection_id": selection_id,
            "identity_status": "SCRATCHED_EXCLUDED",
            "history_status": "NOT_ADMITTED", "historical_results_verified": 0,
            "features": {}, "pit_status": PIT_UNPROVEN, "model_eligible": False,
            "bet_authorized": False,
        }

    stable, reason = resolve_model_identity(
        source_pack["race_id"], selection_id,
        identity_row or {}, current_atg or {}, identities, cutoff,
        race_cutoff=cutoff,
    )
    if stable is None:
        return {
            "schema": SCHEMA, "race_id": source_pack["race_id"],
            "selection_id": selection_id,
            "horse_name": runner["horse_name"],
            "identity_status": "IDENTITY_UNRESOLVED",
            "identity_reason": reason or "NO_REVIEWED_ORIGINAL_SOURCE",
            "history_status": "NOT_ADMITTED",
            "historical_results_verified": 0,
            "features": {},
            "pit_status": PIT_UNPROVEN,
            "model_eligible": False, "bet_authorized": False,
        }
    # A registry attestation can never be swapped for a free-text identifier.
    if (not identities or
            any(x.identity.horse_id != stable for x in identities) or
            len({x.atg_horse_id for x in identities}) != 1):
        raise ValueError("PREWATCH004B2_STABLE_IDENTITY_CONFLICT")
    atg_horse_id = identities[0].atg_horse_id
    original_results = []
    for prior in historical_originals:
        if not isinstance(prior, dict) or set(prior) != {
            "original", "sha256", "atg_race_id", "source_uri",
            "observed_at_utc", "published_at_utc",
        }:
            raise ValueError("PREWATCH004B2_UNREVIEWED_HISTORIC_SOURCE")
        raw = prior["original"]
        if not isinstance(raw, bytes):
            raise TypeError("PREWATCH004B2_ORIGINAL_BYTES_REQUIRED")
        checked = verified_past_race(
            raw,
            claimed_sha256=prior["sha256"],
            claimed_atg_race_id=prior["atg_race_id"],
            source_uri=prior["source_uri"],
            observed_at_utc=prior["observed_at_utc"],
            source_published_at_utc=prior["published_at_utc"],
            model_cutoff_utc=cutoff.isoformat(),
            current_race_start_utc=start.isoformat(),
            horse_id=atg_horse_id,
        )
        if checked.get("status") == "VERIFIED":
            original_results.append(checked)
        elif checked.get("status") == "NOT_AVAILABLE_AT_PIT":
            raise ValueError("PREWATCH004B2_PAST_RESULT_NOT_AVAILABLE")
    aggregate = aggregate_official_history(
        original_results, horse_id=atg_horse_id,
        cutoff_utc=cutoff.isoformat(),
        history_index_complete=history_index_complete,
    )
    return {
        "schema": SCHEMA, "race_id": source_pack["race_id"],
        "source_run_id": source_pack["source"]["run_id"],
        "selection_id": selection_id,
        "horse_name": runner["horse_name"],
        "permanent_horse_identity": stable,
        "permanent_horse_identity_source": identities[0].identity.source,
        "identity_status": "ATTESTED_ORIGINAL_BINDING",
        "history_status": aggregate["status"],
        "historical_results_verified": aggregate["verified_individual_originals"],
        "features": aggregate["features"],
        "history_coverage": aggregate["history_coverage"],
        "pit_status": PIT_UNPROVEN,  # HBI original validator does not grant production PIT.
        "model_eligible": False, "bet_authorized": False,
    }


def make_day_unresolved_report(
    archive: Path, checksum: Path, output: Path, *, date_oslo: str,
) -> dict[str, Any]:
    """Offline and factual: all admitted identities stay ZERO without originals."""
    with tempfile.TemporaryDirectory(prefix="prewatch004b2-") as scratch:
        root = Path(scratch) / "contexts"
        coverage = make_feature_day_packs(archive, checksum, root, day=date_oslo)
        items = []
        for meta in coverage["files"]:
            raw = (root / meta["filename"]).read_bytes()
            if digest(raw) != meta["sha256"]:
                raise ValueError("PREWATCH004B2_FEATURE_CONTEXT_HASH_CONFLICT")
            doc = json.loads(raw)
            for runner in doc["runners"]:
                if runner["scratched"]:
                    continue
                if runner["permanent_identity_attested"] is not False:
                    raise ValueError("PREWATCH004B2_UNEXPECTED_ATTESTED_IDENTITY")
                items.append({
                    "race_id": doc["race_id"],
                    "selection_id": runner["selection_id"],
                    "horse_name": runner["horse_name"],
                    "source_context_sha256": meta["sha256"],
                    "identity_status": "IDENTITY_UNRESOLVED",
                    "history_status": "UNKNOWN",
                    "verified_original_results_admitted": 0,
                    "pit_status": PIT_UNPROVEN,
                    "model_eligible": False,
                })
        report = {
            "schema": DAY_SCHEMA,
            "date_oslo": date_oslo,
            "source_run_id": coverage["source_run_id"],
            "source_original_archive_sha256": coverage["source_original_archive_sha256"],
            "physical_races": coverage["physical_race_count_source_discovered"],
            "listed_runners": coverage["listed_runner_coverage"]["total"],
            "active_runners": coverage["active_runner_coverage"]["total"],
            "raw_prior_pdf_lines": coverage["history_raw_rows_total"],
            "research_semantic_rows": coverage["history_semantic_rows_total"],
            "active_with_independent_permanent_horse_id": 0,
            "active_with_verified_original_history": 0,
            "active_with_min_3_verified_results": 0,
            "active_with_min_5_verified_results": 0,
            "active_with_min_10_verified_results": 0,
            "active_with_complete_last5_history": 0,
            "active_with_pit_qualified_history": 0,
            "active_with_verified_win_top3_rate": 0,
            "active_with_verified_gallop_dq_rate": 0,
            "active_with_verified_distance_method": 0,
            "active_with_history_unknown_or_blocked": len(items),
            "independent_whole_day_denominator_verified": False,
            "original_history_binding_missing_not_actual_zero_results": True,
            "status": "BLOCKED_MISSING_HORSE_IDENTITY_AND_PRE_CUTOFF_HISTORIC_ORIGINALS",
            "horse_observations": items,
            "model_eligible": False, "bet_authorized": False,
        }
        if len(items) != report["active_runners"]:
            raise ValueError("PREWATCH004B2_DAY_ACTIVE_ROSTER_COVERAGE_MISMATCH")
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_once(output, (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
                             + "\n").encode("utf-8"))
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="PREWATCH-004B2 offline original-binding audit (NO BET)")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--date-oslo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    result = make_day_unresolved_report(
        options.archive, options.checksum, options.output, date_oslo=options.date_oslo,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "horse_observations"}, sort_keys=True))


if __name__ == "__main__":
    main()
