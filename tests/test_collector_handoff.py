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
            start_time_utc TEXT, race_date TEXT, country TEXT, discipline TEXT);
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
            history_total_starts INTEGER, history_total_wins INTEGER,
            identity_match_method TEXT, identity_match_confidence REAL);
    """)
    db.execute("INSERT INTO races VALUES (?,?,?,?,?,?)", (
        RID, 10, START.isoformat(), "2026-11-02", "SE", "trot"
    ))
    db.execute("INSERT INTO provider_race_refs VALUES (?,?,?,?)", (
        RID, "rikstoto", KEY, 10
    ))
    raw_rows = _rows(scratched=scratched, tmp=False)
    for i, name in enumerate(NAMES, 1):
        db.execute("INSERT INTO runners VALUES (?,?,?,?,?)", (
            RID, str(i), name, i, int(scratched and i == 8)
        ))
        moment = NOW + timedelta(minutes=2) if future_history else NOW - timedelta(minutes=1)
        db.execute("INSERT INTO runner_fundamental_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            str(i), RID, str(i), moment.isoformat(), moment.isoformat(), 1,
            "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-02_18_10",
            int(scratched and i == 8), 9 + i, 1,
            "UNIQUE_NAME_AND_PROGRAM_NUMBER", 1.0
        ))
    for name, provider, key, body in [
        ("starts", "rikstoto", KEY, {"success": True, "result": {"10": raw_rows}}),
        ("atg", "atg", RID, {
            "passed": True, "probe_only": False, "active_runners": 7 if scratched else 8,
            "provider": "atg", "country": "SE", "discipline": "trot",
            "provider_race_id": "2026-11-02_18_10",
            "source_uri": "https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-11-02_18_10",
            "observed_at_utc": (NOW - timedelta(minutes=1)).isoformat(),
            "collection_started_at_utc": (NOW - timedelta(minutes=2)).isoformat(),
            "race_start_utc": START.isoformat(), "timestamp_basis": "FETCH_COMPLETED",
            "matched_complete_runners": 7 if scratched else 8,
            "active_selections": [str(i) for i in range(1, 8 if scratched else 9)],
            "runners": [
                {"selection_id": str(i), "horse_name": NAMES[i-1],
                 "provider_horse_id": str(10000+i), "schema_ok": True,
                 # Echoed from Rikstoto - never independent ATG identity.
                 "rikstoto_registration": str(10000+i),
                 "match_method": "UNIQUE_NAME_AND_PROGRAM_NUMBER", "reason": None}
                for i in range(1, 8 if scratched else 9)
            ],
        }),
    ]:
        db.execute("INSERT INTO provider_payloads VALUES (?,?,?,?,?,?,?,?,?)", (
            name, provider, "RACEDAY_STARTS" if name == "starts" else "FULL_FIELD_ONLY_V1",
            key, 10, None, (NOW - timedelta(minutes=1)).isoformat(),
            "https://www.rikstoto.no/api/racedays/" + KEY + "/starts"
            if name == "starts" else body["source_uri"], json.dumps(body)
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


def test_copied_registration_cannot_approve_atg_identity_and_pdf_never_replaces_atg(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        before = [r[0] for r in conn.execute(
            "SELECT history_total_starts FROM runner_fundamental_snapshots ORDER BY selection_id")]
        output = verify_import(conn, OriginalArchive(root), RID, asof=NOW, authenticated=True)
        after = [r[0] for r in conn.execute(
            "SELECT history_total_starts FROM runner_fundamental_snapshots ORDER BY selection_id")]
        assert output["source_imported_to_sqlite"] is True, output["blockers"]
        assert output["model_input_approved"] is False
        assert output["research_model_eligible"] is True
        assert output["research_identity_match"] == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
        assert output["independent_identity_attested"] is False
        assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in output["blockers"]
        assert before == after
        assert output["identity_evidence"][0]["atg"]["derived_match_method"] == (
            "UNIQUE_NAME_AND_PROGRAM_NUMBER"
        )
        assert output["identity_evidence"][0]["atg"]["canonical_registration_echo_untrusted"] == "10001"
        assert all(not x["cross_provider_attested"] for x in output["identity_evidence"])
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


def test_incorrect_atg_registration_is_not_a_safe_cross_provider_join(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        row = conn.execute(
            "SELECT payload_json FROM provider_payloads WHERE provider='atg'"
        ).fetchone()
        content = json.loads(row[0])
        # A supposedly exact registration match pointing at another horse
        # must be rejected even though all names/start numbers still match.
        content["runners"][0]["rikstoto_registration"] = "DIFFERENT-HORSE-ID"
        conn.execute(
            "UPDATE provider_payloads SET payload_json=? WHERE provider='atg'",
            (json.dumps(content),),
        )
        result = verify_import(
            conn, OriginalArchive(root), RID, asof=NOW, authenticated=True
        )
        assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
        assert not result["model_input_approved"]


def test_pool_card_pdf_header_resolves_physical_race_number(tmp_path):
    from hbi.collector_handoff import pdf_field

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((50, 50), "V64-6\nLop 9\nSTART KL. 21:15")
    page.insert_text((50, 90), "1 APRIL, Test")
    page.insert_text((50, 110), "2 BETA, Test")
    body = pdf.tobytes()
    pdf.close()
    runners = {"1": {"name": "April"}, "2": {"name": "Beta"}}
    assert pdf_field(body, 9, runners, "2026-11-02") == (
        datetime(2026, 11, 2, 20, 15, tzinfo=UTC).isoformat()
    )
    with pytest.raises(ValueError, match="PHYSICAL_RACE_AMBIGUOUS"):
        pdf_field(body, 10, runners, "2026-11-02")


def test_two_physical_races_share_original_sha_but_have_separate_idempotent_sqlite_rows():
    from hbi.collector_handoff import _persist_original_roster

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE provider_payloads(
          payload_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL, category TEXT NOT NULL,
          provider_raceday_key TEXT NOT NULL, race_number INTEGER,
          product TEXT, observed_at_utc TEXT NOT NULL,
          source_uri TEXT NOT NULL, payload_json TEXT NOT NULL,
          UNIQUE(provider,category,provider_raceday_key,race_number,product,observed_at_utc)
        );
    """)
    key = "OR_NR_2026-11-02"
    shared = "df29a5a3837fcbefe736620cdeec095bd2d2473c58179808bb7bd2b880ffd1c9"
    source = {
        "collector_starts_sha256": shared,
        "collector_program_pdf_sha256": "a" * 64,
        "collector_manifest_sha256": "b" * 64,
        "collector_starts_observed_at_utc": EARLY.isoformat(),
        "collector_pdf_observed_at_utc": EARLY.isoformat(),
        "collector_starts_uri": "https://www.rikstoto.no/api/racedays/" + key + "/starts",
        "collector_pdf_uri": "https://www.rikstoto.no/api/programdownload/ProgramPdf/Utvidet/" + key,
        "atg_fundamental_observed_at_utc": NOW.isoformat(),
    }
    ids = []
    for race_no in (1, 2):
        allowed, key_id = _persist_original_roster(
            conn, race_id=f"RIKSTOTO:{key}:{race_no}", raceday_key=key,
            race_number=race_no, observed_at=EARLY.isoformat(),
            source_uri=source["collector_starts_uri"],
            original_field=[{"start_number": race_no, "horse_name": f"Starter {race_no}"}],
            source_checksums=source,
        )
        assert allowed
        ids.append(key_id)
    assert len(set(ids)) == 2
    rows = conn.execute(
        "SELECT payload_id,race_number,payload_json FROM provider_payloads "
        "WHERE provider='collector' ORDER BY race_number"
    ).fetchall()
    assert len(rows) == 2
    assert [r["race_number"] for r in rows] == [1, 2]
    assert all(json.loads(r["payload_json"])["source_checksums"]["collector_starts_sha256"] == shared for r in rows)

    # Reimport after ATG data changes must not create a new original or a conflict.
    changing_diagnostic = {**source, "atg_fundamental_observed_at_utc": (NOW + timedelta(minutes=1)).isoformat()}
    allowed, same_id = _persist_original_roster(
        conn, race_id=f"RIKSTOTO:{key}:1", raceday_key=key, race_number=1,
        observed_at=EARLY.isoformat(), source_uri=source["collector_starts_uri"],
        original_field=[{"start_number": 1, "horse_name": "Starter 1"}],
        source_checksums=changing_diagnostic,
    )
    assert allowed and same_id == ids[0]
    assert conn.execute("SELECT COUNT(*) FROM provider_payloads").fetchone()[0] == 2

    # A different original is NOT silently OR-IGNORED or written over the old.
    with pytest.raises(ValueError, match="COLLECTOR_IMPORT_REVISION_CONFLICT"):
        _persist_original_roster(
            conn, race_id=f"RIKSTOTO:{key}:1", raceday_key=key, race_number=1,
            observed_at=EARLY.isoformat(), source_uri=source["collector_starts_uri"],
            original_field=[{"start_number": 1, "horse_name": "Altered"}],
            source_checksums=source,
        )
    assert conn.execute("SELECT COUNT(*) FROM provider_payloads").fetchone()[0] == 2


