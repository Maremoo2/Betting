"""File-based betting decisions. No HBI/Champion/database mutation."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .v33 import (
    POLICY,
    POLICY_HASH,
    allocate_stake,
    attach_closing,
    construct_multi_race,
    evaluate,
    reassess,
    review_coupon,
    verify_report,
)


def write_new(path, data):
    # Never overwrite a frozen decision, registration, or opportunity revision.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="betting")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register-batch")
    register.add_argument("batch_id")
    register.add_argument("--output", required=True)
    register.add_argument("--shadow-weights", help="JSON file of frozen research blend weights")
    review = commands.add_parser("review")
    review.add_argument("input")
    review.add_argument("--batch", required=True)
    review.add_argument("--output", required=True)
    multi = commands.add_parser("multi-race")
    multi.add_argument("input")
    multi.add_argument("--output", required=True)
    for name in ("reassess", "closing", "coupon", "stake"):
        command = commands.add_parser(name)
        command.add_argument("decision")
        command.add_argument("input")
        command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "register-batch":
            output = {"batch_id": args.batch_id, "mode": "PROSPECTIVE_BLIND",
                      "registered_at": datetime.now(UTC).isoformat(),
                      "policy_hash": POLICY_HASH, "frozen_policy": POLICY,
                      "outcome_tuning": False, "execution": "SHADOW_ONLY"}
            if args.shadow_weights:
                output["shadow_weights"] = read(args.shadow_weights)
        elif args.command == "review":
            data = read(args.input)
            data["batch"] = read(args.batch)
            output = evaluate(data)
        elif args.command == "multi-race":
            data = read(args.input)
            output = construct_multi_race(data["legs"], data["unit_price"])
        else:
            report, data = read(args.decision), read(args.input)
            if args.command == "reassess":
                output = reassess(report, data["snapshot"], data["decision_time"])
            elif args.command == "closing":
                output = attach_closing(report, data)
            elif args.command == "coupon":
                output = review_coupon(report, **data)
            else:
                verify_report(report)
                if not report["allowed"]:
                    raise ValueError("incomplete single-bet review")
                output = allocate_stake(report["runners"][data["selection"]][data["product"]])
                output["parent_decision_id"] = report["decision_id"]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        output = {"standard": "Betting V3.3", "allowed": False,
                  "errors": [f"INVALID_V33_INPUT:{exc}"], "execution": "SHADOW_ONLY"}
    write_new(args.output, output)
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
    if output.get("allowed") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
