"""Source-SHA and conservative five-line original Collector research tests."""
from __future__ import annotations

import hashlib
import json
import runpy
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

SOURCE=Path(__file__).resolve().parents[1] / "scripts/challenger_v2_collector_pdf_history.py"
mod=runpy.run_path(str(SOURCE))
DATE=mod["DATE"]
KEY="S1_NR_2026-11-07"


def _line(i: int) -> str:
    return f"0{i}.10.26-{i} Race trace not fully parsed"


def _history() -> tuple[dict,str]:
    rows=[
        {"date":f"2026-10-0{i}","raw_text":_line(i)} for i in range(1,6)
    ]
    text="\n".join(_line(i) for i in range(1,6))
    return {"past_starts":rows,"raw_section":text},text


def test_only_five_original_dated_entries_admitted_as_partial():
    horse,text=_history()
    rows=mod["_dated_lines"](horse,text)
    assert len(rows)==5
    assert all(x["placing"]=="MISSING_UNVALIDATED_COLUMN" for x in rows)
    assert all(x["opponent_id"]=="MISSING" for x in rows)
    assert rows[0]["date"]=="2026-10-01"


def test_future_or_edited_derived_line_rejected():
    horse,text=_history()
    horse["past_starts"][0]["date"]="2026-11-07"
    with pytest.raises(ValueError,match="PDF_PAST_DATE"):
        mod["_dated_lines"](horse,text)
    horse,text=_history()
    with pytest.raises(ValueError,match="PDF_LINE_NOT_IN_ORIGINAL_EXTRACTION"):
        mod["_dated_lines"](horse,text.replace("Race trace","bad source"))


def _archive(tmp_path:Path, *, altered:bool=False):
    root=tmp_path/"archive"
    prefix="morning/"
    folder=root / prefix / "meetings" / KEY
    folder.mkdir(parents=True)
    raw=b"%PDF-1.7\nsource original test"
    (folder/"full_program.pdf").write_bytes(raw if not altered else b"%PDF-altered")
    (folder/"full_program.txt").write_text("fixture")
    (folder/"structured_program.json").write_text(json.dumps({
        "qa":{"status":"REVIEW_REQUIRED","document_date":DATE},
        "races":[],
    }))
    manifest=root / prefix / "manifest.json"
    manifest.write_text(json.dumps({
        "date_oslo":DATE,
        "requests":[{
            "url":"https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/"+KEY,
            "at_utc":"2026-11-07T06:18:23+00:00",
            "status":"PDF_OK","raw_readback_verified":True,
            "path":prefix+"meetings/"+KEY+"/full_program.pdf",
            "sha256":hashlib.sha256(raw).hexdigest(),
        }],
    }))
    archive_path=tmp_path/"original.zip"
    with zipfile.ZipFile(archive_path,"w") as z:
        for f in root.rglob("*"):
            if f.is_file():
                z.write(f,f.relative_to(root).as_posix())
    return archive_path


def test_exact_original_pdf_hash_from_manifest_and_derived_qa(tmp_path):
    path=_archive(tmp_path)
    archive=mod["OriginalArchive"](path)
    source,parsed=mod["_collector_pdf"](
        archive,KEY,cutoff=datetime(2026,11,7,7,0,tzinfo=UTC))
    assert source["source_original_pdf_sha256"] == source.get(
        "source_pdf_sha256"
    ) if "source_original_pdf_sha256" in source else len(
        source["source_pdf_sha256"])==64
    assert source["parser_qa_status"]=="REVIEW_REQUIRED"
    assert parsed["races"]==[]


def test_tampered_original_pdf_fails_without_pit_promotion(tmp_path):
    archive=mod["OriginalArchive"](_archive(tmp_path,altered=True))
    with pytest.raises(ValueError,match="COLLECTOR_PDF_SHA_MISMATCH"):
        mod["_collector_pdf"](
            archive,KEY,cutoff=datetime(2026,11,7,7,0,tzinfo=UTC))


def test_source_observed_after_cutoff_rejected(tmp_path):
    archive=mod["OriginalArchive"](_archive(tmp_path))
    with pytest.raises(ValueError,match="COLLECTOR_PDF_SOURCE_AFTER_CUTOFF"):
        mod["_collector_pdf"](
            archive,KEY,cutoff=datetime(2026,11,7,6,0,tzinfo=UTC))
