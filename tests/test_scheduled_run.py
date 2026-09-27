from pathlib import Path

from hbi.scheduled_run import run_once


def test_scheduled_run_without_provider_is_audited_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("HBI_RACE_CARDS_JSON", raising=False)
    monkeypatch.delenv("HBI_MARKET_SNAPSHOTS_JSON", raising=False)
    monkeypatch.delenv("HBI_RESULTS_JSON", raising=False)

    audit = run_once(db_path=str(tmp_path / "hbi.sqlite"), mode="HOURLY_WATCH")

    assert audit.status == "NOOP"
    assert audit.provider_status == "NO_PROVIDER_CONFIGURED"
    assert audit.snapshots_inserted == 0
    assert (tmp_path / "hbi.sqlite").exists()


def test_scheduled_run_can_ingest_canonical_files(tmp_path, monkeypatch):
    root = Path(__file__).parents[1]
    monkeypatch.setenv("HBI_RACE_CARDS_JSON", str(root / "examples" / "races.json"))
    monkeypatch.setenv(
        "HBI_MARKET_SNAPSHOTS_JSON",
        str(root / "examples" / "snapshots.json"),
    )
    monkeypatch.setenv("HBI_RESULTS_JSON", str(root / "examples" / "results.json"))

    audit = run_once(db_path=str(tmp_path / "hbi.sqlite"), mode="MORNING_DISCOVERY")

    assert audit.status == "OK"
    assert audit.provider_status == "CANONICAL_FILES"
    assert audit.race_cards == 1
    assert audit.snapshots_inserted == 2
    assert audit.prewatch_events == 1
    assert audit.results_settled == 1
