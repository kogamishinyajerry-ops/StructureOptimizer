from __future__ import annotations

import argparse
import sys
from pathlib import Path

from structure_optimizer.benchmarks.registry import available_benchmarks
from structure_optimizer.core.demo import generate_demo_package
from structure_optimizer.core.reporting import generate_report
from structure_optimizer.core.study import run_study
from structure_optimizer.core.verification import FAILURE_STATUSES, PASS_STATUS, verify_run
from structure_optimizer.core.workflow import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m structure_optimizer")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser("run", help="Run a benchmark optimization")
    run.add_argument("--benchmark", required=True, choices=available_benchmarks())
    run.add_argument("--preset", default=None, help="Optional benchmark preset, e.g. smoke")

    verify = subcommands.add_parser("verify", help="Verify an existing run directory")
    verify.add_argument("--run", required=True, type=Path)

    report = subcommands.add_parser("report", help="Generate report.md for an existing run directory")
    report.add_argument("--run", required=True, type=Path)

    demo = subcommands.add_parser("demo", help="Generate a self-contained static HTML demo package")
    demo.add_argument("--benchmark", required=True, choices=available_benchmarks())
    demo.add_argument("--preset", default=None, help="Optional benchmark preset, e.g. demo")

    study = subcommands.add_parser("study", help="Run a local parameter study and candidate comparison")
    study.add_argument("--config", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            run_dir = run_benchmark(args.benchmark, preset=args.preset)
            print(run_dir)
            return 0
        if args.command == "verify":
            result = verify_run(args.run)
            print(result["status"])
            return 0 if result["status"] in {PASS_STATUS, *FAILURE_STATUSES} else 1
        if args.command == "report":
            report_path = generate_report(args.run)
            print(report_path)
            return 0
        if args.command == "demo":
            demo_path = generate_demo_package(args.benchmark, preset=args.preset)
            print(demo_path)
            return 0
        if args.command == "study":
            study_path = run_study(args.config)
            print(study_path)
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2
