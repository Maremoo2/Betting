"""Collector -> HBI original-byte handoff tests (synthetic except opt-in real archive)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fitz
import pytest

from hbi.collector_handoff import OriginalArchive, run_import, sha, verify_import

KEY = "S2_NR_2026-11-02"
RID = "RIKSTOTO:" + KEY + ":10"
START = datetime(2026, 11, 2, 20, 33, tzinfo=UTC)
NOW = START - timedelta(minutes=14)
EARLY = START - timedelta(hours=14)
NAMES = [
    "Justanother Winner", "Raya Maya Fly", "Bengt Åke", "Kentucky Buck",
    "Livery", "Queen Khaleesi", "Hereisjohnny", "Lucifer Fårup",
]


def _db(path: Path, *, scratched: bool = False, future_history: bool = False) -> None:
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE races(race_id TEXT PRIMARY KEY, race_no INTEGER,
            start_time_utc TEXT, race_date TEXT);
        CREATE TABLE provider_race_refs(race_id TEXT, provider TEXT,
            provider_raceday_key TEXT, race_number INTEGER);
        CREATE TABLE runners(race_id TEXT, selection_id TEXT, horse_name TEXT,
            post_position INTEGER, scratched INTEGER);
        CREATE TABLE provider_payloads(payload_id TEXT PRIMARY KEY, provider TEXT,
            category TEXT, provider_raceday_key TEXT, race_number INTEGER,
            product TEXT, observed_at_utc TEXT, source_uri TEXT, payload_json TEXT);
        CREATE TABLE runner_fundamental_snapshots(snapshot_id TEXT, race_id TEXT,
            selection_id TEXT, observed_at_utc TEXT, feature_as_of_utc TEXT,
            full_field_history_complete INTEGER, source_uri TEXT, scratched INTEGER,
            history_total_starts INTEGER, history_total_wins INTEGER);
    """)
    db.execute("INSERT INTO races VALUES (?,?,?,?)", (
        RID, 10, START.isoformat(), "2026-11-02"
    ))
    db.execute("INSERT INTO provider_race_refs VALUES (?,?,?,?)", (
        RID, "rikstoto", KEY, 10
    ))
    raw_rows = _rows(scratched=scratched, tmp=False)
    for i, name in enumerate(NAMES, 1):
        db.execute("INSERT INTO runners VALUES (?,?,?,?,?)", (
            RID, str(i), name, i, int(scratched and i == 8)
        ))
        moment = NOW + timedelta(minutes=2) if future_history else NOW - timedelta(seconds=30)
        db.execute("INSERT INTO runner_fundamental_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)", (
            str(i), RID, str(i), moment.isoformat(), moment.isoformat(), 1,
            "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-02_18_10",
            int(scratched and i == 8), 9 + i, 1
        ))
    for name, provider, key, body in [
        ("starts", "rikstoto", KEY, {"success": True, "result": {"10": raw_rows}}),
        ("atg", "atg", RID, {
            "passed": True, "probe_only": False, "active_runners": 7 if scratched else 8,
            "matched_complete_runners": 7 if scratched else 8,
            "active_selections": [str(i) for i in range(1, 8 if scratched else 9)],
            "runners": [
                {"selection_id": str(i), "horse_name": NAMES[i-1],
                 "provider_horse_id": str(10000+i), "schema_ok": True,
                 "match_method": "EXACT_REGISTRATION", "reason": None}
                for i in range(1, 8 if scratched else 9)
            ],
        }),
    ]:
        db.execute("INSERT INTO provider_payloads VALUES (?,?,?,?,?,?,?,?,?)", (
            name, provider, "RACEDAY_STARTS" if name == "starts" else "FULL_FIELD_ONLY_V1",
            key, 10, None, (NOW - timedelta(minutes=1)).isoformat(),
            "https://www.rikstoto.no/api/racedays/" + KEY + "/starts"
            if name == "starts" else "https://www.atg.se", json.dumps(body)
        ))
    db.commit()
    db.close()


