from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from structure_optimizer.core.config import effective_load_cases, parse_config, validate_config
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.manufacturability import analyze_manufacturability
from structure_optimizer.core.manufacturing import evaluate_manufacturing_compliance
from structure_optimizer.core.mesh import StructuredMesh, create_structured_mesh
from structure_optimizer.core.run_store import load_density, read_json, write_json

PASS_STATUS = "passed"
FAILURE_STATUSES = {
    "invalid_config",
    "solver_failed",
    "singular_matrix",
    "volume_constraint_failed",
    "connectivity_failed",
    "design_space_constraint_failed",
    "stress_constraint_failed",
    "report_failed",
}


def verify_run(run_dir: Path | str) -> dict[str, Any]:
    """Re-run independent verification on an existing run directory.

    Reads ``input.json`` + ``density.npy``, replays FEM at baseline + candidate,
    checks all constraints, and writes ``verification.json`` + ``manufacturability.json``.
    Returns the verification dict; never raises on config / solver errors (writes
    them as status fields instead).
    """
    run_dir = Path(run_dir)
    try:
        raw = read_json(run_dir / "input.json")
        config = parse_config(raw)
        validate_config(config)
        mesh = create_structured_mesh(config)
        densities = load_density(run_dir)
    except Exception as exc:
        invalid_result: dict[str, Any] = {"status": "invalid_config", "error": str(exc)}
        write_json(run_dir / "verification.json", invalid_result)
        return invalid_result

    try:
        baseline_densities = np.ones(mesh.elements.shape[0], dtype=float)
        baseline_densities[mesh.frozen_solid_mask] = 1.0
        baseline_densities[mesh.void_mask] = config.optimization.min_density
        baseline, baseline_load_cases = _solve_load_case_metrics(config, mesh, baseline_densities)
        candidate, candidate_load_cases = _solve_load_case_metrics(config, mesh, densities)
    except SolverError as exc:
        status = "singular_matrix" if str(exc) == "singular_matrix" else "solver_failed"
        solver_failure: dict[str, Any] = {"status": status, "error": str(exc)}
        write_json(run_dir / "verification.json", solver_failure)
        return solver_failure

    active_volume = _active_volume(mesh, densities)
    volume_ok = active_volume <= config.optimization.volume_fraction + 0.02
    connectivity_ok = _connectivity_ok(config, mesh, densities)
    frozen_ok = _frozen_solid_ok(mesh, densities)
    void_ok = _void_ok(config, mesh, densities)
    stress_ok, stress_value = _check_stress_constraint(config, mesh, densities)
    manufacturability = analyze_manufacturability(config, mesh, densities)
    manufacturing_compliance = evaluate_manufacturing_compliance(config, mesh, densities)
    if not frozen_ok or not void_ok:
        status = "design_space_constraint_failed"
    elif not volume_ok:
        status = "volume_constraint_failed"
    elif not connectivity_ok:
        status = "connectivity_failed"
    elif not stress_ok:
        status = "stress_constraint_failed"
    else:
        status = PASS_STATUS
    constraints = _constraint_records(config, active_volume, volume_ok, connectivity_ok, frozen_ok, void_ok)
    constraints.extend(_manufacturing_constraint_records(manufacturing_compliance))
    if config.stress_constraint.enabled:
        constraints.append(_stress_constraint_record(config, stress_ok, stress_value))
    n_cases = len(effective_load_cases(config))
    objective_name = f"{config.optimization.case_aggregator}_compliance" if n_cases > 1 else "compliance"

    result = {
        "status": status,
        "volume_fraction_ok": volume_ok,
        "connectivity_ok": connectivity_ok,
        "frozen_solid_ok": frozen_ok,
        "void_regions_ok": void_ok,
        "target_volume_fraction": config.optimization.volume_fraction,
        "actual_volume_fraction": active_volume,
        "objective": {
            "name": objective_name,
            "role": "objective",
            "sense": "minimize",
            "value": candidate["compliance"],
            "source": "independent_verification",
        },
        "responses": _response_records(candidate),
        "constraints": constraints,
        "load_cases": {
            "baseline": baseline_load_cases,
            "candidate": candidate_load_cases,
        },
        "baseline": baseline,
        "candidate": candidate,
        "manufacturability": manufacturability,
        "manufacturing_compliance": manufacturing_compliance,
        "limitations": "2D/2.5D SIMP results are optimization candidates and require engineering review before production use.",
    }
    write_json(run_dir / "verification.json", result)
    write_json(run_dir / "manufacturability.json", manufacturability)
    return result


