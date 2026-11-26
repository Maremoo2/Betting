"""Offline adapter for Collector prewatch_ready_v1 and the existing PREWATCH004 DRAFT.

This is not a source verifier or a production activation. The expected packet
digest must come from a separately trusted carrier. A digest is not a signature.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .prewatch004_pack import validate_phase_a_draft

OSLO = ZoneInfo("Europe/Oslo")
READY_SCHEMA = "prewatch_ready_v1"
DRAFT_ENVELOPE = "CORE_STABILITY_006A_DRAFT_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"\d{8}T\d{12}Z\Z")
MID = re.compile(r"[A-Z0-9]+_NR_\d{4}-\d{2}-\d{2}\Z")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def canonical(value: Any) -> bytes:
    # Same canonical encoding as Collector prewatch_ready. Reject NaN/Infinity.
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def stamp(value: str) -> datetime:
    require(isinstance(value, str), "006A_TIMESTAMP_INVALID")
    when = datetime.fromisoformat(value)
    require(when.utcoffset() is not None, "006A_NAIVE_TIMESTAMP")
    return when.astimezone(UTC)


def _name(value: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), "006A_NAME_INVALID")
    normalized = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value)
                        .encode("ascii", "ignore").decode().casefold())
    require(bool(normalized), "006A_NAME_INVALID")
    return normalized


def _number(value: Any) -> int:
    require(type(value) is int and value > 0, "006A_RUNNER_NUMBER_INVALID")
    return value


def _indexed(rows: list[dict], key: str) -> dict[int, dict]:
    require(isinstance(rows, list), "006A_ROSTER_SHAPE")
    out = {_number(row[key]): row for row in rows}
    require(len(out) == len(rows), "006A_DUPLICATE_RUNNER")
    return out


def _history_refs(entry: dict, day: date) -> set[str]:
    rows = entry["past_starts"]
    require(isinstance(rows, list) and bool(rows), "006A_HISTORY_MISSING")
    refs = set()
    for row in rows:
        raw = row["raw_text"]
        require(isinstance(raw, str) and bool(raw.strip())
                and date.fromisoformat(row["date"]) < day, "006A_HISTORY_INVALID")
        refs.add(hashlib.sha256(raw.encode("utf-8")).hexdigest())
    return refs


def adapt_ready_packet(packet: dict, *, expected_packet_sha256: str) -> dict:
    """Check selected identity and roster and adapt to existing DRAFT validator.

    Only accepts diagnostic/replay packets; cannot turn shadow into production.
    The full source is retained in the original packet, not recreated here.
    Malformed nested structures fail closed (ValueError).
    """
    try:
        require(isinstance(expected_packet_sha256, str)
                and SHA.fullmatch(expected_packet_sha256) is not None
                and digest(packet) == expected_packet_sha256, "006A_PACKET_HASH_MISMATCH")
        publication_disabled = packet.get("operational_publication_allowed") is False
        bare_replay = packet["replay_only"] is True and "operational_publication_allowed" not in packet
        require(packet["schema"] == READY_SCHEMA and packet["status"] == "SOURCE_READY"
                and type(packet["replay_only"]) is bool
                and packet["phase_a_completed"] is False
                and packet["bet_authority"] is False
                and (publication_disabled or bare_replay)
                and packet["freeze_recheck_required"] is True, "006A_UNSAFE_PACKET")
        day = date.fromisoformat(packet["date_oslo"])
        run = packet["collector_run_id"]
        require(RUN.fullmatch(run) is not None
                and run.startswith(day.strftime("%Y%m%d"))
                and SHA.fullmatch(packet["index_sha256"]) is not None,
                "006A_SOURCE_IDENTITY")
        ref = stamp(packet["reference_utc"])
        require(ref.astimezone(OSLO).date() == day, "006A_REFERENCE_DAY")
        selected = packet["selected"]
        meta, source = selected["metadata"], selected["source_pack"]
        require(sum(item == meta for item in packet["queue"]) == 1,
                "006A_SELECTED_QUEUE_MISMATCH")
        race = source["program"]["race"]
        mid, n = race["meeting_id"], _number(race["race_number"])
        rid = f"RIKSTOTO:{mid}:{n}"
        track = race["track"]
        require(_text(track) and "|" not in track, "006A_TRACK_INVALID")
        physical = unicodedata.normalize("NFC", f"{day}|{track}|{n}")
        require(MID.fullmatch(mid) is not None and mid.endswith(str(day))
                and source["schema"] == "prewatch_source_v1"
                and source["record_type"] == "PHASE_A_SOURCE_PROJECTION"
                and source["race_id"] == meta["race_id"] == rid
                and source["source_run_id"] == run
                and source["date_oslo"] == str(day)
                and source["source_archive_tag"] == f"rikstoto-program-{day}-{run}"
                and meta["ledger_race_id"] == physical
                and source["phase_a_completed"] is False
                and source["bet_authority"] is False
                and meta["data_quality"] == "SOURCE_READY_AS_OF_CAPTURE"
                and SHA.fullmatch(meta["race_pack_sha256"]) is not None
                and _number(meta["source_archive_release_id"]) > 0
                and _number(meta["meeting_release_id"]) > 0
                and "win_odds" not in source["program"], "006A_RACE_OR_MARKET_BOUNDARY")
        require(sum(item.get("race_id") == rid for item in packet["queue"]) == 1
                and sum(item.get("ledger_race_id") == physical
                        for item in packet["queue"]) == 1, "006A_DUPLICATE_QUEUE_RACE")
        start = stamp(meta["scheduled_start_iso"])
        require(start.astimezone(OSLO).date() == day
                and start.astimezone(OSLO).strftime("%H:%M")
                == race["scheduled_time_local"].zfill(5)
                and start.second == start.microsecond == 0
                and start > ref, "006A_START_MISMATCH")
        roster = source["official_roster"]
        require(roster["status"] == "VERIFIED_AS_OF_SOURCE_CAPTURE"
                and roster["source_run_id"] == run
                and roster["first_blocker"] is None, "006A_ROSTER_UNVERIFIED")
        times = []
        for key, path in (
            ("starts_source", f"/api/racedays/{mid}/starts"),
            ("driver_changes_source", f"/api/game/program/{mid}/driverChanges"),
        ):
            receipt = roster[key]
            require(receipt["status"] == "SHA_VERIFIED_SOURCE_RECEIPT"
                    and SHA.fullmatch(receipt["sha256"]) is not None
                    and receipt["url"] == "https://www.rikstoto.no" + path,
                    "006A_ROSTER_RECEIPT_INVALID")
            times.append(stamp(receipt["observed_utc"]))
        oldest = min(times)
        deadline = min(oldest + timedelta(minutes=30), start)
        require(max(times) <= ref < deadline
                and stamp(meta["latest_freeze_utc"]) == deadline,
                "006A_DEADLINE_MISMATCH")
        entries = _indexed(source["program"]["entrants"], "program_number")
        official = _indexed(roster["runners"], "start_number")
        changes = _indexed(roster["driver_changes"], "start_number")
        require(set(entries) == set(official) and set(changes) <= set(official),
                "006A_FULL_FIELD_MISMATCH")
        active, scratched, refs, runners = [], [], {}, []
        for num, row in sorted(official.items()):
            entry = entries[num]
            scratch = row["is_scratched"]
            require(type(scratch) is bool
                    and type(row["driver_change_documented"]) is bool
                    and row["driver_change_documented"] == (num in changes)
                    and _name(row["horse_name"]) == _name(entry["name"])
                    and entry["scratch_state"] == (
                        "SCRATCHED_AS_OF_SNAPSHOT" if scratch else "ACTIVE_AS_OF_SNAPSHOT")
                    and _text(row["effective_driver"])
                    and row["effective_driver"] == (
                        changes[num]["new_driver"] if num in changes
                        else row["original_official_driver"]), "006A_ROSTER_CONFLICT")
            runners.append({"selection_id": str(num), "horse_name": row["horse_name"],
                            "scratched": scratch})
            if scratch:
                scratched.append(num)
            else:
                active.append(num)
                refs[str(num)] = _history_refs(entry, day)
        require(bool(active) and active == meta["active_numbers"]
                and scratched == meta["scratch_numbers"], "006A_ACTIVE_FIELD_MISMATCH")
        require(all(type(x) is int for x in meta["active_numbers"] + meta["scratch_numbers"]),
                "006A_ROSTER_NUMBER_TYPE")
        return {
            "race_id": rid, "physical_race_id": physical, "source": {"run_id": run},
            "runners": runners, "active_count": len(active), "scratch_numbers": scratched,
            "history_refs": refs, "packet_sha256": expected_packet_sha256,
            "reference": ref, "start": start, "deadline": deadline,
            "oldest_roster": oldest, "latest_roster": max(times),
            "roster_sha256": digest({
                "race_id": rid, "start": start.isoformat(),
                "runners": roster["runners"], "driver_changes": roster["driver_changes"],
            }),
        }
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
        raise ValueError("006A_PACKET_STRUCTURE_INVALID") from exc


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_envelope(envelope: dict, adapted: dict) -> None:
    """Bind old DRAFT contract to exact packet, active identities and evidence."""
    try:
        require(set(envelope) == {
            "schema", "packet_sha256", "draft", "sports_first",
            "mispricing_candidate", "history_refs",
        } and envelope["schema"] == DRAFT_ENVELOPE
                and envelope["packet_sha256"] == adapted["packet_sha256"],
                "006A_DRAFT_ENVELOPE_INVALID")
        draft = envelope["draft"]
        validate_phase_a_draft(draft, adapted)
        require("champion_provisional" in draft and "champion_evidence" in draft,
                "006A_MISSING_SCORE_EVIDENCE")
        active = {r["selection_id"]: r["horse_name"] for r in adapted["runners"]
                  if not r["scratched"]}
        for key in ("sports_first", "mispricing_candidate"):
            choice = envelope[key]
            fields = {"selection_id", "horse_name"}
            if key == "mispricing_candidate":
                fields |= {"hypothesis", "counterargument"}
            require(set(choice) == fields
                    and isinstance(choice["selection_id"], str)
                    and choice["selection_id"] in active
                    and choice["horse_name"] == active[choice["selection_id"]],
                    "006A_CANDIDATE_IDENTITY")
        candidate = envelope["mispricing_candidate"]
        require(_text(candidate["hypothesis"]) and _text(candidate["counterargument"])
                and draft["candidate"] == f"#{candidate['selection_id']} {candidate['horse_name']}"
                and draft["counterargument"] == candidate["counterargument"],
                "006A_CANDIDATE_REASONING_MISMATCH")
        references = envelope["history_refs"]
        require(set(references) == set(active), "006A_HISTORY_REF_COVERAGE")
        for number, hashes in references.items():
            require(isinstance(hashes, list) and bool(hashes)
                    and all(isinstance(h, str) for h in hashes)
                    and len(set(hashes)) == len(hashes)
                    and set(hashes) <= adapted["history_refs"][number],
                    "006A_HISTORY_REF_MISMATCH")
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("006A_DRAFT_STRUCTURE_INVALID") from exc
