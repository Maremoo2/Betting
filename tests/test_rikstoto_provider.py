from datetime import UTC, datetime
from pathlib import Path

from hbi.providers.atg import AtgClient, AtgFetchResult
from hbi.providers.pmu import PmuClient, PmuFetchResult
from hbi.providers.rikstoto import FetchResult, RikstotoClient
from hbi.rikstoto_collector import RikstotoCollector
from hbi.storage import SQLiteStore

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


class FakeRikstoto(RikstotoClient):
    def __init__(
        self,
        *,
        country: str = "NO",
        track: str = "Bjerke",
        raceday_key: str = "BJ_NR_2026-09-27",
    ):
        self.country = country
        self.track = track
        self.raceday_key = raceday_key

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
                        "raceDayName": self.track,
                        "raceDayKey": self.raceday_key,
                        "trackCode": "T1",
                        "sportType": "T",
                        "countryIsoCode": self.country,
                        "pools": [
                            {
                                "product": "V75",
                                "raceNumbers": [1],
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

    def starts(self, raceday_key):
        return FetchResult(
            url=f"https://example/racedays/{raceday_key}/starts",
            success=True,
            status_code=200,
            latency_ms=1.0,
            error=None,
            payload={
                "result": {
                    "1": [
                        {
                            "startNumber": 1,
                            "horseName": "Alpha",
                            "horseRegistrationNumber": "H1",
                            "driverName": "Driver A",
                            "driverLicenseNumber": "D1",
                            "extraDistance": 0,
                            "isScratched": False,
                            "raceNumber": 1,
                            "raceKey": f"{raceday_key}_1",
                        },
                        {
                            "startNumber": 2,
                            "horseName": "Beta",
                            "horseRegistrationNumber": "H2",
                            "driverName": "Driver B",
                            "driverLicenseNumber": "D2",
                            "extraDistance": 20,
                            "isScratched": False,
                            "raceNumber": 1,
                            "raceKey": f"{raceday_key}_1",
                        },
                    ]
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


class FakeAtg(AtgClient):
    def __init__(self, *, country: str = "SE", track: str = "Färjestad", incomplete: bool = False):
        self.country = country
        self.track = track
        self.incomplete = incomplete

    def calendar_day(self, race_date):
        return AtgFetchResult(
            url="https://example/atg/calendar",
            success=True,
            status_code=200,
            latency_ms=1.0,
            payload={
                "tracks": [
                    {
                        "countryCode": self.country,
                        "name": self.track,
                        "races": [
                            {
                                "id": "2026-09-27_22_1",
                                "number": 1,
                                "startTime": "2026-09-27T18:00:00+00:00",
                            }
                        ],
                    }
                ]
            },
        )

    def race_game(self, race_id):
        return AtgFetchResult(
            url=f"https://example/atg/games/vinnare_{race_id}",
            success=True,
            status_code=200,
            latency_ms=1.0,
            payload={
                "races": [
                    {
                        "starts": [
                            {
                                "number": 1,
                                "distance": 2140,
                                "pools": {"vinnare": {"odds": 225}},
                                "horse": {
                                    "id": "H1",
                                    "name": "Alpha",
                                    "age": 5,
                                    "sex": "horse",
                                    "trainer": {
                                        "firstName": "Anna",
                                        "lastName": "A",
                                    },
                                    "statistics": {
                                        "life": {
                                            "starts": 20,
                                            "earnings": 500000,
                                            "placement": {"1": 8, "2": 3, "3": 2},
                                        }
                                    },
                                },
                            },
                            {
                                "number": 2,
                                "distance": 2160,
                                "pools": {"vinnare": {"odds": 475}},
                                "horse": {
                                    "id": "H2",
                                    "name": "Beta",
                                    "age": 6,
                                    "sex": "gelding",
                                    "trainer": {
                                        "firstName": "Bengt",
                                        "lastName": "B",
                                    },
                                    "statistics": {
                                        "life": (
                                            {"starts": 30, "placement": {"1": 3}}
                                            if self.incomplete
                                            else {
                                                "starts": 30,
                                                "earnings": 250000,
                                                "placement": {"1": 3, "2": 4, "3": 5},
                                            }
                                        )
                                    },
                                },
                            },
                        ]
                    }
                ]
            },
        )



class FakePmu(PmuClient):
    def __init__(
        self,
        *,
        country: str = "FR",
        track: str = "Chantilly",
        available: bool = False,
        incomplete: bool = False,
    ):
        self.country = country
        self.track = track
        self.available = available
        self.incomplete = incomplete

    def programme(self, race_date):
        if not self.available:
            return PmuFetchResult(
                url="https://example/pmu/programme",
                payload=None,
                success=False,
                status_code=404,
                latency_ms=1.0,
                error="not available",
            )
        return PmuFetchResult(
            url="https://example/pmu/programme",
            payload={
                "programme": {
                    "reunions": [
                        {
                            "numOfficiel": 1,
                            "hippodrome": {"libelleCourt": self.track},
                            "pays": {"code": self.country},
                            "courses": [{"numOrdre": 1}],
                        }
                    ]
                }
            },
            success=True,
            status_code=200,
            latency_ms=1.0,
        )

    def participants(self, race_date, reunion_number, race_number):
        if not self.available:
            return PmuFetchResult(
                url="https://example/pmu/participants",
                payload=None,
                success=False,
                status_code=404,
                latency_ms=1.0,
                error="not available",
            )
        beta = {
            "nom": "Beta",
            "numPmu": 2,
            "idCheval": "PMU-H2",
            "age": 6,
            "sexe": "HONGRE",
            "entraineur": "Trainer B",
            "nombreCourses": 30,
            "nombreVictoires": 3,
            "nombrePlaces": 12,
            "nombrePlacesSecond": 4,
            "nombrePlacesTroisieme": 5,
            "gainsParticipant": {"gainsCarriere": 250000},
        }
        if self.incomplete:
            beta["gainsParticipant"] = {}
        return PmuFetchResult(
            url="https://example/pmu/participants",
            payload={
                "participants": [
                    {
                        "nom": "Alpha",
                        "numPmu": 1,
                        "idCheval": "PMU-H1",
                        "age": 5,
                        "sexe": "MALE",
                        "entraineur": "Trainer A",
                        "nombreCourses": 20,
                        "nombreVictoires": 8,
                        "nombrePlaces": 13,
                        "nombrePlacesSecond": 3,
                        "nombrePlacesTroisieme": 2,
                        "gainsParticipant": {"gainsCarriere": 500000},
                    },
                    beta,
                ]
            },
            success=True,
            status_code=200,
            latency_ms=1.0,
        )



def test_rikstoto_raceday_parser_and_market_collection(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    collector = RikstotoCollector(
        store,
        FakeRikstoto(),
        FakeAtg(),
        FakePmu(),
    )

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


def test_norwegian_starts_populate_field_without_fake_history(tmp_path):
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
    )

    assert ok
    assert source.endswith("/starts")
    assert inserted == 2
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)
    assert {row["selection_id"] for row in rows} == {"1", "2"}
    assert all(row["data_quality"] == "FIELD_ONLY_RIKSTOTO" for row in rows)
    assert all(row["history_total_starts"] is None for row in rows)
    assert store.count("runners") == 2


def test_swedish_starts_are_enriched_with_market_free_atg_history(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    rikstoto = FakeRikstoto(
        country="SE",
        track="Färjestad",
        raceday_key="S1_NR_2026-09-27",
    )
    collector = RikstotoCollector(store, rikstoto, FakeAtg(), FakePmu())
    race = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))[0]
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    inserted, ok, _ = collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=observed,
    )

    assert ok
    assert inserted == 2
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)
    alpha = next(row for row in rows if row["selection_id"] == "1")
    beta = next(row for row in rows if row["selection_id"] == "2")
    assert alpha["history_total_starts"] == 20
    assert alpha["history_total_wins"] == 8
    assert alpha["history_total_earnings"] == 500000
    assert alpha["data_quality"] == "FULL_FIELD_HISTORY_ATG"
    assert alpha["enrichment_provider"] == "atg"
    assert alpha["identity_match_confidence"] == 1.0
    assert alpha["full_field_history_complete"] == 1
    assert beta["history_total_starts"] == 30
    assert beta["history_total_wins"] == 3
    assert "odds" not in str(alpha["raw_json"]).lower()
    assert "pools" not in str(alpha["raw_json"]).lower()
    assert store.count("provider_fetch_audit") >= 4




def test_danish_race_uses_same_capability_based_atg_enrichment(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    rikstoto = FakeRikstoto(
        country="DK",
        track="Charlottenlund",
        raceday_key="CL_NR_2026-09-27",
    )
    collector = RikstotoCollector(
        store,
        rikstoto,
        FakeAtg(country="DK", track="Charlottenlund"),
        FakePmu(),
    )
    race = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))[0]
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    inserted, ok, _ = collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=observed,
    )

    assert ok
    assert inserted == 2
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)
    assert all(row["full_field_history_complete"] == 1 for row in rows)
    assert all(row["enrichment_provider"] == "atg" for row in rows)
    assert all(row["history_total_starts"] is not None for row in rows)


