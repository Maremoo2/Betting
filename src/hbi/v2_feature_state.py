"""Incremental observed V2 state, using the original day-delayed updater.

Neither native IDs nor locally recorded captures confer independent PIT status.
Incomplete careers/network coverage remain explicit in every resulting snapshot.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from rikstoto_crawler.archive import verify_outcome
from rikstoto_crawler.transport import digest

from . import benchmark002_retrospective as bench
from .historical_truth import verify_field
from .research_lab import freeze
from .t4_evidence import _aware
from .v2_result_codes import native, result_code


def checked(raw, expected):
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("SOURCE_SHA_MISMATCH")
    return json.loads(raw)


def normalize_original(raw, receipt, roster, *, country, source_id):
    """Decode the existing literal result contract after exact source/field checks."""
    if country not in {"NO", "SE"}:
        raise ValueError("COUNTRY_NOT_SOURCE_VERIFIED")
    source = urlsplit(receipt["source_uri"])
    parts = source.path.split("/")
    if (source.scheme != "https" or source.hostname != "www.rikstoto.no"
            or len(parts) != 7 or parts[1:4] != ["api", "results", "raceDays"]
            or parts[-1] != "completeresults" or receipt.get("http_status") != 200):
        raise ValueError("UNRECOGNIZED_RESULT_SOURCE")
    key, number = parts[4], int(parts[5])
    day = key[-10:]
    if date.fromisoformat(day).year == 2025:
        raise ValueError("LOCKBOX_2025")
    body = checked(raw, receipt["raw_sha256"])
    if body.get("success") is not True or not _aware(receipt.get("observed_at_utc")):
        raise ValueError("RESULT_OR_CAPTURE_CLOCK_INVALID")
    result = body["result"]
    if result.get("isComplete") is not True or result["startTime"][:10] != day:
        raise ValueError("INCOMPLETE_OR_WRONG_DAY_RESULT")
    ok, reason = verify_field(roster, key, number, result)
    if not ok or reason:
        raise ValueError("ORIGINAL_FIELD_CONFLICT:"+str(reason))
    active = {str(r["startNumber"]): r for r in roster if r["isScratched"] is False}
    outcome = verify_outcome(roster, sorted(active), result)
    if outcome["dead_heat"]:
        raise ValueError("DEAD_HEAT_EXCLUDED_BY_ORIGINAL_V2_POLICY")
    events = []
    for row in result["results"]:
        selection = str(row["startNumber"])
        if selection not in active:
            continue
        registration = row["horseRegistrationNumber"]
        if not native(registration) or registration != active[selection]["horseRegistrationNumber"]:
            raise ValueError("HORSE_ID_OR_SELECTION_CONFLICT")
        decoded = result_code(row, False)
        if decoded["code_exclusions"]:
            raise ValueError("UNSUPPORTED_RESULT_SEMANTICS:"+"|".join(decoded["code_exclusions"]))
        events.append({"race_id": f"RIKSTOTO:{key}:{number}", "race_date": day,
            "horse_id": "RIKSTOTO_REG:"+registration, "native_registration": registration,
            "horse_display": row["horseName"], "start_number": selection,
            "country": country, "track": key.split("_")[0], "identity_status": "EXACT_SOURCE_NATIVE_REGISTRATION",
            "record_eligible": True, "scratched": False, "dead_heat": False,
            "winner": selection == outcome["winners"][0], "race_time": decoded["race_time"],
            "gallop_status": decoded["gallop_status"], "result_version": digest(body),
            "source_body_hash": digest(body), "source_hash": receipt["raw_sha256"],
            "source_id": source_id, "source_url": receipt["source_uri"],
            "archived_at": receipt["observed_at_utc"], "published_at": None,
            "availability_evidence": [], "independent_identity_attested": False})
    winners = [r.get("prize") for r in result["results"] if r.get("place") == 1]
    purse = math.log1p(winners[0]) if len(winners)==1 and type(winners[0]) in (int, float) and winners[0]>0 else None
    return {"race_id": events[0]["race_id"], "day": day, "country": country,
            "track": key.split("_")[0], "events": events, "purse": purse,
            "observed_at": receipt["observed_at_utc"], "source_sha256": receipt["raw_sha256"],
            "body_sha256": digest(body), "source_uri": receipt["source_uri"], "source_id": source_id}


def advance(workspace, previous, fields, cutoff, *, retrospective=False):
    """Idempotent full-day commits. Same-day observations remain pending.

    The exact original V2 has one-day delayed rating/history updates. An arriving
    result can be journalled immediately, but cannot change same-day predictions.
    """
    instant = _aware(cutoff)
    if instant is None:
        raise ValueError("CUTOFF_NAIVE_OR_MISSING")
    if previous["last_day"] >= instant.astimezone(ZoneInfo("Europe/Oslo")).date().isoformat():
        raise ValueError("STATE_NOT_BEFORE_TARGET_DAY")
    if not retrospective:
        for source in previous["applied_races"].values():
            observed = _aware(source.get("archived_at"))
            if observed is None or observed >= instant:
                raise ValueError("BASE_SOURCE_NOT_KNOWN_BEFORE_CUTOFF")
    state = copy.deepcopy(previous)
    by_id = {}
    pending, excluded = [], []
    for field in fields:
        rid = field["race_id"]
        if field["day"][:4] == "2025":
            raise ValueError("LOCKBOX_2025")
        observed = _aware(field.get("observed_at"))
        if not retrospective and (observed is None or observed >= instant):
            excluded.append({"race_id": rid, "reason": "SOURCE_NOT_KNOWN_BEFORE_CUTOFF"})
            continue
        if field["day"] >= instant.astimezone(ZoneInfo("Europe/Oslo")).date().isoformat():
            pending.append(rid)
            continue
        old = state["applied_races"].get(rid)
        if old:
            if old.get("source_hash") != field["source_sha256"]:
                raise ValueError("RESULT_REVISION_REQUIRES_REBUILD:"+rid)
            continue
        if field["day"] <= state["last_day"]:
            raise ValueError("OUT_OF_ORDER_BACKFILL_REQUIRES_REBUILD:"+rid)
        if rid in by_id and by_id[rid]["body_sha256"] != field["body_sha256"]:
            raise ValueError("CONFLICTING_RESULT_VERSIONS:"+rid)
        by_id[rid] = field
    selected = sorted(by_id.values(), key=lambda r: (r["day"], r["race_id"]))
    events = [e for f in selected for e in f["events"]]
    targets = [{"race_id": f["race_id"], "day": f["day"], "track": f["track"],
                "horse_ids": [e["horse_id"] for e in f["events"]]} for f in selected]
    sources = {f["race_id"]: f for f in selected}

    def purse_loader(_workspace, row):
        return sources[row["race_id"]]["purse"]

    def checkpoint(day, histories, ratings, admitted):
        for rid in admitted:
            f = sources[rid]
            state["applied_races"][rid] = {"race_date": f["day"], "archived_at": f["observed_at"],
                "published_at": None, "source_url": f["source_uri"], "source_id": f["source_id"],
                "source_hash": f["source_sha256"], "source_body_hash": f["body_sha256"]}
            for e in f["events"]:
                state["event_refs"].setdefault(e["horse_id"], []).append(rid)
                state["identities"][e["horse_id"]] = {"native_registration": e["native_registration"],
                    "last_source_name": e["horse_display"], "identity_scope": "EXACT_RIKSTOTO_NATIVE_NOT_INDEPENDENT_REGISTER"}
        state["histories"] = {h: [[str(r[0]), r[1], float(r[2]) if r[2] is not None else None,
                                  float(r[3]) if r[3] is not None else None, float(r[4])]
                                 for r in values] for h, values in histories.items()}
        state["ratings"] = {h: float(value) for h, value in ratings.items()}
        state["last_day"] = str(day)

    races, _, diagnostics = bench.build_races(workspace, events, targets, initial_state=previous,
                                             after_day=checkpoint, purse_loader=purse_loader,
                                             allow_observed_2026=True)
    if len(races) != len(selected):
        raise ValueError("INCREMENTAL_FULL_FIELD_REJECTED:"+str(diagnostics))
    for h, history in state["histories"].items():
        if len(history) != len(state["event_refs"].get(h, [])):
            raise ValueError("STATE_PROVENANCE_ALIGNMENT_BROKEN")
    state.update(cutoff_utc=instant.isoformat(), PIT_CERTIFIED=False, FULL_F3_COVERAGE=False,
                 source_scope="OBSERVED_2015_2024_PLUS_2026_NOT_COMPLETE_CENSUS")
    return state, {"new_fields": len(races), "pending_same_day": pending, "excluded": excluded,
                   "retrospective_date_only": retrospective}


def freeze_state(path, state):
    freeze(path, state)
    raw = Path(path).read_bytes()
    restored = json.loads(raw)
    if restored != state:
        raise ValueError("STATE_READBACK_MISMATCH")
    return hashlib.sha256(raw).hexdigest()


def append_research_ledger(path, key, payload):
    """One isolated hash-chained CSV; identical retries are no-ops."""
    path = Path(path)
    lock = path.with_suffix(path.suffix+".lock")
    fields = ("key", "payload_sha256", "previous_row_sha256", "row_sha256", "payload_json")
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    payload_sha = hashlib.sha256(content.encode()).hexdigest()
    with lock.open("x"):
        pass
    try:
        previous = "0"*64
        existing = []
        if path.exists():
            with path.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != list(fields):
                    raise ValueError("RESEARCH_LEDGER_HEADER_INVALID")
                existing = list(reader)
        matched = None
        seen = set()
        for row in existing:
            current = digest([row["key"], row["payload_sha256"], previous])
            if (row["previous_row_sha256"] != previous or row["row_sha256"] != current
                    or hashlib.sha256(row["payload_json"].encode()).hexdigest()!=row["payload_sha256"]):
                raise ValueError("RESEARCH_LEDGER_TAMPERED")
            previous = current
            if row["key"] in seen:
                raise ValueError("RESEARCH_LEDGER_DUPLICATE_KEY")
            seen.add(row["key"])
            if row["key"] == key:
                matched = row
        if matched is not None:
            if matched["payload_sha256"] != payload_sha:
                raise ValueError("RESEARCH_LEDGER_KEY_CONFLICT")
            return False
        value = {"key": key, "payload_sha256": payload_sha, "previous_row_sha256": previous,
                 "row_sha256": digest([key, payload_sha, previous]), "payload_json": content}
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if not existing:
                writer.writeheader()
            writer.writerow(value)
            f.flush()
            os.fsync(f.fileno())
        return True
    finally:
        lock.unlink()
