from __future__ import annotations

import argparse
import json

from .job import crawl, january, post, validate_sample


def main(argv=None):
    parser = argparse.ArgumentParser(description="Historical Rikstoto PRE-WINNER research crawler")
    sub = parser.add_subparsers(dest="command", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--days", default="2025-12-22,2025-12-23,2025-12-24,2025-12-25,2025-12-26")
    sample.add_argument("--countries", default="NO,SE,FR")
    sample.add_argument("--max-races-per-meeting", type=int, default=2)
    sample.add_argument("--output", required=True)
    month = sub.add_parser("january")
    month.add_argument("--sample", required=True)
    month.add_argument("--output", required=True)
    results = sub.add_parser("post")
    results.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "sample":
        if args.max_races_per_meeting < 0:
            parser.error("max-races-per-meeting must be nonnegative")
        report = crawl(args.output, args.days.split(","), countries=args.countries.split(","),
                       max_races_per_meeting=args.max_races_per_meeting)
        gate = validate_sample(report)
        print(json.dumps({"accepted": report["accepted"], "by_country": report["by_country"],
                          "rejected": report["rejected"], "expansion_gate": gate}, indent=2))
        if not gate["allowed"]:
            raise SystemExit(2)
    elif args.command == "january":
        report = january(args.output, args.sample)
        print(json.dumps({"accepted": report["accepted"], "by_country": report["by_country"],
                          "rejected_n": len(report["rejected"]),
                          "fetch_errors": report["fetch_errors"],
                          "observed_days": report["observed_days"]}, indent=2))
        if report["fetch_errors"] or len(report["observed_days"]) != 31:
            raise SystemExit(2)
    else:
        print(json.dumps(post(args.output), indent=2))


if __name__ == "__main__":
    main()
