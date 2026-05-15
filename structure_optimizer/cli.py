from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from structure_optimizer.benchmarks.registry import available_benchmarks
from structure_optimizer.core.demo import generate_demo_package
from structure_optimizer.core.reporting import generate_report
from structure_optimizer.core.study import run_study
from structure_optimizer.core.verification import FAILURE_STATUSES, PASS_STATUS, verify_run
from structure_optimizer.core.workflow import run_benchmark


def _package_version() -> str:
    try:
        return version("structure-optimizer")
    except PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argparse parser (5 subcommands + --version + epilog examples)."""
    parser = argparse.ArgumentParser(
        prog="structure-optimizer",
        description=(
            "Local, verifiable 2D/2.5D structural optimization workbench. "
            "Generates SIMP optimization candidates with independent verification "
            "and static HTML review packages."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  structure-optimizer run --benchmark mbb_beam --preset smoke\n"
            "  structure-optimizer verify --run runs/mbb_beam/<run_id>\n"
            "  structure-optimizer demo --benchmark simple_bracket --preset demo\n"
            "  structure-optimizer study --config studies/simple_bracket_tradeoff.json\n"
            "\nDocs: README.md, docs/architecture.md, docs/tutorial.md"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"structure-optimizer {_package_version()}",
    )
    subcommands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = subcommands.add_parser(
        "run",
        help="Run a benchmark optimization",
        description="Run a SIMP topology optimization on a built-in benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  structure-optimizer run --benchmark mbb_beam --preset smoke\n"
            "Prints the run directory path to stdout on success."
        ),
    )
    run.add_argument("--benchmark", required=True, choices=available_benchmarks())
    run.add_argument("--preset", default=None, help="Optional benchmark preset, e.g. smoke")
    run.add_argument(
        "--algorithm",
        default=None,
        choices=["simp", "beso"],
        help="Override optimization algorithm (defaults to config value, usually 'simp')",
    )

    verify = subcommands.add_parser(
        "verify",
        help="Verify an existing run directory",
        description=(
            "Re-run independent verification on a previously-generated run "
            "directory. Returns one of: passed, invalid_config, "
            "solver_failed, singular_matrix, volume_constraint_failed, "
            "connectivity_failed, design_space_constraint_failed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  structure-optimizer verify --run runs/mbb_beam/20260516-180000-123456",
    )
    verify.add_argument("--run", required=True, type=Path)

    report = subcommands.add_parser(
        "report",
        help="Generate report.md for an existing run directory",
        description="Regenerate the engineering Markdown report from a run directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  structure-optimizer report --run runs/mbb_beam/<run_id>",
    )
    report.add_argument("--run", required=True, type=Path)

    demo = subcommands.add_parser(
        "demo",
        help="Generate a self-contained static HTML demo package",
        description=(
            "Run a benchmark and produce a Chinese-localized review HTML "
            "(demo.html) suitable for showing to non-technical reviewers."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  structure-optimizer demo --benchmark simple_bracket --preset demo",
    )
    demo.add_argument("--benchmark", required=True, choices=available_benchmarks())
    demo.add_argument("--preset", default=None, help="Optional benchmark preset, e.g. demo")

    export = subcommands.add_parser(
        "export",
        help="Export geometry from a run directory (SVG / DXF / STL)",
        description=(
            "Extract boundary segments from density.npy and write the geometry "
            "to SVG (vector 2D), DXF R12 (CAD line entities), or ASCII STL "
            "(2.5D extrusion prism mesh). Output path is `<run>/geometry.<ext>`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  structure-optimizer export --run runs/mbb_beam/<run_id> --format svg\n"
            "  structure-optimizer export --run runs/mbb_beam/<run_id> --format dxf\n"
            "  structure-optimizer export --run runs/mbb_beam/<run_id> --format stl --extrusion-depth 5"
        ),
    )
    export.add_argument("--run", required=True, type=Path)
    export.add_argument("--format", required=True, choices=["svg", "dxf", "stl"])
    export.add_argument("--threshold", default=0.5, type=float, help="Density threshold for solid (default 0.5)")
    export.add_argument(
        "--extrusion-depth", default=1.0, type=float, help="STL extrusion depth (model length, default 1.0)"
    )

    study = subcommands.add_parser(
        "study",
        help="Run a local parameter study and candidate comparison",
        description=(
            "Sweep a parameter grid (volume_fraction, filter_radius, "
            "load_weights), score every candidate, compute the Pareto "
            "front, and emit a candidate-comparison study.html."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  structure-optimizer study --config studies/simple_bracket_tradeoff.json",
    )
    study.add_argument("--config", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success, 1 on caught error, 2 on argparse error."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            run_dir = run_benchmark(args.benchmark, preset=args.preset, algorithm=args.algorithm)
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
        if args.command == "export":
            from structure_optimizer.core.config import parse_config, validate_config
            from structure_optimizer.core.geometry_export import (
                write_dxf,
                write_stl_extrusion,
                write_svg,
            )
            from structure_optimizer.core.mesh import create_structured_mesh
            from structure_optimizer.core.run_store import load_density, read_json

            run_dir = args.run
            config = parse_config(read_json(run_dir / "input.json"))
            validate_config(config)
            mesh = create_structured_mesh(config)
            densities = load_density(run_dir)
            out_path = run_dir / f"geometry.{args.format}"
            if args.format == "svg":
                write_svg(out_path, mesh, densities, threshold=args.threshold)
            elif args.format == "dxf":
                write_dxf(out_path, mesh, densities, threshold=args.threshold)
            elif args.format == "stl":
                write_stl_extrusion(
                    out_path, mesh, densities, extrusion_depth=args.extrusion_depth, threshold=args.threshold
                )
            print(out_path)
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2