def _active_volume(mesh: StructuredMesh, densities: np.ndarray) -> float:
    active_count = max(1, int(np.count_nonzero(mesh.design_mask)))
    return float(np.sum(densities[mesh.design_mask]) / active_count)


def _connectivity_ok(config, mesh: StructuredMesh, densities: np.ndarray) -> bool:
    solid = (densities >= max(0.05, config.optimization.min_density)) & ~mesh.void_mask
    node_to_elements: dict[int, set[int]] = {}
    for element_id, nodes in enumerate(mesh.elements):
        if not solid[element_id]:
            continue
        for node in nodes:
            node_to_elements.setdefault(int(node), set()).add(element_id)

    load_records = [load for load_case in effective_load_cases(config) for load in load_case.loads]
    load_elements = _elements_for_records(mesh, load_records, node_to_elements)
    fixed_elements = _elements_for_records(mesh, config.boundary_conditions, node_to_elements)
    if not load_elements or not fixed_elements:
        return False

    visited = set(load_elements)
    queue = list(load_elements)
    while queue:
        current = queue.pop(0)
        if current in fixed_elements:
            return True
        cx, cy = mesh.element_grid_index(current)
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < mesh.nelx and 0 <= ny < mesh.nely:
                neighbor = mesh.element_index(nx, ny)
                if solid[neighbor] and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
    return False


def _elements_for_records(mesh: StructuredMesh, records: list[dict], node_to_elements: dict[int, set[int]]) -> set[int]:
    elements: set[int] = set()
    for record in records:
        for node in mesh.selector_nodes(record["selector"]):
            elements.update(node_to_elements.get(node, set()))
    return elements


def _solve_load_case_metrics(
    config, mesh: StructuredMesh, densities: np.ndarray
) -> tuple[dict[str, float], dict[str, dict]]:
    from structure_optimizer.core.objectives import aggregate as _agg
    from structure_optimizer.core.objectives import solve_all_cases

    load_cases = effective_load_cases(config)
    cases = solve_all_cases(config, mesh, densities, load_cases)
    by_case: dict[str, dict] = {}
    for case in cases:
        by_case[case.name] = {"weight": case.weight, **_analysis_metrics(case.result)}
    aggregated = _agg(config.optimization.case_aggregator, cases)
    aggregate_metrics = {
        "mass": aggregated.mass,
        "compliance": aggregated.compliance,
        "max_displacement": aggregated.max_displacement,
        "max_stress": aggregated.max_stress,
        "aggregator": config.optimization.case_aggregator,
    }
    return aggregate_metrics, by_case


def _analysis_metrics(analysis) -> dict[str, float]:
    return {
        "mass": analysis.mass,
        "compliance": analysis.compliance,
        "max_displacement": analysis.max_displacement,
        "max_stress": analysis.max_stress,
    }


def _check_stress_constraint(config, mesh: StructuredMesh, densities: np.ndarray) -> tuple[bool, float | None]:
    """Evaluate the stress constraint (if enabled). Returns (ok, aggregated_value)."""
    if not config.stress_constraint.enabled:
        return True, None
    from structure_optimizer.core.objectives import solve_and_aggregate
    from structure_optimizer.core.stress import aggregate_stress, element_von_mises_stresses

    load_cases = effective_load_cases(config)
    aggregated = solve_and_aggregate(config, mesh, densities, load_cases, config.optimization.case_aggregator)
    stresses = element_von_mises_stresses(config, mesh, aggregated.displacements)
    mask = densities >= config.stress_constraint.density_threshold
    value = aggregate_stress(stresses, config.stress_constraint.aggregation, config.stress_constraint.p, mask)
    return value <= config.stress_constraint.limit, value


