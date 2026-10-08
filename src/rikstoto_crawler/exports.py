"""Separate upload bundles; PRE rendering never reads POST files or endpoints."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from .extract import keyed, numeric
from .job import file_hash, read
from .transport import ArchiveClient, write_json

PAYOUTS = {"WIN": "winOdds", "PLACE": "placeOdds", "TWIN": "twinOdds",
           "DUO": "duoOdds", "TRIPLE": "tripleOdds"}


def frozen_rows(root):
    root = Path(root)
    manifest = read(root / "freeze.json")
    if file_hash(root / "pre.jsonl") != manifest["file_sha256"]:
        raise ValueError("PRE freeze integrity mismatch")
    return [json.loads(line) for line in (root / "pre.jsonl").read_text(
        encoding="utf-8").splitlines()], manifest


def display_result(row, result):
    """Published top finishers/dividends are display evidence, not full settlement."""
    if result["raceDay"] != row["raceday_key"]:
        raise ValueError("result summary race-day mismatch")
    race = str(row["race_number"])
    finishers = keyed(result["raceResults"][race])
    if not finishers or not set(finishers) <= set(row["active_field"]):
        raise ValueError("result summary outside active field")
    positions = [v["place"] for v in finishers.values()]
    if any(type(p) is not int or p < 1 for p in positions) or 1 not in positions:
        raise ValueError("invalid published positions")
    dividends = {}
    for product, field in PAYOUTS.items():
        source = result["finalOdds"].get(field, {}).get(race)
        if source is None:
            dividends[product] = {"status": "MISSING", "entries": []}
            continue
        entries = []
        if product in {"WIN", "PLACE"}:
            if not isinstance(source, dict):
                raise ValueError("unsupported dividend schema")
            items = [(str(n), item) for n, item in source.items()]
        else:
            if not isinstance(source, list):
                raise ValueError("unsupported combination dividend schema")
            items = [(item["startNumbers"], item) for item in source]
        for selection, item in items:
            numbers = selection.split("-")
            if (not numbers or not set(numbers) <= set(row["active_field"])
                    or len(set(numbers)) != len(numbers)):
                raise ValueError("dividend outside active field")
            if len(numbers) != {"WIN": 1, "PLACE": 1, "TWIN": 2, "DUO": 2, "TRIPLE": 3}[product]:
                raise ValueError("invalid dividend selection")
            value = numeric(item["odds"], minimum=0)
            status = item.get("payoutStatus")
            entries.append({"selection": selection, "payout_status": status,
                            "raw_odds": value,
                            "dividend": value if status == "Dividends" and value > 0 else None})
        dividends[product] = {"status": "PUBLISHED" if entries else "EMPTY", "entries": entries}
    return {"race_id": row["race_id"], "finishers": finishers, "dividends": dividends,
            "identity_method": "PROVIDER_RACE_START_NUMBER_DISPLAY_ONLY",
            "settlement_eligible": False, "full_result_verified": False}


def collect_display(root, *, client=None):
    root = Path(root)
    rows, manifest = frozen_rows(root)
    client = client or ArchiveClient(root)
    records, failures, displays, rejected = {}, {}, [], {}
    for row in rows:
        key = row["raceday_key"]
        try:
            if key in failures:
                raise ValueError(failures[key])
            if key not in records:
                try:
                    records[key] = client.get(f"/results/raceDays/{key}/raceresults", result=True)
                except (OSError, ValueError, TypeError) as exc:
                    failures[key] = str(exc)
                    raise
            record = records[key]
            display = display_result(row, record["body"]["result"])
            display["source"] = {k: record[k] for k in ("url", "fetched_at", "body_sha256")}
            displays.append(display)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            rejected[row["race_id"]] = str(exc)
    frozen_rows(root)
    write_json(root / "post-display.json", {"rows": displays, "rejected": rejected,
                                            "pre_freeze": manifest,
                                            "settlement_eligible": False})
    return {"displayed": len(displays), "rejected": len(rejected)}


def text_cell(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *("| " + " | ".join(text_cell(v) for v in row) + " |" for row in rows)])


def csv_file(path, headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    for row in rows:
        # Prevent spreadsheet formulas in provider-supplied names.
        writer.writerow(["'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                         else v for v in row])
    path.write_text(stream.getvalue(), encoding="utf-8-sig", newline="")


def bundle(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in files:
            archive.write(source, source.name)


def export(root, *, stage="pre"):
    root = Path(root)
    rows, manifest = frozen_rows(root)
    destination = root / "exports"
    destination.mkdir(exist_ok=True)
    outputs = []
    if stage in {"pre", "both"}:
        markets, collective_rows, sections = [], [], [
            "# PRE-winner watch\n\nHistorical market archive; not a live decision snapshot.\n"
            "No finish positions or dividends. PRE SHA-256: " + manifest["file_sha256"]]
        for row in rows:
            sections.append(f"\n## {row['date']} — {row['track']} — Løp {row['race_number']}\n\n"
                            f"Start: {row['race_start']}. Omsetning V/P NOK: "
                            f"{row['turnover']['V']['nok']} / {row['turnover']['P']['nok']}\n")
            visible = []
            for n in sorted(row["runners"], key=lambda n: row["runners"][n].get("win_odds", 1e9)):
                r = row["runners"][n]
                values = [n, r["horse_name"], r["driver_name"], r.get("win_odds"),
                          r.get("place_min"), r.get("place_max"), r["scratched"]]
                visible.append(values)
                markets.append([row["race_id"], row["date"], row["country"], row["track"],
                                row["race_start"], *values, r.get("win_updated_at"),
                                r.get("place_updated_at"), row["turnover"]["V"]["nok"],
                                row["turnover"]["P"]["nok"]])
            sections.append(table(["Nr", "Hest", "Kusk", "Vinner", "Min", "Maks", "Strøket"], visible))
            for pool, data in row["collective"].items():
                for n in row["active_field"]:
                    collective_rows.append([row["race_id"], pool, n, data["raw_shares"][n],
                                            row["pWIN"][n], data["pCOL"][n], data["updated_at"],
                                            data["win_skew_seconds"], data["contemporaneous"]])
        (destination / "PRE.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
        csv_file(destination / "PRE.csv", ["race_id", "date", "country", "track", "start",
                 "number", "horse", "driver", "WIN", "PLACE_min", "PLACE_max", "scratched",
                 "WIN_updated", "PLACE_updated", "V_turnover_NOK", "P_turnover_NOK"], markets)
        csv_file(destination / "COLLECTIVE.csv", ["race_id", "pool", "number", "share_percent",
                 "pWIN", "pCOL", "updated_at", "WIN_skew_seconds", "contemporaneous"], collective_rows)
        bundle(destination / "PRE-upload.zip", [destination / "PRE.md", destination / "PRE.csv",
               destination / "COLLECTIVE.csv", root / "pre.jsonl", root / "freeze.json"])
        outputs.append(str(destination / "PRE-upload.zip"))
    if stage in {"post", "both"}:
        data = read(root / "post-display.json")
        if data["pre_freeze"]["file_sha256"] != manifest["file_sha256"]:
            raise ValueError("POST display belongs to another PRE freeze")
        verified = read(root / "post-results.json") if (root / "post-results.json").exists() else {}
        if verified and verified["pre_freeze"]["file_sha256"] != manifest["file_sha256"]:
            raise ValueError("POST results belong to another PRE freeze")
        joined = {r["race_id"] for r in verified.get("rows", [])}
        indexed = {r["race_id"]: r for r in rows}
        records, sections = [], [("# POST-race\n\nPublished positions/dividends, separately from PRE.\n"
                                 "Partial summaries are display evidence, never automatic settlement.")]
        for display in data["rows"]:
            row = indexed[display["race_id"]]
            full = display["race_id"] in joined
            sections.append(f"\n## {row['date']} — {row['track']} — Løp {row['race_number']}\n\n"
                            f"Full-field identity/result check: {'PASS' if full else 'UNVERIFIED/QUARANTINED'}.\n")
            sections.append("Strøket: " + ", ".join(n for n, r in row["runners"].items() if r["scratched"]) + "\n")
            visible = []
            for n, finisher in sorted(display["finishers"].items(), key=lambda item: item[1]["place"]):
                r = row["runners"][n]
                def single(product, display=display, n=n):
                    return next((e["dividend"] for e in display["dividends"][product]["entries"]
                                 if e["selection"] == n), None)
                values = [finisher["place"], n, r["horse_name"], r["driver_name"], single("WIN"), single("PLACE")]
                visible.append(values)
                records.append([row["race_id"], *values, full])
            sections.append(table(["Pl", "Nr", "Hest", "Kusk", "Vinner", "Plass"], visible))
            sections.append("\nCombination dividends (selection remains explicit):\n")
            sections.append(table(["Produkt", "Kombinasjon", "Utbetaling", "Status"],
                [[p, e["selection"], e["dividend"], e["payout_status"]]
                 for p in ("TWIN", "DUO", "TRIPLE") for e in display["dividends"][p]["entries"]]))
        sections.append("\nMissing/invalid summaries: " + json.dumps(data["rejected"], ensure_ascii=False))
        (destination / "POST.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
        csv_file(destination / "POST.csv", ["race_id", "place", "number", "horse", "driver",
                                            "WIN_dividend", "PLACE_dividend", "full_result_verified"], records)
        csv_file(destination / "DIVIDENDS.csv", ["race_id", "product", "selection", "dividend", "status"],
                 [[d["race_id"], p, e["selection"], e["dividend"], e["payout_status"]]
                  for d in data["rows"] for p in PAYOUTS for e in d["dividends"][p]["entries"]])
        files = [destination / "POST.md", destination / "POST.csv", destination / "DIVIDENDS.csv",
                 root / "post-display.json"]
        if (root / "post-results.json").exists():
            files.append(root / "post-results.json")
        bundle(destination / "POST-upload.zip", files)
        outputs.append(str(destination / "POST-upload.zip"))
    frozen_rows(root)
    return {"files": outputs, "pre_unchanged": True}
