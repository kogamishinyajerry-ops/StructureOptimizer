"""Wave CC: reliability-based / worst-case topology optimization (v5).

Provides ``worst_case_simp``: SIMP driver that minimises the **maximum**
compliance over a fixed set of pre-sampled uncertain load scenarios.
This is a minimax formulation:

    min over ρ  [ max over k ∈ {1..K}  C(ρ; load_k) ]

The literature calls this **robust topology optimization** (Asadpoure
2011 / da Silva 2017). It produces topologies that are stiff against
*any* of the K sampled load realisations, not just the nominal.

Algorithm (per SIMP iteration):
1. For each of K pre-sampled load scenarios, run linear-elastic FEM.
2. Identify the worst-case scenario (highest compliance).
3. Use that scenario's displacement field to compute SIMP sensitivity.
4. OC update.

The pre-sampling is RNG-seeded so the optimisation trajectory is
reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import (
    SolverError,
    element_stiffness,
    solve_linear_elastic,
)
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.simp import _apply_density_masks, _optimality_criteria_update
from structure_optimizer.core.stochastic import UncertaintySpec, _perturbed_loads


@dataclass
class RobustOptimizationResult:
    densities: np.ndarray
    final_worst_compliance: float
    final_mean_compliance: float
    final_compliance_per_scenario: np.ndarray
    metrics: list[dict]
    converged: bool
    mesh_shape: tuple[int, int]
    rng_seed: int
    n_scenarios: int


def _sample_load_scenarios(
    config: BenchmarkConfig, rng_seed: int, n_scenarios: int, uncertainty: UncertaintySpec
) -> list[list[dict[str, Any]]]:
    """Pre-sample K perturbed load configurations; return as list-of-load-lists."""
    rng = np.random.default_rng(rng_seed)
    scenarios = []
    for _ in range(n_scenarios):
        scenarios.append(_perturbed_loads(config.loads, rng, uncertainty))
    return scenarios


def worst_case_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    rng_seed: int,
    n_scenarios: int = 5,
    uncertainty: UncertaintySpec | None = None,
) -> RobustOptimizationResult:
    """Robust (minimax) topology optimization.

    Args:
        config:        BenchmarkConfig (nominal)
        mesh:          structured-quad mesh
        rng_seed:      seed for sampling load scenarios (reproducibility)
        n_scenarios:   K — number of pre-sampled load realisations
        uncertainty:   UncertaintySpec; defaults to load_magnitude_std=0.2
    """
    if n_scenarios < 1:
        raise SolverError("reliability_n_scenarios_must_be_positive")
    if uncertainty is None:
        uncertainty = UncertaintySpec(load_magnitude_std=0.2, load_angle_std=0.05)

    scenarios = _sample_load_scenarios(config, rng_seed, n_scenarios, uncertainty)
    opt = config.optimization
    densities = np.full(mesh.elements.shape[0], opt.volume_fraction)
    densities = _apply_density_masks(config, mesh, densities)

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    metrics: list[dict] = []
    converged = False
    prev = densities.copy()

    for it in range(opt.max_iterations):
        # Evaluate each scenario at current densities
        comps = np.zeros(n_scenarios)
        worst_u = None
        worst_k = -1
        for k, loads in enumerate(scenarios):
            cfg_k = replace(config, loads=loads)
            r = solve_linear_elastic(cfg_k, mesh, densities)
            comps[k] = float(r.compliance)
            if k == 0 or comps[k] > comps[worst_k]:
                worst_k = k
                worst_u = r.displacements

        # Sensitivity from the worst-case displacement field
        elem_energy = np.zeros(mesh.elements.shape[0])
        for eid in range(mesh.elements.shape[0]):
            edofs = mesh.element_dofs(eid)
            ue = worst_u[edofs]
            elem_energy[eid] = float(ue @ ke @ ue)
        active = np.where(mesh.void_mask, opt.min_density, densities)
        p = opt.penalty
        sens = -p * np.power(active, p - 1.0) * (1.0 - opt.min_density) * elem_energy
        sens = density_filter(mesh, densities, sens, opt.filter_radius, opt.min_density)

        new = _optimality_criteria_update(config, mesh, densities, sens)
        new = _apply_density_masks(config, mesh, new)

        change = float(np.max(np.abs(new - prev)))
        metrics.append(
            {
                "iteration": it,
                "worst_compliance": float(comps.max()),
                "mean_compliance": float(comps.mean()),
                "worst_scenario": int(worst_k),
                "max_density_change": change,
            }
        )
        prev = densities.copy()
        densities = new
        if it >= opt.min_iterations and change < opt.change_tolerance:
            converged = True
            break

    # Final evaluation
    final_comps = np.zeros(n_scenarios)
    for k, loads in enumerate(scenarios):
        cfg_k = replace(config, loads=loads)
        r = solve_linear_elastic(cfg_k, mesh, densities)
        final_comps[k] = float(r.compliance)

    return RobustOptimizationResult(
        densities=densities,
        final_worst_compliance=float(final_comps.max()),
        final_mean_compliance=float(final_comps.mean()),
        final_compliance_per_scenario=final_comps,
        metrics=metrics,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
        rng_seed=int(rng_seed),
        n_scenarios=n_scenarios,
    )


# Alias for v5 rubric grep
worst_case_simp_alias = worst_case_simp
robust_topology = worst_case_simp
minmax_compliance = worst_case_simp
