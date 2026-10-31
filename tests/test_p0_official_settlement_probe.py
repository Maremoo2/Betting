"""Fail-closed evidence-only tests for official Shadow result GET probe."""
from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "p0_official_settlement_probe.py"
SPEC = importlib.util.spec_from_file_location("p0_official_settlement_probe", PATH)
assert SPEC and SPEC.loader
probe_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_module)


def fetch(kind, payload=None, *, success=True, status=200, hash_value="a" * 64):
    suffix = ("raceresults" if kind == "raceday"
              else "6/completeresults")
    return SimpleNamespace(
        url=f"https://www.rikstoto.no/api/results/raceDays/S4_NR_2026-10-14/{suffix}",
        success=success, payload=payload, status_code=status,
        response_body_sha256=hash_value if success else None,
        response_completed_at=datetime(2026, 10, 30, 19, 0, tzinfo=UTC),
        http_date=None, http_etag=None, error=None if success else "HTTP Error: 403",
    )


class FakeClient:
    def __init__(self, *, day=None, complete=None):
        self.day = day or fetch("raceday", {
            "finalOdds": {"winOdds": {"6": {
                "5": {"payoutStatus": "Dividends", "odds": 5.3}
            }}}
        })
        self.complete = complete or fetch("complete", {
            "isComplete": True,
            "results": [{"startNumber": 5, "place": 1},
                        {"startNumber": 8, "place": 9}],
        })
        self.calls = []

    def raceday_results(self, key):
        self.calls.append(("raceday_results", key))
        return self.day

    def complete_results(self, key, race_number):
        self.calls.append(("complete_results", key, race_number))
        return self.complete

    @staticmethod
    def result_object(result):
        return result.payload


def check(client):
    return probe_module.probe(
        client=client, raceday_key="S4_NR_2026-10-14",
        race_number=6, selected="8", cached_winner="5",
    )


def test_valid_official_contract_is_still_not_permission_to_settle():
    client = FakeClient()
    result = check(client)
    assert len(client.calls) == 2
    assert result["both_official_http_payloads_observed"] is True
    assert result["structurally_settlement_ready"] is True
    assert result["winning_result"] == "5"
    assert result["bookkeeping_authority"] is False
    assert result["real_money_authority"] is False
    assert result["p0_status"] == "BLOCKED_PENDING_INDEPENDENT_ADJUDICATION"
    assert result["raceday_results"]["response_sha256"] == "a" * 64
    assert "results" not in result


def test_http_failure_blocks_without_settlement_attempt():
    client = FakeClient(complete=fetch("complete", success=False, status=403))
    result = check(client)
    assert result["both_official_http_payloads_observed"] is False
    assert "MISSING_ORIGINAL_OFFICIAL_SOURCE_PAYLOADS" in result["structural_reasons"]
    assert result["bookkeeping_authority"] is False
    assert result["complete_results"]["http_status"] == 403


def test_nonofficial_origin_cannot_be_attested():
    client = FakeClient()
    client.day.url = "https://not-rikstoto.example.org/something"
    result = check(client)
    assert result["both_official_http_payloads_observed"] is False
    assert "SOURCE_AUTHENTICITY_AND_FETCH_TIME_UNATTESTED" in result["structural_reasons"]


def test_incomplete_result_blocks_even_with_http_200():
    client = FakeClient()
    client.complete.payload["isComplete"] = False
    result = check(client)
    assert result["structurally_settlement_ready"] is False
    assert "OFFICIAL_RESULT_NOT_COMPLETE" in result["structural_reasons"]


def test_missing_selected_horse_blocks():
    client = FakeClient()
    client.complete.payload["results"].pop()
    result = check(client)
    assert "TICKET_SELECTION_ABSENT_FROM_OFFICIAL_FIELD" in result["structural_reasons"]


def test_missing_winner_dividend_blocks():
    client = FakeClient()
    client.day.payload["finalOdds"]["winOdds"]["6"]["5"]["payoutStatus"] = "None"
    result = check(client)
    assert "WINNING_DIVIDEND_NOT_CONFIRMED" in result["structural_reasons"]


@pytest.mark.parametrize("key,number,selection", [
    ("NOT-A-S4-KEY", 6, "8"), ("S4_NR_2026-10-14", 0, "8"),
    ("S4_NR_2026-10-14", 6, "other"),
])
def test_invalid_scope_rejected_before_network(key, number, selection):
    client = FakeClient()
    with pytest.raises(ValueError):
        probe_module.probe(client=client, raceday_key=key,
                           race_number=number, selected=selection)
    assert client.calls == []


def test_official_place_zero_participant_fields_preserved_without_accounting():
    client = FakeClient()
    client.complete.payload["results"][1].update({
        "kmTime": "1.19,6", "odds": 12.4, "scratched": False, "status": "finished"
    })
    result = check(client)
    selected = result["public_selected_participant_fields"]
    assert selected["selected_row_count"] == 1
    assert selected["place"] == 9
    assert selected["km_time"] == "1.19,6"
    assert selected["odds"] == 12.4
    assert selected["scratched"] is False
    assert selected["winner_selection"] == "5"
    assert selected["winner_dividend_status"] == "Dividends"
    assert result["bookkeeping_authority"] is False


