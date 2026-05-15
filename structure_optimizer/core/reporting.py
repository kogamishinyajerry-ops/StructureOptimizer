from __future__ import annotations

from pathlib import Path

from structure_optimizer.core.config import parse_config, validate_config
from structure_optimizer.core.run_store import input_hash, load_metrics, read_json, write_json
from structure_optimizer.core.verification import verify_run


def generate_report(run_dir: Path | str) -> Path:
    run_dir = Path(run_dir)
    config = parse_config(read_json(run_dir / "input.json"))
    validate_config(config)
    metrics = load_metrics(run_dir)
    verification_path = run_dir / "verification.json"
    verification = read_json(verification_path) if verification_path.exists() else verify_run(run_dir)
    summary = read_json(run_dir / "summary.json") if (run_dir / "summary.json").exists() else {}

    lines = [
        f"# StructureOptimizer Run Report: {config.name}",
        "",
        "## Run",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Input hash: `{input_hash(config)}`",
        f"- Status: `{summary.get('status', 'unknown')}`",
        f"- Stop reason: `{summary.get('stop_reason', 'unknown')}`",
        "",
        "## Configuration",
        "",
        f"- Dimension: `{config.dimension}`",
        f"- Units: `{config.units}`",
        f"- Mesh: `{config.mesh.nelx} x {config.mesh.nely}` structured quadrilateral elements",
        f"- Thickness: `{config.thickness}`",
        f"- Young modulus: `{config.material.young_modulus}`",
        f"- Poisson ratio: `{config.material.poisson_ratio}`",
        f"- Density: `{config.material.density}`",
        f"- Objective: `{config.optimization.objective}`",
        f"- Target volume fraction: `{config.optimization.volume_fraction}`",
        f"- Penalty: `{config.optimization.penalty}`",
        f"- Filter radius: `{config.optimization.filter_radius}`",
        f"- Max iterations: `{config.optimization.max_iterations}`",
        "",
        "## Objective",
        "",
        _objective_table(verification.get("objective", {})),
        "",
        "## Responses",
        "",
        _records_table(verification.get("responses", []), ["name", "value", "unit", "source"]),
        "",
        "## Constraints",
        "",
        _records_table(verification.get("constraints", []), ["name", "value", "limit", "unit", "source", "status"]),
        "",
        "## Baseline Metrics",
        "",
        _metric_table(verification.get("baseline", {})),
        "",
        "## Optimization Iteration Metrics",
        "",
        _iteration_table(metrics),
        "",
        "## Independent Verification Metrics",
        "",
        f"- Verification status: `{verification.get('status', 'missing')}`",
        f"- Volume fraction OK: `{verification.get('volume_fraction_ok', False)}`",
        f"- Connectivity OK: `{verification.get('connectivity_ok', False)}`",
        f"- Actual volume fraction: `{verification.get('actual_volume_fraction', 'n/a')}`",
        "",
        _metric_table(verification.get("candidate", {})),
        "",
        "## Load Case Verification Metrics",
        "",
        _load_case_table(verification.get("load_cases", {}).get("candidate", {})),
        "",
        "## Manufacturability Warnings",
        "",
        _manufacturability_table(verification.get("manufacturability", {})),
        "",
        "## Output Files",
        "",
        "- `input.json`: resolved input configuration snapshot",
        "- `metrics.csv`: per-iteration optimization metrics",
        "- `baseline.png`: baseline design domain visualization",
        "- `loadcase.png`: load and constraint visualization",
        "- `optimization.gif`: animated density evolution",
        "- `density.npy`: final density field",
        "- `density.png`: final density visualization",
        "- `convergence.png`: compliance convergence visualization",
        "- `verification.json`: independent verification result",
        "- `manufacturability.json`: coarse manufacturability warning result",
        "- `report.md`: this report",
        "",
        "![density](density.png)",
        "",
        "![convergence](convergence.png)",
        "",
        "## Limitations",
        "",
        "This MVP uses 2D/2.5D linear-elastic SIMP benchmark models. Results are optimization candidates only and require engineering review, high-fidelity validation, manufacturability checks, and physical testing before production use.",
        "",
    ]
    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(lines))
    if summary:
        summary["report"] = str(report_path)
        write_json(run_dir / "summary.json", summary)
    return report_path


def _metric_table(metrics: dict) -> str:
    if not metrics:
        return "_No metrics available._"
    return "\n".join(
        [
            "| metric | value |",
            "|---|---:|",
            f"| mass | {metrics.get('mass', 'n/a')} |",
            f"| compliance | {metrics.get('compliance', 'n/a')} |",
            f"| max_displacement | {metrics.get('max_displacement', 'n/a')} |",
            f"| max_stress | {metrics.get('max_stress', 'n/a')} |",
        ]
    )


def _objective_table(objective: dict) -> str:
    if not objective:
        return "_No objective available._"
    return "\n".join(
        [
            "| objective | sense | value | source |",
            "|---|---|---:|---|",
            f"| {objective.get('name', 'n/a')} | {objective.get('sense', 'n/a')} | {objective.get('value', 'n/a')} | {objective.get('source', 'n/a')} |",
        ]
    )


def _records_table(records: list[dict], columns: list[str]) -> str:
    if not records:
        return "_No records available._"
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for record in records:
        rows.append("| " + " | ".join(str(record.get(column, "n/a")) for column in columns) + " |")
    return "\n".join(rows)


def _load_case_table(load_cases: dict) -> str:
    if not load_cases:
        return "_No load case metrics available._"
    rows = ["| load_case | weight | compliance | max_displacement | max_stress |", "|---|---:|---:|---:|---:|"]
    for name, metrics in load_cases.items():
        rows.append(
            f"| {name} | {metrics.get('weight', 'n/a')} | {metrics.get('compliance', 'n/a')} | {metrics.get('max_displacement', 'n/a')} | {metrics.get('max_stress', 'n/a')} |"
        )
    return "\n".join(rows)


def _iteration_table(metrics: list[dict]) -> str:
    if not metrics:
        return "_No iteration metrics available._"
    selected = metrics[:3]
    if len(metrics) > 6:
        selected = metrics[:3] + metrics[-3:]
    elif len(metrics) > 3:
        selected = metrics
    rows = ["| iteration | compliance | volume_fraction | change | max_displacement |", "|---:|---:|---:|---:|---:|"]
    for metric in selected:
        rows.append(
            f"| {metric['iteration']} | {metric['compliance']} | {metric['volume_fraction']} | {metric['change']} | {metric['max_displacement']} |"
        )
    return "\n".join(rows)


def _manufacturability_table(manufacturability: dict) -> str:
    if not manufacturability:
        return "_No manufacturability checks available._"
    rows = ["| check | status | detail |", "|---|---|---|"]
    for name, check in manufacturability.get("checks", {}).items():
        detail = ", ".join(f"{key}={value}" for key, value in check.items() if key not in {"status", "rule"})
        rows.append(f"| {name} | `{check.get('status', 'unknown')}` | {detail} |")
    rows.append(f"| overall | `{manufacturability.get('status', 'unknown')}` | v0.2 coarse warning checks |")
    return "\n".join(rows)
