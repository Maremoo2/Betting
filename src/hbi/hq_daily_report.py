"""Render a Norwegian NO BET briefing from existing, archived research outputs."""

import argparse
import json
import math
import re
import sqlite3
from collections import Counter
from datetime import date, timedelta
from email import policy
from email.message import EmailMessage
from html import escape
from pathlib import Path
from zipfile import ZipFile

from .evaluation import log_loss, multiclass_brier
from .prospective_outcome_scorecard import _field, _market, _official_winner, _probs, clock, digest
from .providers.atg import AtgClient
from .providers.rikstoto import OSLO, RikstotoClient
from .research_ledger import checked

REASONS = {
    "COLLECTOR_ATG_ATG_FULL_FIELD_GATE_NOT_PASSED": "ATG har ikke bekreftet hele feltet.",
    "COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE": "Verifisert ATG-historikk mangler for deler av feltet.",
    "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED": "Startlisten inneholder midlertidige heste-ID-er.",
    "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED": "Identiteten på tvers av kildene er ikke attestert.",
    "COLLECTOR_PDF_START_CLOCK_CONFLICT": "Programmet og den registrerte starttiden avviker.",
    "COLLECTOR_SQLITE_FIELD_MISMATCH": "Det importerte feltet samsvarer ikke med programfeltet.",
    "MODEL_SOURCE_COHORT_NOT_FOUND": "Et samlet modellgrunnlag mangler.",
    "COLLECTOR_PDF_RACE_CLOCK_UNVERIFIED": "Programmet gir ingen verifisert starttid.",
    "COLLECTOR_PDF_PHYSICAL_RACE_AMBIGUOUS": "Løpet kan ikke identifiseres entydig i programmet.",
    "NO_ARCHIVED_MODEL_PORT_EVIDENCE": "Ingen bevart modellportobservasjon for dette løpet.",
    "MODEL_FREEZE_AT_OR_AFTER_T4": "Modellfryset ble fullført ved eller etter beslutningsfristen.",
    "NOT_IN_INSPECTED_COHORTS": "Løpet ligger utenfor de kontrollerte modellkohortene.",
    "ATG_MEETING_WITHOUT_COLLECTOR_RIKSTOTO_MAPPING": (
        "Møtet er dokumentert hos ATG. En verifisert Rikstoto-kobling og Collector-original mangler."
    ),
    "NO_WIN_MARKET_AS_OF": "Komplett WIN fra samme frys mangler.",
    "NOT_BEFORE_CONSERVATIVE_T4": "Kjøringen var ved eller etter beslutningsfristen.",
}


def market_rows(db, race_id, observed):
    if not observed:
        return {}
    return {
        str(selection): (odds, observed)
        for selection, odds in db.execute(
            """SELECT selection_key, odds_decimal FROM provider_market_snapshots
               WHERE provider='rikstoto' AND product='V' AND race_id=? AND observed_at_utc=?""",
            (race_id, observed),
        )
        if odds is not None and math.isfinite(odds) and odds > 1
    }


def original_roster(archive, race_id):
    _, meeting, race_no = race_id.split(":")
    suffix = f"/meetings/{meeting}/starts.raw.json"
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        return [], None
    raw = archive.read(matches[0])
    result = json.loads(raw).get("result")
    if not isinstance(result, dict):
        return [], None
    rows = result.get(race_no, [])
    if (not isinstance(rows, list) or any(
        not isinstance(row, dict) or type(row.get("startNumber")) is not int
        or type(row.get("isScratched")) is not bool
        or row.get("raceNumber") != int(race_no)
        or row.get("raceKey") not in {f"{meeting}#{race_no}", f"{meeting}_{race_no}"}
        for row in rows
    ) or len({row["startNumber"] for row in rows}) != len(rows)):
        return [], None
    return sorted(rows, key=lambda row: row["startNumber"]), digest(raw)


def model_runners(model):
    active, blockers = _field(model)
    if blockers:
        return []
    same_win = _market(active, clock(model["as_of_utc"]))
    return [
        {
            "number": r["start_number"], "name": r["horse_name"], "scratch": False,
            "p": r["champion_p_win"], "core": r["core004_p_win"],
            "fair": 1 / r["champion_p_win"] if r["champion_p_win"] > 0 else None,
            "win": r.get("win_odds") if same_win else None,
            "win_at": r.get("win_odds_observed_at_utc") if same_win else None,
            "ev": r["champion_p_win"] * r["win_odds"] - 1 if same_win else None,
            "status": r.get("research_status") if r.get("research_status") in {"WATCH", "PASS"} else None,
            "starts": r.get("historical_starts"), "wins": r.get("historical_wins"),
            "minimum_odds": r.get("minimum_bet_odds"),
        } for r in active
    ]


def model_analysis(model, sha):
    runners = model_runners(model)
    if not runners:
        return None
    return {"runners": runners, "versions": model["model_versions"],
            "as_of": model["as_of_utc"], "sha256": sha,
            "created_at_utc": model["report_created_at_utc"],
            "calculated_at_utc": model.get("model_calculated_at_utc"),
            "start_at_freeze_utc": model["race"]["start_time_utc"],
            "code_sha": model.get("git_sha_of_current_workspace")}


