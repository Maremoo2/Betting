"""DATA-004 research tests: source patterns, integrity, and holdout fail-closed."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from hbi.data004_diagnostic import FIELDS, propose_historical_fields, run_audit


def test_nonword_equipment_literals_are_retained():
    for shoes, wagon in [("¢¢", "Va"), ("¢c", "Va"), ("c¢", "Am"), ("cc", "Va")]:
        raw = f"Sed Li Å 18.05.26-1|5 5 1 2140 12,8a 165 43' {shoes} {wagon}"
        proposed = propose_historical_fields(
            raw, parser_status="PARTIAL", format_group="TRAV_SPACED"
        )
        assert proposed == {"shoes": shoes, "wagon": wagon}


def test_gallop_positive_does_not_assume_absent_marker_means_false():
    for code in ("30,5 g", "br g", "21,0g", "19,3ag", "ug", "dg"):
        proposed = propose_historical_fields(
            f"Ste Bj BT 05.09.26-3|4 9 0 2120 {code} 240 40' cc Va",
            parser_status="PARSED", format_group="TRAV_SPACED",
        )
        assert proposed["gallop"] == "True", code
    for code in ("30,5", "br", "kubug", "gdk"):
        proposed = propose_historical_fields(
            f"Ste Bj BT 05.09.26-3|4 9 0 2120 {code} 240 40' cc Va",
            parser_status="PARSED", format_group="TRAV_SPACED",
        )
        assert "gallop" not in proposed


def test_unknown_formats_or_missing_section_separator_stay_unparsed():
    raw = "Lin Ma F 15.10.26-8|1111 8 1640 15,8ag 755 16' ¢¢ Va"
    for status, group in (
        ("UNPARSEABLE", "TRAV_JOINED"),
        ("PARTIAL", "TRAV_JOINED"),
        ("PARSED", "FOREIGN_FLAT"),
    ):
        assert propose_historical_fields(
            raw, parser_status=status, format_group=group
        ) == {}
    assert propose_historical_fields(
        "2140 15,8ag 755 16' ¢¢ Va",
        parser_status="PARSED", format_group="TRAV_SPACED",
    ) == {}


def _write_csv(path: Path, values: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def _fixture(tmp_path: Path):
    gold = []
    fields = []
    for number in range(60):
        sid = str(number)
        status = ["PARSED", "PARTIAL", "UNPARSEABLE"][number // 20]
        raw = "Ste Bj BT 05.09.26-3|4 9 0 2120 30,5 g 240 40' ¢¢ Va"
        row = {
            "sample_id": sid, "horse": "TEST HORSE",
            "original_data002_status": status,
            "pdf_path": "original.pdf", "pdf_sha256": "a" * 64,
            "original_pdf_row_text": raw, "source_pdf_page": "2",
            "row_identity_status": "VERIFIED", "gold_shoes": "¢¢",
            "gold_shoes_status": "VERIFIED", "gold_wagon": "Va",
            "gold_wagon_status": "VERIFIED", "gold_gallop": "True",
            "gold_gallop_status": "VERIFIED",
        }
        for field in FIELDS:
            if field not in {"shoes", "wagon", "gallop"}:
                row[f"gold_{field}"] = ""
                row[f"gold_{field}_status"] = "UNAVAILABLE"
        gold.append(row)
        for field in FIELDS:
            value = row[f"gold_{field}"]
            gold_status = row[f"gold_{field}_status"]
            fields.append({
                "sample_id": sid, "horse": row["horse"],
                "original_data002_status": status,
                "source_pdf": row["pdf_path"],
                "source_pdf_sha256": row["pdf_sha256"],
                "source_row": row["original_pdf_row_text"],
                "source_page": row["source_pdf_page"],
                "field": field, "gold_status": gold_status,
                "gold_value": value, "parser_value": "",
                "comparison": (
                    "MISSING" if gold_status == "VERIFIED" else "UNAVAILABLE_GOLD"
                ),
                "format_group": (
                    "TRAV_SPACED" if status != "UNPARSEABLE" else "TRAV_JOINED"
                ),
                "gold_frozen_sha256": "TO_FILL",
            })
    gold_path = tmp_path / "DATA-003B_gold_standard_60.csv"
    fields_path = tmp_path / "DATA-003B_field_validation.csv"
    sums_path = tmp_path / "DATA-003B_checksums.txt"
    _write_csv(gold_path, gold)
    gold_sha = hashlib.sha256(gold_path.read_bytes()).hexdigest()
    for row in fields:
        row["gold_frozen_sha256"] = gold_sha
    _write_csv(fields_path, fields)
    sums_path.write_text(
        f"{gold_sha}  {gold_path.name}\n"
        f"{hashlib.sha256(fields_path.read_bytes()).hexdigest()}  {fields_path.name}\n",
        encoding="utf-8",
    )
    return gold_path, fields_path, sums_path


def test_development_audit_does_not_certify_holdout(tmp_path):
    report = run_audit(*_fixture(tmp_path))
    assert report["source_rows"] == 60
    assert report["field_assessments"] == 780
    assert report["status"] == "DEVELOPMENT_ONLY_HOLDOUT_REQUIRED"
    assert report["holdout_verified"] is False
    assert report["production_parser_changed"] is False
    assert report["proposed_verified_fix_count"] == 120
    assert report["proposed_verified_fixes_by_field"] == {
        "shoes": 40, "wagon": 40, "gallop": 40,
    }
    json.dumps(report)


def test_bad_checksum_fails_closed(tmp_path):
    paths = _fixture(tmp_path)
    paths[0].write_text(
        paths[0].read_text(encoding="utf-8") + "corruption", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="SHA256"):
        run_audit(*paths)


def test_repeated_sample_field_fails_closed(tmp_path):
    paths = _fixture(tmp_path)
    with paths[1].open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    rows[1] = rows[0].copy()
    _write_csv(paths[1], rows)
    paths[2].write_text(
        f"{hashlib.sha256(paths[0].read_bytes()).hexdigest()}  {paths[0].name}\n"
        f"{hashlib.sha256(paths[1].read_bytes()).hexdigest()}  {paths[1].name}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown/duplicate"):
        run_audit(*paths)
