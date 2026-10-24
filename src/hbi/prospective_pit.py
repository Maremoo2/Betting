"""One-shot research snapshots and sealed offline replay; never a scheduler/model."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .date_overview import timestamp
from .history_feasibility import SCENARIOS, local_instant, select_asof
from .pdf_validation import sha

VERSION = "M7B2C_SNAPSHOT_V1"
ROLES = ("PROGRAM", "HISTORY")
MAX_BYTES = 2_000_000
SAFE_KEYS = {"races", "id", "date", "number", "sport", "status", "track", "countryCode", "name", "starts", "horse",
    "scratched", "scheduledStartTime", "startTime", "distance", "startMethod", "history", "event_date", "test_only",
    "result", "place", "kmTime", "minutes", "seconds", "tenths", "galloped", "disqualified"}
PRIVATE_KEYS = {"owner", "breeder", "trainer", "driver", "jockey", "person", "firstname", "lastname",
    "email", "phone", "address", "birth", "contact", "license", "account", "credentials", "token"}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_once(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("SYMLINK_FORBIDDEN")
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o444)


def now():
    return datetime.now(UTC)


def cutoff(target, minutes):
    return timestamp(local_instant(target["scheduled_start_local"], target["timezone"])) - timedelta(minutes=minutes)


def source_url(url, target, mode):
    if url is None:
        return
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment or parsed.query
            or parsed.netloc != "www.atg.se"
            or parsed.path != f"/services/racinginfo/v1/api/games/vinnare_{target['race_id']}"):
        raise ValueError("UNAPPROVED_SOURCE_URL")
    if mode == "REAL" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d+_\d+", target["race_id"]):
        raise ValueError("INVALID_OFFICIAL_RACE_ID")


def validate_plan(plan):
    if (plan["schema"] != VERSION or plan["mode"] not in {"REAL", "TEST_ONLY"}
            or plan["model_eligible"] is not False or plan["automatic_collection"] is not False
            or not 1 <= len(plan["targets"]) <= 2 or plan["window_seconds"] != 300):
        raise ValueError("BOUNDED_RESEARCH_PLAN_REQUIRED")
    timestamp(plan["created_at"])
    ids = set()
    for t in plan["targets"]:
        if t["country"] not in {"NO", "SE"} or t["timezone"] != {"NO": "Europe/Oslo", "SE": "Europe/Stockholm"}[t["country"]]:
            raise ValueError("COUNTRY_TIMEZONE_CONFLICT")
        if t["race_id"] in ids or not re.fullmatch(r"[A-Za-z0-9_-]+", t["race_id"]):
            raise ValueError("DUPLICATE_OR_UNSAFE_TARGET")
        ids.add(t["race_id"])
        start = cutoff(t, 0)
        if plan["mode"] == "REAL" and t["race_id"][:10] != t["scheduled_start_local"][:10]:
            raise ValueError("TARGET_DATE_CONFLICT")
        if start <= timestamp(plan["created_at"]):
            raise ValueError("PLAN_MUST_PRECEDE_TARGET")
        if set(t["sources"]) != set(ROLES):
            raise ValueError("EXPLICIT_REQUIRED_ROLES")
        for role in ROLES:
            source_url(t["sources"][role]["url"], t, plan["mode"])
            if t["sources"][role]["purpose"] not in {"INPUT", "CONTROL_LABEL"}:
                raise ValueError("INVALID_SOURCE_PURPOSE")
        expected = t["expected_runner_ids"]
        if (expected is not None and (len(expected) < 2 or any(type(i) is not int or i <= 0 for i in expected)
                or len(set(expected)) != len(expected))):
            raise ValueError("INVALID_EXPECTED_FIELD")
    return plan


def init_store(plan_path, root):
    raw = Path(plan_path).read_bytes()
    plan = validate_plan(json.loads(raw))
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    write_once(root / "plan.json", raw)
    registered = now().isoformat() if plan["mode"] == "REAL" else plan["created_at"]
    write_once(root / "registration.json", encode({"registered_at": registered, "mode": plan["mode"], "plan_sha256": sha(raw)}))
    return {"plan_sha256": sha(raw), "mode": plan["mode"], "planned_races": len(plan["targets"]),
        "planned_rounds": 4 * len(plan["targets"]), "automatic_collection": False, "model_eligible": False}


def read_plan(root, expected):
    path = Path(root) / "plan.json"
    if path.is_symlink() or sha(path.read_bytes()) != expected:
        raise ValueError("PLAN_CHANGED")
    return validate_plan(json.loads(path.read_bytes()))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_FORBIDDEN")


def fetch_raw(url):
    """Public GET only, normal inherited proxy/CA, no retries/login/bypass."""
    req = urllib.request.Request(url, headers={"User-Agent": "Betting-bounded-research/1.0", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as response:
            body = response.read(MAX_BYTES + 1)
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        return exc.code, {}, b""  # Do not persist arbitrary error pages.


def privacy_check(body):
    """Only structured non-personal race data; opaque PDF/HTML not auto-cleared."""
    if len(body) > MAX_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise TypeError("STRUCTURED_SOURCE_OBJECT_REQUIRED")
    def check(v):
        if isinstance(v, dict):
            for k, item in v.items():
                if str(k).casefold() in PRIVATE_KEYS:
                    raise ValueError("PERSONAL_OR_UNRELATED_FIELDS_REJECTED")
                if k not in SAFE_KEYS:
                    raise ValueError("UNREVIEWED_OR_UNRELATED_FIELD_REJECTED")
                if k in {"races", "starts"} and (not isinstance(item, list) or any(not isinstance(x, dict) for x in item)):
                    raise ValueError("INVALID_SOURCE_LIST")
                if k in {"horse", "track", "result"} and not isinstance(item, dict):
                    raise ValueError("INVALID_SOURCE_OBJECT")
                check(item)
        elif isinstance(v, list):
            for item in v:
                check(item)
        elif isinstance(v, str) and (re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", v) or re.search(r"https?://", v)):
            raise ValueError("CONTACT_OR_EMBEDDED_LINK_REJECTED")
    check(value)
    return value


def capture(root, plan_sha, race_id, minutes, *, fetch=None, clock=None):
    root = Path(root)
    plan = read_plan(root, plan_sha)
    if (root / "seal.json").exists():
        raise ValueError("STORE_SEALED")
    if minutes not in SCENARIOS:
        raise ValueError("UNKNOWN_CUTOFF")
    if plan["mode"] == "REAL" and (fetch is not None or clock is not None):
        raise ValueError("REAL_OBSERVATIONS_CANNOT_BE_INJECTED")
    if plan["mode"] == "TEST_ONLY" and (fetch is None or clock is None):
        raise ValueError("TEST_ONLY_CANNOT_USE_LIVE_TRANSPORT")
    t = next(t for t in plan["targets"] if t["race_id"] == race_id)
    fetch, clock = fetch or fetch_raw, clock or now
    folder = root / "captures" / race_id / str(minutes)
    # Two explicit attempts per slot; never an automatic retry/loop/scheduler.
    attempt = sum(p.is_dir() for p in folder.glob("*")) + 1
    if attempt > 2:
        raise ValueError("ATTEMPT_BUDGET_EXHAUSTED")
    folder = folder / str(attempt)
    folder.mkdir(parents=True, exist_ok=False)
    records = []
    registered = timestamp(json.loads((root / "registration.json").read_bytes())["registered_at"])
    for role in ROLES:
        spec = t["sources"][role]
        started = clock()
        timestamp(started.isoformat())
        item = {"role": role, "purpose": spec["purpose"], "url": spec["url"], "request_started_at": started.isoformat(),
            "planned_cutoff_at": cutoff(t, minutes).isoformat(), "http_status": None, "headers": {},
            "observed_at": None, "body_sha256": None, "body_file": None, "status": "NOT_OBSERVED", "error": None}
        if spec["url"] is None:
            item["error"] = "SOURCE_NOT_CONFIGURED"
        else:
            try:
                code, headers, body = fetch(spec["url"])
                observed = clock()
                if observed < started or started < max(timestamp(plan["created_at"]), registered):
                    raise ValueError("CLOCK_ORDER_CONFLICT")
                item.update(http_status=code, observed_at=observed.isoformat(),
                    headers={k.lower(): v for k, v in headers.items() if k.lower() in {"date", "etag", "last-modified", "content-type", "age"}})
                if code != 200:
                    raise ValueError("PROVIDER_UNAVAILABLE")
                privacy_check(body)
                item.update(body_sha256=sha(body), body_file=f"{role}.json", status="OBSERVED")
                write_once(folder / item["body_file"], body)
            except (ValueError, TypeError, OSError, TimeoutError, UnicodeError) as exc:
                item.update(status="ERROR", error=type(exc).__name__ + ":" + str(exc))
        records.append(item)
    record = {"schema": VERSION, "mode": plan["mode"], "plan_sha256": plan_sha, "race_id": race_id,
        "cutoff_minutes": minutes, "attempt": attempt, "records": records, "model_eligible": False}
    raw = encode(record)
    write_once(folder / "capture.json", raw)
    return {"capture_sha256": sha(raw), "path": str(folder.relative_to(root)), "records": records,
        "mode": plan["mode"], "model_eligible": False}


def store_files(root):
    files = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_symlink():
            raise ValueError("SYMLINK_FORBIDDEN")
        if p.is_file() and p.relative_to(root) != Path("seal.json"):
            files[str(p.relative_to(root))] = sha(p.read_bytes())
    return files


def seal(root, plan_sha):
    root = Path(root)
    plan = read_plan(root, plan_sha)
    for folder in root.glob("captures/*/*/*"):
        if folder.is_dir() and not (folder / "capture.json").is_file():
            raise ValueError("INCOMPLETE_CAPTURE_NOT_SEALABLE")
    issued = now().isoformat() if plan["mode"] == "REAL" else max([plan["created_at"]] + [json.loads(p.read_bytes())["records"][0]["request_started_at"] for p in root.glob("captures/*/*/*/capture.json")])
    raw = encode({"schema": VERSION, "plan_sha256": plan_sha, "mode": plan["mode"], "issued_at": issued, "files": store_files(root)})
    write_once(root / "seal.json", raw)
    return {"seal_sha256": sha(raw), "plan_sha256": plan_sha, "mode": plan["mode"], "model_eligible": False}


def roster_check(body, target):
    """Existing ATG field names only; no PDF/history parser or feature construction."""
    raw = json.loads(body)
    if len(raw.get("races", [])) != 1:
        return {"status": "UNRESOLVED", "reasons": ["PHYSICAL_RACE_UNRESOLVED"]}
    r = raw["races"][0]
    if (r.get("id") != target["race_id"] or r.get("sport") != "trot" or r.get("track", {}).get("countryCode") != target["country"]):
        return {"status": "CONFLICT", "reasons": ["RACE_OR_COUNTRY_CONFLICT"]}
    if r.get("status") == "results" or any(s.get("result") for s in r.get("starts", [])):
        return {"status": "CONFLICT", "reasons": ["RESULT_LABEL_NOT_PRE_RACE_INPUT"]}
    starts = r.get("starts", [])
    ids = [s.get("horse", {}).get("id") for s in starts]
    reasons = []
    if r.get("date") != target["scheduled_start_local"][:10]:
        reasons.append("SOURCE_DATE_CONFLICT")
    clock = r.get("scheduledStartTime")
    if not clock:
        reasons.append("SCHEDULE_NOT_CORROBORATED")
    elif timestamp(local_instant(clock, target["timezone"])) != cutoff(target, 0):
        reasons.append("SOURCE_SCHEDULE_CHANGED")
    if len(starts) < 2 or any(type(i) is not int or i <= 0 for i in ids):
        reasons.append("HORSE_IDENTITY_MISSING")
    if any(type(s.get("number")) is not int or s["number"] <= 0 for s in starts):
        reasons.append("START_NUMBER_MISSING_OR_INVALID")
    if len(set(ids)) != len(ids) or len({s.get("number") for s in starts}) != len(starts):
        reasons.append("IDENTITY_COLLISION")
    if target["expected_runner_ids"] is None:
        reasons.append("EXPECTED_FULL_FIELD_UNKNOWN")
    elif set(ids) != set(target["expected_runner_ids"]):
        reasons.append("INCOMPLETE_OR_CHANGED_FIELD")
    if any(type(s.get("scratched")) is not bool for s in starts):
        reasons.append("SCRATCH_STATE_UNKNOWN")
    return {"status": "SOURCE_FIELD_MATCH" if not reasons else "UNRESOLVED", "reasons": reasons,
        "runner_count": len(starts), "observed_ids": ids, "identity_scope": "SOURCE_ID_PRESENCE_NOT_HISTORICAL_IDENTITY_ADMISSION",
        "normalized_fields": {"race_id": r["id"], "country": target["country"], "runner_ids": ids}, "model_eligible": False}


def replay(root, seal_sha):
    root = Path(root)
    raw = (root / "seal.json").read_bytes()
    if sha(raw) != seal_sha or (root / "seal.json").is_symlink():
        raise ValueError("SEAL_CHANGED")
    sealed = json.loads(raw)
    if store_files(root) != sealed["files"]:
        raise ValueError("SEALED_SNAPSHOT_CHANGED")
    plan = read_plan(root, sealed["plan_sha256"])
    registration = json.loads((root / "registration.json").read_bytes())
    if registration["mode"] != plan["mode"] or registration["plan_sha256"] != sealed["plan_sha256"]:
        raise ValueError("REGISTRATION_CONFLICT")
    captures, verified = [], 0
    for p in sorted(root.glob("captures/*/*/*/capture.json")):
        event = json.loads(p.read_bytes())
        if event["plan_sha256"] != sealed["plan_sha256"] or event["mode"] != plan["mode"] or event["model_eligible"] is not False:
            raise ValueError("CAPTURE_BINDING_CONFLICT")
        target = next(t for t in plan["targets"] if t["race_id"] == event["race_id"])
        if (event["cutoff_minutes"] not in SCENARIOS or len(event["records"]) != len(ROLES)
                or {i["role"] for i in event["records"]} != set(ROLES)):
            raise ValueError("CAPTURE_ROLE_OR_SLOT_CONFLICT")
        for item in event["records"]:
            source = target["sources"][item["role"]]
            if (item["url"] != source["url"] or item["purpose"] != source["purpose"]
                    or timestamp(item["planned_cutoff_at"]) != cutoff(target, event["cutoff_minutes"])):
                raise ValueError("SOURCE_BINDING_CONFLICT")
            if item["status"] == "OBSERVED" and (not item["observed_at"] or timestamp(item["observed_at"]) < timestamp(item["request_started_at"])
                    or timestamp(item["request_started_at"]) < timestamp(registration["registered_at"])):
                raise ValueError("OBSERVATION_CLOCK_MISSING_OR_INVALID")
            if item["body_file"]:
                if item["body_file"] != f"{item['role']}.json" or sha((p.parent / item["body_file"]).read_bytes()) != item["body_sha256"]:
                    raise ValueError("BODY_HASH_CONFLICT")
                verified += 1
        captures.append((event, p.parent))
    rows = []
    for t in plan["targets"]:
        for minutes in SCENARIOS:
            end = cutoff(t, minutes)
            slot = [e for e, _ in captures if e["race_id"] == t["race_id"] and e["cutoff_minutes"] == minutes]
            selected, exclusions, missing = {}, [], []
            for role in ROLES:
                candidates = []
                lookup = {}
                for event, path in captures:
                    if event["race_id"] != t["race_id"]:
                        continue
                    for item in event["records"]:
                        if item["role"] != role:
                            continue
                        if item["status"] != "OBSERVED":
                            exclusions.append(f"{role}:{item['error'] or item['status']}")
                            continue
                        if item["purpose"] != "INPUT":
                            exclusions.append(f"{role}:LABEL_OR_CONTROL_EXCLUDED")
                            continue
                        if timestamp(item["observed_at"]) >= end:
                            exclusions.append(f"{role}:POST_CUTOFF_EXCLUDED")
                            continue
                        # Explicit research freshness window; not a betting rule.
                        if end - timestamp(item["observed_at"]) > timedelta(seconds=plan["window_seconds"]):
                            exclusions.append(f"{role}:OUTSIDE_DECLARED_WINDOW")
                            continue
                        source_value = json.loads((path / item["body_file"]).read_bytes())
                        if any(r.get("id") == t["race_id"] and (r.get("status") == "results" or any(s.get("result") for s in r.get("starts", []))) for r in source_value.get("races", [])):
                            exclusions.append(f"{role}:RESULT_LABEL_NOT_PRE_RACE_INPUT")
                            continue
                        ref = {"url": item["url"], "sha256": item["body_sha256"], "observed_at": item["observed_at"]}
                        candidates.append(ref)
                        lookup[item["body_sha256"]] = (item, path)
                chosen = select_asof(candidates, end.isoformat())
                if not chosen:
                    missing.append(role)
                    continue
                item, path = lookup[chosen["sha256"]]
                selected[role] = {**chosen, "raw_file": str((path / item["body_file"]).relative_to(root)),
                    "source_published_at": "NOT_REPORTED", "provider_version": item["headers"].get("etag", "NOT_REPORTED"),
                    "source_time_basis": "ACTUAL_OBSERVATION_NOT_HTTP_DATE"}
            field = roster_check((root / selected["PROGRAM"]["raw_file"]).read_bytes(), t) if "PROGRAM" in selected else {"status": "NOT_OBSERVED", "reasons": ["PROGRAM_NOT_OBSERVED"]}
            rows.append({"race_id": t["race_id"], "country": t["country"], "cutoff_minutes": minutes,
                "planned_cutoff_at": end.isoformat(), "cutoff_state_at_seal": "FUTURE" if end > timestamp(sealed["issued_at"]) else "PAST", "attempts_in_slot": len(slot), "slot_status": "NOT_OBSERVED" if not slot else "ATTEMPTED",
                "selected_sources": selected, "missing_roles": missing, "exclusions": sorted(set(exclusions)), "roster": field,
                "source_replay": "PROVEN" if not missing and field["status"] == "SOURCE_FIELD_MATCH" else "NOT_PROVEN",
                "historical_replay": "REPLAY_NOT_PROVEN", "gate_A": "SOURCE_HASH_VERIFIED" if selected else "NOT_OBSERVED",
                "gate_B": "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "gate_C": "SOURCE_RACE_MATCH" if field["status"] == "SOURCE_FIELD_MATCH" else "UNRESOLVED",
                "gate_D": "NOT_ADMITTED", "gate_E": "OBSERVED_BEFORE_CUTOFF" if selected else "NOT_OBSERVED",
                "model_eligible": False})
    return {"schema": VERSION, "mode": plan["mode"], "plan_sha256": sealed["plan_sha256"], "seal_sha256": seal_sha,
        "plan_registered_at": registration["registered_at"], "planned_races": len(plan["targets"]), "planned_snapshot_rounds": 4 * len(plan["targets"]),
        "actual_attempts": len(captures), "stored_source_observations": verified, "hash_verified_sources": verified,
        "complete_historical_replays": 0, "prospective_collection": "NOT_YET_OBSERVED" if plan["mode"] == "TEST_ONLY" or not captures else "NOT_PROVEN" if not verified else "PROVEN" if all(r["source_replay"] == "PROVEN" for r in rows) else "PARTIAL",
        "genuine_source_observations": verified if plan["mode"] == "REAL" else 0, "test_only_source_observations": verified if plan["mode"] == "TEST_ONLY" else 0,
        "missing_input_roles": sum(len(r["missing_roles"]) for r in rows), "source_failure_records": sum(i["status"] == "ERROR" for e, _ in captures for i in e["records"]),
        "identity_conflict_rounds": sum("IDENTITY_COLLISION" in r["roster"]["reasons"] for r in rows),
        "historical_fields_reconstructed": [], "historical_field_exclusions": ["HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "HISTORICAL_IDENTITY_NOT_ADMITTED", "CORRECTION_TIMELINE_UNKNOWN"],
        "complete_replay": "NOT_PROVEN", "existing_model_gates": "CLOSED_UNCHANGED", "model_eligible": False,
        "cutoff_coverage": {str(m): {"planned_rounds": len(plan["targets"]), "slots_not_observed": sum(r["slot_status"] == "NOT_OBSERVED" for r in rows if r["cutoff_minutes"] == m),
            "source_replay_complete": sum(r["source_replay"] == "PROVEN" for r in rows if r["cutoff_minutes"] == m),
            "missing_role_inputs": sum(len(r["missing_roles"]) for r in rows if r["cutoff_minutes"] == m)} for m in SCENARIOS}, "observations": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--plan", type=Path, required=True)
    init.add_argument("--store", type=Path, required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--store", type=Path, required=True)
    cap.add_argument("--plan-sha256", required=True)
    cap.add_argument("--race-id", required=True)
    cap.add_argument("--cutoff-minutes", type=int, choices=SCENARIOS, required=True)
    lock = sub.add_parser("seal")
    lock.add_argument("--store", type=Path, required=True)
    lock.add_argument("--plan-sha256", required=True)
    rep = sub.add_parser("replay")
    rep.add_argument("--store", type=Path, required=True)
    rep.add_argument("--seal-sha256", required=True)
    rep.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "init":
        result = init_store(args.plan, args.store)
    elif args.command == "capture":
        result = capture(args.store, args.plan_sha256, args.race_id, args.cutoff_minutes)
    elif args.command == "seal":
        result = seal(args.store, args.plan_sha256)
    else:
        result = replay(args.store, args.seal_sha256)
        write_once(args.output, encode(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