def freeze_order(member):
    model, sha = member
    active, blockers = _field(model)
    if blockers:
        return None
    return (
        _market(active, clock(model["as_of_utc"])) is None,
        clock(model["report_created_at_utc"]),
        sha,
    )


def read_cohort(path, pin):
    with ZipFile(path) as archive:
        index = checked(archive.read("cohort-index.json"), pin)
        if (index.get("schema") != "BET_MVP_002_FIXED_COHORT_INDEX_V1"
                or index.get("bet_authority") is not False or index.get("pit_certified") is not False):
            raise ValueError("Unsafe model cohort")
        models = {}
        blocked_timing = set()
        eligibility = {row["race_id"]: row for row in index["eligible_prestart"]}
        for item in index["processed"]:
            if not re.fullmatch(r"bet-mvp-shadow/race-[0-9]{3,}", item["directory"]):
                raise ValueError("Unexpected model path")
            name = item["directory"].split("/")[-1]
            if item["race_id"] in models or item["race_id"] not in index["original_cohort"]:
                raise ValueError("Duplicate or undeclared model race")
            model = checked(archive.read(f"{name}/shadow.json"), item["report_sha256"])
            if model["race"]["race_id"] != item["race_id"]:
                raise ValueError("Model race mismatch")
            models[item["race_id"]] = model, item["report_sha256"]
            eligible = eligibility[item["race_id"]]
            start = clock(eligible["start_time_utc"])
            earliest = clock(eligible["earliest_source_start_utc"])
            as_of = clock(model.get("as_of_utc"))
            calculated = clock(model.get("model_calculated_at_utc"))
            frozen = clock(model.get("report_created_at_utc"))
            if (all(t is not None for t in (start, earliest, as_of, calculated, frozen))
                    and earliest <= start == clock(model["race"].get("start_time_utc"))
                    and as_of <= calculated <= frozen < earliest - timedelta(minutes=4)):
                continue
            blocked_timing.add(item["race_id"])
    return index, models, blocked_timing


def official_observation(rid, directory, model):
    _, meeting, race_no = rid.split(":")
    paths = {
        "complete": f"raceDays/{meeting}/{race_no}/completeresults",
        "raceday": f"racedays/{meeting}/raceresults",
    }
    receipts = {}
    bodies = {}
    for role, path in paths.items():
        receipt = json.loads((directory / f"{role}.receipt.json").read_bytes())
        if (receipt.get("http_status") != 200 or receipt.get("role") != role
                or receipt.get("source_uri") != f"https://www.rikstoto.no/api/results/{path}"
                or clock(receipt.get("observed_at_utc")) is None):
            raise ValueError("Invalid official result receipt")
        body = checked((directory / f"{role}.raw.json").read_bytes(), receipt["raw_sha256"])
        if body.get("success") is not True:
            raise ValueError("Official result source failed")
        receipts[role], bodies[role] = receipt, body["result"]
    complete, raceday = bodies["complete"], bodies["raceday"]
    if raceday.get("raceDay") != meeting or complete.get("isComplete") is not True:
        raise ValueError("Incomplete or mismatched official result")
    actual = RikstotoClient.parse_timestamp(complete["startTime"])
    if any(clock(receipt["observed_at_utc"]) <= actual for receipt in receipts.values()):
        raise ValueError("Official result receipt predates reported start")
    winners = [row for row in complete["results"] if row["place"] == 1]
    published = raceday.get("raceWinners", {}).get(race_no)
    if not isinstance(published, list) or not published:
        raise ValueError("OFFICIAL_RACEDAY_WINNER_NOT_PUBLISHED")
    winner = None
    if len(winners) == len(published) == 1 and winners[0]["startNumber"] == published[0]["startNumber"]:
        winner = {"number": winners[0]["startNumber"], "name": winners[0]["horseName"]}
    status = "NO_FROZEN_MODEL"
    scores = None
    if model:
        active, blockers = _field(model)
        if not blockers:
            winner_id, status = _official_winner(
                complete, raceday, active=active, frozen_roster=model["runners"], race_no=int(race_no),
            )
            if status is None and (winner is None or winner_id is None):
                status = "OFFICIAL_WINNER_CONFLICT"
            if status is None:
                vectors = {
                    "Champion": _probs(active, "champion_p_win"), "CORE-004": _probs(active, "core004_p_win"),
                    "WIN": _market(active, clock(model["as_of_utc"])),
                }
                scores = {name: {"log_loss": log_loss(vector, winner_id),
                                 "brier": multiclass_brier(vector, winner_id)}
                          for name, vector in vectors.items() if vector is not None}
        else:
            status = blockers[0]
    return {
        "reported_actual_start_raw": complete["startTime"], "reported_actual_start_utc": actual.isoformat(),
        "receipts": receipts, "winner": winner, "score_blocker": status, "scores": scores,
        "scratches": [row["horseName"] for row in complete["results"] if row.get("kmTime") == "Str"],
    }


