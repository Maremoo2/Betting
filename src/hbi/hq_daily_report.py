"""Render a Norwegian NO BET briefing from existing, archived research outputs."""

import argparse
import json
import math
import re
import sqlite3
from datetime import date
from email import policy
from email.message import EmailMessage
from html import escape
from pathlib import Path
from zipfile import ZipFile

from .prospective_outcome_scorecard import _field, _market, clock, digest
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
            "as_of": model["as_of_utc"], "sha256": sha}


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
    with ZipFile(args.cohort) as archive:
        index = checked(archive.read("cohort-index.json"), current["cohort_index_sha256"])
        models = {}
        for item in index["processed"]:
            if not re.fullmatch(r"bet-mvp-shadow/race-[0-9]{3,}", item["directory"]):
                raise ValueError("Unexpected model path")
            name = item["directory"].split("/")[-1]
            models[item["race_id"]] = (
                checked(archive.read(f"{name}/shadow.json"), item["report_sha256"]), item["report_sha256"]
            )
    ids = [row["race_id"] for row in current["records"]]
    if (len(ids) != len(set(ids)) or set(ids) != set(source["races_in_fixed_cohort"])
            or set(ids) != set(index["original_cohort"])):
        raise ValueError("Original race cohort mismatch")
    readiness = {row["race_id"]: row for row in source["race_readiness_after"]}
    races = []
    if digest(args.db.read_bytes()) != index["source_database_sha256"]:
        raise ValueError("Archived database SHA-256 mismatch")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db, ZipFile(
        args.collector
    ) as collector:
        for row in current["records"]:
            rid = row["race_id"]
            _, meeting, race_no = rid.split(":")
            if not meeting.endswith(args.date.isoformat()):
                continue
            track, country, _ = db.execute(
                "SELECT track, country, start_time_utc FROM races WHERE race_id=?", (rid,)
            ).fetchone()
            ready = readiness[rid]
            roster, roster_sha = original_roster(collector, rid)
            market = market_rows(db, rid, ready["win_market_cohort_at_utc"])
            roster_pin = handoff_by_race.get(rid, {}).get("model_input_sources", {}).get("collector_starts_sha256")
            if roster_pin and roster_sha != roster_pin:
                raise ValueError("Collector startlist SHA-256 mismatch")
            model, model_sha = models.get(rid, (None, None))
            analysis = None
            if model is not None and row["full_field"] and row["model_sha256"]:
                if model["race"]["race_id"] != rid or model_sha != row["model_sha256"]:
                    raise ValueError("Model race mismatch")
                analysis = model_analysis(model, row["model_sha256"])
            runners = [
                {"number": r["startNumber"], "name": r["horseName"], "scratch": r["isScratched"],
                 "win": market.get(str(r["startNumber"]), (None, None))[0] if not r["isScratched"] else None,
                 "win_at": market.get(str(r["startNumber"]), (None, None))[1] if not r["isScratched"] else None}
                for r in roster
            ]
            races.append({
                "race_id": rid, "track": track, "country": country, "number": int(race_no),
                "start": ready["canonical_start_utc"], "active": sum(not r["scratch"] for r in runners)
                if runners else None, "scratched": sum(r["scratch"] for r in runners) if runners else None,
                "verified_history": ready["verified_active_history"], "roster_sha256": roster_sha,
                "runners": runners, "analysis": analysis,
                "reasons": [row["primary_stop_reason"], *row["collector_blockers"], *row["model_blockers"]],
                "full_market": bool(runners and any(not r["scratch"] for r in runners)
                                    and all(r["scratch"] or r["win"] is not None for r in runners)),
            })
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
            historical = {"race": model["race"], "analysis": model_analysis(model, pin["source_model_original_sha256"])}
    return {
        "date": args.date.isoformat(), "as_of": index["as_of_utc"], "run": args.run,
        "ledger_sha256": args.ledger_sha, "races": sorted(
            races, key=lambda r: (not bool(r["analysis"]), not r["full_market"], r["start"] or "", r["race_id"])
        ),
        "historical": historical, "benchmark": benchmark, "archive_run": args.archive_run, "bet_authority": False, "pit_certified": False,
    }


def number(value, scale=1, suffix=""):
    return "–" if value is None else f"{value * scale:.2f}{suffix}".replace(".", ",")


def clock_label(value):
    return "ukjent" if not value else value.replace("T", " ").split("+")[0].split(".")[0] + " UTC"


def render(report):
    title = f"Betting HQ · {report['date']}"
    races = report["races"]
    models = sum(bool(r["analysis"]) for r in races)
    market = sum(r["full_market"] for r in races)
    market_any = sum(any(r["win"] is not None for r in race["runners"]) for race in races)
    summary = (f"{len(races)} løp i CORE-003-kohorten · {models} med modellestimat · "
               f"{market_any} med WIN-priser ({market} komplette felt) · {len(races) - models} uten gyldig modell.")
    text = [title, summary, "Research / NO BET. " + clock_label(report["as_of"]),
            f"BET: 0 autoriserte · {len(races)} ikke-eksekverbare løpsobservasjoner.",
            "Shadow-P/L og CLV er utilgjengelig for denne rapportkilden."]
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
        text.append(f"Frys {clock_label(analysis['as_of'])} · {analysis['versions']}")
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
        section(f"{race['track']} · {race['country']} · løp {race['number']}",
                f"Planlagt {clock_label(race['start'])} · {active} aktive · {scratch} strøket · {status}.")
        if race["analysis"]:
            analysis_table(race["analysis"])
        else:
            reasons = " ".join(REASONS[code] for code in dict.fromkeys(race["reasons"]) if code in REASONS)
            explanation = reasons or "Verifisert fullfeltmodell mangler i denne kjøringen."
            text.append(explanation)
            html.append(f"<p>{escape(explanation)}</p>")
            if race["runners"]:
                table(["Nr", "Hest", "Status", "WIN", "Observert"], [
                    [str(r["number"]), r["name"], "Strøket" if r["scratch"] else "Aktiv",
                     number(r["win"]), clock_label(r["win_at"])] for r in race["runners"]
                ])
    if report["historical"] and report["historical"]["analysis"]:
        example = report["historical"]
        race = example["race"]
        section("Historisk analyseeksempel",
                f"{race['track']} · løp {race['race_no']} · {race['race_date']}. Arkivert før start. "
                "Forskningsestimater og teoretisk EV. WATCH/PASS er arkiverte forskningsvurderinger.")
        analysis_table(example["analysis"])
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
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--archive-sha")
    parser.add_argument("--archive-run", type=int)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--recipient", help="Optional To header for the local preview. Never sends mail.")
    args = parser.parse_args()
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
