"""Synthetic discovery/runtime contracts, never authentic field qualification."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbi import live_smoke as smoke

NOW = datetime(2026, 11, 23, 10, tzinfo=UTC)


def race(country, sport="T"):
    key = country + sport
    return SimpleNamespace(start_time=NOW + timedelta(hours=2), country_code=country,
                           progress_status="Future", raceday_key=key, race_number=1,
                           race_id=key, raceday_name=key, sport_type=sport)


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.delenv("HBI_SMOKE_REQUIRED_COUNTRIES", raising=False)
    state = {"races": [race(c) for c in ("FR", "DK", "NO", "SE")]
             + [race("NO", "G"), race("SE", "G")], "seen": [],
             "coverage": {}, "passed": {}, "eligible": {}, "registry": {}}

    class Clock:
        @staticmethod
        def now(zone):
            return NOW

    class Collector:
        def __init__(self, store):
            pass

        def discover(self, now):
            return state["races"]

        @staticmethod
        def _discipline(sport):
            return "trot" if sport == "T" else "gallop"

        def collect_fundamentals(self, *, race_id, **kwargs):
            state["seen"].append(race_id)
            self.last_capability = {"passed": state["passed"].get(race_id, True),
                                    "country": race_id[:2]}

    def model(store, *, race_id, created_at):
        return SimpleNamespace(shadow_eligible=state["eligible"].get(race_id, True),
                               history_coverage=state["coverage"].get(race_id, 1))

    monkeypatch.setattr(smoke, "datetime", Clock)
    monkeypatch.setattr(smoke, "_store", lambda path: object())
    monkeypatch.setattr(smoke, "RikstotoCollector", Collector)
    monkeypatch.setattr(smoke, "run_and_persist_fundamental", model)
    monkeypatch.setattr(smoke, "capability", lambda provider, country, discipline:
                        {"status": state["registry"].get(country, "VERIFIED")})
    return state


def test_only_no_se_trot_can_satisfy_product_contract(runtime):
    report = smoke.run_live_smoke()
    assert report.required_countries == ["NO", "SE"]
    assert report.acceptance_scope == "NO_SE_TROT_PRODUCT_V1"
    assert set(runtime["seen"]) == {"NOT", "SET"}
    assert report.candidate_races_by_country == {"NO": 1, "SE": 1}
    assert set(report.verified_countries) == {"NO", "SE"} and not report.errors


def test_gallop_or_foreign_fields_cannot_replace_missing_norwegian_trot(runtime):
    runtime["races"] = [r for r in runtime["races"] if r.race_id != "NOT"]
    report = smoke.run_live_smoke()
    assert report.verified_countries == ["SE"]
    assert "NO_FULL_FIELD_LIVE_PASS:NO" in report.errors


def test_incomplete_history_still_blocks_required_country(runtime):
    runtime["coverage"]["NOT"] = 0.99
    report = smoke.run_live_smoke()
    assert "RUNTIME_GATE_MISMATCH:NOT" in report.errors
    assert "NO_FULL_FIELD_LIVE_PASS:NO" in report.errors


@pytest.mark.parametrize("unverified", [False, True])
def test_failed_or_unverified_field_cannot_escape_gate(runtime, unverified):
    if unverified:
        runtime["registry"]["NO"] = "UNVERIFIED"
        expected = "UNVERIFIED_PAIR_ESCAPED_GATE:NOT"
    else:
        runtime["passed"]["NOT"] = False
        expected = "FAILED_FIELD_ESCAPED_GATE:NOT"
    assert expected in smoke.run_live_smoke().errors


def test_diagnostics_have_separate_scope_and_actual_missing_country(runtime, monkeypatch):
    monkeypatch.setenv("HBI_SMOKE_REQUIRED_COUNTRIES", "DK,FR")
    runtime["races"] = [r for r in runtime["races"] if r.country_code != "DK"]
    report = smoke.run_live_smoke()
    assert report.acceptance_scope == "DK_FR_TROT_DIAGNOSTIC_V1"
    assert runtime["seen"] == ["FRT"]
    assert "NO_FULL_FIELD_LIVE_PASS:DK" in report.errors
    assert not any(x in report.verified_countries for x in ("NO", "SE"))


@pytest.mark.parametrize("scope", ["NO", "SE", "", "NO,SE,DK,FR"])
def test_misconfiguration_cannot_weaken_two_country_contract(runtime, monkeypatch, scope):
    monkeypatch.setenv("HBI_SMOKE_REQUIRED_COUNTRIES", scope)
    with pytest.raises(ValueError, match="PROVIDER_SMOKE_SCOPE"):
        smoke.run_live_smoke()
    assert not runtime["seen"]


def test_workflow_keeps_mandatory_gate_and_diagnostic_failure_distinct():
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/provider-live-smoke.yml").read_text()
    mandatory, diagnostic = workflow.split("  provider-diagnostics:", 1)
    assert "HBI_SMOKE_REQUIRED_COUNTRIES: NO,SE" in mandatory
    assert "continue-on-error" not in mandatory
    assert "if-no-files-found: error" in mandatory
    assert "HBI_SMOKE_REQUIRED_COUNTRIES: DK,FR" in diagnostic
    assert "continue-on-error: true" in diagnostic
    assert "steps.diagnostic.outcome" in diagnostic
    assert "mandatory_for_product': False" in diagnostic
    assert "hbi-provider-diagnostic-dk-fr-" in diagnostic