def calendar_only_races(calendar, day, collector_races):
    """Report extra ATG meetings under their own source identities."""
    if calendar.get("date") != day.isoformat():
        raise ValueError("ATG_CALENDAR_DAY_MISMATCH")
    programme = {(r["country"], r["track"].casefold().strip(), r["number"]) for r in collector_races}
    seen = set()
    records = []
    for track in calendar["tracks"]:
        country, name = track.get("countryCode"), track["name"]
        if country not in {"NO", "SE"} or track.get("sport") != "trot":
            continue
        # The calendar comparison never imports any identities or model data.
        for race in track["races"]:
            source_id, number = race["id"], race["number"]
            if (type(number) is not int or number < 1 or type(track["id"]) is not int
                    or source_id != f"{day.isoformat()}_{track['id']}_{number}" or source_id in seen):
                raise ValueError("ATG_CALENDAR_RACE_ID_MISMATCH")
            seen.add(source_id)
            if (country, name.casefold().strip(), number) in programme:
                continue
            start = AtgClient._parse_time(race.get("startTime"))
            status = race.get("status")
            records.append({
                "race_id": f"ATG:{source_id}", "track": name, "country": country, "number": number,
                "calendar_only": True, "calendar_status": status, "calendar_start_raw": race.get("startTime"),
                "start": start.isoformat() if start is not None and status == "upcoming" else None,
                "active": None, "scratched": None, "roster_sha256": None,
                "runners": [], "analysis": None, "official": None, "full_market": False,
                "queue_evidence": [], "model_attempts": [],
                "model_evidence_status": "BLOCKED_SOURCE_MAPPING",
                "reasons": ["ATG_MEETING_WITHOUT_COLLECTOR_RIKSTOTO_MAPPING"],
            })
    return records


def official_atg_observation(race, directory):
    """Verify the post-race result under its original ATG identity."""
    source_id = race["race_id"].removeprefix("ATG:")
    receipt = json.loads((directory / "game.receipt.json").read_bytes())
    if (receipt.get("source_uri") != f"{AtgClient.GAME_API}/vinnare_{source_id}"
            or receipt.get("http_status") != 200 or clock(receipt.get("observed_at_utc")) is None):
        raise ValueError("ATG_OFFICIAL_RESULT_RECEIPT_INVALID")
    game = checked((directory / "game.raw.json").read_bytes(), receipt["sha256"])
    candidates = game.get("races", [])
    if game.get("id") != f"vinnare_{source_id}" or len(candidates) != 1:
        raise ValueError("ATG_OFFICIAL_RESULT_ID_MISMATCH")
    source = candidates[0]
    track = source.get("track", {})
    if (source.get("id") != source_id or str(source.get("number")) != str(race["number"])
            or source.get("date") != source_id[:10] or source.get("sport") != "trot"
            or track.get("id") != int(source_id.split("_")[1])
            or track.get("name") != race["track"] or track.get("countryCode") != race["country"]):
        raise ValueError("ATG_OFFICIAL_RESULT_ID_MISMATCH")
    actual = AtgClient._parse_time(source.get("startTime"))
    if (source.get("status") != "results" or actual is None
            or clock(receipt["observed_at_utc"]) <= actual):
        raise ValueError("ATG_OFFICIAL_RESULT_NOT_AVAILABLE")
    starts = source["starts"]
    numbers = [str(r["number"]) for r in starts]
    if (not starts or len(numbers) != len(set(numbers))
            or any(not n.isascii() or not n.isdecimal() or int(n) <= 0 for n in numbers)
            or any(r.get("id") != f"{source_id}_{n}" for r, n in zip(starts, numbers, strict=True))):
        raise ValueError("ATG_OFFICIAL_RESULT_FIELD_MISMATCH")
    winners = [
        {"number": int(row["number"]), "name": row["horse"]["name"]}
        for row in starts if (row.get("result") or {}).get("place") == 1
    ]
    pool = source.get("pools", {}).get("vinnare", {}).get("result", {}).get("winners", [])
    if not winners or {row["number"] for row in winners} != {row["number"] for row in pool}:
        raise ValueError("ATG_OFFICIAL_RESULT_WINNER_MISMATCH")
    scratched = set(source.get("result", {}).get("scratchings", []))
    if not scratched <= {int(n) for n in numbers}:
        raise ValueError("ATG_OFFICIAL_RESULT_FIELD_MISMATCH")
    return {
        "reported_actual_start_raw": source["startTime"], "reported_actual_start_utc": actual.isoformat(),
        "scheduled_start_raw": source.get("scheduledStartTime"), "receipts": {"atg": receipt},
        "winner": winners[0] if len(winners) == 1 else None, "winners": winners,
        "scratches": [r["horse"]["name"] for r in starts if int(r["number"]) in scratched],
        "result_roster": [
            {"number": int(r["number"]), "name": r["horse"]["name"],
             "scratch": int(r["number"]) in scratched, "win": None, "win_at": None}
            for r in starts
        ],
        "score_blocker": "NO_FROZEN_MODEL", "scores": None,
    }


