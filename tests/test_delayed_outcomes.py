from datetime import UTC, date, datetime

from test_observatory import ResultClient, _store

from hbi.observatory import collect_decision_outcomes, materialize_race_evaluations


class DelayedResultClient(ResultClient):
    complete = True
    calls = 0

    def complete_results(self, *args):
        self.calls += 1
        fetch = super().complete_results(*args)
        fetch.payload["result"]["isComplete"] = self.complete
        return fetch


def test_earlier_missing_outcome_and_evaluation_are_retried_once(tmp_path):
    store = _store(tmp_path)
    before = store.fetch_table("shadow_decision_runs")
    day = date(2026, 9, 29)
    now = datetime(2026, 9, 30, tzinfo=UTC)
    client = DelayedResultClient()
    result = collect_decision_outcomes(store, day, client=client, settled_at=now)
    assert result.persisted == 1 and client.calls == 1
    assert materialize_race_evaluations(store, day, created_at=now) == 1
    assert collect_decision_outcomes(store, day, client=client, settled_at=now).attempted == 0
    assert materialize_race_evaluations(store, day, created_at=now) == 0
    assert store.fetch_table("shadow_decision_runs") == before


def test_backlog_needs_complete_result_and_cannot_fetch_future_race(tmp_path):
    store = _store(tmp_path)
    client = DelayedResultClient()
    client.complete = False
    result = collect_decision_outcomes(store, date(2026, 9, 29), client=client,
                                       settled_at=datetime(2026, 9, 30, tzinfo=UTC))
    assert result.persisted == 0 and result.pending == 1
    with store.connect() as c:
        c.execute("UPDATE shadow_decision_runs SET race_start_time_utc=?",
                  ("2026-10-01T18:00:00+00:00",))
    result = collect_decision_outcomes(store, date(2026, 9, 29), client=client,
                                       settled_at=datetime(2026, 9, 30, tzinfo=UTC))
    assert result.attempted == 0 and client.calls == 1