def test_zero_place_not_relabeled_as_a_loss_or_valid_participation():
    client = FakeClient()
    client.complete.payload["results"][1].update({
        "place": 0, "kmTime": None, "odds": None, "scratched": True
    })
    result = check(client)
    selected = result["public_selected_participant_fields"]
    assert selected["place"] == 0
    assert selected["scratched"] is True
    assert result["structurally_settlement_ready"] is False
    assert result["bookkeeping_authority"] is False
    assert "ZERO_FINISH_NOT_PROVEN_DISQUALIFIED_PARTICIPANT" in result["structural_reasons"]


class FakeWithStarts(FakeClient):
    def __init__(self, *, is_scratched=False, scratch_entries=None):
        super().__init__()
        self.is_scratched = is_scratched
        self.scratch_entries = [] if scratch_entries is None else scratch_entries

    def starts(self, key):
        self.calls.append(("starts", key))
        response = fetch("complete", {"6": [
            {"startNumber": 5, "isScratched": False},
            {"startNumber": 8, "isScratched": self.is_scratched},
        ]})
        response.url = f"https://www.rikstoto.no/api/racedays/{key}/starts"
        return response

    def scratched(self, key):
        self.calls.append(("scratched", key))
        response = fetch("complete", {"6": self.scratch_entries})
        response.url = f"https://www.rikstoto.no/api/racedays/{key}/scratched"
        return response


def test_official_raceday_starts_and_scratches_are_not_automatic_start_proof():
    client = FakeWithStarts()
    report = probe_module.probe(
        client=client, raceday_key="S4_NR_2026-10-14",
        race_number=6, selected="8", cached_winner="5",
        corroborate_starts=True,
    )
    item = report["official_start_and_scratch_corroboration"]
    assert item["starts_get"]["http_status"] == 200
    assert item["scratches_get"]["http_status"] == 200
    assert item["selected_in_startlist_rows"] == 1
    assert item["selected_is_scratched_in_startlist"] is False
    assert item["selected_on_scratched_list"] is False
    assert item["start_participation_certified"] is False
    assert item["bookkeeping_authority"] is False
    assert report["bookkeeping_authority"] is False
    assert len(client.calls) == 4


def test_original_scratched_marker_does_not_get_cleared():
    client = FakeWithStarts(is_scratched=True, scratch_entries=[{"startNumber": 8}])
    report = probe_module.probe(
        client=client, raceday_key="S4_NR_2026-10-14",
        race_number=6, selected="8", corroborate_starts=True,
    )
    item = report["official_start_and_scratch_corroboration"]
    assert item["selected_is_scratched_in_startlist"] is True
    assert item["selected_on_scratched_list"] is True
    assert report["bookkeeping_authority"] is False


def test_unknown_scratch_shape_cannot_be_interpreted_as_not_scratched():
    client = FakeWithStarts(scratch_entries=[{"other": 8}])
    report = probe_module.probe(
        client=client, raceday_key="S4_NR_2026-10-14",
        race_number=6, selected="8", corroborate_starts=True,
    )
    item = report["official_start_and_scratch_corroboration"]
    assert item["scratched_list_shape_recognized"] is False
    assert item["selected_on_scratched_list"] is None
    assert item["start_participation_certified"] is False


def test_anonymous_place_zero_shapes_are_counted_without_status_interpretation():
    client = FakeWithStarts()
    client.complete.payload["results"].extend([
        {"startNumber": 7, "place": 0, "kmTime": "0,0"},
        {"startNumber": 9, "place": 0, "kmTime": "Dsk"},
        {"startNumber": 10, "place": 0, "kmTime": None},
    ])
    report = probe_module.probe(
        client=client, raceday_key="S4_NR_2026-10-14",
        race_number=6, selected="8", corroborate_starts=True,
    )
    shape = report["anonymous_result_code_distribution"]
    assert shape["parseable"] is True
    assert shape["rows"] == 5
    assert shape["place_zero"] == 3
    assert shape["zero_km_time_categories"]["ZERO_TIME"] == 1
    assert shape["zero_km_time_categories"]["Dsk"] == 1
    assert shape["zero_km_time_categories"]["MISSING_TIME"] == 1
    assert shape["payout_authority"] is False
    assert report["bookkeeping_authority"] is False


def test_unavailable_complete_results_never_fabricates_place_zero_statistics():
    client = FakeWithStarts()
    client.complete.success = False
    client.complete.payload = None
    result = probe_module.probe(
        client=client, raceday_key="S4_NR_2026-10-14",
        race_number=6, selected="8", corroborate_starts=True,
    )
    distribution = result["anonymous_result_code_distribution"]
    assert distribution["parseable"] is False
    assert distribution["rows"] == 0
    assert result["bookkeeping_authority"] is False
