"""Source-derived exact-code settlement regressions. Never touch real HBI state.

S1_NR_2026-11-03 race 7 official complete original:
CORE-003 run 41911371831 / DEV009 artifact 13364215238.
complete.raw.json SHA256 5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091
raceday.raw.json SHA256 1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d
The *selected row code values* below were independently extracted from those
original bytes; this test file does not claim to embed the complete raw JSON.
"""
from __future__ import annotations

import copy
import json

import pytest
from test_shadow_ledger import _store

from hbi import nightly
from hbi.providers.rikstoto import FetchResult, RikstotoClient


# Real result row values from the original, not synthetic outcome rewrites.
ESKILSTUNA_COMPLETE = {
    "isComplete": True,
    "results": [
        {"startNumber": 6, "place": 1, "kmTime": "14,6", "odds": 53},
        {"startNumber": 4, "place": 2, "kmTime": "15,3", "odds": 73},
        {"startNumber": 7, "place": 3, "kmTime": "15,0", "odds": 64},
        {"startNumber": 5, "place": 4, "kmTime": "15,6", "odds": 437},
        {"startNumber": 8, "place": 5, "kmTime": "15,7", "odds": 140},
        {"startNumber": 3, "place": 0, "kmTime": "19,1", "odds": 24},
        {"startNumber": 2, "place": 0, "kmTime": "Dsk", "odds": 60},
        {"startNumber": 1, "place": 0, "kmTime": "Dsk", "odds": 431},
    ],
}
ESKILSTUNA_RACEDAY_WIN = {
    "finalOdds": {
        "winOdds": {"1": {"6": {"payoutStatus": "Dividends", "odds": 5.33}}},
    },
}


def _ticket(store, selection="3"):
    """Only an isolated test database, never user-facing or historical state."""
    store.create_shadow_ticket({
        "ticket_id": "MVP021_TEST_ONLY",
        "dedupe_key": "MVP021_TEST_ONLY",
        "created_at_utc": "2026-09-27T17:56:00Z",
        "decision_time_utc": "2026-09-27T17:56:00Z",
        "race_id": "r1",
        "provider": "rikstoto",
        "provider_raceday_key": "BJ_NR_2026-09-27",
        "product": "V",
        "decision": "BET",
        "status": "SHADOW_BET",
        "selections_json": json.dumps([selection]),
        "stake_nok": 25,
        "number_of_rows": 1,
        "available_price": 2.64,
        "model_version": "TEST_ONLY_CONTRACT_PROBE",
    })


class SourceDerivedClient(RikstotoClient):
    def __init__(self, *, full=None, day=None):
        self.full = copy.deepcopy(
            ESKILSTUNA_COMPLETE if full is None else full
        )
        self.day = copy.deepcopy(
            ESKILSTUNA_RACEDAY_WIN if day is None else day
        )

    def complete_results(self, *_args):
        return FetchResult(
            url="https://www.rikstoto.no/api/results/raceDays/"
                "S1_NR_2026-11-03/7/completeresults",
            success=True, status_code=200, latency_ms=0.1,
            error=None, payload={"result": self.full},
        )

    def raceday_results(self, *_args):
        return FetchResult(
            url="https://www.rikstoto.no/api/results/racedays/"
                "S1_NR_2026-11-03/raceresults",
            success=True, status_code=200, latency_ms=0.1,
            error=None, payload={"result": self.day},
        )


def test_source_derived_zero_place_numeric_is_not_admitted_as_loss(tmp_path):
    """Original Eskilstuna #3: 0 / 19,1 / 24 is NOT an approved settlement."""
    full = copy.deepcopy(ESKILSTUNA_COMPLETE)
    assert nightly._finish_map(full)["3"] == 0
    assert nightly._confirmed_disqualification(full, "3") is False
    assert nightly._confirmed_disqualification(full, "2") is True  # Dsk, odds 60.
    assert nightly._confirmed_disqualification(full, "1") is True  # Dsk, odds 431.
    assert nightly._confirmed_win_dividends(ESKILSTUNA_RACEDAY_WIN, 1, {"6"})
    store = _store(tmp_path)
    _ticket(store, selection="3")
    for _ in range(2):
        summary = nightly.settle_open_shadow_tickets(
            store, client=SourceDerivedClient()
        )
        assert summary.attempted == 1
        assert summary.settled == 0 and summary.pending == 1
        row = store.fetch_table("shadow_tickets")[0]
        assert row["status"] == "SHADOW_BET"
        for key in ("settlement_source_uri", "gross_return_nok",
                    "net_pnl_nok", "closing_price", "clv"):
            assert row[key] is None


def test_source_derived_dsk_is_executable_under_existing_frozen_contract(tmp_path):
    """Original selection #2 is Dsk with positive odds, NOT a scratch."""
    store = _store(tmp_path)
    _ticket(store, selection="2")
    result = nightly.settle_open_shadow_tickets(
        store, client=SourceDerivedClient()
    )
    assert result.settled == 1
    row = store.fetch_table("shadow_tickets")[0]
    assert row["gross_return_nok"] == 0
    assert row["net_pnl_nok"] == -25
    assert row["closing_price"] is None and row["clv"] is None
    assert nightly.settle_open_shadow_tickets(
        store, client=SourceDerivedClient()
    ).attempted == 0


@pytest.mark.parametrize("payout_status,price", [
    ("Pending", 5.33), ("Dividends", 0),
    ("Dividends", float("nan")), ("Dividends", -2),
])
def test_authoritative_winner_dividend_negative_cases_remain_pending(
    tmp_path, payout_status, price,
):
    day = copy.deepcopy(ESKILSTUNA_RACEDAY_WIN)
    day["finalOdds"]["winOdds"]["1"]["6"] = {
        "payoutStatus": payout_status, "odds": price
    }
    store = _store(tmp_path)
    _ticket(store, selection="2")
    result = nightly.settle_open_shadow_tickets(
        store, client=SourceDerivedClient(day=day)
    )
    assert result.settled == 0
    assert store.fetch_table("shadow_tickets")[0]["status"] == "SHADOW_BET"


def test_conflicting_complete_winner_and_dividend_is_not_assumed_loss(tmp_path):
    """TEST_ONLY contradiction, not the real Eskilstuna original."""
    full = copy.deepcopy(ESKILSTUNA_COMPLETE)
    full["results"][0]["place"] = 0
    full["results"][1]["place"] = 1  # #4 but only #6 has dividends.
    store = _store(tmp_path)
    _ticket(store, selection="2")
    result = nightly.settle_open_shadow_tickets(
        store, client=SourceDerivedClient(full=full)
    )
    assert result.settled == 0
    assert store.fetch_table("shadow_tickets")[0]["status"] == "SHADOW_BET"


def test_missing_authoritative_complete_source_cannot_settle(tmp_path):
    """Skive #82/Bjerke race8 have no archived official source in exact V1 DB."""
    store = _store(tmp_path)
    _ticket(store, selection="2")
    client = SourceDerivedClient(full={"isComplete": False, "results": []})
    assert nightly.settle_open_shadow_tickets(store, client=client).settled == 0
    assert store.fetch_table("shadow_tickets")[0]["status"] == "SHADOW_BET"
