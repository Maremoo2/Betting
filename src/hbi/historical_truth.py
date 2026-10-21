"""Retrospective authoritative result display, separate from pre-start features."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from rikstoto_crawler.archive import verify_outcome
from rikstoto_crawler.transport import HOST, digest

from .provider_capability import name_key

LEVELS = ("SOURCE_EXCERPT_ONLY", "IDENTITY_VERIFIED", "RESULT_VERIFIED", "PIT_VERIFIED",
          "MODEL_ELIGIBLE", "CONFLICT", "UNRESOLVED")


class HistoricalTruth:
    """Read checksum-pinned, original ArchiveClient envelopes. No network or writes."""

    def __init__(self, path, checksum):
        from .date_overview import timestamp

        raw = Path(path).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if self.sha256 != checksum:
            raise ValueError("HISTORY_ARCHIVE_SHA256_MISMATCH")
        bundle = json.loads(raw)
        if bundle["schema"] != "RIKSTOTO_HISTORICAL_TRUTH_V1":
            raise ValueError("UNSUPPORTED_HISTORY_SCHEMA")
        self.sources = {}
        for source in bundle["sources"]:
            path = source["path"]
            if path in self.sources or source["url"] != HOST + "/api" + path:
                raise ValueError("DUPLICATE_OR_UNTRUSTED_HISTORY_SOURCE")
            if source["body_sha256"] != digest(source["body"]):
                raise ValueError("HISTORY_BODY_HASH_MISMATCH")
            timestamp(source["fetched_at"])
            if source["body"].get("success") is not True:
                raise ValueError("UNSUCCESSFUL_HISTORY_SOURCE")
            self.sources[path] = source
        self.races = []
        for path, source in self.sources.items():
            match = re.fullmatch(r"/results/racedays/(\d{4}-\d{2}-\d{2})/\1/list", path)
            if not match:
                continue
            day = match[1]
            date.fromisoformat(day)
            for group in source["body"]["result"]:
                if group["date"][:10] != day:
                    raise ValueError("HISTORY_LIST_DATE_MISMATCH")
                for meeting in group["raceDays"]:
                    if meeting.get("countryIsoCode") != "NO" or meeting.get("isMultiTrack") is not False:
                        continue
                    key = meeting["raceDay"]
                    if not re.fullmatch(r"[A-Z0-9]+_NR_" + re.escape(day), key):
                        raise ValueError("HISTORY_MEETING_DATE_MISMATCH")
                    roster_source = self.sources.get(f"/racedays/{key}/starts")
                    if not roster_source:
                        continue
                    for race in meeting["races"]:
                        number = race["raceNumber"]
                        rows = roster_source["body"]["result"].get(str(number), [])
                        result_source = self.sources.get(f"/results/raceDays/{key}/{number}/completeresults")
                        if not rows or not result_source:
                            continue
                        start_numbers = [r.get("startNumber") for r in rows]
                        ids = [r.get("horseRegistrationNumber") for r in rows]
                        roster_valid = (
                            type(number) is int and number > 0
                            and len(set(start_numbers)) == len(rows) and len(set(ids)) == len(rows)
                            and all(type(n) is int and n > 0 for n in start_numbers)
                            and all(isinstance(i, str) and i and not i.upper().startswith("TMP") for i in ids)
                            and all(r.get("raceKey") == f"{key}#{number}" and r.get("raceNumber") == number
                                    and type(r.get("isScratched")) is bool for r in rows)
                        )
                        result = result_source["body"]["result"]
                        full_field_error = None
                        try:
                            if not roster_valid:
                                raise ValueError("HISTORICAL_ROSTER_IDENTITY_CONFLICT")
                            active = [str(r["startNumber"]) for r in rows if r["isScratched"] is False]
                            verify_outcome(rows, active, result)
                            result_ids = [r.get("horseRegistrationNumber") for r in result["results"]]
                            if len(result_ids) != len(set(result_ids)):
                                raise ValueError("DUPLICATE_RESULT_IDENTITIES")
                        except (ValueError, KeyError, TypeError) as exc:
                            full_field_error = str(exc)
                        refs = [self.ref(s) for s in (source, roster_source, result_source)]
                        self.races.append({"day": day, "key": key, "number": number,
                                           "track": meeting["raceDayName"], "rows": rows,
                                           "result": result, "roster_valid": roster_valid,
                                           "full_field_error": full_field_error, "sources": refs,
                                           "result_source": result_source})

    def ref(self, source):
        return {"url": source["url"], "path": source["path"],
                "fetched_at": source["fetched_at"], "body_sha256": source["body_sha256"],
                "bundle_sha256": self.sha256, "hash_basis": "ARCHIVECLIENT_CANONICAL_JSON_BODY",
                "published_at": None}

    def link(self, horse, prior, cutoff, day):
        """Use verified registration and official date/race roster, never a text guess."""
        from .date_overview import timestamp

        identity = horse["identity"]
        registration = identity["verified_registration"] if identity["status"] == "VERIFIED" else None
        event_day, number = prior.get("date"), prior.get("race_number")
        record = {"event_date": event_day, "source_race_number": number,
                  "horse_name": horse["name"], "verified_registration": registration,
                  "horse_identity_verified": identity["status"] == "VERIFIED",
                  "historical_race_identity_verified": False, "authoritative_result_verified": False,
                  "pit_verified": False, "model_eligible": False,
                  "status": "IDENTITY_VERIFIED" if registration else "SOURCE_EXCERPT_ONLY",
                  "result": None, "historical_race_id": None, "source_refs": [],
                  "display_mode": "RETROSPECTIVE_TRUTH_NOT_PRE_RACE_FEATURE",
                  "reasons": ["HISTORICAL_PUBLICATION_TIME_NOT_DOCUMENTED",
                              "HISTORICAL_FEATURE_FULL_FIELD_NOT_VERIFIED"],
                  "source_excerpt": prior.get("raw_text"),
                  "excerpt_warning": "UNVERIFIED_SOURCE; MARKET_COLUMNS_ARE_NOT_FEATURES"}
        try:
            if not event_day or date.fromisoformat(event_day) >= date.fromisoformat(day):
                raise ValueError("NOT_A_PRIOR_EVENT")
            if type(number) is not int or number <= 0:
                raise ValueError("HISTORICAL_RACE_NUMBER_UNRESOLVED")
        except ValueError as exc:
            record.update(status="UNRESOLVED", source_excerpt=None)
            record["reasons"].append(str(exc))
            return record
        if identity["status"] == "CONFLICT":
            record.update(status="CONFLICT", source_excerpt=None)
            record["reasons"].append("TARGET_HORSE_IDENTITY_CONFLICT")
            return record
        if not registration:
            record["reasons"].append("TARGET_HORSE_IDENTITY_UNRESOLVED")
            return record
        matches = [r for r in self.races if r["day"] == event_day and r["number"] == number
                   and any(h.get("horseRegistrationNumber") == registration for h in r["rows"])]
        if not matches:
            record["reasons"].append("NO_MATCH_IN_SELECTED_AUTHORITATIVE_SOURCES")
            return record
        if len(matches) != 1:
            record.update(status="CONFLICT", source_excerpt=None)
            record["reasons"].append("MULTIPLE_HISTORICAL_RACE_MATCHES")
            return record
        race = matches[0]
        record["source_refs"] = race["sources"]
        row = next(r for r in race["rows"] if r["horseRegistrationNumber"] == registration)
        if not race["roster_valid"] or name_key(row["horseName"]) != name_key(horse["name"]):
            record.update(status="CONFLICT", source_excerpt=None)
            record["reasons"].append("HISTORICAL_IDENTITY_CONFLICT")
            return record
        record.update(historical_race_identity_verified=True,
                      historical_race_id=f"RIKSTOTO:{race['key']}:{number}", track=race["track"])
        if race["full_field_error"]:
            if any(code in race["full_field_error"] for code in ("IDENTITY", "FIELD_MISMATCH", "DUPLICATE")):
                record["status"] = "CONFLICT"
            record["reasons"].append("FULL_FIELD_RESULT_REJECTED:" + race["full_field_error"])
            return record
        result = race["result"]
        if not result.get("startTime") or result["startTime"][:10] != event_day:
            record["reasons"].append("RESULT_EVENT_TIME_UNRESOLVED")
            return record
        results = [r for r in result["results"] if r.get("horseRegistrationNumber") == registration]
        if len(results) != 1 or row["isScratched"] is not False:
            record["reasons"].append("INDIVIDUAL_RESULT_MISSING_OR_SCRATCHED")
            return record
        result_row = results[0]
        place, km = result_row.get("place"), result_row.get("kmTime")
        placing = place if type(place) is int and place > 0 else None
        record["result"] = {"placing": placing, "place_raw": place, "km_time_raw": km,
                            "distance_m": result_row.get("distance"),
                            "start_method_raw": result.get("startMethod"),
                            "start_time_local_raw": result["startTime"],
                            "status": "WINNER" if placing == 1 else "PLACED" if placing else "UNRESOLVED_CODE",
                            "gallop": None, "disqualified": None, "did_not_finish": None,
                            "code_interpretation": "NO_CODE_LEGEND_VERIFIED; RETAIN_ORIGINAL",
                            "full_result_field_verified": True,
                            "registration": registration, "historical_start_number": result_row["startNumber"],
                            "json_pointer": f"/result/results/{result['results'].index(result_row)}"}
        record.update(status="RESULT_VERIFIED", authoritative_result_verified=True)
        # Acquisition after the target cutoff is not evidence of prior availability.
        if timestamp(race["result_source"]["fetched_at"]) > timestamp(cutoff):
            record["reasons"].append("RESULT_ACQUIRED_AFTER_ANALYSIS_CUTOFF")
        if not placing or not isinstance(km, str) or not re.fullmatch(r"\d{1,2},\d", km):
            record["reasons"].append("RESULT_CODE_OR_TIME_SEMANTICS_UNRESOLVED")
        return record


def attach_history(report, archive, truth):
    """Deduplicate starts, keep every source occurrence and report auditable counters."""
    observations = {}
    for entry, doc in zip(report["races"], archive.data["races"], strict=True):
        analysis = entry["fundamental_analysis"]
        for horse, source_horse in zip(analysis["horses"], doc["entrants"], strict=True):
            horse["historical_results"] = []
            for index, prior in enumerate(source_horse.get("past_starts", [])):
                record = truth.link(horse, prior, analysis["cutoff"], archive.day)
                # Composite entries do not create extra observations. They remain visible in M2/M3.
                if entry["composite_product"]:
                    continue
                identity = horse["identity"]["verified_registration"] or (
                    entry["source_entry_id"] + ":" + horse["selection_id"])
                key = [identity, record["historical_race_id"] or prior.get("date"),
                       prior.get("race_number")]
                oid = hashlib.sha256(json.dumps(key).encode()).hexdigest()
                occurrence = {"source_entry_id": entry["source_entry_id"],
                              "selection_id": horse["selection_id"], "history_index": index,
                              "source_ref": {**horse["facts"]["original_identity"]["source_refs"][0],
                                             "history_index": index}}
                if oid in observations:
                    old = observations[oid]
                    if old["source_excerpt"] != record["source_excerpt"]:
                        old.update(status="CONFLICT", authoritative_result_verified=False,
                                   pit_verified=False, model_eligible=False, result=None)
                        old["reasons"].append("DIVERGENT_EXCERPTS_FOR_SAME_START")
                else:
                    observations[oid] = {**record, "observation_id": oid, "occurrences": []}
                observations[oid]["occurrences"].append(occurrence)
                horse["historical_results"].append(oid)
    for entry in report["races"]:
        for horse in entry["fundamental_analysis"]["horses"]:
            horse_rows = [observations[i] for i in dict.fromkeys(horse["historical_results"])]
            horse["historical_coverage"] = {
                "unique_observations": len(horse_rows),
                "verified_results": sum(r["authoritative_result_verified"] for r in horse_rows),
                "pit_verified": sum(r["pit_verified"] for r in horse_rows),
                "model_eligible": sum(r["model_eligible"] for r in horse_rows),
                "by_status": dict(Counter(r["status"] for r in horse_rows)),
            }
    rows = list(observations.values())
    status = Counter(r["status"] for r in rows)
    report["historical_truth"] = {
        "scope": "SELECTED_AUTHORITATIVE_SOURCES_AND_INDEPENDENT_ARCHIVE_ENTRIES",
        "source_bundle_sha256": truth.sha256, "observations": rows,
        "counts": {"total_unique_observations": len(rows),
                   "source_occurrences": sum(len(r["occurrences"]) for r in rows),
                   "horse_identity_verified": sum(r["horse_identity_verified"] for r in rows),
                   "historical_race_identity_verified": sum(r["historical_race_identity_verified"] for r in rows),
                   "authoritative_result_verified": sum(r["authoritative_result_verified"] for r in rows),
                   "pit_verified": sum(r["pit_verified"] for r in rows),
                   "model_eligible": sum(r["model_eligible"] for r in rows),
                   "by_status": {level: status[level] for level in LEVELS}},
        "reason_counts": dict(Counter(reason for r in rows for reason in dict.fromkeys(r["reasons"]))),
        "deduplication": "VERIFIED_REGISTRATION_OR_SOURCE_SECTION_PLUS_HISTORICAL_RACE_OR_DATE_AND_RACE_NUMBER; DIVERGENT_EXCERPTS_CONFLICT",
        "model_readiness": "BLOCKED", "missing": ["DOCUMENTED_HISTORICAL_AVAILABILITY",
            "VERIFIED_RESULT_CODE_LEGEND", "VERIFIED_FULL_FIELD_PIT_FEATURE_DATASET",
            "TEMPORAL_TRAIN_TEST_DESIGN_AND_OOS_CALIBRATION"]}


def render_history(report, race):
    catalog = {r["observation_id"]: r for r in report["historical_truth"]["observations"]}
    lines = ["  Historisk resultatkontroll: etterkontroll; ingen nye PRE-features."]
    for horse in race["fundamental_analysis"]["horses"]:
        rows = [catalog[i] for i in dict.fromkeys(horse["historical_results"])]
        lines.append(f"    {horse['selection_id']} {horse['name']}: " + "; ".join(
            f"{r['event_date']} L{r['source_race_number']} {r['status']}" + (
                f" [{r['historical_race_id']}; plass={r['result']['placing']}; "
                f"originalkode={r['result']['place_raw']}; tid={r['result']['km_time_raw']}; "
                f"distanse={r['result']['distance_m']} m; "
                f"kildesemantikk={r['result']['status']}; PIT=ikke verifisert; "
                f"kilde={r['source_refs'][-1]['url']}]" if r["result"] else "")
            for r in rows))
    return lines
