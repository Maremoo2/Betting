import json
from datetime import UTC, datetime

import pytest
from test_shadow_ledger import SettlementClient, _store

from hbi.nightly import settle_open_shadow_tickets


def ticket(store, selection="2"):
    store.create_shadow_ticket({
        "ticket_id": "loss", "dedupe_key": "loss", "created_at_utc": "2026-09-27T17:56:00Z",
        "decision_time_utc": "2026-09-27T17:56:00Z", "race_id": "r1",
        "provider": "rikstoto", "provider_raceday_key": "BJ_NR_2026-09-27",
        "product": "V", "decision": "BET", "status": "SHADOW_BET",
        "selections_json": json.dumps([selection]), "stake_nok": 25,
        "number_of_rows": 1, "available_price": 4.8, "model_version": "test",
    })


class ResultsClient(SettlementClient):
    complete = True
    finish = 2
    payout_status = "Dividends"
    payout_price = 2.5

    def complete_results(self, *args):
        result = super().complete_results(*args)
        result.payload["result"]["isComplete"] = self.complete
        result.payload["result"]["results"][1]["place"] = self.finish
        return result

    def raceday_results(self, *args):
        result = super().raceday_results(*args)
        result.payload["result"]["finalOdds"]["winOdds"]["1"]["1"].update(
            payoutStatus=self.payout_status, odds=self.payout_price)
        return result


def test_official_loss_settles_without_loser_dividend_and_is_idempotent(tmp_path):
    store = _store(tmp_path)
    ticket(store)
    summary = settle_open_shadow_tickets(store, client=ResultsClient(),
                                        settled_at=datetime(2026, 9, 28, tzinfo=UTC))
    assert summary.settled == 1
    row = store.fetch_table("shadow_tickets")[0]
    assert row["status"] == "SETTLED"
    assert row["gross_return_nok"] == 0
    assert row["net_pnl_nok"] == -25
    assert row["closing_price"] is None and row["clv"] is None
    assert json.loads(row["result_json"])["finish"] == 2
    assert settle_open_shadow_tickets(store, client=ResultsClient()).attempted == 0


@pytest.mark.parametrize("attribute,value", [
    ("complete", False), ("complete", None), ("finish", 0),
    ("payout_status", "Pending"), ("payout_status", None),
    ("payout_price", float("nan")), ("payout_price", 0),
])
def test_unconfirmed_result_or_ambiguous_scratch_remains_pending(tmp_path, attribute, value):
    store = _store(tmp_path)
    ticket(store)
    client = ResultsClient()
    setattr(client, attribute, value)
    summary = settle_open_shadow_tickets(store, client=client)
    assert summary.pending == 1 and summary.settled == 0
    assert store.fetch_table("shadow_tickets")[0]["status"] == "SHADOW_BET"


def test_absent_selection_is_not_assumed_to_have_lost(tmp_path):
    store = _store(tmp_path)
    ticket(store, "99")
    assert settle_open_shadow_tickets(store, client=ResultsClient()).settled == 0


class DisqualifiedClient(ResultsClient):
    finish = 0
    marker = "Dsk"
    participation_odds = 18

    def complete_results(self, *args):
        fetch = super().complete_results(*args)
        fetch.payload["result"]["results"][1].update(
            kmTime=self.marker, odds=self.participation_odds)
        return fetch


def test_verified_disqualification_settles_loss_without_invented_closing(tmp_path):
    store = _store(tmp_path)
    ticket(store)
    result = settle_open_shadow_tickets(store, client=DisqualifiedClient())
    assert result.settled == 1 and result.pending == 0
    row = store.fetch_table("shadow_tickets")[0]
    assert row["net_pnl_nok"] == -25 and row["gross_return_nok"] == 0
    assert row["closing_price"] is None and row["clv"] is None


@pytest.mark.parametrize("attribute,value", [
    ("marker", "Str"), ("marker", ""), ("marker", None),
    ("participation_odds", 0), ("participation_odds", float("nan")),
    ("complete", False), ("payout_status", "Pending"),
])
def test_ambiguous_or_unconfirmed_zero_finish_still_pending(tmp_path, attribute, value):
    store = _store(tmp_path)
    ticket(store)
    client = DisqualifiedClient()
    setattr(client, attribute, value)
    assert settle_open_shadow_tickets(store, client=client).pending == 1
