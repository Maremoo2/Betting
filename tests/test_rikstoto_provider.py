from datetime import UTC, datetime
from pathlib import Path

from hbi.providers.rikstoto import FetchResult, RikstotoClient
from hbi.rikstoto_collector import RikstotoCollector
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


class FakeRikstoto(RikstotoClient):
    def racedays(self):
        return FetchResult(
            url="https://www.rikstoto.no/api/racedays/",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": [
                    {
                        "raceDayName": "Bjerke",
                        "raceDayKey": "BJ_NR_2026-09-27",
                        "trackCode": "BJ",
                        "sportType": "T",
                        "countryIsoCode": "NO",
                        "pools": [
                            {
                                "product": "V75",
                                "raceNumbers": [1, 2, 3, 4, 5, 6, 7],
                            }
                        ],
                        "singleLegProducts": [
                            {"product": "V", "raceNumber": 1},
                            {"product": "P", "raceNumber": 1},
                        ],
                        "races": [
                            {
                                "raceNumber": 1,
                                "startTime": "2026-09-27T20:00:00",
                                "startMethod": "Auto",
                                "progressStatus": "Future",
                            }
                        ],
                    }
                ]
            },
        )


    def program(self, raceday_key, product):
        return FetchResult(
            url=f"https://example/program/{product}",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": {
                    "raceDay": raceday_key,
                    "product": product,
                    "races": [
                        {
                            "raceNumber": 1,
                            "distance": 2100,
                            "startMethod": "Auto",
                            "raceName": "Testløp",
                            "starts": [
                                {
                                    "startNumber": 1,
                                    "horseName": "Alpha",
                                    "driver": "Driver A",
                                    "trainer": "Trainer A",
                                    "extraDistance": 0,
                                    "totalEarnings": 500000,
                                    "age": 5,
                                    "sex": "H",
                                    "postPosition": 1,
                                    "recordVolt": "14,5",
                                    "recordAuto": "13,8",
                                    "horseAnnualStatistics": {
                                        "total": {
                                            "numberOfStarts": 20,
                                            "numberOfFirstPlaces": 8,
                                            "numberOfSecondPlaces": 3,
                                            "numberOfThirdPlaces": 2,
                                            "totalEarnings": 500000,
                                        },
                                        "currentYear": {
                                            "numberOfStarts": 8,
                                            "numberOfFirstPlaces": 3,
                                            "numberOfSecondPlaces": 1,
                                            "numberOfThirdPlaces": 1,
                                            "totalEarnings": 180000,
                                        },
                                    },
                                },
                                {
                                    "startNumber": 2,
                                    "horseName": "Beta",
                                    "driver": "Driver B",
                                    "trainer": "Trainer B",
                                    "extraDistance": 0,
                                    "totalEarnings": 250000,
                                    "age": 6,
                                    "sex": "V",
                                    "postPosition": 2,
                                    "recordVolt": "15,0",
                                    "recordAuto": "14,2",
                                    "horseAnnualStatistics": {
                                        "total": {
                                            "numberOfStarts": 30,
                                            "numberOfFirstPlaces": 3,
                                            "numberOfSecondPlaces": 4,
                                            "numberOfThirdPlaces": 5,
                                            "totalEarnings": 250000,
                                        },
                                        "currentYear": {
                                            "numberOfStarts": 10,
                                            "numberOfFirstPlaces": 1,
                                            "numberOfSecondPlaces": 2,
                                            "numberOfThirdPlaces": 1,
                                            "totalEarnings": 90000,
                                        },
                                    },
                                },
                            ],
                        }
                    ],
                }
            },
        )

    def scratched(self, raceday_key):
        return FetchResult(
            url="https://example/scratched",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={"result": {"1": []}},
        )

    def win_odds(self, raceday_key, race_number):
        return FetchResult(
            url="https://example/win",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": [
                    {"startNumber": 1, "odds": 3.0, "lastUpdated": "2026-09-27T19:55:00"},
                    {"startNumber": 2, "odds": 2.0, "lastUpdated": "2026-09-27T19:55:00"},
                ]
            },
        )

    def place_odds(self, raceday_key, race_number):
        return FetchResult(
            url="https://example/place",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": [
                    {
                        "startNumber": 1,
                        "minOdds": 1.4,
                        "maxOdds": 1.8,
                        "lastUpdated": "2026-09-27T19:55:00",
                    }
                ]
            },
        )

    def twin_odds(self, raceday_key, race_number):
        return FetchResult(
            url="https://example/twin",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={"result": [{"startNumber1": 1, "startNumber2": 2, "odds": 8.0}]},
        )

    def triple_odds(self, raceday_key, race_number):
        return FetchResult(
            url="https://example/triple",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": [
                    {"startNumber1": 1, "startNumber2": 2, "startNumber3": 3, "odds": 40.0}
                ]
            },
        )


def test_rikstoto_raceday_parser_and_market_collection(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    collector = RikstotoCollector(store, FakeRikstoto())

    races = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))
    assert len(races) == 1
    assert races[0].race_id == "RIKSTOTO:BJ_NR_2026-09-27:1"
    assert races[0].pools == ("V75",)

    inserted, failures = collector.collect_market(
        raceday_key=races[0].raceday_key,
        race_number=1,
        race_id=races[0].race_id,
        observed_at=datetime(2026, 9, 27, 17, 56, tzinfo=UTC),
    )
    assert failures == 0
    assert inserted == 5
    assert store.count("provider_market_snapshots") == 5
    assert store.count("market_snapshots") == 2


def test_naive_rikstoto_timestamps_are_interpreted_as_oslo():
    parsed = RikstotoClient.parse_timestamp("2026-09-27T20:00:00")
    assert parsed.tzinfo is not None
    assert parsed.hour == 18


def test_rikstoto_program_populates_market_free_fundamentals(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    collector = RikstotoCollector(store, FakeRikstoto())
    race = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))[0]
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    inserted, ok, source = collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=observed,
        products=["V", "V75"],
    )

    assert ok
    assert source == "https://example/program/V"
    assert inserted == 2
    assert store.count("runner_fundamental_snapshots") == 2
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)
    assert {row["selection_id"] for row in rows} == {"1", "2"}
    alpha = next(row for row in rows if row["selection_id"] == "1")
    assert alpha["history_total_starts"] == 20
    assert alpha["history_total_wins"] == 8
    assert store.count("runners") == 2
