"""Real archived source replay; synthetic decision failures are separate tests."""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from betting.cli import main as betting_main
from hbi.crawler_replay import BODY_SHA256, RACE_ID, archive_card, review_input
from pre_winner.engine import load_input

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "tests/fixtures/bjerke-2026-10-20-source.md"


def test_real_archived_field_import_and_blocked_review(tmp_path):
    card, provenance = archive_card(SOURCE.read_text(encoding="utf-8"))
    assert provenance["body_sha256"] == BODY_SHA256
    assert provenance["previous_start_rows"] == 60
    assert card["race"]["start_time_utc"] == "2026-10-20T17:20:00+00:00"
    source = tmp_path / "race.json"
    source.write_text(json.dumps({"races": [card]}))
    db = tmp_path / "isolated.sqlite"
    result = subprocess.run(
        [sys.executable, "-m", "hbi.cli", "--db", str(db), "import-races", str(source)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "imported 1 race cards"
    from hbi.storage import SQLiteStore

    store = SQLiteStore(db)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT selection_id,horse_name FROM runners WHERE race_id=?", (RACE_ID,)
        ).fetchall()
    assert {tuple(row) for row in rows} == {
        (r["selection_id"], r["horse_name"]) for r in card["runners"]
    }
    assert len(rows) == 12
    assert store.count("outcomes") == store.count("predictions") == 0
    assert store.count("market_snapshots") == store.count("decisions") == 0
    data = review_input(card)
    data["active_field"] = [r[0] for r in rows]
    request, batch, output = [tmp_path / name for name in ("review.json", "batch.json", "out.json")]
    request.write_text(json.dumps(data))
    # Intentionally unregistered: never forge a historical prospective registration.
    batch.write_text(json.dumps({"mode": "RETROSPECTIVE_REPLAY", "batch_id": "M1-only"}))
    with pytest.raises(SystemExit) as exc:
        betting_main(["review", str(request), "--batch", str(batch), "--output", str(output)])
    assert exc.value.code == 2
    report = json.loads(output.read_text())
    assert report["allowed"] is False
    assert report["execution"] == "SHADOW_ONLY"
    assert report["errors"] == [
        "INVALID_V33_INPUT:FULL_FIELD_ONLY: exact identity evidence required"
    ]


@pytest.mark.parametrize("mutation", ["name", "late_source", "partial_field", "POST", "odds"])
def test_archive_mutation_rejected(mutation):
    body = SOURCE.read_text(encoding="utf-8")
    changed = {
        "name": body.replace("MIO NOVA", "OTHER HORSE", 1),
        "late_source": body.replace("05:18:04.113215", "19:18:04.113215", 1),
        "partial_field": body.replace("#12 HOVS RAPPEN", "omitted runner", 1),
        "POST": body + "\nPOST winner=1\n",
        "odds": body + '\nWIN={"1":2.5}\n',
    }[mutation]
    with pytest.raises(ValueError, match="ARCHIVE_SHA256_MISMATCH"):
        archive_card(changed)


def test_corrupt_zip_rejected_by_existing_archive_loader(tmp_path):
    path = tmp_path / "corrupt.zip"
    path.write_bytes(b"not a zip archive")
    with pytest.raises(zipfile.BadZipFile):
        load_input(path)


def test_real_field_late_review_rejected(tmp_path):
    card, _ = archive_card(SOURCE.read_text(encoding="utf-8"))
    data = review_input(card)
    data["decision_time"] = data["race_start"]
    request, batch, output = [tmp_path / name for name in ("late.json", "batch.json", "out.json")]
    request.write_text(json.dumps(data))
    batch.write_text("{}")
    with pytest.raises(SystemExit) as exc:
        betting_main(["review", str(request), "--batch", str(batch), "--output", str(output)])
    assert exc.value.code == 2
    assert json.loads(output.read_text())["errors"] == ["INVALID_V33_INPUT:RACE_ALREADY_STARTED"]


@pytest.mark.parametrize("missing", ["fundamental", "probability", "WIN_odds"])
def test_synthetic_missing_model_or_prices_never_creates_bet(tmp_path, missing):
    # Existing artificial schema example, deliberately separate from archived evidence.
    data = json.loads((ROOT / "examples/betting-v33.json").read_text())
    if missing == "fundamental":
        del data["fundamental"]
    elif missing == "probability":
        del data["fundamental"]["probabilities"]["2"]
    else:
        del data["decision_snapshot"]["WIN"]["odds"]["2"]
    request, batch, output = [tmp_path / name for name in ("input.json", "batch.json", "out.json")]
    request.write_text(json.dumps(data))
    batch.write_text("{}")
    with pytest.raises(SystemExit) as exc:
        betting_main(["review", str(request), "--batch", str(batch), "--output", str(output)])
    assert exc.value.code == 2
    report = json.loads(output.read_text())
    assert report["allowed"] is False and report["execution"] == "SHADOW_ONLY"
    assert "runners" not in report
    assert report["errors"][0].startswith("INVALID_V33_INPUT:")