def _rows(*, tmp=True, scratched=False):
    return [
        {"startNumber": i, "horseName": name, "raceNumber": 10,
         "raceKey": KEY + "#10", "horseRegistrationNumber": (
             f"TMP-S2-20261102-10-{i:02d}" if tmp else str(10000+i)
         ), "isScratched": bool(scratched and i == 8)}
        for i, name in enumerate(NAMES, 1)
    ]


def _archive(path: Path, *, tmp=True, scratched=False, bad_sha=False,
             physical_clock="21:33"):
    keydir = path / "output" / "daily" / "2026-11-02" / "20261102T060000000000Z"
    meeting = keydir / "meetings" / KEY
    meeting.mkdir(parents=True)
    payload = json.dumps(
        {"success": True, "result": {"10": _rows(tmp=tmp, scratched=scratched)}},
        ensure_ascii=False, separators=(",", ":")
    ).encode()
    (meeting / "starts.raw.json").write_bytes(payload)
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((50, 50), "10\nSTART KL. " + physical_clock)
    y = 90
    for i, name in enumerate(NAMES, 1):
        # DejaVu font to render Swedish accents faithfully, if present.
        name = name.replace("Å", "A").replace("å", "a")
        page.insert_text((50, y), f"{i} {name.upper()}, Test")
        y += 20
    pdf_bytes = pdf.tobytes()
    pdf.close()
    (meeting / "full_program.pdf").write_bytes(pdf_bytes)
    # This PDF fixture intentionally uses base-font fallbacks for accented
    # letters; independently verified real-source test uses genuine PDF.
    relative = meeting.relative_to(path).as_posix()
    manifest = {
        "date_oslo": "2026-11-02", "status": "CAPTURED_UNVERIFIED",
        "meetings": [{
            "meeting_id": KEY, "is_multi_track_product": False,
            "startlist_pdf_audit": {
                "status": "MATCHED_AS_OF_SNAPSHOT",
                "verified_race_numbers": [10], "mismatches": [],
            },
        }],
        "requests": [
            {"url": "https://www.rikstoto.no/api/racedays/" + KEY + "/starts",
             "raw_path": relative + "/starts.raw.json",
             "sha256": ("f"*64 if bad_sha else sha(payload)),
             "at_utc": EARLY.isoformat()},
            {"url": "https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/" + KEY,
             "path": relative + "/full_program.pdf",
             "sha256": sha(pdf_bytes), "at_utc": EARLY.isoformat()},
        ],
    }
    (keydir / "manifest.json").write_text(json.dumps(manifest))
    return path


def _archive_unicode(path: Path, *, tmp=True, scratched=False, bad_sha=False,
                     physical_clock="21:33"):
    """Patch PDF source fixture with embedded DejaVu for faithful Unicode."""
    root = _archive(path, tmp=tmp, scratched=scratched, bad_sha=bad_sha,
                    physical_clock=physical_clock)
    pdf_file = next(root.rglob("full_program.pdf"))
    pdf = fitz.open()
    page = pdf.new_page()
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not Path(font).exists():
        pytest.skip("DejaVu font unavailable")
    page.insert_font(fontname="Dvs", fontfile=font)
    page.insert_text((50, 50), "10\nSTART KL. " + physical_clock, fontname="Dvs", fontsize=10)
    y = 90
    for i, name in enumerate(NAMES, 1):
        page.insert_text((50, y), f"{i} {name.upper()}, Test", fontname="Dvs", fontsize=10)
        y += 20
    data = pdf.tobytes()
    pdf.close()
    pdf_file.write_bytes(data)
    manifest_file = next(root.rglob("manifest.json"))
    manifest = json.loads(manifest_file.read_text())
    manifest["requests"][1]["sha256"] = sha(data)
    manifest_file.write_text(json.dumps(manifest))
    return root


