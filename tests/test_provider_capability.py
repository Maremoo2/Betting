import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_rikstoto_provider import SCHEMA, FakeAtg, FakeRikstoto

from hbi.fundamental import run_and_persist_fundamental
from hbi.provider_capability import full_field_gate, resolve_field
from hbi.rikstoto_collector import RikstotoCollector
from hbi.shadow import run_win_shadow_decision
from hbi.storage import SQLiteStore

NOW = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)
START = NOW + timedelta(minutes=4)


def inputs():
    return {
        "starts": FakeRikstoto().starts("x").payload["result"]["1"],
        "scratches": set(),
        "scratch_ok": True,
        "payload": FakeAtg().race_game("race").payload["races"][0],
        "country": "SE",
        "discipline": "trot",
        "race_number": 1,
        "expected_start": START,
        "observed_at": NOW,
        "provider_race_id": "race",
        "source_uri": "https://example",
    }


def test_complete_market_free_field_and_confidence():
    kwargs = inputs()
    matched, evidence = resolve_field(**kwargs)
    assert set(matched) == {"1", "2"}
    assert evidence["passed"]
    assert all(r["match_confidence"] == 1 and r["schema_ok"] for r in evidence["runners"])
    assert evidence["source_published_at_utc"] is None
    assert evidence["timestamp_basis"] == "FETCH_COMPLETED"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda k: k["payload"]["starts"].pop(),
        lambda k: k["payload"]["starts"].append(deepcopy(k["payload"]["starts"][0])),
        lambda k: k["starts"].append(deepcopy(k["starts"][0])),
        lambda k: k["starts"].append({"bad": "schema"}),
        lambda k: k["payload"]["starts"][0]["horse"].update(name="Different"),
        lambda k: k["payload"]["starts"][0].update(number=2),
        lambda k: k["payload"]["starts"][0].update(scratched=True),
        lambda k: k["payload"]["starts"][0].update(scratched="false"),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["life"].pop("earnings"),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["life"]["placement"].pop("3"),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["life"].update(starts=1),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["life"].update(starts=True),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["life"].update(starts=20.5),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["life"].update(
            earnings=float("nan")
        ),
        lambda k: k["payload"]["starts"][0]["horse"]["statistics"]["years"]["2026"].update(
            starts=999
        ),
        lambda k: k["payload"]["starts"][0]["horse"].pop("trainer"),
        lambda k: k["payload"].update(status="results"),
        lambda k: k["payload"].update(id="wrong-race"),
        lambda k: k["payload"].update(sport="gallop"),
        lambda k: k["payload"].update(track=[]),
        lambda k: k["payload"].update(startTime="2026-09-27T20:20:00"),
        lambda k: k.update(scratch_ok=False),
        lambda k: k.update(observed_at=START),
        lambda k: k.update(country="XX"),
    ],
)
def test_every_partial_or_unsafe_field_fails_closed(mutation):
    kwargs = inputs()
    mutation(kwargs)
    matched, evidence = resolve_field(**kwargs)
    assert not evidence["passed"]
    assert not matched  # No partial enrichment, even at 99% coverage.
    assert evidence["reasons"]


def test_zero_career_is_explicit_not_missing():
    kwargs = inputs()
    life = kwargs["payload"]["starts"][0]["horse"]["statistics"]["life"]
    life.update(starts=0, earnings=0, placement={"1": 0, "2": 0, "3": 0})
    assert resolve_field(**kwargs)[1]["passed"]
    life.pop("starts")
    assert not resolve_field(**kwargs)[1]["passed"]


def test_scratched_runner_excluded_only_on_agreed_full_field():
    kwargs = inputs()
    third = deepcopy(kwargs["starts"][0])
    third.update(startNumber=3, horseName="Gamma", isScratched=True)
    kwargs["starts"].append(third)
    assert resolve_field(**kwargs)[1]["passed"]
    third["isScratched"] = False
    assert not resolve_field(**kwargs)[1]["passed"]


def test_registration_namespace_never_overrides_name_number():
    kwargs = inputs()
    kwargs["starts"][0]["horseRegistrationNumber"] = "H2"
    matched, _ = resolve_field(**kwargs)
    assert matched["1"]["horse"]["name"] == "Alpha"
    kwargs["starts"][0]["horseName"] = "Beta"
    assert not resolve_field(**kwargs)[1]["passed"]


def test_calendar_requires_unique_country_discipline_time_status():
    client = FakeAtg()
    calendar = client.calendar_day(NOW.date())
    kw = {"track_name": "Färjestad", "race_number": 1, "expected_start": START}
    assert client.resolve_race(calendar, **kw)
    assert client.resolve_race(calendar, **kw, country="DK") is None
    assert client.resolve_race(calendar, **kw, discipline="gallop") is None
    assert (
        client.resolve_race(calendar, **{**kw, "expected_start": START + timedelta(hours=1)})
        is None
    )
    calendar.payload["tracks"].append(deepcopy(calendar.payload["tracks"][0]))
    assert client.resolve_race(calendar, **kw) is None


