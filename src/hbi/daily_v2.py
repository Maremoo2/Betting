"""Manual trained-2024 V2 integration. No scheduler, training, DB or bet writer."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ARTIFACT = Path(__file__).with_name("artifacts")/"challenger_v2_2024.json"
ARTIFACT_SHA256 = "cbb9ca7c13032eafc6e639f832f49e2e4cebab0969f501b8170eb62c8853bcf8"


def trained_artifact(path=ARTIFACT):
    from .benchmark002_shadow import load_artifact

    raw = Path(path).read_bytes()
    return raw, load_artifact(raw, ARTIFACT_SHA256)


def collector_packet(root, race_id, *, now):
    """Read existing Collector originals. Never collect odds while loading PRE."""
    from rikstoto_crawler.transport import digest

    from .benchmark002_shadow import checked_json
    from .collector_handoff import OriginalArchive, pdf_field
    from .providers.rikstoto import RikstotoClient
    from .shadow import ShadowPolicy
    from .t4_evidence import _aware

    match = re.fullmatch(r"RIKSTOTO:([A-Za-z0-9]+_NR_\d{4}-\d{2}-\d{2}):([1-9]\d*)", race_id)
    if not match or match[1][-10:-6] == "2025":
        raise ValueError("INVALID_PHYSICAL_RACE_OR_LOCKBOX")
    key, number = match[1], int(match[2])
    archive = OriginalArchive(Path(root))
    try:
        if archive.zipped and (len(archive.zipped.namelist()) != len(archive.names)
                or sum(i.file_size for i in archive.zipped.infolist()) > 100_000_000):
            raise ValueError("UNSAFE_COLLECTOR_ARCHIVE")
        sr, starts_raw = archive.request(key, "starts", race_id, now)
        pr, pdf_raw = archive.request(key, "pdf", race_id, now)
        if sr.get("status") not in (200, "JSON_OK") or pr.get("status") not in (200, "PDF_OK"):
            raise ValueError("COLLECTOR_HTTP_STATUS_UNVERIFIED")
        starts = checked_json(starts_raw, sr["sha256"])
        if starts.get("success") is not True:
            raise ValueError("COLLECTOR_STARTLIST_UNSUCCESSFUL")
        roster = starts["result"][str(number)]
        names = {}
        registrations = set()
        for row in roster:
            n = row.get("startNumber")
            reg = row.get("horseRegistrationNumber")
            if (type(n) is not int or n <= 0 or str(n) in names or reg in registrations
                    or not isinstance(reg, str) or not reg or not row.get("horseName")
                    or type(row.get("isScratched")) is not bool
                    or row.get("raceKey") != key+"#"+str(number) or row.get("raceNumber") != number):
                raise ValueError("COLLECTOR_FIELD_IDENTITY_CONFLICT")
            names[str(n)] = {"name": row["horseName"]}
            registrations.add(reg)
        start_at = pdf_field(pdf_raw, number, names, key[-10:])
        metadata = []
        for record in archive.manifest.get("requests", []):
            if not re.fullmatch(r"https://www[.]rikstoto[.]no/api/racedays(?:/?|/dates/\d{4}-\d{2}-\d{2}(?:/\d{4}-\d{2}-\d{2})?)", record.get("url", "")):
                continue
            stamp = _aware(record.get("at_utc"))
            if stamp is None or stamp > now or record.get("status") not in (200, "JSON_OK"):
                raise ValueError("COLLECTOR_CALENDAR_CLOCK_OR_STATUS_INVALID")
            raw = archive.read(record.get("raw_path") or record.get("path"))
            body = checked_json(raw, record["sha256"])
            if body.get("success") is not True or not isinstance(body.get("result"), list):
                continue
            for meeting in body["result"]:
                if meeting.get("raceDayKey") == key:
                    if (meeting.get("countryIsoCode") not in {"NO", "SE"}
                            or meeting.get("sportType") != "T" or meeting.get("isMultiTrack") is not False):
                        raise ValueError("UNSUPPORTED_OR_COMPOSITE_COLLECTOR_MEETING")
                    races = [r for r in meeting["races"] if r.get("raceNumber") == number]
                    if len(races) != 1 or races[0].get("raceKey") != key+"#"+str(number):
                        raise ValueError("COLLECTOR_CALENDAR_RACE_CONFLICT")
                    canonical = RikstotoClient.parse_timestamp(races[0]["startTime"]).isoformat()
                    metadata.append((meeting["countryIsoCode"], canonical, record["sha256"], stamp))
        if not metadata or len({(m[0], m[1]) for m in metadata}) != 1:
            raise ValueError("COLLECTOR_CALENDAR_MISSING_OR_CONFLICTING")
        if metadata[0][1] != start_at:
            raise ValueError("COLLECTOR_PDF_CALENDAR_START_CONFLICT")
        cutoff = _aware(start_at)-timedelta(minutes=ShadowPolicy().target_minutes_to_start)
        clocks = [_aware(sr.get("at_utc")), _aware(pr.get("at_utc")), *[m[3] for m in metadata]]
        if any(t is None or t >= cutoff for t in clocks):
            raise ValueError("COLLECTOR_ORIGINAL_AT_OR_AFTER_T4")
        return {"race_id": race_id, "key": key, "number": number, "country": metadata[0][0],
            "start_at": start_at, "roster": roster, "starts_raw": starts_raw,
            "starts_receipt": {"url": sr["url"], "sha256": sr["sha256"], "status": 200,
                               "completed_at": sr["at_utc"]},
            "source_hashes": {"starts": sr["sha256"], "program": pr["sha256"],
                              "calendar": sorted({m[2] for m in metadata}), "manifest": digest(archive.manifest)}}
    finally:
        if archive.zipped:
            archive.zipped.close()


def coverage_rows(source, state):
    from .v2_result_codes import native

    rows = []
    for runner in source["roster"]:
        if runner["isScratched"]:
            continue
        reg = runner["horseRegistrationNumber"]
        horse = "RIKSTOTO_REG:"+reg
        history = state.get("histories", {}).get(horse, [])
        blocks = []
        if not isinstance(history, list) or any(not isinstance(e, (list, tuple)) or len(e) != 5 for e in history):
            blocks.append("INVALID_OBSERVED_HISTORY_SHAPE")
            history = []
        if not native(reg):
            blocks.append("PERMANENT_IDENTITY_UNRESOLVED")
        if not history:
            blocks.append("MISSING_OBSERVED_HISTORY")
        if not any(e[2] is not None for e in history):
            blocks.append("MISSING_OBSERVED_CLEAN_TIME")
        if not any(e[3] is not None for e in history):
            blocks.append("MISSING_OBSERVED_WINNER_PRIZE")
        if len(history) != len(state.get("event_refs", {}).get(horse, [])):
            blocks.append("UNBOUND_HISTORY_PROVENANCE")
        rating = state.get("ratings", {}).get(horse)
        if type(rating) not in (int, float) or not math.isfinite(rating):
            blocks.append("MISSING_OR_INVALID_RATING")
        rows.append({"selection_id": str(runner["startNumber"]), "horse_name": runner["horseName"],
            "horse_id": horse, "observed_starts": len(history), "fundamental_p": None,
            "fundamental_fair_odds": None, "conditional_fundamental_p": None,
            "conditional_fundamental_fair_odds": None, "combined_p": None,
            "WIN": None, "EV": None, "signal": "BLOCKED", "PIT_CERTIFIED": False,
            "feature_blockers": ";".join(blocks), "source_quality": "OBSERVED_NOT_PIT_QUALIFIED"})
    return rows


def qualified_market(freeze_path, artifact_raw, output, *, now=None, reader):
    """Lazy Collector/Phase-B access. A caller flag cannot open the source gate."""
    from .benchmark002_shadow import combine_original
    from .v2_source_recovery import audit_market

    frozen_raw = Path(freeze_path).read_bytes()
    frozen = json.loads(frozen_raw)
    if frozen.get("scope") != "PROSPECTIVE" or frozen.get("pit_certified") is not True:
        raise ValueError("WIN_NOT_READ_PIT_UNVERIFIED")
    # All command-created prospective freezes must first pass the canonical
    # freeze_fundamental source adapter. That adapter remains fail-closed today.
    envelope = reader()
    now = now or datetime.now(UTC)
    raw = json.dumps(envelope, ensure_ascii=False, allow_nan=False).encode()
    receipt = {"url": envelope["url"], "status": 200, "sha256": hashlib.sha256(
        json.dumps(envelope["body"]).encode()).hexdigest(),
        "started_at": envelope["fetched_at"], "completed_at": envelope["fetched_at"]}
    market_raw = json.dumps(envelope["body"]).encode()
    packet = {"race_id": frozen["race_id"], "runners": frozen["active"]}
    audit = audit_market(market_raw, receipt, packet, now=now)
    if audit["errors"]:
        raise ValueError("MARKET_NOT_VERIFIED:"+";".join(audit["errors"]))
    return combine_original(freeze_path, hashlib.sha256(frozen_raw).hexdigest(), artifact_raw,
                            ARTIFACT_SHA256, raw, hashlib.sha256(raw).hexdigest(), output, now)


def execute(args, *, now=None, clock_reader=None):
    from rikstoto_crawler.transport import ArchiveClient

    from .benchmark002_shadow import checked_json, freeze_fundamental
    from .local_watcher import clock_offset
    from .research_lab import freeze
    from .shadow import ShadowPolicy
    from .t4_evidence import _aware
    from .v2_feature_state import advance
    from .v2_limited_research import freeze_limited, packet_for_field

    clock_reader = clock_reader or clock_offset
    fixed_now = now  # Library-only test clock; the CLI provides no override.
    now = fixed_now or datetime.now(UTC)
    if _aware(now.isoformat()) is None:
        raise ValueError("RUNTIME_CLOCK_NAIVE")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "DAILY_V2_V1", "status": "BLOCKED", "race_id": args.race_id,
        "executed_at_utc": now.isoformat(), "scope": "PROSPECTIVE", "blockers": [], "rows": [],
        "artifact_sha256": ARTIFACT_SHA256, "PIT_CERTIFIED": False, "BET_AUTHORITY": False,
        "AUTO_BET": False, "MODEL_VALIDATED": False, "WIN_read": False}
    try:
        artifact_raw, model = trained_artifact(args.artifact)
        report.update(model=model["model"], feature_order=model["feature_order"],
            fundamental_weights=model["fundamental_weights"], combination_weights=model["market_fundamental_weights"])
        if args.parity_packet:
            if args.collector_root or args.state or args.limited_protocol or args.market_cache:
                raise ValueError("PARITY_MODE_CANNOT_READ_LIVE_INPUTS_OR_MARKET")
            raw = Path(args.parity_packet).read_bytes()
            packet = checked_json(raw, args.parity_packet_sha256)
            if packet.get("scope") != "RETROSPECTIVE" or packet["race_id"] != args.race_id:
                raise ValueError("PARITY_PACKET_SCOPE_OR_RACE_MISMATCH")
            frozen = freeze_fundamental(artifact_raw, ARTIFACT_SHA256, raw,
                args.parity_packet_sha256, output/"fundamental_freeze.json", now)
            report.update(status="RETROSPECTIVE_PARITY", scope="RETROSPECTIVE_PARITY",
                          source_quality=packet["source_quality"])
            report["rows"] = [{**r, "fundamental_p": frozen["fundamental"][r["selection_id"]],
                "fundamental_fair_odds": 1/frozen["fundamental"][r["selection_id"]],
                "combined_p": None, "WIN": None, "EV": None, "signal": "PARITY_ONLY",
                "PIT_CERTIFIED": False, "source_quality": packet["source_quality"]} for r in frozen["active"]]
        else:
            if not args.collector_root or not args.state or not args.state_sha256:
                raise ValueError("COLLECTOR_AND_HASHED_STATE_REQUIRED")
            source = collector_packet(args.collector_root, args.race_id, now=now)
            state = checked_json(Path(args.state).read_bytes(), args.state_sha256)
            report.update(start_at=source["start_at"], source_hashes=source["source_hashes"],
                          state_sha256=args.state_sha256, known_gaps=state.get("known_gaps", []))
            report["rows"] = coverage_rows(source, state)
            report["blockers"].extend(sorted({b for row in report["rows"] for b in row["feature_blockers"].split(";") if b}))
            report["blockers"].extend(["CANONICAL_V2_SOURCE_ADAPTER_NOT_ATTESTED",
                "INDEPENDENT_PERMANENT_IDENTITY_NOT_ATTESTED", "INDEPENDENT_SCRATCHINGS_NOT_ATTESTED"])
            if state.get("FULL_F3_COVERAGE") is not True or state.get("known_gaps"):
                report["blockers"].append("INCOMPLETE_CAREER_AND_OPPONENT_GRAPH")
            if state.get("PIT_CERTIFIED") is not True:
                report["blockers"].append("HISTORICAL_VERSION_AVAILABILITY_NOT_ATTESTED")
            cutoff = _aware(source["start_at"])-timedelta(minutes=ShadowPolicy().target_minutes_to_start)
            if now >= cutoff:
                raise ValueError("MODEL_AT_OR_AFTER_T4")
            # Reuse existing state availability checks; never persist a changed state here.
            advance(Path(args.state).parent, state, [], now.isoformat())
            packet = packet_for_field(state, source["key"], source["number"], source["starts_raw"],
                source["starts_receipt"], source["start_at"], country=source["country"])
            packet["original_program_sha256"] = source["source_hashes"]["program"]
            freeze(output/"input_packet.json", packet)
            offset_ms = clock_reader("time.windows.com")*1000
            # Source loading and NTP can take time. Never backdate the freeze
            # to the command's initial timestamp.
            now = fixed_now or datetime.now(UTC)
            if now >= cutoff:
                raise ValueError("MODEL_AT_OR_AFTER_T4")
            if args.limited_protocol:
                protocol = json.loads(Path(args.limited_protocol).read_bytes())
                frozen = freeze_limited(output/"limited_fundamental_freeze.json", artifact_raw,
                    ARTIFACT_SHA256, packet, args.state_sha256, protocol, now=now,
                    clock_offset_ms=offset_ms, explicit_research_opt_in=True)
                report["status"] = "LIMITED_RESEARCH"
                for row in report["rows"]:
                    p = frozen["conditional_fundamental_p"][row["selection_id"]]
                    row.update(conditional_fundamental_p=p, conditional_fundamental_fair_odds=1/p,
                               signal="RESEARCH_ONLY", variant=frozen["variant"])
            else:
                packet.update(scope="PROSPECTIVE", clock_offset_ms=offset_ms,
                              canonical_collector_row={"race_id": args.race_id})
                raw = json.dumps(packet).encode()
                frozen = freeze_fundamental(artifact_raw, ARTIFACT_SHA256, raw,
                    hashlib.sha256(raw).hexdigest(), output/"fundamental_freeze.json", now)
                # Existing source gate must grant the freeze before this can run.
                if args.market_cache:
                    _, key, number = args.race_id.split(":")
                    client = ArchiveClient(Path(args.market_cache))
                    decision = qualified_market(output/"fundamental_freeze.json", artifact_raw,
                        output/"market_decision.json", now=fixed_now,
                        reader=lambda: client.get(f"/game/{key}/betdistribution/winodds/{number}", refresh=True))
                    report.update(rows=decision["rows"], WIN_read=True)
    except (ValueError, TypeError, KeyError, OSError, IndexError, zipfile.BadZipFile) as exc:
        report["blockers"].append(str(exc))
    report["blockers"] = sorted(set(report["blockers"]))
    for row in report["rows"]:
        row["race_blockers"] = ";".join(report["blockers"])
    report["active_runners"] = len(report["rows"])
    report["completed_at_utc"] = (fixed_now or datetime.now(UTC)).isoformat()
    report["fundamental_sum"] = sum(row.get("fundamental_p") or row.get("conditional_fundamental_p") or 0 for row in report["rows"])
    freeze(output/"report.json", report)
    if report["rows"]:
        fields = list(dict.fromkeys(k for row in report["rows"] for k in row))
        with (output/"full_field.csv").open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(report["rows"])
    return report


def add_arguments(parser):
    parser.add_argument("--race-id", required=True)
    parser.add_argument("--artifact", type=Path, default=ARTIFACT)
    parser.add_argument("--collector-root", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--state-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limited-protocol", type=Path, help="Explicit unqualified research opt-in; never reads WIN")
    parser.add_argument("--parity-packet", type=Path, help="One historical source packet; no backtest or market")
    parser.add_argument("--parity-packet-sha256")
    parser.add_argument("--market-cache", type=Path, help="Collector cache; accessed only after canonical PIT approval")


def cli(args):
    try:
        report = execute(args)
    except ModuleNotFoundError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": "RESEARCH_DEPENDENCY_MISSING", "module": exc.name,
                          "install": "pip install -e .[dev]"}))
        raise SystemExit(2) from exc
    print(json.dumps({"status": report["status"], "active_runners": report["active_runners"],
                      "blockers": report["blockers"], "report": str(args.output/"report.json")}, ensure_ascii=False))
    if report["status"] == "BLOCKED":
        raise SystemExit(2)
