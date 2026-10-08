from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import run


def main():
    parser = argparse.ArgumentParser(description="Frozen PRE-WINNER bulk research; never POST")
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    inputs = []
    for value in args.input:
        path = Path(value)
        if path.is_dir() and not (path / "freeze.json").exists():
            inputs.extend(sorted(path.glob("Rikstoto_PRE_*.zip")))
        else:
            inputs.append(path)
    if not inputs:
        parser.error("no PRE archives found")
    qc = run(inputs, args.output)
    print(json.dumps({k: v for k, v in qc.items() if k != "aggregates"}, indent=2))
    if qc["rejected_races"] or qc["conflicting_races"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