def test_partial_provider_history_is_hidden_from_entire_active_field(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    rikstoto = FakeRikstoto(
        country="DK",
        track="Charlottenlund",
        raceday_key="CL_NR_2026-09-27",
    )
    collector = RikstotoCollector(
        store,
        rikstoto,
        FakeAtg(country="DK", track="Charlottenlund", incomplete=True),
        FakePmu(),
    )
    race = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))[0]
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=observed,
    )
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)

    assert len(rows) == 2
    assert all(row["full_field_history_complete"] == 0 for row in rows)
    assert all(row["history_total_starts"] is None for row in rows)
    assert all(row["history_total_wins"] is None for row in rows)
    assert all(
        row["data_quality"] == "FIELD_ONLY_INCOMPLETE_ENRICHMENT"
        for row in rows
    )



def test_french_race_uses_complete_pmu_history_when_atg_is_not_full(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    rikstoto = FakeRikstoto(
        country="FR",
        track="Chantilly",
        raceday_key="F1_NR_2026-09-27",
    )
    collector = RikstotoCollector(
        store,
        rikstoto,
        FakeAtg(country="SE", track="Färjestad"),
        FakePmu(country="FR", track="Chantilly", available=True),
    )
    race = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))[0]
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    inserted, ok, _ = collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=observed,
    )

    assert ok
    assert inserted == 2
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)
    assert all(row["enrichment_provider"] == "pmu" for row in rows)
    assert all(row["full_field_history_complete"] == 1 for row in rows)
    assert all(row["data_quality"] == "FULL_FIELD_HISTORY_PMU" for row in rows)
    alpha = next(row for row in rows if row["selection_id"] == "1")
    assert alpha["history_total_starts"] == 20
    assert alpha["history_total_wins"] == 8
    assert alpha["history_total_seconds"] == 3
    assert alpha["history_total_thirds"] == 2
    assert alpha["identity_match_confidence"] == 0.99
    assert "dernierRapport" not in str(alpha["raw_json"])


