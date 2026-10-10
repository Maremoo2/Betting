from __future__ import annotations

import argparse
import json

from .exports import collect_display, export
from .integrity import run as integrity
from .job import crawl, january, post, validate_sample
from .weekly import weekly


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
    upload = sub.add_parser("export")
    upload.add_argument("--output", required=True)
    upload.add_argument("--stage", choices=("pre", "post", "both"), default="pre")
    check = sub.add_parser("integrity")
    check.add_argument("--output", required=True)
    weeks = sub.add_parser("weekly")
    weeks.add_argument("--output", required=True)
    weeks.add_argument("--stage", choices=("pre", "post", "both"), default="pre")
    capture = sub.add_parser("capture-v3")
    capture.add_argument("--days", required=True)
    capture.add_argument("--countries", default="NO,SE,DK,FR")
    capture.add_argument("--meeting")
    capture.add_argument("--refresh", action="store_true")
    capture.add_argument("--output", required=True)
    watcher = sub.add_parser("watch-v3")
    watcher.add_argument("--day", required=True)
    watcher.add_argument("--meeting", required=True)
    watcher.add_argument("--duration", type=int, default=3600)
    watcher.add_argument("--interval", type=int, default=30)
    watcher.add_argument("--output", required=True)
    for name in ("weekly-v3", "post-v3"):
        command = sub.add_parser(name)
        command.add_argument("--output", required=True)
    historical = sub.add_parser("archive")
    historical.add_argument("--first", default="2015-01")
    historical.add_argument("--last", default="2025-12")
    historical.add_argument("--mode", choices=("census", "pilot", "full"), default="census")
    historical.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "archive":
        from .archive import run
        print(json.dumps(run(args.output, args.first, args.last, mode=args.mode), indent=2))
    elif args.command in {"weekly-v3", "post-v3"}:
        from .capture_exports import post_v3, weekly_v3
        print(json.dumps((weekly_v3 if args.command == "weekly-v3" else post_v3)(args.output), indent=2))
    elif args.command == "watch-v3":
        from .watch import watch
        print(json.dumps(watch(args.output, args.day, args.meeting,
                               duration=args.duration, interval=args.interval), indent=2))
    elif args.command == "capture-v3":
        from .capture import collect
        print(json.dumps(collect(args.output, args.days.split(","),
                                 countries=args.countries.split(","), refresh=args.refresh,
                                 meeting_key=args.meeting), indent=2))
    elif args.command == "sample":
        if args.max_races_per_meeting < 0:
            parser.error("max-races-per-meeting must be nonnegative")
        report = crawl(args.output, args.days.split(","), countries=args.countries.split(","),
                       max_races_per_meeting=args.max_races_per_meeting)
        gate = validate_sample(report)
        export(args.output)
        print(json.dumps(weekly(args.output)))
        print(json.dumps({"accepted": report["accepted"], "by_country": report["by_country"],
                          "rejected": report["rejected"], "expansion_gate": gate}, indent=2))
        if not gate["allowed"]:
            raise SystemExit(2)
    elif args.command == "january":
        report = january(args.output, args.sample)
        export(args.output)
        print(json.dumps(weekly(args.output)))
        print(json.dumps({"accepted": report["accepted"], "by_country": report["by_country"],
                          "rejected_n": len(report["rejected"]),
                          "fetch_errors": report["fetch_errors"],
                          "observed_days": report["observed_days"]}, indent=2))
        if report["fetch_errors"] or len(report["observed_days"]) != 31:
            raise SystemExit(2)
    elif args.command == "post":
        print(json.dumps(post(args.output), indent=2))
        print(json.dumps(collect_display(args.output), indent=2))
        print(json.dumps(export(args.output, stage="both"), indent=2))
        print(json.dumps(weekly(args.output, stage="both"), indent=2))
    elif args.command == "integrity":
        print(json.dumps(integrity(args.output), indent=2))
    elif args.command == "weekly":
        print(json.dumps(weekly(args.output, stage=args.stage), indent=2))
    else:
        print(json.dumps(export(args.output, stage=args.stage), indent=2))


if __name__ == "__main__":
    main()
