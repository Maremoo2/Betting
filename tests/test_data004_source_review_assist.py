"""DATA-004F tests use synthetic PDF glyphs, never accepted racing gold."""
import copy
import csv

import fitz
import pytest

from hbi.data004_source_review_assist import source_field_hints, write_navigation_csv


def _fixture(*, placing="4", time="15,1a", include_shoes=True,
             include_wagon=True, foreign=False):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((14, 60), "8 C.R.NOBLESS", fontsize=11)
    if foreign:
        page.insert_text((25, 90), "H.BOUTINLIG 20.08.26-2", fontsize=5.3)
    else:
        page.insert_text((25, 90), "Sva Os", fontsize=5.3)
        page.insert_text((48, 90), "Mp 20.08.26-2|1 1", fontsize=5.3)
        page.insert_text((102, 90), placing, fontsize=5.3)
        page.insert_text((114, 90), f"2140 {time}", fontsize=5.3)
        if include_shoes:
            page.insert_text((176, 90), "cc", fontsize=5.3)
        if include_wagon:
            page.insert_text((189, 90), "Va Winner", fontsize=5.3)
    raw = page.get_text("dict")
    dated = [
        span for block in raw["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if "20.08.26-2" in span["text"]
    ]
    assert len(dated) == 1
    row = {
        "sample_id": "156",
        "horse": "C.R.NOBLESS",
        "meeting": "S2_NR_2026-10-19",
        "source_pdf_page": 10,
        "source_pdf_sha256": "a" * 64,
        "date_race_token_bbox_pdf_points": dated[0]["bbox"],
        "historical_date_race_token": "20.08.26-2",
    }
    return doc, page, row


def _fields(result):
    return {item["field"]: item for item in result["evidence"]}


def test_printed_tokens_include_glyph_accurate_pdf_boxes_only():
    doc, page, row = _fixture()
    try:
        result = source_field_hints(page, row)
        values = _fields(result)
        assert len(values) == 13
        for name, token in {
            "date": "20.08.26",
            "race_number": "2",
            "track": "Mp",
            "driver": "Sva Os",
            "placing": "4",
            "distance": "2140",
            "km_time": "15,1a",
            "shoes": "cc",
            "wagon": "Va",
        }.items():
            item = values[name]
            assert item["printed_token"] == token
            assert item["hint_status"] == "PRINTED_TOKEN_HINT_UNREVIEWED"
            x0, y0, x1, y1 = item["printed_bbox_pdf_points"]
            assert 0 <= x0 < x1 <= page.rect.width
            assert 0 <= y0 < y1 <= page.rect.height
        assert values["date"]["printed_bbox_pdf_points"][0] > (
            values["track"]["printed_bbox_pdf_points"][2]
        )
        assert result["independent_gold_fields_accepted"] == 0
        assert result["holdout_verified"] is False
    finally:
        doc.close()


def test_absent_gallop_dq_and_derived_fields_never_get_fabricated_values():
    doc, page, row = _fixture(placing="0", time="15,1a")
    try:
        fields = _fields(source_field_hints(page, row))
        for field in ("gallop", "dq", "start_method", "result_category"):
            assert fields[field]["printed_token"] == ""
            assert fields[field]["hint_status"] == "VISUAL_REVIEW_REQUIRED"
            assert fields[field]["printed_bbox_pdf_points"] is None
    finally:
        doc.close()


def test_positive_gallop_and_dq_are_literal_hints_not_bool_certifications():
    doc, page, row = _fixture(placing="d", time="ug")
    try:
        fields = _fields(source_field_hints(page, row))
        assert fields["placing"]["printed_token"] == "d"
        assert fields["dq"]["printed_token"] == "d"
        assert fields["gallop"]["printed_token"] == "ug"
        assert fields["km_time"]["printed_token"] == ""
        assert all(x["hint_only_not_gold"] is True for x in fields.values())
    finally:
        doc.close()


def test_missing_shoes_wagon_do_not_get_negative_source_hints():
    doc, page, row = _fixture(include_shoes=False, include_wagon=False)
    try:
        fields = _fields(source_field_hints(page, row))
        assert fields["shoes"]["printed_token"] == ""
        assert fields["wagon"]["printed_token"] == ""
        assert fields["date"]["printed_token"] == "20.08.26"
    finally:
        doc.close()


def test_foreign_joined_driver_history_does_not_force_scandinavian_fields():
    doc, page, row = _fixture(foreign=True)
    try:
        fields = _fields(source_field_hints(page, row))
        assert fields["date"]["printed_token"] == "20.08.26"
        assert fields["race_number"]["printed_token"] == "2"
        for field in ("driver", "track", "placing", "distance", "km_time"):
            assert fields[field]["printed_token"] == ""
    finally:
        doc.close()


@pytest.mark.parametrize("bad_marker", ["21.08.26-2", "20.08.26-3"])
def test_wrong_history_marker_fails_closed(bad_marker):
    doc, page, row = _fixture()
    try:
        row["historical_date_race_token"] = bad_marker
        with pytest.raises(ValueError):
            source_field_hints(page, row)
    finally:
        doc.close()


def _synthetic_csv_report():
    doc, page, row = _fixture()
    try:
        one = source_field_hints(page, row)
    finally:
        doc.close()
    records = []
    for index in range(30):
        item = copy.deepcopy(one)
        item["sample_id"] = str(index + 1)
        records.append(item)
    return {
        "schema_version": "DATA004F_ORIGINAL_PDF_REVIEW_HINTS_V1",
        "locked_rows": 30,
        "field_assessments": 390,
        "literal_hints_total": sum(
            e["hint_status"] == "PRINTED_TOKEN_HINT_UNREVIEWED"
            for record in records for e in record["evidence"]
        ),
        "independent_source_gold_accepted": 0,
        "holdout_verified": False,
        "rows": records,
    }


def test_390_cell_navigation_csv_never_contains_accepted_gold(tmp_path):
    report = _synthetic_csv_report()
    target = tmp_path / "review_source_hints.csv"
    write_navigation_csv(report, target)
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 390
    assert len({(r["sample_id"], r["field"]) for r in rows}) == 390
    assert all(r["source_reading_accepted_gold"] == "NO" for r in rows)
    assert not any("parser" in key or "gold_value" in key for key in rows[0])
    assert sum(bool(r["printed_token_hint_unreviewed"]) for r in rows) == (
        report["literal_hints_total"]
    )
    with pytest.raises(FileExistsError):
        write_navigation_csv(report, target)


@pytest.mark.parametrize("fault", [
    "duplicate_sample", "missing_field", "auto_gold", "hint_count_mismatch",
    "fabricated_missing_token",
])
def test_navigation_export_rejects_bad_source_or_gold_claim(tmp_path, fault):
    report = _synthetic_csv_report()
    if fault == "duplicate_sample":
        report["rows"][-1]["sample_id"] = report["rows"][0]["sample_id"]
    elif fault == "missing_field":
        report["rows"][0]["evidence"].pop()
    elif fault == "auto_gold":
        report["rows"][0]["evidence"][0]["hint_only_not_gold"] = False
    elif fault == "hint_count_mismatch":
        report["literal_hints_total"] += 1
    elif fault == "fabricated_missing_token":
        field = next(
            e for e in report["rows"][0]["evidence"]
            if e["hint_status"] == "VISUAL_REVIEW_REQUIRED"
        )
        field["printed_token"] = "invented"
    with pytest.raises(ValueError):
        write_navigation_csv(report, tmp_path / "invalid.csv")
