"""Read-only authentic Collector PDF five-line history sidecar, NO BET.

Verifies the exact original PDF bytes against the 07 Oslo collector manifest,
then joins the structured *derived* program against source-confirmed canonical
names and physical race numbers. REVEALING a dated raw program line does NOT
constitute an independently parsed official result, verified opponent ID,
provider publication time, PIT certificate or market-free Challenger feature.

No changes to Champion, V3.3.12, thresholds, scheduler or model snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath

SCHEMA = "COLLECTOR_PDF_LASTFIVE_PIT_RESEARCH_V1"
SOURCES = {
    "BERGSAKER_V85":"S1_NR_2026-11-07",
    "KLOSTERSKOGEN_V75":"KL_NR_2026-11-07",
}
DATE = "2026-11-07"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _clock(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("COLLECTOR_SOURCE_CLOCK_NOT_AWARE")
    return parsed.astimezone(UTC)


class OriginalArchive:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.zip = zipfile.ZipFile(root) if root.is_file() else None
        self.files = (self.zip.namelist() if self.zip else
                      [p.relative_to(root).as_posix()
                       for p in root.rglob("*") if p.is_file()])
        names=[x for x in self.files if x.endswith("/manifest.json")]
        if len(names)!=1:
            raise ValueError("COLLECTOR_MANIFEST_NOT_UNIQUE")
        self.manifest_path = names[0]
        self.prefix = names[0].removesuffix("manifest.json")
        self.manifest_raw = self.read(names[0])
        self.manifest = json.loads(self.manifest_raw)

    def read(self, name: str) -> bytes:
        part=PurePosixPath(name)
        if (not isinstance(name,str) or not name
                or part.is_absolute() or ".." in part.parts
                or name not in self.files):
            raise ValueError("COLLECTOR_ARCHIVE_MEMBER_NOT_ALLOWED")
        if self.zip:
            return self.zip.read(name)
        file=self.root.joinpath(*part.parts)
        if file.is_symlink():
            raise ValueError("COLLECTOR_SYMLINK_ORIGINAL_UNSAFE")
        return file.read_bytes()


def _collector_pdf(
    archive: OriginalArchive, key: str, *,
    cutoff: datetime,
) -> tuple[dict, dict]:
    url=(f"https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/{key}")
    candidates=[r for r in archive.manifest.get("requests",[])
                if isinstance(r,dict) and r.get("url")==url]
    if len(candidates)!=1:
        raise ValueError("COLLECTOR_PDF_MANIFEST_RECEIPT_NOT_UNIQUE")
    receipt=candidates[0]
    observed=_clock(receipt.get("at_utc"))
    if observed>cutoff:
        raise ValueError("COLLECTOR_PDF_SOURCE_AFTER_CUTOFF")
    member=archive.prefix+"meetings/"+key+"/full_program.pdf"
    if (receipt.get("path")!=member
            or receipt.get("status")!="PDF_OK"
            or receipt.get("raw_readback_verified") is not True):
        raise ValueError("COLLECTOR_PDF_NOT_RAW_ORIGINAL")
    raw=archive.read(member)
    if not raw.startswith(b"%PDF-") or _sha(raw)!=receipt.get("sha256"):
        raise ValueError("COLLECTOR_PDF_SHA_MISMATCH")
    parsed_path=archive.prefix+"meetings/"+key+"/structured_program.json"
    text_path=archive.prefix+"meetings/"+key+"/full_program.txt"
    parsed_bytes=archive.read(parsed_path)
    parsed=json.loads(parsed_bytes)
    text=archive.read(text_path).decode("utf-8")
    if (not isinstance(parsed.get("qa"),dict)
            or parsed["qa"].get("document_date")!=DATE
            or not isinstance(parsed.get("races"),list)):
        raise ValueError("COLLECTOR_PDF_DERIVED_SCHEMA_UNVERIFIED")
    return {
        "source_pdf_sha256":receipt["sha256"],
        "source_observed_at_utc":observed.isoformat(),
        "source_published_at_utc":None,
        "source_url":url,
        "collector_derivative_sha256":_sha(parsed_bytes),
        "manifest_original_sha256":_sha(archive.manifest_raw),
        "parser_qa_status":parsed["qa"].get("status"),
        "extracted_text":text,
    }, parsed


def _dated_lines(entry: dict, text: str) -> list[dict]:
    history=entry.get("past_starts")
    if not isinstance(history,list) or len(history)!=5:
        raise ValueError("PDF_NOT_EXACTLY_FIVE_DATED_ORIGINAL_LINES")
    output=[]
    for row in history:
        stamp,raw=row.get("date"),row.get("raw_text")
        if not isinstance(stamp,str) or not isinstance(raw,str):
            raise TypeError("PDF_LINE_DATE_OR_RAW_MISSING")
        matches=re.findall(r"(\d\d)\.(\d\d)\.(\d\d)-(\d+)",raw)
        if len(matches)!=1 or raw not in entry.get("raw_section","") or raw not in text:
            raise ValueError("PDF_LINE_NOT_IN_ORIGINAL_EXTRACTION")
        day,month,year,no=matches[0]
        reconstructed=date(2000+int(year),int(month),int(day))
        if reconstructed.isoformat()!=stamp or reconstructed>=date.fromisoformat(DATE):
            raise ValueError("PDF_PAST_DATE_UNATTESTED_OR_AFTER_EVENT")
        output.append({
            "date":stamp,"past_race_number_from_line":int(no),
            "raw_text":raw,"raw_line_sha256":_sha(raw.encode("utf-8")),
            "placing":"MISSING_UNVALIDATED_COLUMN",
            "time":"MISSING_UNVALIDATED_COLUMN",
            "kilometre_time":"MISSING_UNVALIDATED_COLUMN",
            "distance":"MISSING_UNVALIDATED_COLUMN",
            "opponent_id":"MISSING",
        })
    if [r["date"] for r in output]!=sorted(r["date"] for r in output):
        raise ValueError("PDF_PAST_HISTORY_UNSORTED")
    return output


def audit(collector: Path, current_source: Path, *, as_of_utc: str) -> dict:
    now=_clock(as_of_utc)
    archive=OriginalArchive(collector)
    capture=json.loads(current_source.read_bytes())
    if (capture.get("schema")!="WEEKEND_20261106_07_ORIGINAL_INTELLIGENCE_V1"
            or capture.get("bet_authority") is not False):
        raise ValueError("UNTRUSTED_PHYSICAL_RACE_SOURCE")
    if archive.manifest.get("date_oslo")!=DATE:
        raise ValueError("COLLECTOR_WRONG_RACEDAY")
    rounds={g["name"]:g for g in capture["weekend_rounds"]}
    output=[]
    for game,key in SOURCES.items():
        if game not in rounds:
            raise ValueError("COLLECTOR_PHYSICAL_MEETING_NOT_FOUND")
        source,derived=_collector_pdf(archive,key,cutoff=now)
        races={r["race"]["race_number"]:r for r in derived["races"]}
        scored=[]
        for leg in rounds[game]["legs"]:
            physical=leg["physical_race_id"]
            if physical!=f"RIKSTOTO:{key}:{leg['race_no']}":
                raise ValueError("COLLECTOR_PHYSICAL_RACE_JOIN_DEFECT")
            start=_clock(leg["race_start_utc"])
            existing=races.get(leg["race_no"])
            if existing is None:
                raise ValueError("COLLECTOR_PDF_RACE_NOT_PRESENT")
            entrants={int(e["program_number"]):e for e in existing["entrants"]}
            if len(entrants)!=len(existing["entrants"]):
                raise ValueError("PDF_PROGRAM_NUMBER_COLLISION")
            runners=[]
            for person in leg["runners"]:
                if not person["active"]:
                    continue
                entry=entrants.get(person["number"])
                label=(entry.get("name","") if isinstance(entry,dict) else "")
                if not label or label.strip().casefold()!=person["name"].strip().casefold():
                    runners.append({
                        "number":person["number"],"horse":person["name"],
                        "status":"IDENTITY_UNRESOLVED",
                        "last_5":"MISSING","last_10":"MISSING","last_20":"MISSING",
                    })
                    continue
                if _clock(source["source_observed_at_utc"])>=start or now>=start:
                    runners.append({
                        "number":person["number"],"horse":person["name"],
                        "status":"NOT_AVAILABLE_AT_PIT",
                        "last_5":"NOT_AVAILABLE_AT_PIT",
                        "last_10":"MISSING","last_20":"MISSING",
                    })
                    continue
                historic=_dated_lines(entry,source["extracted_text"])
                runners.append({
                    "number":person["number"],"horse":person["name"],
                    "status":"PARTIAL_REVIEW_REQUIRED",
                    "last_5":"PARTIAL_DATED_SOURCE_LINES_NOT_VERIFIED_RESULTS",
                    "last_10":"MISSING","last_20":"MISSING",
                    "prior_opponents":"MISSING_NO_STABLE_PREVIOUS_RACE_IDENTITIES",
                    "source_original_pdf_sha256":source["source_pdf_sha256"],
                    "source_observed_at_utc":source["source_observed_at_utc"],
                    "source_published_at_utc":None,
                    "past_starts":historic,
                    "bet_authority":False,
                })
            scored.append({
                "leg":leg["leg"],"race_id":physical,
                "active_runners":leg["active_runners"],
                "five_dated_rows":sum(x.get("status")=="PARTIAL_REVIEW_REQUIRED"
                                       for x in runners),
                "runners":runners,
            })
        del source["extracted_text"]
        output.append({"round":game,"source":source,"legs":scored})
    return {
        "schema":SCHEMA,"as_of_utc":now.isoformat(),
        "bet_authority":False,"pit_certified":False,
        "source_originals_verified":True,
        "parser_five_line_results_verified":False,
        "registered_historic_5_rows":sum(
            x["five_dated_rows"] for g in output for x in g["legs"]),
        "historic_opponent_strength_available":0,
        "full_last5_10_20_verified":0,"rounds":output,
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collector-root",type=Path,required=True)
    p.add_argument("--current-source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    out=audit(args.collector_root,args.current_source,
              as_of_utc=datetime.now(UTC).isoformat())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({
        "history_rows":out["registered_historic_5_rows"],
        "bet_authority":False,
    }))


if __name__=="__main__":
    main()