def test_incomplete_pmu_history_fails_closed_for_entire_french_field(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    rikstoto = FakeRikstoto(
        country="FR",
        track="Chantilly",
        raceday_key="F1_NR_2026-09-27",
    )
    collector = RikstotoCollector(
        store,
        rikstoto,
        FakeAtg(country="SE", track="Färjestad"),
        FakePmu(
            country="FR",
            track="Chantilly",
            available=True,
            incomplete=True,
        ),
    )
    race = collector.discover(datetime(2026, 9, 27, 17, 0, tzinfo=UTC))[0]
    observed = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)

    collector.collect_fundamentals(
        raceday_key=race.raceday_key,
        race_number=1,
        race_id=race.race_id,
        observed_at=observed,
    )
    rows = store.latest_runner_fundamentals(race.race_id, before=observed)

    assert all(row["full_field_history_complete"] == 0 for row in rows)
    assert all(row["history_total_starts"] is None for row in rows)
    assert all(row["enrichment_provider"] is None for row in rows)



def test_legacy_pool_endpoints_are_disabled_by_default(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    collector = RikstotoCollector(store, FakeRikstoto())
    inserted, failures = collector.collect_pool_context(
        raceday_key="BJ_NR_2026-09-27",
        products=["V75"],
        observed_at=datetime(2026, 9, 27, 17, 56, tzinfo=UTC),
    )
    assert inserted == 0
    assert failures == 0
