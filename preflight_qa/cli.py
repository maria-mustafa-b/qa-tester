from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from preflight_qa.config import load_config
from preflight_qa.reporting import write_reports
from preflight_qa.scanner import run_scan

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preflight-qa",
        description="Run safe, evidence-first pre-release checks against an authorized web application.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan", help="scan an authorized web application")
    scan_parser.add_argument("--url", help="absolute target URL; overrides config target")
    scan_parser.add_argument("--config", type=Path, help="YAML scan configuration")
    scan_parser.add_argument("--output", type=Path, help="report output directory")
    scan_parser.add_argument(
        "--authorized",
        action="store_true",
        help="confirm you own or have explicit permission to test the target",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "scan":
        return 2
    if not args.authorized:
        print("Error: pass --authorized only after confirming permission to test the target.", file=sys.stderr)
        return 2

    try:
        config = load_config(args.config, args.url)
        output_dir = args.output or Path("reports") / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        print(f"[preflight] target: {config.target}")
        print(f"[preflight] page limit: {config.max_pages}")
        print(f"[preflight] viewports: {', '.join(v.name for v in config.viewports)}")
        report = run_scan(config, output_dir)
        json_path, html_path = write_reports(report, output_dir)
        data = report.to_dict()
        print(f"[preflight] pages tested: {data['summary']['pages_tested']}")
        print(f"[preflight] findings: {data['summary']['findings']}")
        print(f"[preflight] JSON: {json_path}")
        print(f"[preflight] HTML: {html_path}")
        return _result_exit_code(data, config.fail_on)
    except KeyboardInterrupt:
        print("\n[preflight] scan cancelled", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[preflight] error: {exc}", file=sys.stderr)
        return 2


def _result_exit_code(data: dict, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[fail_on]
    for severity, count in data["summary"]["by_severity"].items():
        if count and SEVERITY_RANK[severity] >= threshold:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

