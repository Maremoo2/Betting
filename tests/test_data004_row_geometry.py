"""Synthetic layout controls: no generated history values are gold."""
import fitz
import pytest

from hbi.data004_row_geometry import identify_original_row


def _page(*, other_heading=False, foreign_token=False, duplicate_history=False,
          missing_header=False, history_in_next_section=False):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    if not missing_header:
        page.insert_text((14, 100), "8 C.R.NOBLESS", fontsize=11)
    if not history_in_next_section:
        marker = "21.08.26-2" if foreign_token else "20.08.26-2"
        page.insert_text((48, 135), "Mp " + marker + "|1 1", fontsize=5.3)
        if duplicate_history:
            page.insert_text((48, 149), "Mp " + marker + "|1 1", fontsize=5.3)
    if other_heading or history_in_next_section:
        page.insert_text((14, 180), "9 DIFFERENT HORSE", fontsize=11)
    if history_in_next_section:
        page.insert_text((48, 200), "Mp 20.08.26-2|1 1", fontsize=5.3)
    return doc, page


def test_unique_horse_header_and_history_token_in_same_section():
    doc, page = _page(other_heading=True)
    try:
        item = identify_original_row(
            page, horse="C.R.NOBLESS", source_date="2026-08-20",
            race_token="2026.08.-2",
        )
        assert item["status"] == "GEOMETRY_UNIQUE_HEADER_AND_HISTORY_TOKEN"
        assert item["historical_date_race_token"] == "20.08.26-2"
        assert 100 < item["date_race_token_bbox_pdf_points"][1] < 180
        assert item["independent_visual_field_gold"] is False
    finally:
        doc.close()


@pytest.mark.parametrize("fault", [
    "missing_header", "foreign_token", "duplicate_history", "history_in_next_section",
])
def test_invalid_identity_or_ownership_abstains(fault):
    doc, page = _page(**{fault: True})
    try:
        with pytest.raises(ValueError):
            identify_original_row(
                page, horse="C.R.NOBLESS", source_date="2026-08-20",
                race_token="2026.08.-2",
            )
    finally:
        doc.close()


def test_missing_race_id_and_invalid_date_do_not_force_source_match():
    doc, page = _page()
    try:
        for day, race in [("2026-08-20", "missing"), ("2026-99-80", "2026.08.-2")]:
            with pytest.raises(ValueError):
                identify_original_row(page, horse="C.R.NOBLESS",
                                      source_date=day, race_token=race)
    finally:
        doc.close()


def test_no_header_font_does_not_count_as_unique_horse_section():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((14, 100), "8 C.R.NOBLESS", fontsize=6)
    page.insert_text((48, 135), "Mp 20.08.26-2|1 1", fontsize=5.3)
    try:
        with pytest.raises(ValueError):
            identify_original_row(page, horse="C.R.NOBLESS",
                                  source_date="2026-08-20",
                                  race_token="2026.08.-2")
    finally:
        doc.close()