def _connection(db: Path):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def test_original_halmstad_shape_and_eight_horses_with_tmp_block(tmp_path):
    root = _archive_unicode(tmp_path / "collector")
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        result = verify_import(conn, OriginalArchive(root), RID, asof=NOW, authenticated=True)
        assert len(result["runners"]) == 8
        assert [h["horse_name"] for h in result["runners"]] == NAMES
        assert result["source_imported_to_sqlite"] is True
        assert result["model_input_approved"] is False
        assert "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED" in result["blockers"]
        assert result["model_input_sources"]["collector_program_pdf_sha256"]
        assert result["model_input_sources"]["collector_starts_sha256"]
        rows = conn.execute(
            "SELECT payload_json FROM provider_payloads "
            "WHERE provider='collector' AND category='ORIGINAL_PROGRAM_ROSTER_V1'"
        ).fetchall()
        assert len(rows) == 1
        assert json.loads(rows[0][0])["original_field"][0]["horse_name"] == NAMES[0]


def test_positive_verified_input_is_existing_sqlite_roster_not_pdf_history(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        before = [r[0] for r in conn.execute(
            "SELECT history_total_starts FROM runner_fundamental_snapshots ORDER BY selection_id")]
        output = verify_import(conn, OriginalArchive(root), RID, asof=NOW, authenticated=True)
        after = [r[0] for r in conn.execute(
            "SELECT history_total_starts FROM runner_fundamental_snapshots ORDER BY selection_id")]
        assert output["model_input_approved"] is True, output["blockers"]
        assert output["status"] == "MODEL_INPUT_VERIFIED_RESEARCH_ONLY"
        assert before == after
        assert output["bet_authority"] is False and output["pit_certified"] is False


@pytest.mark.parametrize(("alter", "reason"), [
    ("bad_sha", "COLLECTOR_ORIGINAL_HASH_MISMATCH"),
    ("scratch", "COLLECTOR_SQLITE_FIELD_MISMATCH"),
    ("clock", "COLLECTOR_PDF_START_CLOCK_CONFLICT"),
    ("future_history", "COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE"),
])
def test_conflicting_source_or_inputs_are_blocked(tmp_path, alter, reason):
    root = _archive_unicode(tmp_path / "collector", tmp=False,
                            bad_sha=alter == "bad_sha",
                            scratched=alter == "scratch",
                            physical_clock="21:34" if alter == "clock" else "21:33")
    db = tmp_path / "hbi.sqlite"
    _db(db, future_history=alter == "future_history")
    with _connection(db) as conn:
        result = verify_import(conn, OriginalArchive(root), RID, asof=NOW, authenticated=True)
        assert reason in result["blockers"], result
        assert result["model_input_approved"] is False


def test_missing_archive_fails_closed_without_model_approval(tmp_path):
    db = tmp_path / "hbi.sqlite"
    _db(db)
    report = tmp_path / "source.json"
    report.write_text(json.dumps({"races_in_fixed_cohort": [RID]}))
    out = tmp_path / "handoff.json"
    result = run_import(
        db, tmp_path / "missing", tmp_path / "missing_provenance.json",
        report, out, asof=NOW
    )
    assert result["records"][0]["status"] == "BLOCKED"
    assert "COLLECTOR_AUTHENTICATED_ARCHIVE_UNAVAILABLE" in result["records"][0]["blockers"]
    assert result["records"][0]["model_input_approved"] is False


def test_conflicting_atg_id_or_name_blocks_without_replacing_historic_features(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        source = json.loads(conn.execute(
            "SELECT payload_json FROM provider_payloads WHERE provider='atg'"
        ).fetchone()[0])
        source["runners"][0]["horse_name"] = "NOT THE SAME HORSE"
        conn.execute(
            "UPDATE provider_payloads SET payload_json=? WHERE provider='atg'",
            (json.dumps(source),)
        )
        original_history = conn.execute(
            "SELECT history_total_starts FROM runner_fundamental_snapshots "
            "WHERE selection_id='1'"
        ).fetchone()[0]
        result = verify_import(conn, OriginalArchive(root), RID, asof=NOW, authenticated=True)
        assert not result["model_input_approved"]
        assert "COLLECTOR_ATG_ATG_HORSE_NAME_MISMATCH" in result["blockers"]
        assert conn.execute(
            "SELECT history_total_starts FROM runner_fundamental_snapshots "
            "WHERE selection_id='1'"
        ).fetchone()[0] == original_history


def test_no_independently_authenticated_collector_origin_is_never_approved(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        result = verify_import(conn, OriginalArchive(root), RID, asof=NOW, authenticated=False)
        assert "COLLECTOR_ORIGIN_OR_DAY_NOT_VERIFIED" in result["blockers"]
        assert result["source_imported_to_sqlite"] is False


def test_optional_real_halmstad_original_archive(tmp_path):
    """Run with COLLECTOR_HISTORICAL_ARCHIVE=/path/to/original GitHub ZIP.

    Never synthesizes original raw bytes; CI may skip when artifact unavailable.
    """
    actual = os.environ.get("COLLECTOR_HISTORICAL_ARCHIVE")
    if not actual or not Path(actual).is_file():
        pytest.skip("Original historical GitHub Collector artifact not mounted")
    archive = OriginalArchive(Path(actual))
    key = KEY
    starts, start_raw = archive.request(key, "starts", RID, NOW)
    pdf, pdf_raw = archive.request(key, "pdf", RID, NOW)
    from hbi.collector_handoff import pdf_field
    from hbi.core_pit_roster_verification import parse_rikstoto_roster
    roster, err = parse_rikstoto_roster(start_raw.decode(), 10, key)
    assert err is None
    assert len(roster["all"]) == 8
    assert [roster["all"][str(i)]["name"] for i in range(1, 9)] == NAMES
    assert sha(start_raw) == "a4d1432357bf7006a9cc1983afc6b46f09bb3f483c6a286971eb7a8fb3cf260b"
    assert sha(pdf_raw) == "6ef632537a00d527381641702d1d8a1f58f428ed0e0a7847f10b3c3bb3fc3bd6"
    assert pdf_field(pdf_raw, 10, roster["all"], "2026-11-02") == START.isoformat()
    assert all(str(x["reg"]).startswith("TMP-") for x in roster["all"].values())
    assert starts["at_utc"] < pdf["at_utc"]


def _pit_receipt_for_physical_tenth():
    return {
        "schema": "PIT_T4_SOURCE_RECEIPT_V1",
        "race_id": RID, "raceday_key": KEY, "race_number": 10,
        "canonical_start_utc": START.isoformat(),
        "t_minus_4_utc": (START - timedelta(minutes=4)).isoformat(),
        "runners": [
            {"start_number": row["startNumber"], "horse_name": row["horseName"],
             "scratched": row["isScratched"],
             "registration_number": row["horseRegistrationNumber"]}
            for row in _rows(tmp=False)
        ],
    }


def test_pit_original_verifier_replays_physical_race_ten_without_live_promotion(tmp_path):
    """Test the removed race_no==1 restriction on genuine-shaped original bytes."""
    from hbi.core_pit_roster_verification import VerifiedCollectorEvidence
    from hbi.core_t4_receipt import verify_collector_original

    root = _archive_unicode(tmp_path / "collector", tmp=False)
    provenance = root / "provenance.json"
    provenance.write_text(json.dumps({
        "source_repository": "Maremoo2/rikstoto-program-collector",
        "event": "schedule", "conclusion": "success",
        "workflow_name": "Daily Rikstoto full programs – 07 Oslo",
        "created_at_utc": (EARLY - timedelta(hours=1)).isoformat(),
        "github_run_id": 12345,
        "obtained_via_authenticated_gh_cli": True,
    }))
    evidence = verify_collector_original(
        root, provenance, _pit_receipt_for_physical_tenth()
    )
    assert isinstance(evidence, VerifiedCollectorEvidence)
    assert evidence.race_id == RID
    assert evidence.full_field_pdf_startlist_reconciled is True
    assert evidence.original_bytes_sha256_verified is True

    # An original PDF with a different physical off-time must never certify.
    other = _archive_unicode(tmp_path / "different-clock", tmp=False,
                             physical_clock="21:34")
    different_provenance = other / "provenance.json"
    different_provenance.write_bytes(provenance.read_bytes())
    assert verify_collector_original(
        other, different_provenance, _pit_receipt_for_physical_tenth()
    ) is None
