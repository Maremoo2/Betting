"""Synthetic scope contract; no live evidence or model approval."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from hbi import cloud_run002_import as importer

MID = "MO_NR_2026-11-22"
R1 = f"RIKSTOTO:{MID}:1"
R2 = f"RIKSTOTO:{MID}:2"


@pytest.fixture
def archive(monkeypatch):
    def part(n, start):
        return {"race": {"meeting_id": MID, "race_number": n,
                         "scheduled_time_local": start, "distance_m": 2140,
                         "start_method": "Voltestart", "source_url": "https://www.rikstoto.no/program"},
                "entrants": [{"program_number": 1, "name": f"TEST {n}", "scratched": False}]}
    parts = [part(1, "12:00"), part(2, "18:15")]
    roster = {str(n): [{"startNumber": 1, "horseName": f"TEST {n}",
                        "isScratched": False, "driverName": "TEST DRIVER"}] for n in (1, 2)}
    meeting = {"meeting_id": MID, "source_date": "2026-11-22",
               "listing_source": {"country": "NO", "sport_type": "T", "meeting_id": MID,
                                  "track": "Momarken"},
               "is_multi_track_product": False, "captured_utc": "2026-11-22T14:00:00+00:00",
               "pdf_race_numbers": [1, 2],
               "startlist_pdf_audit": {"status": "MATCHED_AS_OF_SNAPSHOT",
                                      "race_numbers_match": True, "horses_verified": 2}}

    class Archive:
        def __init__(self, path):
            self.prefix = "original/"
            self.names = set()
            self.manifest = {"requests": [], "meetings": [deepcopy(meeting)],
                             "status": "CAPTURED_UNVERIFIED"}

        def request(self, *args):
            return {}, json.dumps({"result": roster}).encode()

        def read(self, path):
            return json.dumps({"races": parts}).encode()

    monkeypatch.setattr(importer, "OriginalArchive", Archive)
    monkeypatch.setattr(importer, "audit_release", lambda *args: {
        "date_oslo": "2026-11-22", "run_id": "TEST_ONLY",
        "archive_sha256": "a" * 64, "manifest_sha256": "b" * 64})
    return parts, roster, meeting


def prepare(scope):
    return importer.prepare_source(Path("test.zip"), Path("test.sha256"), race_ids=scope)


def test_default_whole_day_still_rejects_a_poststart_original(archive):
    with pytest.raises(ValueError, match="SNAPSHOT_AFTER_RACE_START"):
        prepare(None)


def test_explicit_upcoming_race_keeps_old_race_visible_but_unqualified(archive):
    receipt, races = prepare([R2])
    assert [r.card.race["race_id"] for r in races] == [R2]
    assert receipt["excluded_races"] == [{
        "race_id": R1, "reason": "OUTSIDE_EXPLICIT_IMPORT_SCOPE",
        "start_time_utc": "2026-11-22T11:00:00+00:00",
        "source_observed_at_utc": "2026-11-22T14:00:00+00:00",
        "source_completed_before_start": False, "model_ready": False, "pit_certified": False}]
    assert races[0].payload["model_ready"] is False


def test_selecting_late_race_does_not_bypass_time_guard(archive):
    with pytest.raises(ValueError, match="SNAPSHOT_AFTER_RACE_START"):
        prepare([R1])


def test_unknown_requested_race_is_not_silently_dropped(archive):
    with pytest.raises(ValueError, match="REQUESTED_RACE_NOT_VERIFIED"):
        prepare([R2, f"RIKSTOTO:{MID}:99"])


@pytest.mark.parametrize("scope", [[], "all", [R2, R2], [None], [False]])
def test_invalid_or_duplicate_scope_fails_closed(archive, scope):
    with pytest.raises(ValueError, match="RACE_SCOPE_INVALID"):
        prepare(scope)


def test_nonselected_field_still_must_reconcile(archive):
    parts, _, _ = archive
    parts[0]["entrants"][0]["name"] = "WRONG HORSE"
    with pytest.raises(ValueError, match="IDENTITY_OR_SCRATCH_CONFLICT"):
        prepare([R2])


def test_selected_partial_field_fails_closed(archive):
    _, roster, _ = archive
    roster["2"].append({"startNumber": 2, "horseName": "MISSING FROM PDF", "isScratched": False})
    with pytest.raises(ValueError, match="FIELD_SIZE_CONFLICT"):
        prepare([R2])
