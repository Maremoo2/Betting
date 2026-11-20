"""Explicitly unqualified, gap-state research. Never opens the canonical V2 gate."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import timedelta
from pathlib import Path

import numpy as np

from rikstoto_crawler.transport import digest

from .benchmark002_retrospective import race_softmax
from .benchmark002_shadow import checked_json, feature_matrix, load_artifact
from .decision import DecisionPolicy, assess_value
from .probability import combine_probabilities, normalize_market_odds
from .research_lab import freeze
from .shadow import ShadowPolicy
from .t4_evidence import _aware
from .v2_feature_state import append_research_ledger, normalize_original
from .v2_result_codes import native

VARIANT = "V2_OBSERVED_GAP_RESEARCH_V1"


def packet_for_field(state, meeting, number, starts_raw, starts_receipt, start_at, *, country):
    if country not in {"NO", "SE"} or state["last_day"] >= meeting[-10:]:
        raise ValueError("INVALID_COUNTRY_OR_FUTURE_STATE")
    body = checked_json(starts_raw, starts_receipt["sha256"])
    if (starts_receipt.get("status") != 200 or body.get("success") is not True
            or starts_receipt.get("url") != f"https://www.rikstoto.no/api/racedays/{meeting}/starts"):
        raise ValueError("ORIGINAL_STARTLIST_UNVERIFIED")
    raw_roster = body["result"][str(number)]
    runners = []
    for row in raw_roster:
        registration = row["horseRegistrationNumber"]
        if (not native(registration) or row["raceKey"] != f"{meeting}#{number}"
                or row["raceNumber"] != number or type(row["isScratched"]) is not bool):
            raise ValueError("NATIVE_ID_OR_RACE_CONFLICT")
        runners.append({"selection_id": str(row["startNumber"]), "registration": registration,
            "horse_id": "RIKSTOTO_REG:"+registration, "horse_name": row["horseName"], "scratched": row["isScratched"]})
    active = [r for r in runners if not r["scratched"]]
    history = {}
    for row in active:
        horse = row["horse_id"]
        observed = state["histories"].get(horse, [])
        if not observed or not any(e[2] is not None for e in observed) or not any(e[3] is not None for e in observed):
            raise ValueError("MISSING_OBSERVED_HISTORY_TIME_OR_PURSE:"+horse)
        if len(observed) != len(state["event_refs"].get(horse, [])):
            raise ValueError("UNBOUND_HISTORY_PROVENANCE:"+horse)
        if type(state["ratings"].get(horse)) not in (int, float) or not math.isfinite(state["ratings"][horse]):
            raise ValueError("INVALID_OPPONENT_RATING_STATE")
        history[horse] = {"history": observed, "rating": state["ratings"][horse]}
    packet = {"race_id": f"RIKSTOTO:{meeting}:{number}", "day": meeting[-10:],
              "country": country, "sport": "T", "runners": runners, "state": history,
              "start_at": start_at, "source_quality": "PARTIAL_OBSERVED_STATE_NOT_QUALIFIED_V2",
              "known_gaps": state["known_gaps"], "startlist_sha256": starts_receipt["sha256"],
              "source_startlist_completed_at": starts_receipt.get("completed_at"),
              "state_cutoff_utc": state.get("cutoff_utc")}
    feature_matrix(packet)
    return packet


def freeze_limited(path, artifact_raw, artifact_sha, packet, state_sha, protocol,
                   *, now, clock_offset_ms, explicit_research_opt_in=False):
    if not explicit_research_opt_in or protocol.get("variant") != VARIANT:
        raise ValueError("EXPLICIT_LIMITED_RESEARCH_OPT_IN_REQUIRED")
    artifact = load_artifact(artifact_raw, artifact_sha)
    moment, start = _aware(now.isoformat()), _aware(packet.get("start_at"))
    if moment is None or start is None or moment >= start-timedelta(minutes=ShadowPolicy().target_minutes_to_start):
        raise ValueError("LATE_OR_UNVERIFIED_RESEARCH_CLOCK")
    if type(clock_offset_ms) not in (int, float) or not math.isfinite(clock_offset_ms) or abs(clock_offset_ms)>250:
        raise ValueError("CLOCK_OFFSET_NOT_WITHIN_250_MS")
    for name in ("source_startlist_completed_at", "state_cutoff_utc"):
        available = _aware(packet.get(name))
        if available is None or available > moment:
            raise ValueError("SOURCE_AVAILABLE_AFTER_RESEARCH_FREEZE")
    active, matrix = feature_matrix(packet)
    logits = matrix @ np.asarray(artifact["fundamental_weights"])
    p = race_softmax(logits)
    if not np.isfinite(p).all() or (p <= 0).any() or abs(sum(p)-1)>1e-12:
        raise ValueError("INVALID_LIMITED_DISTRIBUTION")
    doc = {"schema": "V2_LIMITED_RESEARCH_FREEZE_V1", "variant": VARIANT,
        "race_id": packet["race_id"], "start_at": start.isoformat(), "frozen_at_utc": moment.isoformat(),
        "state_sha256": state_sha, "artifact_sha256": artifact_sha,
        "packet_sha256": digest(packet), "feature_sha256": digest(matrix.tolist()),
        "protocol_sha256": digest(protocol), "runners": active,
        "conditional_fundamental_p": {r["selection_id"]: float(value) for r, value in zip(active, p)},
        "full_field_sum": float(sum(p)), "qualified_full_field": False, "PIT_CERTIFIED": False,
        "source_quality": packet["source_quality"], "known_gaps": packet["known_gaps"],
        "full_F3_coverage": False, "qualified_decision": "BLOCKED_SOURCE", "BET_AUTHORITY": False,
        "scope": "LIMITED_PROSPECTIVE_RESEARCH_NOT_CANONICAL_V2"}
    doc["prediction_sha256"] = digest(doc["conditional_fundamental_p"])
    freeze(path, doc)
    return doc


def combine_limited(frozen_raw, freeze_sha, artifact_raw, artifact_sha, market_raw, receipt, *, now):
    frozen = checked_json(frozen_raw, freeze_sha)
    artifact = load_artifact(artifact_raw, artifact_sha)
    if (frozen.get("variant") != VARIANT or frozen.get("qualified_full_field") is not False
            or frozen["artifact_sha256"] != artifact_sha):
        raise ValueError("LIMITED_MODEL_IDENTITY_CONFLICT")
    _, meeting, number = frozen["race_id"].split(":")
    if receipt.get("url") != f"https://www.rikstoto.no/api/game/{meeting}/betdistribution/winodds/{number}" or receipt.get("status") != 200:
        raise ValueError("WRONG_MARKET_SOURCE")
    moment = _aware(now.isoformat())
    start = _aware(frozen["start_at"])
    began, completed = _aware(receipt.get("started_at")), _aware(receipt.get("completed_at"))
    froze = _aware(frozen["frozen_at_utc"])
    if any(t is None for t in (moment, start, began, completed, froze)):
        raise ValueError("MARKET_CLOCK_MISSING")
    if not froze <= began <= completed <= moment < start-timedelta(minutes=ShadowPolicy().target_minutes_to_start):
        raise ValueError("MARKET_ORDER_OR_T4_FAILED")
    if moment-completed > timedelta(seconds=300):
        raise ValueError("MARKET_OUTSIDE_EXISTING_RESEARCH_WINDOW")
    body = checked_json(market_raw, receipt["sha256"])
    if body.get("success") is not True or not isinstance(body.get("result"), list):
        raise ValueError("MARKET_UNAVAILABLE")
    quotes = body["result"]
    if any(type(r.get("startNumber")) is not int for r in quotes):
        raise ValueError("INVALID_MARKET_SELECTION")
    prices = {str(r["startNumber"]): r.get("odds") for r in quotes}
    fundamental = frozen["conditional_fundamental_p"]
    if len(prices)!=len(quotes) or set(prices)!=set(fundamental):
        raise ValueError("INCOMPLETE_MARKET_OR_SCRATCH_CONFLICT")
    if any(type(p) not in (int, float) or not math.isfinite(p) or p<=1 for p in prices.values()):
        raise ValueError("INVALID_MARKET_PRICE")
    for quote in quotes:
        updated = _aware(quote.get("lastUpdated"))
        if updated is None:
            raise ValueError("PROVIDER_MARKET_TIMESTAMP_MISSING_OR_NAIVE")
        if updated > completed or completed-updated > timedelta(seconds=300):
            raise ValueError("PROVIDER_MARKET_STALE_OR_FUTURE")
    market = normalize_market_odds(prices)
    beta, alpha = artifact["market_fundamental_weights"]
    combined = combine_probabilities(fundamental, market, fundamental_weight=alpha, market_weight=beta)
    rows = []
    policy = ShadowPolicy()
    for runner in frozen["runners"]:
        key = runner["selection_id"]
        value = assess_value(probability=combined[key], available_price=prices[key],
                             policy=DecisionPolicy(policy.minimum_edge, policy.safety_margin))
        quote = next(q for q in quotes if str(q["startNumber"])==key)
        updated = _aware(quote.get("lastUpdated"))
        rows.append({**runner, "variant": VARIANT, "conditional_fundamental_p": fundamental[key],
            "conditional_combined_p": combined[key], "market_p": market[key], "observed_WIN": prices[key],
            "conditional_fair_odds": value.fair_odds, "conditional_minimum_odds": value.minimum_price,
            "conditional_EV": value.expected_value,
            "limited_research_label": {"BET": "LIMITED_PRICE_ABOVE_FIXED_MINIMUM", "WATCH": "LIMITED_POSITIVE_PRICE_DIFFERENCE", "PASS": "LIMITED_PASS"}[value.decision.value],
            "qualified_decision": "BLOCKED_SOURCE", "qualified_full_field": False,
            "provider_last_updated_raw": quote.get("lastUpdated"),
            "provider_clock_status": "AWARE_SOURCE_CLOCK" if updated else "UNKNOWN_OR_NAIVE_SOURCE_CLOCK",
            "market_response_completed_at": receipt["completed_at"], "source_quality": frozen["source_quality"],
            "early_market_calibration_validated": False, "PIT_CERTIFIED": False, "BET_AUTHORITY": False})
    return {"schema": "V2_LIMITED_RESEARCH_PRICING_V1", "race_id": frozen["race_id"], "variant": VARIANT,
            "rows": rows, "fundamental_freeze_sha256": freeze_sha, "market_sha256": receipt["sha256"],
            "scope": frozen["scope"], "qualified_full_field": False, "qualified_signals": 0,
            "PIT_CERTIFIED": False, "BET_AUTHORITY": False}


def require_registered_pre(ledger, frozen_raw, freeze_sha):
    """Verify the whole existing chain and exact PRE before any POST read."""
    frozen = checked_json(frozen_raw, freeze_sha)
    path = Path(ledger)
    if not path.exists():
        raise ValueError("REGISTERED_PRE_MISSING")
    previous, found, seen = "0"*64, False, set()
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["key", "payload_sha256", "previous_row_sha256", "row_sha256", "payload_json"]:
            raise ValueError("REGISTERED_PRE_LEDGER_HEADER_INVALID")
        for row in reader:
            current = digest([row["key"], row["payload_sha256"], previous])
            if (row["previous_row_sha256"] != previous or row["row_sha256"] != current
                    or hashlib.sha256(row["payload_json"].encode()).hexdigest() != row["payload_sha256"]
                    or row["key"] in seen):
                raise ValueError("REGISTERED_PRE_LEDGER_TAMPERED")
            previous = current
            seen.add(row["key"])
            payload = json.loads(row["payload_json"])
            if (payload.get("record_type") == "LIMITED_RESEARCH_FORECAST"
                    and payload.get("race_id") == frozen["race_id"]
                    and payload.get("fundamental_freeze_sha256") == freeze_sha
                    and payload.get("conditional_fundamental_p") == frozen["conditional_fundamental_p"]
                    and payload.get("frozen_at_utc") == frozen["frozen_at_utc"]):
                found = True
    if not found:
        raise ValueError("REGISTERED_PRE_MISSING_OR_DIFFERENT")
    return frozen


def append_limited_result(ledger, frozen_raw, freeze_sha, result_raw, receipt, roster, *, country):
    """Append a source-verified outcome; never rewrite a forecast.

    Local capture/hash validation is research provenance, not official-source
    independence or PIT certification. Revisions get distinct append-only keys.
    """
    frozen = require_registered_pre(ledger, frozen_raw, freeze_sha)
    if (frozen.get("schema") != "V2_LIMITED_RESEARCH_FREEZE_V1"
            or frozen.get("variant") != VARIANT or frozen.get("qualified_full_field") is not False):
        raise ValueError("LIMITED_RESULT_FORECAST_INVALID")
    start, froze = _aware(frozen.get("start_at")), _aware(frozen.get("frozen_at_utc"))
    captured = _aware(receipt.get("observed_at_utc"))
    if any(t is None for t in (start, froze, captured)) or not froze < start <= captured:
        raise ValueError("RESULT_CAPTURE_ORDER_INVALID")
    field = normalize_original(result_raw, receipt, roster, country=country, source_id="LIMITED_RESULT_APPEND")
    if field["race_id"] != frozen["race_id"]:
        raise ValueError("RESULT_RACE_CONFLICT")
    expected = {r["selection_id"]: r["horse_id"] for r in frozen["runners"]}
    actual = {e["start_number"]: e["horse_id"] for e in field["events"]}
    if expected != actual:
        raise ValueError("RESULT_FIELD_OR_IDENTITY_CONFLICT")
    p = frozen["conditional_fundamental_p"]
    if (set(p) != set(expected) or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in p.values())
            or abs(sum(p.values())-1) > 1e-12):
        raise ValueError("RESULT_FORECAST_DISTRIBUTION_INVALID")
    winner = next(e["start_number"] for e in field["events"] if e["winner"])
    payload = {"record_type": "LIMITED_RESEARCH_RESULT", "race_id": field["race_id"],
        "variant": VARIANT, "fundamental_freeze_sha256": freeze_sha,
        "result_sha256": receipt["raw_sha256"], "result_source_uri": receipt["source_uri"],
        "result_captured_at_utc": receipt["observed_at_utc"], "winner_selection_id": winner,
        "conditional_fundamental_log_loss": -math.log(p[winner]),
        "conditional_fundamental_brier": sum((v-int(k==winner))**2 for k, v in p.items()),
        "closing_line": None, "CLV": None, "dividend": None,
        "qualified_full_field": False, "PIT_CERTIFIED": False, "BET_AUTHORITY": False}
    return append_research_ledger(ledger, field["race_id"]+"|RESULT|"+receipt["raw_sha256"], payload)
