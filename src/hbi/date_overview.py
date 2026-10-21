"""Offline date inventory of a checksum-verified crawler daily ZIP.

Source eligibility is not handicapping. No model, odds or case is manufactured.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from betting.cli import main as betting_main

from .provider_capability import name_key


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("UNKNOWN_SOURCE_TIMEZONE")
    return parsed


class DailyArchive:
    """Read existing crawler JSON members, never execute or extract ZIP contents."""

    def __init__(self, path, expected_sha256, day):
        self.day = date.fromisoformat(day).isoformat()
        raw = Path(path).read_bytes()
        self.sha256 = digest(raw)
        if self.sha256 != expected_sha256:
            raise ValueError("ARCHIVE_SHA256_MISMATCH")
        self.zip = zipfile.ZipFile(io.BytesIO(raw))
        names = self.zip.namelist()
        if len(names) != len(set(names)) or any(
            PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names
        ):
            raise ValueError("UNSAFE_OR_DUPLICATE_ZIP_MEMBERS")
        if sum(i.file_size for i in self.zip.infolist()) > 100_000_000:
            raise ValueError("ARCHIVE_TOO_LARGE")
        manifests = [n for n in names if n.endswith("/manifest.json")]
        if len(manifests) != 1:
            raise ValueError("ONE_DAILY_MANIFEST_REQUIRED")
        self.prefix = manifests[0].rsplit("/", 1)[0]
        self.manifest = self.read("manifest.json")
        self.data = self.read("structured_program_day.json")
        if self.manifest["date_oslo"] != self.day or self.data["date"] != self.day:
            raise ValueError("DATE_NOT_IN_ARCHIVE")
        if (self.data["run_id"] != self.manifest["run_id"]
                or self.prefix != f"{self.day}/{self.data['run_id']}"):
            raise ValueError("ARCHIVE_RUN_MISMATCH")
        docs = self.data["races"]
        if (len(docs) != self.data["counts"]["races"]
                or sum(len(d["entrants"]) for d in docs) != self.data["counts"]["horses"]
                or sum(len(h["past_starts"]) for d in docs for h in d["entrants"])
                != self.data["counts"]["prior_starts"]):
            raise ValueError("SOURCE_COUNTS_MISMATCH")
        for daily_key, manifest_key in [("races", "pdf_races_parsed"),
                                        ("horses", "pdf_horses_parsed"),
                                        ("prior_starts", "pdf_history_rows")]:
            if self.data["counts"][daily_key] != self.manifest["counts"][manifest_key]:
                raise ValueError("MANIFEST_COUNTS_MISMATCH")
        keys = [(d["race"]["meeting_id"], d["race"]["race_number"]) for d in docs]
        self.duplicates = {key for key, count in Counter(keys).items() if count > 1}

    def read(self, member):
        raw = self.zip.read(f"{self.prefix}/{member}")
        return json.loads(raw)

    def source(self, member):
        path = f"{self.prefix}/{member}"
        return {"member": path, "member_sha256": digest(self.zip.read(path)),
                "hash_basis": "ARCHIVED_FILE_BYTES_NOT_RAW_HTTP"}


MISSING_MODELS = ["CALIBRATED_WIN_INTERVALS", "FFQ1_FULL_FIELD_CASES",
                  "FRESH_FULL_FIELD_WIN", "INDEPENDENT_PLACE_MODEL"]


def inspect_race(archive, doc, meeting, starts):
    race, horses = doc["race"], doc["entrants"]
    mid, number = race["meeting_id"], race["race_number"]
    if not re.fullmatch(r"[A-Z0-9]+_NR_" + re.escape(archive.day), mid):
        raise ValueError("SOURCE_MEETING_DATE_MISMATCH")
    if type(number) is not int or not 1 <= number <= 30:
        raise ValueError("INVALID_SOURCE_RACE_NUMBER")
    blockers = []
    if (mid, number) in archive.duplicates:
        blockers.append("AMBIGUOUS_SOURCE_RACE_NUMBER")
    if set(doc) != {"race", "entrants", "scratches", "win_odds", "qa"}:
        blockers.append("UNSUPPORTED_OR_POST_FIELDS")
    composite = meeting.get("is_multi_track_product") is True
    if composite:
        blockers.append("COMPOSITE_PRODUCT_NOT_AN_INDEPENDENT_RACE")
    local = race.get("scheduled_time_local")
    start = None
    if isinstance(local, str) and re.fullmatch(r"\d\d:\d\d", local) and local != "00:00":
        start = datetime.fromisoformat(f"{archive.day}T{local}").replace(
            tzinfo=ZoneInfo("Europe/Oslo")
        ).astimezone(ZoneInfo("UTC"))
    else:
        blockers.append("SCHEDULED_START_UNKNOWN")
    observed = timestamp(race["captured_at_utc"])
    rows = []
    if starts and starts.get("response", {}).get("success") is True:
        rows = starts["response"].get("result", {}).get(str(number), [])
        observed = max(observed, timestamp(starts["fetched_utc"]))
    numbers = [h.get("program_number") for h in horses]
    api_numbers = [r.get("startNumber") for r in rows]
    complete = bool(horses and rows) and (
        all(type(n) is int and n > 0 for n in numbers + api_numbers)
        and len(set(numbers)) == len(numbers) and len(set(api_numbers)) == len(api_numbers)
        and set(numbers) == set(api_numbers)
    )
    api = {r.get("startNumber"): r for r in rows}
    if complete:
        complete = all(
            name_key(h["name"]) == name_key(api[h["program_number"]].get("horseName"))
            and type(api[h["program_number"]].get("isScratched")) is bool for h in horses
        )
    if not complete:
        blockers.append("PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH")
    if start and observed >= start:
        blockers.append("SOURCE_NOT_PRE_START")
    listing = meeting.get("listing_source", {})
    country = listing.get("country")
    discipline = {"T": "trot", "G": "gallop"}.get(listing.get("sport_type"))
    if not country or not discipline:
        blockers.append("COUNTRY_OR_DISCIPLINE_UNKNOWN")
    roster = []
    for horse in horses:
        row = api.get(horse.get("program_number"), {}) if complete else {}
        registration = row.get("horseRegistrationNumber")
        stable = bool(registration and not str(registration).upper().startswith("TMP"))
        history = horse.get("past_starts", [])
        if any(not h.get("date") or h["date"] >= archive.day for h in history):
            blockers.append("POST_OR_UNDATED_HISTORY")
        roster.append({
            "selection_id": str(horse.get("program_number")), "name": horse["name"],
            "scratched_as_of_snapshot": row.get("isScratched"),
            "provider_registration_observed": registration,
            "provider_identity_usable": stable,
            "driver_startlist": row.get("driverName"),
            "driver_pdf_raw": horse.get("driver"),
            "history_rows": len(history), "history_model_validated": False,
        })
    ids = [h["provider_registration_observed"] for h in roster if h["provider_identity_usable"]]
    if len(ids) != len(set(ids)):
        blockers.append("DUPLICATE_PROVIDER_IDENTITIES")
    card = None
    rid = f"RIKSTOTO:{mid}:{number}"
    if not blockers:
        card = {"race": {
            "race_id": rid, "race_date": archive.day, "country": country,
            "track": race["track"], "race_no": number, "start_time_utc": start.isoformat(),
            "discipline": discipline, "distance_m": race.get("distance_m"),
            "start_method": race.get("start_method"), "created_at_utc": observed.isoformat(),
        }, "runners": [{
            "race_id": rid, "selection_id": h["selection_id"], "horse_name": h["name"],
            "driver_or_jockey": h["driver_startlist"],
            "scratched": int(h["scratched_as_of_snapshot"]),
        } for h in roster]}
    active = [h for h in roster if h["scratched_as_of_snapshot"] is False]
    missing = list(MISSING_MODELS)
    available = ["ARCHIVED_PROGRAM", "SOURCE_RUNNER_NAMES"]
    if race.get("distance_m"):
        available.append("SOURCE_DISTANCE")
    else:
        missing.append("SOURCE_DISTANCE")
    if any(h["history_rows"] for h in roster):
        available.append("RAW_HISTORY_EXCERPTS")
    if not active or any(not h["history_rows"] for h in active):
        missing.append("FULL_FIELD_RAW_HISTORY")
    if any(not h["provider_identity_usable"] for h in active) or not complete:
        missing.append("VERIFIED_FULL_FIELD_PROVIDER_IDENTITIES")
    item = {
        "race_id": rid, "date": archive.day, "track": race["track"], "race_number": number,
        "scheduled_local_raw": local, "scheduled_start_utc": start.isoformat() if start else None,
        "runner_count": len(horses), "active_count": len(active) if complete else None,
        "composite_product": composite, "source_present": True, "imported": False,
        "screened": True, "screening_scope": "INPUT_ELIGIBILITY_ONLY",
        "fully_analyzed": False, "full_field_status": (
            "MATCHED_AS_OF_SNAPSHOT" if complete and not composite else "UNVERIFIED"
        ),
        "source": {"url": race["source_url"], "captured_at": race["captured_at_utc"],
                   "latest_observation": observed.isoformat(),
                   "archive_sha256": archive.sha256,
                   "structured": archive.source("structured_program_day.json"),
                   "startlist": archive.source(f"meetings/{mid}/starts.json") if starts else None,
                   "collection_status": archive.manifest["status"],
                   "qa": doc["qa"], "meeting_audit": meeting.get("startlist_pdf_audit")},
        "identity_coverage": {"source_name_number_matches": len(horses) if complete else 0,
                              "usable_provider_ids": len(ids), "total": len(horses)},
        "history_coverage": {"runners_with_raw_history": sum(h["history_rows"] > 0 for h in roster),
                             "raw_rows": sum(h["history_rows"] for h in roster),
                             "model_validated_runners": 0},
        "available_inputs": available,
        "missing_inputs": missing,
        "input_limitations": ["NO_VALIDATED_HISTORY_FEATURES", "NO_VALIDATED_EQUIPMENT_FEATURES",
                              "NO_VALIDATED_DRAW_FEATURES", "PDF_DRIVER_TEXT_MAY_BE_MIXED"],
        "blockers": sorted(set(blockers)), "betting_runtime": None, "runners": roster,
    }
    return item, card


def write(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run_overview(day, archive_path, sha256, output, fundamental=False,
                 results_archive=None, results_sha256=None):
    from .cli import _store, cmd_import_races

    if bool(results_archive) != bool(results_sha256) or (results_archive and not fundamental):
        raise ValueError("HISTORICAL_RESULTS_REQUIRE_FUNDAMENTAL_AND_CHECKSUM")
    truth = None
    if results_archive:
        from .historical_truth import HistoricalTruth

        truth = HistoricalTruth(results_archive, results_sha256)
    archive = DailyArchive(archive_path, sha256, day)
    meetings = {m["meeting_id"]: m for m in archive.manifest["meetings"]}
    entries, cards, docs = [], [], {}
    for source_index, doc in enumerate(archive.data["races"]):
        mid = doc["race"]["meeting_id"]
        try:
            starts = archive.read(f"meetings/{mid}/starts.json")
        except KeyError:
            starts = None
        entry, card = inspect_race(archive, doc, meetings[mid], starts)
        entry["source_entry_id"] = f"{archive.sha256}:races:{source_index}"
        if fundamental:
            from .fundamental_view import analyze_race

            entry["fundamental_analysis"] = analyze_race(archive, doc, entry, starts)
        entries.append(entry)
        docs[entry["race_id"]] = doc
        if card:
            cards.append(card)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)  # Always a new isolated database/run.
    write(output / "canonical-races.json", {"races": cards})
    with (output / "import.log").open("x", encoding="utf-8") as log, redirect_stdout(log):
        cmd_import_races(argparse.Namespace(
            db=str(output / "hbi.sqlite"), schema=None, file=output / "canonical-races.json",
        ))
    store = _store(str(output / "hbi.sqlite"))
    admitted = {c["race"]["race_id"] for c in cards}
    batch = output / "retrospective-batch.json"
    write(batch, {"mode": "RETROSPECTIVE_REPLAY", "batch_id": archive.data["run_id"]})
    for i, entry in enumerate(entries):
        if entry["race_id"] not in admitted:
            continue
        entry["imported"] = True
        store.insert_provider_payload(
            payload_id=digest((archive.sha256 + entry["race_id"]).encode()), provider="RIKSTOTO",
            category="ARCHIVED_DAILY_PROGRAM", provider_raceday_key=docs[entry["race_id"]][
                "race"]["meeting_id"], race_number=entry["race_number"],
            observed_at=timestamp(entry["source"]["latest_observation"]),
            source_uri=entry["source"]["url"],
            payload={"provenance": entry["source"], "program": docs[entry["race_id"]]},
        )
        active = [h for h in entry["runners"] if h["scratched_as_of_snapshot"] is False]
        request = {"race_id": entry["race_id"], "race_start": entry["scheduled_start_utc"],
                   "decision_time": entry["source"]["latest_observation"],
                   "active_field": [h["selection_id"] for h in active],
                   "identity_matches": {h["selection_id"]: {
                       "status": "EXACT", "confidence": 1,
                       "provider_id": h["provider_registration_observed"],
                   } for h in active if h["provider_identity_usable"]}}
        request_path, decision_path = output / f"input-{i}.json", output / f"decision-{i}.json"
        write(request_path, request)
        code = 0
        with (output / f"review-{i}.log").open("x", encoding="utf-8") as log, redirect_stdout(log):
            try:
                betting_main(["review", str(request_path), "--batch", str(batch),
                              "--output", str(decision_path)])
            except SystemExit as exc:
                code = exc.code
        result = json.loads(decision_path.read_text(encoding="utf-8"))
        entry["betting_runtime"] = {"exit_code": code, "report": result,
                                    "decision_file": decision_path.name}
    independent = [r for r in entries if not r["composite_product"]]
    report = {"date": archive.day, "run_id": archive.data["run_id"],
              "scope": "SELECTED_ARCHIVE_ONLY", "day_completeness_verified": False,
              "races_outside_archive": "UNKNOWN_NOT_ENUMERATED",
              "archive_sha256": archive.sha256,
              "source_counts": archive.data["counts"],
              "counts": {"source_race_entries": len(entries),
                         "source_runner_entries": sum(r["runner_count"] for r in entries),
                         "independent_races": len(independent),
                         "independent_runners": sum(r["runner_count"] for r in independent),
                         "full_field_matched_races": sum(
                             r["full_field_status"] == "MATCHED_AS_OF_SNAPSHOT" for r in entries),
                         "independent_runners_with_raw_history": sum(
                             r["history_coverage"]["runners_with_raw_history"] for r in independent),
                         "imported_races": len(cards), "imported_runners": store.count("runners"),
                         "screened_for_input_eligibility": len(entries),
                         "betting_reviews_executed": sum(r["betting_runtime"] is not None for r in entries),
                         "blocked_before_review": sum(r["betting_runtime"] is None for r in entries),
                         "fully_analyzed": 0},
              "races": entries}
    if fundamental:
        report["descriptive_analysis"] = {
            "verified_horses": sum(h["identity"]["status"] == "VERIFIED"
                for r in independent for h in r["fundamental_analysis"]["horses"]),
            "model_analyzed_races": 0, "scope": "DESCRIPTIVE_NOT_PREDICTIVE",
        }
    if truth:
        from .historical_truth import attach_history

        attach_history(report, archive, truth)
        write(output / "model-readiness.json", report["historical_truth"])
    write(output / "overview.json", report)
    text = summary(report)
    (output / "summary.txt").write_text(text, encoding="utf-8")
    return report, text


def summary(report):
    counts = report["counts"]
    lines = [f"Dato {report['date']} — kun valgt arkiv; hele dagens dekning er ikke verifisert.",
             (f"Kilde: {counts['source_race_entries']} oppføringer / {counts['source_runner_entries']} hester; "
              f"selvstendige: {counts['independent_races']} løp / {counts['independent_runners']} hester."),
             (f"Importert: {counts['imported_races']} løp / {counts['imported_runners']} hester; "
              f"Betting-review: {counts['betting_reviews_executed']}; fullverdig analysert: 0.")]
    labels = {
        "SCHEDULED_START_UNKNOWN": "starttid mangler i kilden",
        "COMPOSITE_PRODUCT_NOT_AN_INDEPENDENT_RACE": "sammensatt spillpakke, ikke selvstendig løp",
        "COUNTRY_OR_DISCIPLINE_UNKNOWN": "land eller disiplin er ukjent",
        "PDF_STARTLIST_FIELD_NAME_OR_SCRATCH_MISMATCH": "PDF og startliste stemmer ikke fullstendig",
        "AMBIGUOUS_SOURCE_RACE_NUMBER": "tvetydig løpsnummer i kilden",
    }
    for race in report["races"]:
        runtime = race["betting_runtime"]
        if not runtime:
            reason = "; ".join(labels.get(b, b) for b in race["blockers"])
        elif runtime["report"]["errors"] == ["INVALID_V33_INPUT:'fundamental'"]:
            reason = "kalibrerte fundamentale sannsynlighetsintervaller mangler"
        else:
            reason = "; ".join(runtime["report"]["errors"]).replace(
                "INVALID_V33_INPUT:FULL_FIELD_ONLY: exact identity evidence required",
                "verifisert fullfelt-identitet mangler",
            )
        lines.append(f"{race['track']} L{race['race_number']:02d} "
                     f"{race['scheduled_start_utc'] or 'start ukjent'} | "
                     f"{race['runner_count']} hester | import={'ja' if race['imported'] else 'nei'} | "
                     f"{'REVIEW_AVVIST' if runtime else 'BLOKKERT_FØR_REVIEW'}: {reason}")
        lines.append("  Hester: " + "; ".join(
            f"{h['selection_id']} {h['name']}" + (
                " (strøket ved snapshot)" if h["scratched_as_of_snapshot"] is True else ""
            ) for h in race["runners"]
        ))
        if "fundamental_analysis" in race:
            from .fundamental_view import render

            lines.extend(render(race["fundamental_analysis"]))
        if "historical_truth" in report and not race["composite_product"]:
            from .historical_truth import render_history

            lines.extend(render_history(report, race))
    if "historical_truth" in report:
        lines.append("Model-readiness: " + json.dumps(report["historical_truth"]["counts"], ensure_ascii=False))
        lines.append("MODELLGRUNNLAG BLOKKERT: historisk tilgjengelighet og fullfelt-PIT-features er ikke dokumentert.")
    return "\n".join(lines) + "\n"


def cli(args):
    try:
        _, text = run_overview(args.date, args.archive, args.sha256, args.output,
                               fundamental=getattr(args, "fundamental", False),
                               results_archive=getattr(args, "results_archive", None),
                               results_sha256=getattr(args, "results_sha256", None))
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"allowed": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
    print(text, end="")
    print(f"JSON: {Path(args.output) / 'overview.json'}")