def test_claimed_exact_method_with_registration_echo_cannot_authorize_models(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        payload = json.loads(conn.execute(
            "SELECT payload_json FROM provider_payloads WHERE provider='atg'"
        ).fetchone()[0])
        for row in payload["runners"]:
            row["match_method"] = "EXACT_REGISTRATION"
            row["rikstoto_registration"] = str(10000 + int(row["selection_id"]))
        conn.execute("UPDATE provider_payloads SET payload_json=? WHERE provider='atg'",
                     (json.dumps(payload),))
        result = verify_import(
            conn, OriginalArchive(root), RID, asof=NOW, authenticated=True,
        )
        assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
        assert result["model_input_approved"] is False



@pytest.mark.parametrize(("tamper", "expected"), [
    ("wrong_atg_race", "RESEARCH_ATG_RACE_OR_CLOCK_NOT_VERIFIED"),
    ("wrong_atg_start", "RESEARCH_ATG_RACE_OR_CLOCK_NOT_VERIFIED"),
    ("ambiguous_atg_name", "COLLECTOR_ATG_ATG_HORSE_NAME_MISMATCH"),
    ("missing_history", "COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE"),
    ("atg_source_conflict", "RESEARCH_ATG_HISTORY_CLOCK_OR_SOURCE_CONFLICT"),
    ("wrong_race_number", "COLLECTOR_RACE_REFERENCE_CONFLICT"),
    ("retained_roster_revision", "COLLECTOR_LIVE_ROSTER_REVISION_CONFLICT"),
])
def test_research_only_gate_rejects_incomplete_or_conflicting_evidence(
    tmp_path, tamper, expected,
):
    root = _archive_unicode(tmp_path / "collector", tmp=False)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    with _connection(db) as conn:
        if tamper == "wrong_race_number":
            conn.execute(
                "UPDATE provider_race_refs SET race_number=9 WHERE race_id=?", (RID,)
            )
        elif tamper == "missing_history":
            conn.execute(
                "DELETE FROM runner_fundamental_snapshots "
                "WHERE race_id=? AND selection_id='8'", (RID,)
            )
        elif tamper == "retained_roster_revision":
            row = conn.execute(
                "SELECT payload_json FROM provider_payloads WHERE provider='rikstoto'"
            ).fetchone()
            changed = json.loads(row[0])
            changed["result"]["10"][0]["horseName"] = "A DIFFERENT HORSE"
            conn.execute("INSERT INTO provider_payloads VALUES (?,?,?,?,?,?,?,?,?)", (
                "altered-newer-roster", "rikstoto", "RACEDAY_STARTS",
                KEY, 10, None, (NOW - timedelta(seconds=3)).isoformat(),
                "https://www.rikstoto.no/api/racedays/" + KEY + "/starts",
                json.dumps(changed),
            ))
        else:
            source = json.loads(conn.execute(
                "SELECT payload_json FROM provider_payloads WHERE provider='atg'"
            ).fetchone()[0])
            if tamper == "wrong_atg_race":
                source["provider_race_id"] = "WRONG-RACE"
            elif tamper == "wrong_atg_start":
                source["race_start_utc"] = (START + timedelta(minutes=5)).isoformat()
            elif tamper == "ambiguous_atg_name":
                source["runners"][1]["horse_name"] = source["runners"][0]["horse_name"]
            elif tamper == "atg_source_conflict":
                source["source_uri"] = "https://www.atg.se/WRONG-SOURCE"
            conn.execute(
                "UPDATE provider_payloads SET payload_json=? WHERE provider='atg'",
                (json.dumps(source),),
            )
        result = verify_import(
            conn, OriginalArchive(root), RID, asof=NOW, authenticated=True,
        )
        assert result["research_model_eligible"] is False, result
        assert result["model_input_approved"] is False
        assert expected in result["blockers"], result


def test_research_only_tmp_may_score_but_never_be_exact_identity(tmp_path):
    root = _archive_unicode(tmp_path / "collector", tmp=True)
    db = tmp_path / "hbi.sqlite"
    _db(db)
    # Preserve the authentic provenance pattern: the original & independent
    # Rikstoto /starts retain the same TMP registrations.
    with _connection(db) as conn:
        raw = json.loads(conn.execute(
            "SELECT payload_json FROM provider_payloads WHERE provider='rikstoto'"
        ).fetchone()[0])
        raw["result"]["10"] = _rows(tmp=True)
        conn.execute(
            "UPDATE provider_payloads SET payload_json=? WHERE provider='rikstoto'",
            (json.dumps(raw),),
        )
        result = verify_import(
            conn, OriginalArchive(root), RID, asof=NOW, authenticated=True,
        )
        assert result["research_model_eligible"] is True, result
        assert result["research_identity_match"] == "UNIQUE_NAME_AND_PROGRAM_NUMBER"
        assert "COLLECTOR_TMP_IDENTITY_NOT_ADMITTED" in result["blockers"]
        assert "IDENTITY_CROSS_PROVIDER_NOT_ATTESTED" in result["blockers"]
        assert result["independent_identity_attested"] is False
        assert result["model_input_approved"] is False
        assert result["pit_certified"] is False
        assert result["bet_authority"] is False
