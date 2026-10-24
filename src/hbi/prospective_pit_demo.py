"""Deterministic TEST_ONLY snapshot evidence. Never invokes a live endpoint."""
import argparse
import json
from datetime import timedelta
from pathlib import Path

from .prospective_pit import VERSION, capture, cutoff, encode, init_store, replay, seal, write_once


def test_plan():
    targets = []
    for country, hour in [("NO", "17:52"), ("SE", "13:45")]:
        rid = f"TEST_ONLY_{country}"
        url = f"https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{rid}"
        targets.append({"race_id": rid, "country": country, "track": "TEST_ONLY_TRACK", "number": 1,
            "scheduled_start_local": f"2026-10-25T{hour}:00", "timezone": "Europe/Oslo" if country == "NO" else "Europe/Stockholm",
            "expected_runner_ids": [101, 102], "sources": {"PROGRAM": {"url": url, "purpose": "INPUT"},
                "HISTORY": {"url": url if country == "NO" else None, "purpose": "INPUT"}}})
    return {"schema": VERSION, "mode": "TEST_ONLY", "created_at": "2026-10-23T08:00:00+00:00", "automatic_collection": False,
        "window_seconds": 300, "model_eligible": False, "targets": targets}


def test_body(target):
    return encode({"test_only": True, "races": [{"id": target["race_id"], "date": "2026-10-25", "sport": "trot", "status": "scheduled",
        "scheduledStartTime": target["scheduled_start_local"], "track": {"countryCode": target["country"]},
        "starts": [{"number": i, "horse": {"id": hid, "name": f"TEST_ONLY_HORSE_{i}"}, "scratched": False} for i, hid in [(1, 101), (2, 102)]]}]})


def demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    plan = test_plan()
    write_once(output / "test-only-plan.json", encode(plan))
    receipt = init_store(output / "test-only-plan.json", output / "store")
    no, se = plan["targets"]
    for target, minutes, delta, status in [(no, 1440, -1, 200), (no, 60, 1, 200), (no, 15, -1, 503), (se, 60, -1, 200)]:
        at = cutoff(target, minutes) + timedelta(seconds=delta)
        def transport(url, target=target, status=status):
            return status, {"Content-Type": "application/json", "Date": "TEST_ONLY_NOT_PUBLICATION"}, test_body(target)
        capture(output / "store", receipt["plan_sha256"], target["race_id"], minutes,
            fetch=transport, clock=lambda at=at: at)
    locked = seal(output / "store", receipt["plan_sha256"])
    report = replay(output / "store", locked["seal_sha256"])
    write_once(output / "receipt.json", encode(locked))
    write_once(output / "report.json", encode(report))
    return {**locked, "report": report}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    result = demo(args.output_dir)
    print(json.dumps({"evidence": "TEST_ONLY", **{k: v for k, v in result["report"].items() if k != "observations"},
        "receipt": {k: v for k, v in result.items() if k != "report"}}, indent=2))


if __name__ == "__main__":
    main()
