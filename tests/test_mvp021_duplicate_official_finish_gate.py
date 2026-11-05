"""Fail closed on duplicate runner numbers in complete result before paper settlement.

A duplicate start number is not a second entrant or verified official placing.
Tests use only disposable SQLite and NEVER modify canonical betting history.
"""
from __future__ import annotations

import json

import pytest
from test_shadow_ledger import _store

from hbi import nightly
from hbi.providers.rikstoto import FetchResult, RikstotoClient


class OriginalContractClient(RikstotoClient):
    def __init__(self, complete):
        self.complete = complete

    def complete_results(self, *_args):
        return FetchResult(
            url="https://www.rikstoto.no/api/results/raceDays/T_TEST/1/completeresults",
            success=True, status_code=200, latency_ms=0.1,
            error=None, payload={"result": self.complete},
        )

    def raceday_results(self, *_args):
        return FetchResult(
            url="https://www.rikstoto.no/api/results/racedays/T_TEST/raceresults",
            success=True, status_code=200, latency_ms=0.1,
            error=None,
            payload={"result": {
                "finalOdds": {
                    "winOdds": {"1": {"6": {"payoutStatus": "Dividends", "odds": 5.33}}},
                },
            }},
        )


def _seed(store, number="3"):
    store.create_shadow_ticket({
        "ticket_id": "MVP021_DUPLICATE_RESULT_TEST_ONLY",
        "dedupe_key": "MVP021_DUPLICATE_RESULT_TEST_ONLY",
        "created_at_utc": "2026-09-27T17:56:00Z",
        "decision_time_utc": "2026-09-27T17:56:00Z",
        "race_id": "r1",
        "provider": "rikstoto",
        "provider_raceday_key": "T_TEST",
        "product": "V",
        "decision": "BET",
        "status": "SHADOW_BET",
        "selections_json": json.dumps([number]),
        "stake_nok": 25,
        "number_of_rows": 1,
        "available_price": 2.64,
        "model_version": "TEST_ONLY_FROZEN_CONTRACT",
    })


@pytest.mark.parametrize("rows", [
    [
        {"startNumber": 6, "place": 1, "kmTime": "14,6", "odds": 53},
        {"startNumber": 3, "place": 1, "kmTime": "15,0", "odds": 24},
        {"startNumber": 3, "place": 2, "kmTime": "15,1", "odds": 24},
    ],
    [
        {"startNumber": 6, "place": 1, "kmTime": "14,6", "odds": 53},
        {"startNumber": 3, "place": 0, "kmTime": "Dsk", "odds": 60},
        {"startNumber": 3, "place": None, "kmTime": "Str", "odds": None},
    ],
    [
        {"startNumber": 6, "place": 1, "kmTime": "14,6", "odds": 53},
        {"startNumber": 3, "place": 2, "kmTime": "15,0", "odds": 24},
        {"startNumber": 6, "place": 3, "kmTime": "15,1", "odds": 24},
    ],
])
def test_duplicate_official_start_number_blocks_whole_finish_map(rows):
    assert nightly._finish_map({"results": rows}) == {}


@pytest.mark.parametrize("selected", ["3", "6"])
def test_duplicate_official_result_never_settles_disposable_ticket(tmp_path, selected):
    store = _store(tmp_path)
    _seed(store, selected)
    full = {
        "isComplete": True,
        "results": [
            {"startNumber": 6, "place": 1, "kmTime": "14,6", "odds": 53},
            {"startNumber": 3, "place": 2, "kmTime": "15,0", "odds": 24},
            {"startNumber": 3, "place": 3, "kmTime": "15,1", "odds": 24},
        ],
    }
    for _ in range(2):
        summary = nightly.settle_open_shadow_tickets(
            store, client=OriginalContractClient(full)
        )
        assert summary.settled == 0 and summary.pending == 1
        row = store.fetch_table("shadow_tickets")[0]
        assert row["status"] == "SHADOW_BET"
        for key in (
            "settlement_source_uri", "gross_return_nok", "net_pnl_nok",
            "closing_price", "clv",
        ):
            assert row[key] is None


def test_unique_original_runner_numbers_still_represent_true_finishers():
    original = {
        "isComplete": True,
        "results": [
            {"startNumber": 6, "place": 1, "kmTime": "14,6", "odds": 53},
            {"startNumber": 3, "place": 0, "kmTime": "19,1", "odds": 24},
            {"startNumber": 2, "place": 0, "kmTime": "Dsk", "odds": 60},
        ],
    }
    assert nightly._finish_map(original) == {"6": 1, "3": 0, "2": 0}
    assert nightly._confirmed_disqualification(original, "3") is False
    assert nightly._confirmed_disqualification(original, "2") is True
    assert nightly._confirmed_win_dividends(
        {"finalOdds": {"winOdds": {"1": {
            "6": {"payoutStatus": "Dividends", "odds": 5.33},
        }}}}, 1, {"6"},
    )
