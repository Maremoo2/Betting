"""Read-only authentic Romme V65 2026-11-06 official results (NO BET)."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

KEY = "S1_NR_2026-11-06"
HOST = "https://www.rikstoto.no/api"
PATHS = [f"/results/raceDays/{KEY}/{n}/completeresults" for n in range(2, 8)]
PATHS += [
    f"/results/raceDays/{KEY}/raceresults",
    f"/game/prizepayout/system/{KEY}/V65",
    f"/results/raceDays/{KEY}/totalInvestment",
]


def original_winner(raw: bytes, race_no: int) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("success") is False:
        raise ValueError("OFFICIAL_ENVELOPE_INVALID")
    result = data.get("result")
    if not isinstance(result, dict) or result.get("isComplete") is not True:
        raise ValueError("OFFICIAL_RESULT_INCOMPLETE")
    rows = result.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("OFFICIAL_RESULT_ROWS_MISSING")
    numbered = [row for row in rows if isinstance(row, dict)
                and type(row.get("startNumber")) is int]
    if (len(numbered) != len(rows)
            or len({r["startNumber"] for r in numbered}) != len(rows)):
        raise ValueError("OFFICIAL_START_NUMBER_CONFLICT")
    winners = [row for row in rows if row.get("place") == 1]
    if len(winners) != 1:
        raise ValueError("OFFICIAL_WINNER_NOT_UNIQUE")
    return {
        "race_no": race_no,
        "winner_number": winners[0]["startNumber"],
        "winner_name": winners[0].get("horseName"),
        "winner_registration": winners[0].get("horseRegistrationNumber"),
        "result_rows": len(rows),
    }


def capture(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    (output / "originals").mkdir()
    receipts = []
    for path in PATHS:
        url = HOST + path
        started = datetime.now(UTC)
        raw, code, headers, error = None, None, {}, None
        try:
            request = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "Romme-P0-original-only-post-race/1.0",
            })
            with urllib.request.urlopen(request, timeout=18) as response:
                code, headers = response.status, dict(response.headers)
                if response.url != url:
                    raise ValueError("OFFICIAL_UNEXPECTED_REDIRECT")
                raw = response.read(3_000_001)
                if len(raw) > 3_000_000:
                    raise ValueError("OFFICIAL_ORIGINAL_TOO_LARGE")
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, ValueError) as exc:
            code = exc.code if isinstance(exc, urllib.error.HTTPError) else code
            error = f"{type(exc).__name__}:{str(exc)[:140]}"
            raw = None
        receipt = {
            "path": path, "url": url,
            "http_status": code,
            "request_started_utc": started.isoformat(),
            "response_completed_utc": datetime.now(UTC).isoformat(),
            "http_date_not_publication_proof": headers.get("Date"),
            "sha256": None, "original_file": None,
            "result": None, "error": error,
        }
        if code == 200 and raw:
            sha = hashlib.sha256(raw).hexdigest()
            dest = output / "originals" / f"{sha}.json"
            if dest.exists() and dest.read_bytes() != raw:
                raise ValueError("OFFICIAL_SHA_COLLISION")
            if not dest.exists():
                dest.write_bytes(raw)
            receipt["sha256"], receipt["original_file"] = (
                sha, f"originals/{sha}.json",
            )
            if path.endswith("/completeresults"):
                try:
                    receipt["result"] = original_winner(
                        raw, int(path.rsplit("/", 2)[1]),
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    receipt["error"] = str(exc)
        receipts.append(receipt)
    report = {
        "schema": "ROMME_20261106_OFFICIAL_RESULT_ORIGINAL_V1",
        "completed_utc": datetime.now(UTC).isoformat(),
        "official_winners_verified": sum(r["result"] is not None for r in receipts),
        "bet_authority": False, "no_prior_model_mutation": True,
        "receipts": receipts,
    }
    (output / "index.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({"verified": report["official_winners_verified"],
                      "errors": [(r["path"], r["error"]) for r in receipts if r["error"]]}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parsed = parser.parse_args()
    if capture(parsed.output)["official_winners_verified"] != 6:
        raise SystemExit("OFFICIAL_RESULT_SIX_RACES_UNVERIFIED")