def build_report(args):
    with ZipFile(args.ledger) as archive:
        ledger = checked(archive.read("index.json"), args.ledger_sha)
    current = ledger["current_observations"]
    if (ledger.get("schema") != "HBI_RESEARCH_LEDGER_V1"
            or ledger.get("bet_authority") is not False or ledger.get("pit_certified") != 0):
        raise ValueError("Unsafe ledger contract")
    with ZipFile(args.handoff) as archive:
        handoff = checked(archive.read("collector-handoff.json"), current["collector_handoff_sha256"])
    if handoff.get("source_report_sha256") != current["source_report_sha256"]:
        raise ValueError("Collector handoff source mismatch")
    handoff_by_race = {row["race_id"]: row for row in handoff["records"]}
    with ZipFile(args.core) as archive:
        source = checked(archive.read("core003-pilot-report.json"), current["source_report_sha256"])
    anchor = read_cohort(args.cohort, current["cohort_index_sha256"])
    index, anchor_models, _ = anchor
    models = {}
    late = set()
    readiness = {row["race_id"]: row for row in source["race_readiness_after"]}
    timing = {current["source_report_sha256"]: readiness}
    source_reports = {current["source_report_sha256"]: source}
    for path, pin in args.timing_core:
        with ZipFile(path) as archive:
            original_core = checked(archive.read("core003-pilot-report.json"), pin)
        source_reports[pin] = original_core
        timing[pin] = {row["race_id"]: row for row in original_core["race_readiness_after"]}
    result_dirs = {rid: Path(path) for rid, path in args.official_result}
    model_attempts = {}
    prior_reasons = {}
    prior_readiness = {}
    win_observations = {}
    cohorts = [(pin, read_cohort(Path(path), pin)) for path, pin in args.prior_cohort]
    cohorts.append((current["cohort_index_sha256"], anchor))
    for pin, (prior, members, prior_late) in sorted(cohorts, key=lambda item: clock(item[1][0]["as_of_utc"])):
        late.update(prior_late)
        for rid, ready in timing.get(prior["source_report_sha256"], {}).items():
            prior_readiness[rid] = ready
            observed = clock(ready.get("win_market_cohort_at_utc"))
            previous = clock(win_observations.get(rid))
            if observed is not None and (previous is None or observed > previous):
                win_observations[rid] = ready["win_market_cohort_at_utc"]
        for rid, member in members.items():
            order = None if rid in prior_late else freeze_order(member)
            if order is not None and (rid not in models or order < freeze_order(models[rid])):
                models[rid] = member
        for disposition in ("not_processed", "errors", "processed"):
            for row in prior[disposition]:
                rid = row["race_id"]
                model_attempts.setdefault(rid, []).append({
                    "disposition": disposition, "as_of_utc": prior["as_of_utc"],
                    "cohort_sha256": pin, "model_sha256": row.get("report_sha256"),
                    "reason": row.get("reason"), "model_status": row.get("model_status"),
                    "collector_blockers": row.get("collector_blockers", []),
                })
                if disposition != "processed":
                    prior_reasons[rid] = [row["reason"], *row.get("collector_blockers", [])]
    queue_events = {}
    for pin, core in source_reports.items():
        groups = (
            ("provider_events", "PROVIDER_EVENT"),
            ("queue_selected", "SELECTED"),
            ("queue_deferred_capacity", "DEFERRED_CAPACITY"),
            ("queue_clock_exclusions", "CLOCK_EXCLUSION"),
        )
        for key, status in groups:
            for item in core.get(key, []):
                queue_events.setdefault(item["race_id"], []).append({
                    **item, "evidence": status, "started_at_utc": core["started_at_utc"],
                    "source_report_sha256": pin,
                })
    ids = [row["race_id"] for row in current["records"]]
    if (len(ids) != len(set(ids)) or set(ids) != set(source["races_in_fixed_cohort"])
            or set(ids) != set(index["original_cohort"])):
        raise ValueError("Original race cohort mismatch")
    races = []
    if digest(args.db.read_bytes()) != index["source_database_sha256"]:
        raise ValueError("Archived database SHA-256 mismatch")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db, ZipFile(
        args.collector
    ) as collector:
        observations = {row["race_id"]: row for row in current["records"]}
        report_ids = list(observations)
        listings = {}
        if args.meeting or args.nordic:
            manifests = [name for name in collector.namelist() if name.endswith("/manifest.json")]
            if len(manifests) != 1:
                raise ValueError("Expected one Collector manifest")
            manifest = json.loads(collector.read(manifests[0]))
            meetings = [
                m for m in manifest["meetings"]
                if (m["meeting_id"] == args.meeting if args.meeting else
                    m.get("listing_source", {}).get("country") in {"NO", "SE"}
                    and m.get("listing_source", {}).get("sport_type") == "T")
            ]
            if args.meeting and not meetings:
                raise ValueError("Collector meeting not found")
            listings = {m["meeting_id"]: m["listing_source"] for m in meetings}
            report_ids = [
                f"RIKSTOTO:{m['meeting_id']}:{number}" for m in meetings for number in m["race_numbers"]
            ]
        for rid in report_ids:
            _, meeting, race_no = rid.split(":")
            if not meeting.endswith(args.date.isoformat()):
                continue
            row = observations.get(rid, {})
            metadata = db.execute(
                "SELECT track, country, start_time_utc FROM races WHERE race_id=?", (rid,)
            ).fetchone()
            if metadata is None:
                listing = listings[meeting]
                metadata = listing["track"], listing["country"], None
            track, country, scheduled = metadata
            ready = readiness.get(rid, prior_readiness.get(rid, {}))
            roster, roster_sha = original_roster(collector, rid)
            win_at = max(
                filter(None, (ready.get("win_market_cohort_at_utc"), win_observations.get(rid))),
                key=clock, default=None,
            )
            market = market_rows(db, rid, win_at)
            roster_pin = handoff_by_race.get(rid, {}).get("model_input_sources", {}).get("collector_starts_sha256")
            if roster_pin and roster_sha != roster_pin:
                raise ValueError("Collector startlist SHA-256 mismatch")
            model, model_sha = models.get(rid, (None, None))
            analysis = None
            if row.get("full_field") and anchor_models.get(rid, (None, None))[1] != row["model_sha256"]:
                raise ValueError("Model SHA mismatch")
            if model is not None:
                analysis = model_analysis(model, model_sha)
                if analysis:
                    source_pin = model["collector_source_evidence"].get("sha256") if model.get(
                        "collector_source_evidence"
                    ) else None
                    original_timing = timing.get(source_pin, {}).get(rid)
                    if original_timing:
                        cutoff = original_timing["t4_cutoff_utc"]
                        if (original_timing["canonical_start_utc"] != analysis["start_at_freeze_utc"]
                                or not clock(analysis["as_of"]) <= clock(analysis["created_at_utc"])
                                < clock(cutoff)):
                            raise ValueError("Model freeze conflicts with original CORE-003 timing")
                        analysis["cutoff_utc"] = cutoff
                        analysis["timing_source_sha256"] = source_pin
            schedule_versions = []
            later_cutoff = None
            if analysis:
                at_freeze = analysis["start_at_freeze_utc"]
                schedules = [(at_freeze, analysis["as_of"])]
                if clock(scheduled) != clock(at_freeze):
                    schedules.append((scheduled, index["as_of_utc"]))
                for schedule, observed_before in schedules:
                    order = "DESC" if schedule == at_freeze else "ASC"
                    event = db.execute(
                        f"""SELECT source_uri, source_schedule_raw, normalized_start_utc,
                                  observed_at_utc, source_body_sha256, source_grade
                           FROM race_schedule_observations WHERE race_id=? AND normalized_start_utc=?
                             AND julianday(observed_at_utc) <= julianday(?)
                           ORDER BY julianday(observed_at_utc) {order} LIMIT 1""",
                        (rid, schedule, observed_before),
                    ).fetchone()
                    if (event and schedule == scheduled
                            and clock(scheduled) != clock(analysis["start_at_freeze_utc"])):
                        later_cutoff = (clock(scheduled) - timedelta(minutes=4)).isoformat()
                    if event and event not in schedule_versions:
                        schedule_versions.append(event)
            official = official_observation(rid, result_dirs[rid], model) if rid in result_dirs else None
            runners = [
                {"number": r["startNumber"], "name": r["horseName"], "scratch": r["isScratched"],
                 "win": market.get(str(r["startNumber"]), (None, None))[0] if not r["isScratched"] else None,
                 "win_at": market.get(str(r["startNumber"]), (None, None))[1] if not r["isScratched"] else None}
                for r in roster
            ]
            races.append({
                "race_id": rid, "track": track, "country": country, "number": int(race_no),
                "start": readiness.get(rid, {}).get("canonical_start_utc") or scheduled, "active": sum(not r["scratch"] for r in runners)
                if runners else None, "scratched": sum(r["scratch"] for r in runners) if runners else None,
                "verified_history": ready.get("verified_active_history"), "roster_sha256": roster_sha,
                "runners": runners, "analysis": analysis, "official": official,
                "queue_evidence": queue_events.get(rid, []),
                "model_attempts": model_attempts.get(rid, []),
                "model_evidence_status": (
                    "VERIFIED_FREEZE" if analysis else "ARCHIVED_PORT_DISPOSITION"
                    if model_attempts.get(rid) else "NO_ARCHIVED_MODEL_PORT_EVIDENCE"
                ),
                "later_schedule_cutoff_utc": later_cutoff,
                "schedule_versions": [
                    dict(zip(("uri", "raw", "start_utc", "observed_utc", "sha256", "grade"), event, strict=True))
                    for event in schedule_versions
                ],
                "reasons": (
                    model.get("market_blockers", []) if analysis else
                    ["NOT_BEFORE_CONSERVATIVE_T4"] if rid in late else
                    [row["primary_stop_reason"], *row["collector_blockers"], *row["model_blockers"]]
                    if row else prior_reasons.get(rid, ["NO_ARCHIVED_MODEL_PORT_EVIDENCE"])
                ),
                "full_market": bool(runners and any(not r["scratch"] for r in runners)
                                    and all(r["scratch"] or r["win"] is not None for r in runners)),
            })
    atg_calendar = getattr(args, "atg_calendar", None)
    if atg_calendar is not None:
        calendar = checked(atg_calendar.read_bytes(), args.atg_calendar_sha)
        calendar_races = calendar_only_races(calendar, args.date, races)
        for race in calendar_races:
            folder = result_dirs.get(race["race_id"])
            if folder:
                observation = official_atg_observation(race, folder)
                race["official"] = observation
                race["runners"] = observation["result_roster"]
        races.extend(calendar_races)
    benchmark = historical = None
    if args.archive:
        old = checked(args.archive.read_bytes(), args.archive_sha)
        benchmark = old["metrics"]
        candidates = sorted(
            (r for r in old["records"] if r["evaluation_status"] == "TRIPLE_EVALUABLE"),
            key=lambda r: (r["start_utc"], r["race_id"]), reverse=True,
        )
        if candidates:
            row = candidates[0]
            pin = row["source_freeze"]
            member = pin["source_model_path"].split("/", 1)[1]
            if not re.fullmatch(r"[0-9]+/race-[0-9]{3,}/shadow\.json", member):
                raise ValueError("Unexpected archived model path")
            model = checked((args.models / member).read_bytes(), pin["source_model_original_sha256"])
            if model["race"]["race_id"] != row["race_id"]:
                raise ValueError("Historical model race mismatch")
            historical = {
                "race": model["race"], "analysis": model_analysis(model, pin["source_model_original_sha256"]),
                "scores": row["scores"], "winner_selection_id": row["winner_selection_id"],
                "winner_name": next(
                    runner["horse_name"] for runner in model["runners"]
                    if runner["selection_id"] == row["winner_selection_id"]
                ),
            }
    return {
        "atg_calendar_sha256": args.atg_calendar_sha if atg_calendar else None,
        "date": args.date.isoformat(), "as_of": index["as_of_utc"], "run": args.run,
        "ledger_sha256": args.ledger_sha, "report_at": args.report_at, "meeting": args.meeting, "prior_run": args.prior_run, "races": sorted(
            races, key=lambda r: (not bool(r["analysis"]), not r["full_market"], r["start"] or "", r["race_id"])
        ),
        "historical": historical, "benchmark": benchmark, "archive_run": args.archive_run, "bet_authority": False, "pit_certified": False,
    }