def _stress_constraint_record(config, stress_ok: bool, stress_value: float | None) -> dict[str, Any]:
    return {
        "name": "stress_constraint",
        "value": stress_value,
        "limit": config.stress_constraint.limit,
        "unit": f"{config.stress_constraint.aggregation}_stress (p={config.stress_constraint.p})",
        "source": "independent_verification",
        "status": "passed" if stress_ok else "failed",
    }


def _frozen_solid_ok(mesh: StructuredMesh, densities: np.ndarray) -> bool:
    if not np.any(mesh.frozen_solid_mask):
        return True
    return bool(np.all(densities[mesh.frozen_solid_mask] >= 0.999))


def _void_ok(config, mesh: StructuredMesh, densities: np.ndarray) -> bool:
    if not np.any(mesh.void_mask):
        return True
    return bool(np.all(densities[mesh.void_mask] <= config.optimization.min_density + 1e-12))


def _constraint_records(
    config,
    active_volume: float,
    volume_ok: bool,
    connectivity_ok: bool,
    frozen_ok: bool,
    void_ok: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "volume_fraction",
            "value": active_volume,
            "limit": config.optimization.volume_fraction + 0.02,
            "unit": "ratio",
            "source": "independent_verification",
            "status": "passed" if volume_ok else "failed",
        },
        {
            "name": "load_to_support_connectivity",
            "value": connectivity_ok,
            "limit": True,
            "unit": "boolean",
            "source": "independent_verification",
            "status": "passed" if connectivity_ok else "failed",
        },
        {
            "name": "frozen_solid_regions",
            "value": frozen_ok,
            "limit": True,
            "unit": "boolean",
            "source": "independent_verification",
            "status": "passed" if frozen_ok else "failed",
        },
        {
            "name": "void_regions",
            "value": void_ok,
            "limit": True,
            "unit": "boolean",
            "source": "independent_verification",
            "status": "passed" if void_ok else "failed",
        },
    ]


def _manufacturing_constraint_records(report: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name, payload in report.items():
        status = str(payload.get("status", "missing"))
        if status == "missing":
            continue
        if name == "symmetry_compliance":
            records.append(
                {
                    "name": "symmetry_compliance",
                    "value": payload.get("residual"),
                    "limit": payload.get("tolerance"),
                    "unit": "density_residual",
                    "source": "manufacturing_projection",
                    "status": status,
                }
            )
        elif name == "extrusion_compliance":
            records.append(
                {
                    "name": "extrusion_compliance",
                    "value": payload.get("residual"),
                    "limit": payload.get("tolerance"),
                    "unit": "density_residual",
                    "source": "manufacturing_projection",
                    "status": status,
                }
            )
        elif name == "min_member_size_compliance":
            records.append(
                {
                    "name": "min_member_size_compliance",
                    "value": payload.get("enforced_length"),
                    "limit": payload.get("min_member_size"),
                    "unit": "model_length",
                    "source": "filter_radius_heuristic",
                    "status": status,
                }
            )
    return records


def _response_records(candidate: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {"name": "mass", "value": candidate["mass"], "unit": "model_mass", "source": "independent_verification"},
        {
            "name": "compliance",
            "value": candidate["compliance"],
            "unit": "force_length",
            "source": "independent_verification",
        },
        {
            "name": "max_displacement",
            "value": candidate["max_displacement"],
            "unit": "model_length",
            "source": "independent_verification",
        },
        {
            "name": "max_stress",
            "value": candidate["max_stress"],
            "unit": "model_stress",
            "source": "independent_verification",
        },
    ]
