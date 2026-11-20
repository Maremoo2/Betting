"""Manual, source-gated BENCHMARK-002 inference. No execution or DB writer.

Historical packet inference is explicitly retrospective. Live inference requires
reviewed originals and a source-bound graph replay; numeric caller flags never
approve a source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from rikstoto_crawler.transport import digest

from . import benchmark002_retrospective as bench
from .decision import DecisionPolicy, assess_value
from .probability import combine_probabilities, fair_odds, normalize_market_odds
from .research_lab import freeze
from .shadow import ShadowPolicy
from .t4_evidence import _aware

MODEL = "BENCHMARK002_CHALLENGER_V2_RETRO_V1"
FEATURE_ORDER = ("F0_CAREER", "F1_LAST5", "F1_LAST10", "F1_EXP90", "F1_LAYOFF",
                 "F2_PRIOR_PURSE", "F2_PURSE_TIME", "F3_OWN_RATING", "F3_FACED_RATING")


def checked_json(raw, expected):
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("ORIGINAL_SHA_MISMATCH")
    return json.loads(raw)


def load_artifact(raw, expected):
    try:
        artifact = checked_json(raw, expected)
    except (ValueError, TypeError) as error:
        raise ValueError("ARTIFACT_"+str(error)) from error
    if (artifact.get("model") != MODEL or artifact.get("feature_order") != list(FEATURE_ORDER)
            or artifact.get("training_last_year") >= artifact.get("calibration_year")
            or artifact.get("calibration_year") >= artifact.get("test_year")
            or artifact.get("ridge") != bench.RIDGE
            or artifact.get("market_domain") != "TERMINAL_RETROSPECTIVE"):
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH")
    weights = np.asarray(artifact["fundamental_weights"], dtype=float)
    combination = np.asarray(artifact["market_fundamental_weights"], dtype=float)
    if (weights.shape != (9,) or combination.shape != (2,)
            or not np.isfinite(weights).all() or not np.isfinite(combination).all()
            or (combination < 0).any() or combination.sum() <= 0):
        raise ValueError("ARTIFACT_WEIGHTS_INVALID")
    return artifact


def feature_matrix(packet):
    if packet["country"] not in {"NO", "SE"} or packet["sport"] != "T":
        raise ValueError("UNSUPPORTED_COHORT")
    target = date.fromisoformat(packet["day"])
    if target.year == 2025:
        raise ValueError("LOCKBOX_2025")
    runners = packet["runners"]
    active = [r for r in runners if r["scratched"] is False]
    ids = [r["selection_id"] for r in active]
    horses = [r["horse_id"] for r in active]
    if (len(active) < 2 or len(ids) != len(set(ids)) or len(horses) != len(set(horses))
            or any(type(r["scratched"]) is not bool for r in runners)
            or len({r["selection_id"] for r in runners}) != len(runners)):
        raise ValueError("FULL_FIELD_OR_IDENTITY_CONFLICT")
    if any(k in packet for k in ("winner", "target_result", "market_odds", "pWIN")):
        raise ValueError("LABEL_OR_MARKET_IN_FEATURE_PACKET")
    matrix = []
    for runner in active:
        if (not runner["horse_id"].startswith("RIKSTOTO_REG:")
                or runner["horse_id"] != "RIKSTOTO_REG:"+runner["registration"]):
            raise ValueError("IDENTITY_STATE_CONFLICT")
        state = packet["state"].get(runner["horse_id"])
        if not state or not state["history"]:
            raise ValueError("MISSING_VERIFIED_HISTORY_STATE")
        history = []
        for row in state["history"]:
            when = date.fromisoformat(row[0])
            if when >= target or when.year == 2025:
                raise ValueError("HISTORY_LOOKAHEAD_OR_LOCKBOX")
            if type(row[1]) is not bool:
                raise ValueError("HISTORY_WIN_SEMANTICS_INVALID")
            if any(value is not None and (type(value) not in (int, float) or not math.isfinite(value))
                   for value in row[2:]):
                raise ValueError("HISTORY_NONFINITE")
            history.append((when, *row[1:]))
        if history != sorted(history, key=lambda r: r[0]):
            raise ValueError("HISTORY_NOT_CHRONOLOGICAL")
        matrix.append(bench.feature(history, state["rating"], target, len(active)))
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (len(active), 9) or not np.isfinite(matrix).all():
        raise ValueError("FEATURE_MATRIX_INVALID")
    return active, matrix


def freeze_fundamental(artifact_raw, artifact_sha, packet_raw, packet_sha, path, now, *,
                       source_state_raw=None, source_state_sha256=None, source_evidence=None,
                       runtime_clock=None, clock_offset_reader=None):
    """Write the market-free forecast before a market reader can be invoked."""
    artifact = load_artifact(artifact_raw, artifact_sha)
    packet = checked_json(packet_raw, packet_sha)
    current = _aware(now.isoformat())
    if current is None:
        raise ValueError("MODEL_CLOCK_NAIVE")
    scope = packet.get("scope")
    if scope not in {"RETROSPECTIVE", "PROSPECTIVE"}:
        raise ValueError("EVIDENCE_SCOPE_MISSING")
    if scope == "RETROSPECTIVE" and date.fromisoformat(packet["day"]) >= current.date():
        raise ValueError("RETROSPECTIVE_TARGET_NOT_PAST")
    if int(packet["day"][:4]) < artifact["test_year"]:
        raise ValueError("MODEL_AFTER_TARGET")
    if scope == "PROSPECTIVE":
        start = _aware(packet.get("start_at"))
        if start is None or current >= start-timedelta(minutes=ShadowPolicy().target_minutes_to_start):
            raise ValueError("MODEL_AT_OR_AFTER_T4_OR_CLOCK_MISSING")
        offset = packet.get("clock_offset_ms")
        if type(offset) not in (int, float) or not math.isfinite(offset) or abs(offset) > 250:
            raise ValueError("CLOCK_OFFSET_EXCEEDS_250_MS")
        canonical = packet.get("canonical_collector_row")
        if not canonical or canonical.get("race_id") != packet["race_id"]:
            raise ValueError("CANONICAL_COLLECTOR_ROW_MISSING")
        from .v2_source_admission import assess_sources

        admission = assess_sources(packet, source_state_raw, source_state_sha256,
            source_evidence, artifact_sha256=artifact_sha, moment=current)
        if not admission["qualified"]:
            raise ValueError("BLOCKED_SOURCE:V2_LIVE_STATE_ADAPTER_NOT_ATTESTED|"+
                             "|".join(admission["blockers"]))
        if clock_offset_reader is not None:
            offset = clock_offset_reader()
            if type(offset) not in (int, float) or not math.isfinite(offset) or abs(offset) > 250:
                raise ValueError("CLOCK_OFFSET_EXCEEDS_250_MS")
        actual = runtime_clock() if runtime_clock else datetime.now(UTC)
        if actual < current or actual >= start-timedelta(minutes=ShadowPolicy().target_minutes_to_start):
            raise ValueError("MODEL_AT_OR_AFTER_T4_OR_CLOCK_ROLLBACK")
        current = actual
    active, matrix = feature_matrix(packet)
    probabilities = bench.race_softmax(matrix @ np.asarray(artifact["fundamental_weights"]))
    if not np.isfinite(probabilities).all() or (probabilities <= 0).any() or abs(probabilities.sum()-1)>1e-12:
        raise ValueError("INVALID_PROBABILITIES")
    result = {"schema": "BENCHMARK002_SHADOW_FREEZE_V1", "race_id": packet["race_id"],
        "day": packet["day"], "start_at": packet.get("start_at"), "scope": scope,
        "created_at": current.isoformat(), "model": MODEL, "artifact_sha256": artifact_sha,
        "packet_sha256": packet_sha, "feature_sha256": digest(matrix.tolist()),
        "active": active, "fundamental": dict(zip([r["selection_id"] for r in active], probabilities.tolist())),
        "pit_certified": scope == "PROSPECTIVE", "bet_authority": False,
        "source_quality": "PIT_VERIFIED" if scope == "PROSPECTIVE" else packet["source_quality"]}
    if scope == "PROSPECTIVE":
        actual = runtime_clock() if runtime_clock else datetime.now(UTC)
        if actual < current or actual >= start-timedelta(minutes=ShadowPolicy().target_minutes_to_start):
            raise ValueError("MODEL_FINISHED_AT_OR_AFTER_T4_OR_CLOCK_ROLLBACK")
        result.update(created_at=actual.isoformat(), source_admission=admission,
                      source_state_sha256=source_state_sha256, measured_clock_offset_ms=offset)
    freeze(Path(path), result)
    return result


def verify_prospective_freeze(frozen, artifact, packet_raw, state_raw, source_evidence, *, artifact_sha256):
    """Rebind approved originals and model outputs; a caller PIT flag is insufficient."""
    from .v2_source_admission import assess_sources

    if frozen.get("scope") != "PROSPECTIVE" or frozen.get("pit_certified") is not True:
        raise ValueError("PIT_QUALIFIED_FREEZE_REQUIRED")
    packet = checked_json(packet_raw, frozen["packet_sha256"])
    if (frozen.get("artifact_sha256") != artifact_sha256 or frozen.get("model") != artifact["model"]
            or any(frozen.get(k) != packet.get(k) for k in ("race_id", "day", "start_at"))):
        raise ValueError("FROZEN_SOURCE_OR_MODEL_BINDING_CONFLICT")
    created = _aware(frozen.get("created_at"))
    if created is None:
        raise ValueError("QUALIFIED_FREEZE_CLOCK_INVALID")
    admission = assess_sources(packet, state_raw, frozen.get("source_state_sha256"),
        source_evidence, artifact_sha256=frozen["artifact_sha256"], moment=created)
    if not admission["qualified"]:
        raise ValueError("BLOCKED_SOURCE:"+"|".join(admission["blockers"]))
    active, matrix = feature_matrix(packet)
    if frozen.get("active") != active or frozen.get("feature_sha256") != digest(matrix.tolist()):
        raise ValueError("FROZEN_FIELD_OR_FEATURE_BINDING_CONFLICT")
    expected = dict(zip([r["selection_id"] for r in active],
        bench.race_softmax(matrix @ np.asarray(artifact["fundamental_weights"])).tolist()))
    if expected != frozen["fundamental"]:
        raise ValueError("FROZEN_PREDICTION_SOURCE_OR_MODEL_CONFLICT")
    return admission


def check_market_clock(frozen, original, current):
    """Existing prospective-research 300-second window, never a BET freshness claim."""
    created = _aware(frozen.get("created_at"))
    observed = _aware(original.get("fetched_at"))
    start = _aware(frozen.get("start_at"))
    if current.utcoffset() is None or created is None or observed is None or start is None:
        raise ValueError("MARKET_TIMESTAMP_MISSING_OR_NAIVE")
    cutoff = start-timedelta(minutes=ShadowPolicy().target_minutes_to_start)
    if not created <= observed <= current < cutoff:
        raise ValueError("MARKET_TIME_ORDER_OR_T4_FAILED")
    # hbi.prospective_pit's frozen research plan fixes window_seconds at 300.
    if current-observed > timedelta(seconds=300):
        raise ValueError("MARKET_OUTSIDE_EXISTING_RESEARCH_WINDOW")


def combine_original(freeze_path, freeze_sha, artifact_raw, artifact_sha,
                     market_raw, market_sha, output, now, *, source_state_raw=None,
                     source_packet_raw=None, source_evidence=None, runtime_clock=None):
    frozen = checked_json(Path(freeze_path).read_bytes(), freeze_sha)
    artifact = load_artifact(artifact_raw, artifact_sha)
    if frozen["artifact_sha256"] != artifact_sha or frozen["model"] != MODEL:
        raise ValueError("FROZEN_MODEL_CONFLICT")
    current = _aware(now.isoformat())
    created = _aware(frozen["created_at"])
    if current is None or created is None or current < created:
        raise ValueError("MARKET_READ_BEFORE_FUNDAMENTAL_FREEZE")
    original = checked_json(market_raw, market_sha)
    _, key, number = frozen["race_id"].split(":")
    endpoint = f"/game/{key}/betdistribution/winodds/{number}"
    if (original.get("path") != endpoint or original.get("url") != "https://www.rikstoto.no/api"+endpoint
            or original.get("body_sha256") != digest(original["body"])
            or original["body"].get("success") is not True):
        raise ValueError("MARKET_ORIGINAL_RACE_OR_BODY_CONFLICT")
    quotes = original["body"]["result"]
    if any(type(r.get("startNumber")) is not int for r in quotes):
        raise ValueError("INVALID_WIN_SELECTION")
    prices = {str(r["startNumber"]): r.get("odds") for r in quotes}
    if len(prices) != len(quotes) or set(prices) != set(frozen["fundamental"]):
        raise ValueError("MARKET_ACTIVE_FIELD_OR_SCRATCH_CONFLICT")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 1 for v in prices.values()):
        raise ValueError("INVALID_WIN_ODDS")
    if frozen["scope"] == "PROSPECTIVE":
        check_market_clock(frozen, original, current)
        verify_prospective_freeze(frozen, artifact, source_packet_raw, source_state_raw, source_evidence,
                                  artifact_sha256=artifact_sha)
        from .private_win_archive import _blob, verify_win

        retention = original.get("raw_retention")
        if not isinstance(retention, dict):
            raise ValueError("ORIGINAL_WIN_RETENTION_REQUIRED")
        root = Path(retention["root"])
        retained = verify_win(root, retention["receipt_sha256"])
        if (retained["race_id"] != frozen["race_id"] or retained["source_uri"] != original["url"]
                or retained["response_completed_at_utc"] != original["fetched_at"]
                or json.loads(_blob(root, retained["body_sha256"])) != original["body"]):
            raise ValueError("ORIGINAL_WIN_RETENTION_BINDING_CONFLICT")
        current = runtime_clock() if runtime_clock else datetime.now(UTC)
        check_market_clock(frozen, original, current)
        completed = _aware(original["fetched_at"])
        for quote in quotes:
            updated = _aware(quote.get("lastUpdated"))
            if updated is None or updated > completed or completed-updated > timedelta(seconds=300):
                raise ValueError("PROVIDER_MARKET_TIME_UNVERIFIED_OR_STALE")
    market = normalize_market_odds(prices)
    beta, alpha = artifact["market_fundamental_weights"]
    combined = combine_probabilities(frozen["fundamental"], market,
        fundamental_weight=alpha, market_weight=beta)
    policy = ShadowPolicy()
    rows = []
    for runner in frozen["active"]:
        selection = runner["selection_id"]
        assessment = assess_value(probability=combined[selection], available_price=prices[selection],
            policy=DecisionPolicy(policy.minimum_edge, policy.safety_margin))
        status = {"BET": "SHADOW_VALUE", "WATCH": "SHADOW_WATCH", "PASS": "SHADOW_PASS"}[assessment.decision.value]
        rows.append({**runner, "fundamental_p": frozen["fundamental"][selection],
            "market_p": market[selection], "combined_p": combined[selection],
            "fair_odds": fair_odds(combined[selection]), "minimum_odds": assessment.minimum_price,
            "WIN": prices[selection], "EV": assessment.expected_value, "status": status,
              "scope": "PROSPECTIVE_SHADOW" if frozen["scope"] == "PROSPECTIVE" else "RETROSPECTIVE_NON_EXECUTABLE",
              "uncertainty": "UNCALIBRATED_AT_DECISION_TIME",
            "market_observed_at": original.get("fetched_at"), "market_read_at": current.isoformat(),
            "freeze_at": frozen["created_at"], "model": MODEL, "bet_authority": False})
    decision = {"schema": "BENCHMARK002_SHADOW_DECISION_V1", "race_id": frozen["race_id"],
        "scope": "PROSPECTIVE_SHADOW" if frozen["scope"] == "PROSPECTIVE" else "RETROSPECTIVE_NON_EXECUTABLE",
        "rows": rows, "artifact_sha256": artifact_sha,
        "fundamental_freeze_sha256": freeze_sha, "market_file_sha256": market_sha,
        "market_body_sha256": original["body_sha256"],
        "PIT_CERTIFIED": frozen["scope"] == "PROSPECTIVE", "BET_AUTHORITY": False}
    freeze(Path(output), decision)
    return decision


def main(argv=None):
    """Explicit manual command; runtime clocks cannot be supplied or backdated."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("fundamental", "combine"))
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fundamental-freeze", type=Path)
    parser.add_argument("--freeze-sha256")
    args = parser.parse_args(argv)
    try:
        if args.phase == "fundamental":
            result = freeze_fundamental(args.artifact.read_bytes(), args.artifact_sha256,
                args.input.read_bytes(), args.input_sha256, args.output, datetime.now(UTC))
        else:
            if args.fundamental_freeze is None or args.freeze_sha256 is None:
                raise ValueError("FUNDAMENTAL_FREEZE_REQUIRED")
            result = combine_original(args.fundamental_freeze, args.freeze_sha256,
                args.artifact.read_bytes(), args.artifact_sha256, args.input.read_bytes(),
                args.input_sha256, args.output, datetime.now(UTC))
    except (ValueError, KeyError, TypeError, OSError) as error:
        reason = str(error)
        status = ("BLOCKED_MODEL" if reason.startswith(("ARTIFACT_", "MODEL_AFTER_TARGET", "INVALID_PROBABILITIES"))
                  else "BLOCKED_SOURCE" if args.phase == "fundamental" else "BLOCKED_MARKET")
        print(json.dumps({"status": status, "reason": reason, "bet_authority": False}))
        return 2
    print(json.dumps({"status": "FROZEN", "race_id": result["race_id"],
                      "scope": result["scope"], "bet_authority": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