def number(value, scale=1, suffix=""):
    return "–" if value is None else f"{value * scale:.2f}{suffix}".replace(".", ",")


def clock_label(value):
    instant = clock(value)
    return "ukjent" if instant is None else instant.astimezone(OSLO).strftime("%d.%m.%Y %H:%M:%S")


def render(report):
    track = f" · {report['races'][0]['track']}" if report.get("meeting") and report["races"] else ""
    title = f"Betting HQ{track} · {report['date']}"
    races = report["races"]
    models = sum(bool(r["analysis"]) for r in races)
    market = sum(r["full_market"] or bool(r["analysis"] and all(
        h["win"] is not None for h in r["analysis"]["runners"]
    )) for r in races)
    market_any = sum(any(r["win"] is not None for r in race["runners"])
                     or bool(race["analysis"] and any(h["win"] is not None for h in race["analysis"]["runners"]))
                     for race in races)
    summary = (f"{len(races)} løp i rapporten · {models} med modellestimat · "
               f"{market_any} med WIN-priser ({market} komplette felt) · {len(races) - models} uten gyldig modell.")
    text = [title, summary, "Research / NO BET. Datagrunnlag " + clock_label(report["as_of"]) + " · Europe/Oslo",
            f"BET: 0 autoriserte · {len(races)} ikke-eksekverbare løpsobservasjoner.",
            "Shadow-P/L og CLV er utilgjengelige i rapportgrunnlaget."]
    html = [f"<h1>{escape(title)}</h1>", f"<p><strong>{escape(summary)}</strong></p>",
            *[f"<p>{escape(line)}</p>" for line in text[2:]]]

    def section(heading, description):
        text.extend(["", heading, description])
        html.extend([f"<h2>{escape(heading)}</h2>", f"<p>{escape(description)}</p>"])

    def table(headers, rows):
        text.append(" | ".join(headers))
        text.extend(" | ".join(row) for row in rows)
        html.append('<div style="overflow-x:auto"><table><thead><tr>')
        html.extend(f'<th scope="col">{escape(cell)}</th>' for cell in headers)
        html.append("</tr></thead><tbody>")
        for row in rows:
            html.append("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>")
        html.append("</tbody></table></div>")

    def analysis_table(analysis):
        text.append(f"Frys {clock_label(analysis['created_at_utc'])} · {analysis['versions']} · Forskningsestimater, PIT ikke sertifisert.")
        html.append(f"<p>{escape(text[-1])}</p>")
        table(["Nr", "Hest", "Champion", "CORE-004", "Fair odds", "WIN", "EV", "Vurdering og grunnlag"], [
            [str(r["number"]), r["name"], number(r["p"], 100, "%"), number(r["core"], 100, "%"),
             number(r["fair"]), f"{number(r['win'])} · {clock_label(r['win_at'])}",
             number(r["ev"], 100, "%"),
             f"{r['status'] or 'Ingen klassifisering'} · Historikk {r['starts']} starter / {r['wins']} seire"
             + (f" · Minste BET-odds {number(r['minimum_odds'])}" if r["minimum_odds"] else "")]
            for r in analysis["runners"]
        ])

    for race in races:
        active = "ukjent" if race["active"] is None else str(race["active"])
        scratch = "ukjent" if race["scratched"] is None else str(race["scratched"])
        status = "Forskningsestimater" if race["analysis"] else "NO VALID MODEL"
        if race.get("calendar_only"):
            status = "Kun ATG-kalender · " + str(race.get("calendar_status") or "ukjent status")
        section(f"{race['track']} · {race['country']} · løp {race['number']}",
                f"Planlagt {clock_label(race['start'])} · {active} aktive · {scratch} strøket · {status}.")
        report_at = clock(report.get("report_at"))
        start = clock(race["start"])
        if report_at and start:
            state = "Planlagt start passert" if start <= report_at else "Kommende etter registrert plan"
            text.append(state)
            html.append(f"<p>{state}</p>")
        analysis = race["analysis"]
        official = race.get("official")
        if analysis:
            market_note = REASONS["NO_WIN_MARKET_AS_OF"]
            if not any(r["win"] is not None for r in analysis["runners"]):
                text.append(market_note)
                html.append(f"<p>{escape(market_note)}</p>")
            timing_line = f"Start ved frys {clock_label(analysis['start_at_freeze_utc'])}."
            if analysis.get("cutoff_utc"):
                timing_line += f" Opprinnelig T−4 {clock_label(analysis['cutoff_utc'])}."
            if race.get("later_schedule_cutoff_utc"):
                timing_line += (
                    f" Senere kalenderverdi gir T−4 {clock_label(race['later_schedule_cutoff_utc'])}."
                    " Fryset vurderes mot den opprinnelige fristen."
                )
            text.append(timing_line)
            html.append(f"<p>{escape(timing_line)}</p>")
            analysis_table(analysis)
        else:
            reasons = " ".join(REASONS[code] for code in dict.fromkeys(race["reasons"]) if code in REASONS)
            explanation = reasons or "Verifisert fullfeltmodell mangler i denne kjøringen."
            history_count = race.get("verified_history")
            if history_count is not None:
                explanation += f" CORE-003 verifiserte historikk for {history_count} aktive hester."
            else:
                explanation += " Historikkdekning er ikke målt i de kontrollerte kjøringene."
            text.append(explanation)
            html.append(f"<p>{escape(explanation)}</p>")
            if race["runners"]:
                if race.get("calendar_only"):
                    roster_note = "Startfelt fra offisielt ATG-resultat etter løpet."
                    text.append(roster_note)
                    html.append(f"<p>{roster_note}</p>")
                table(["Nr", "Hest", "Status", "WIN", "Observert"], [
                    [str(r["number"]), r["name"], "Strøket" if r["scratch"] else "Aktiv",
                     number(r["win"]), clock_label(r["win_at"])] for r in race["runners"]
                ])
        if official:
            winner = official["winner"]
            result = f"Resultatkilden oppgir faktisk start {clock_label(official['reported_actual_start_utc'])}."
            if winner:
                result += f" Vinner {winner['number']} {winner['name']}."
            elif official.get("winners"):
                result += " Delt seier " + ", ".join(
                    f"{row['number']} {row['name']}" for row in official["winners"]
                ) + "."
            if official["scratches"]:
                result += f" Strøket i resultatet: {', '.join(official['scratches'])}."
            if official["score_blocker"] == "OFFICIAL_LATE_SCRATCH_NOT_FROZEN":
                result += " Skåring blokkert fordi det offisielle feltet avviker fra feltet ved frys."
            elif official["score_blocker"]:
                result += " Skåring mangler verifisert grunnlag."
            text.append(result)
            html.append(f"<p>{escape(result)}</p>")
            if official["scores"]:
                table(["Grunnlag", "Log loss", "Multiclass Brier"], [
                    [name, number(score["log_loss"]), number(score["brier"])]
                    for name, score in official["scores"].items()
                ])
    if report["historical"] and report["historical"]["analysis"]:
        example = report["historical"]
        race = example["race"]
        section("Historisk analyseeksempel",
                f"{race['track']} · løp {race['race_no']} · {race['race_date']}. Arkivert før start. "
                "Forskningsestimater og teoretisk EV. WATCH/PASS er arkiverte forskningsvurderinger.")
        analysis_table(example["analysis"])
        result = f"Arkivert offisiell vinner {example['winner_selection_id']} {example['winner_name']}."
        text.append(result)
        html.append(f"<p>{escape(result)}</p>")
        table(["Grunnlag", "Log loss", "Multiclass Brier"], [
            [label, number(example["scores"][key]["log_loss"]),
             number(example["scores"][key]["multiclass_brier"])]
            for key, label in (("champion", "Champion"), ("core004", "CORE-004"), ("market", "WIN"))
        ])
    if report.get("meeting") is None and report["races"]:
        meetings = Counter((r["track"], r["country"]) for r in races)
        section("Møter i rapporten", "Fysiske løp i det arkiverte programmet.")
        table(["Bane", "Land", "Løp"], [[track, country, str(count)]
                                        for (track, country), count in sorted(meetings.items())])
    if report["benchmark"]:
        metrics = report["benchmark"]["triple"]
        section("Historisk modellkvalitet",
                f"{report['benchmark']['pair']['races']} evaluerbare modellpar. "
                f"{metrics['races']} løp med alle tre modeller/marked på samme grunnlag.")
        table(["Grunnlag", "Log loss", "Multiclass Brier"], [
            [label, number(metrics["scores"][key]["log_loss"]), number(metrics["scores"][key]["multiclass_brier"])]
            for key, label in (("champion", "Champion"), ("core004", "CORE-004"), ("market", "WIN"))
            if metrics["scores"] and key in metrics["scores"]
        ])
    source = f"https://github.com/Maremoo2/Betting/actions/runs/{report['run']}"
    text.extend(["", "Originale Actions-artefakter", source])
    html.append(f'<p><a href="{source}">Originale Actions-artefakter</a></p>')
    if report.get("prior_run"):
        link = f"https://github.com/Maremoo2/Betting/actions/runs/{report['prior_run']}"
        text.append("Original modellkjøring · " + link)
        html.append(f'<p><a href="{link}">Original modellkjøring</a></p>')
    if report["archive_run"]:
        archive_link = f"https://github.com/Maremoo2/Betting/actions/runs/{report['archive_run']}"
        text.append("Historisk originaleksempel · " + archive_link)
        html.append(f'<p><a href="{archive_link}">Historisk originaleksempel</a></p>')
    style = ("body{font:16px/1.5 Arial,sans-serif;color:#182b35;background:#f3f7f6;margin:0}"
             "main{max-width:1040px;margin:auto;padding:clamp(16px,5vw,48px)}"
             "h1{color:#124b40}h2{border-top:1px solid #b7cbc5;padding-top:20px}"
             "table{border-collapse:collapse;width:100%;background:#fff}"
             "th,td{text-align:left;padding:8px;border-bottom:1px solid #d4e1dd}"
             "th{background:#d9ebe5}a{color:#125a4b}")
    page = ('<!doctype html><html lang="nb"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title><style>{style}</style><main>{''.join(html)}</main></html>")
    return title, "\n".join(text) + "\n", page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("ledger", "core", "cohort", "handoff", "collector", "db", "output"):
        parser.add_argument(f"--{key}", required=True, type=Path)
    parser.add_argument("--ledger-sha", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--run", required=True, type=int)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--meeting")
    scope.add_argument("--nordic", action="store_true")
    parser.add_argument("--timing-core", nargs=2, action="append", default=[])
    parser.add_argument("--official-result", nargs=2, action="append", default=[])
    parser.add_argument("--prior-cohort", nargs=2, action="append", default=[])
    parser.add_argument("--report-at")
    parser.add_argument("--prior-run", type=int)
    parser.add_argument("--atg-calendar", type=Path)
    parser.add_argument("--atg-calendar-sha")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--archive-sha")
    parser.add_argument("--archive-run", type=int)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--recipient", help="Optional To header for the local preview. Never sends mail.")
    args = parser.parse_args()
    if bool(args.atg_calendar) != bool(args.atg_calendar_sha) or (args.atg_calendar and not args.nordic):
        parser.error("--atg-calendar and --atg-calendar-sha require --nordic and each other")
    if args.report_at and clock(args.report_at) is None:
        parser.error("--report-at requires a timezone-aware timestamp")
    if any((args.archive, args.archive_sha, args.models)) and not all((args.archive, args.archive_sha, args.models)):
        parser.error("--archive, --archive-sha and --models must be supplied together")
    report = build_report(args)
    title, text, html = render(report)
    message = EmailMessage(policy=policy.SMTP)
    message["Subject"] = title + " · Research / NO BET"
    if args.recipient:
        message["To"] = args.recipient
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, body in {
        "betting-hq.html": html.encode(), "betting-hq.txt": text.encode(),
        "betting-hq.json": json.dumps(report, ensure_ascii=False, indent=2).encode(),
        "betting-hq.eml": message.as_bytes(),
    }.items():
        (args.output / filename).write_bytes(body)


if __name__ == "__main__":
    main()