def setup_collector(tmp_path):
    store = SQLiteStore(tmp_path / "test.sqlite")
    store.initialize(SCHEMA)
    rik = FakeRikstoto(country="SE", track="Färjestad")
    collector = RikstotoCollector(store, rik, FakeAtg(), clock=lambda: NOW)
    race = collector.discover(NOW)[0]
    kw = {
        "raceday_key": race.raceday_key,
        "race_number": 1,
        "race_id": race.race_id,
        "observed_at": NOW - timedelta(seconds=5),
    }
    return store, collector, race, kw


def test_pit_cohort_failure_revokes_previous_success_and_shadow(tmp_path):
    store, collector, race, kw = setup_collector(tmp_path)
    collector.collect_fundamentals(**kw)
    rows = store.latest_runner_fundamentals(race.race_id, before=NOW)
    assert all(r["feature_as_of_utc"] == NOW.isoformat() for r in rows)
    assert not store.latest_runner_fundamentals(race.race_id, before=kw["observed_at"])
    assert full_field_gate(store, race.race_id, rows, NOW) is None
    run = run_and_persist_fundamental(store, race_id=race.race_id, created_at=NOW)
    assert run.shadow_eligible
    assert full_field_gate(store, race.race_id, rows[:-1], NOW)
    later = NOW + timedelta(seconds=1)
    collector.clock = lambda: later
    original = collector.client.starts

    def broken(key):
        fetch = original(key)
        fetch.payload["result"]["1"] = []
        return fetch

    collector.client.starts = broken
    collector.collect_fundamentals(**kw)
    assert full_field_gate(store, race.race_id, rows, later)
    decision = run_win_shadow_decision(
        store,
        race_id=race.race_id,
        provider_raceday_key=race.raceday_key,
        race_start_at=START,
        decision_time=later,
    )
    assert decision.status == "NOT_EXECUTABLE"
    assert "FULL_FIELD_ONLY" in decision.reason


def test_probe_cannot_enable_shadow_or_old_snapshots(tmp_path):
    store, collector, race, kw = setup_collector(tmp_path)
    collector.capability_probe = True
    collector.collect_fundamentals(**kw)
    assert collector.last_capability["passed"]
    run = run_and_persist_fundamental(store, race_id=race.race_id, created_at=NOW)
    assert not run.shadow_eligible
    assert full_field_gate(store, "RIKSTOTO:unknown:1", [], NOW)


def test_market_mutations_do_not_change_features(tmp_path):
    store, collector, race, kw = setup_collector(tmp_path)
    collector.collect_fundamentals(**kw)
    before = store.latest_runner_fundamentals(race.race_id, before=NOW)
    original = collector.atg_client.race_game

    def mutate(race_id):
        fetch = original(race_id)
        for start in fetch.payload["races"][0]["starts"]:
            start["pools"] = {"vinnare": {"odds": 999999, "betDistribution": 9900}}
            start["horse"]["statistics"]["lastFiveStarts"] = {"averageOdds": 9000}
        return fetch

    collector.atg_client.race_game = mutate
    collector.collect_fundamentals(**kw)
    after = store.latest_runner_fundamentals(race.race_id, before=NOW)
    assert before == after
    assert all("odds" not in json.dumps(row).lower() for row in after)


def test_missing_live_races_is_not_green(monkeypatch):
    import hbi.live_smoke as smoke

    class EmptyCollector:
        def __init__(self, store):
            pass

        def discover(self, now):
            return []

    monkeypatch.setattr(smoke, "RikstotoCollector", EmptyCollector)
    report = smoke.run_live_smoke()
    assert not report.verified_countries
    assert "MULTI_COUNTRY_EVIDENCE_MISSING" in report.errors


def test_stale_evidence_and_model_cohort_are_rejected(tmp_path):
    store, collector, race, kw = setup_collector(tmp_path)
    collector.collect_fundamentals(**kw)
    rows = store.latest_runner_fundamentals(race.race_id, before=NOW)
    assert full_field_gate(store, race.race_id, rows, NOW + timedelta(minutes=11))
    run_and_persist_fundamental(store, race_id=race.race_id, created_at=NOW)
    later = NOW + timedelta(seconds=1)
    collector.clock = lambda: later
    collector.collect_fundamentals(**kw)
    collector.collect_market(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=later,
        products={"V"},
    )
    decision = run_win_shadow_decision(
        store,
        race_id=race.race_id,
        provider_raceday_key=race.raceday_key,
        race_start_at=START,
        decision_time=later,
    )
    assert decision.reason == "FULL_FIELD_ONLY_MODEL_COHORT_MISMATCH"
