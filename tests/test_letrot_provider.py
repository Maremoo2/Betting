from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_provider_capability import inputs

from hbi.providers.atg import AtgFetchResult
from hbi.providers.letrot import EmbeddedData, LeTrotClient

NOW = datetime(2026, 9, 27, 17, 56, tzinfo=UTC)


class FakeLeTrot(LeTrotClient):
    def __init__(self):
        self.horses = {
            "Alpha": {
                "numCheval": "a",
                "nomCheval": "Alpha",
                "nbCourses": 20,
                "nbVictoire": 8,
                "annee": 2021,
            },
            "Beta": {
                "numCheval": "b",
                "nomCheval": "Beta",
                "nbCourses": 30,
                "nbVictoire": 3,
                "annee": 2020,
            },
        }
        self.race = {
            "statut": "INCOMING",
            "numCourse": 1,
            "dateCourse": "2026-09-27",
            "discipline": "A",
            "nomHippodrome": "Laval",
            "heure": {"date": "2026-09-27 20:00:00", "timezone": "Europe/Paris"},
            "partants": [
                {
                    "name": "Alpha",
                    "id": "a",
                    "leavingNumber": 1,
                    "nonPartant": False,
                    "horseUrl": "/stats/chevaux/Alpha/a/courses",
                },
                {
                    "name": "Beta",
                    "id": "b",
                    "leavingNumber": 2,
                    "nonPartant": False,
                    "horseUrl": "/stats/chevaux/Beta/b/courses",
                },
            ],
        }

    def fetch(self, path, tag, attribute):
        if tag == "meeting-day":
            data = {"meetings": [{"nomHippodrome": "Laval", "numHippodrome": "5305"}]}
        elif tag == "race-detail":
            data = {"race": self.race}
        else:
            data = self.horses[path.split("/")[3]]
        return AtgFetchResult("https://www.letrot.com" + path, data, True, 200, 1)


def corroborate(client, now=NOW):
    matched = {str(s["number"]): s for s in inputs()["payload"]["starts"]}
    return client.corroborate(
        track="Laval",
        race_number=1,
        expected_start=NOW + timedelta(minutes=4),
        matched=matched,
        audit=lambda *a, **kw: None,
        clock=lambda: now,
    )


def test_full_career_corroboration_is_market_free():
    result = corroborate(FakeLeTrot())
    assert result["passed"]
    assert len(result["runners"]) == 2
    assert all(r["passed"] for r in result["runners"])
    assert "rapportProbable" not in str(result)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.horses["Alpha"].update(nbCourses=21),
        lambda c: c.horses["Alpha"].update(nbVictoire=7),
        lambda c: c.horses["Alpha"].update(numCheval="wrong"),
        lambda c: c.horses["Alpha"].update(nomCheval="Wrong horse"),
        lambda c: c.horses["Alpha"].update(annee=2015),
        lambda c: c.horses["Alpha"].pop("nbCourses"),
        lambda c: c.race["partants"].pop(),
        lambda c: c.race["partants"].append(deepcopy(c.race["partants"][0])),
        lambda c: c.race["partants"][0].update(nonPartant=True),
        lambda c: c.race.update(statut="FINISHED"),
        lambda c: c.race.update(nomHippodrome="Vincennes"),
    ],
)
def test_disagreement_or_partial_corroboration_rejects_entire_field(mutation):
    client = FakeLeTrot()
    mutation(client)
    assert not corroborate(client)["passed"]


def test_fetch_finishing_after_start_is_rejected():
    assert not corroborate(FakeLeTrot(), NOW + timedelta(minutes=5))["passed"]


def test_embedded_json_only_and_network_path_allowlist():
    parser = EmbeddedData("horse-main", ":horse")
    parser.feed('<horse-main :horse="{&quot;nbCourses&quot;:12}"></horse-main>')
    assert parser.values == [{"nbCourses": 12}]
    with pytest.raises(ValueError):
        LeTrotClient().fetch("https://untrusted.invalid/", "horse-main", ":horse")


def test_fetch_failure_blocks_corroboration():
    client = FakeLeTrot()
    client.fetch = lambda *a: AtgFetchResult(
        "https://www.letrot.com/courses/x", None, False, 403, 1, "Forbidden"
    )
    assert not corroborate(client)["passed"]
