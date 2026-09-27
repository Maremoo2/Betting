from pathlib import Path

from hbi.export import export_database_csv
from hbi.json_provider import load_market_snapshots, load_race_cards, load_results
from hbi.pipeline import HBIPipeline
from hbi.storage import SQLiteStore


ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


def test_end_to_end_json_to_database_and_export(tmp_path):
    store = SQLiteStore(tmp_path / "hbi.sqlite")
    store.initialize(SCHEMA)
    pipeline = HBIPipeline(store)

    cards = load_race_cards(ROOT / "examples" / "races.json")
    for card in cards:
        pipeline.persist_race_card(card)

    snapshots = load_market_snapshots(ROOT / "examples" / "snapshots.json")
    for snapshot in snapshots:
        pipeline.process_snapshot(snapshot, source_uri="fixture://market")

    results = load_results(ROOT / "examples" / "results.json")
    for result in results:
        pipeline.settle(result)

    assert store.count("races") == 1
    assert store.count("runners") == 1
    assert store.count("market_snapshots") == 2
    assert store.count("prewatch_events") == 1
    assert store.count("outcomes") == 1

    counts = export_database_csv(store, tmp_path / "exports")
    assert counts["races"] == 1
    assert counts["market_snapshots"] == 2
    assert (tmp_path / "exports" / "races.csv").exists()
