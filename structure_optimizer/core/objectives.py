"""Multi-load-case compliance aggregation strategies (v1.5 / Wave E).

Three aggregator modes exposed via ``OptimizationConfig.case_aggregator``:

- ``weighted_sum`` (default): each case contributes ``weight / Σweights`` to
  the total compliance; ``element_strain_energy`` is the corresponding linear
  combination. Matches v1.4.0 behavior exactly when invoked with default
  config (legacy ``loads`` is wrapped into one ``"primary"`` case with
  weight 1.0 so the weighted_sum collapses to single-case compliance).
- ``average``: ignores user-supplied weights, treats all cases equally
  (equivalent to ``weighted_sum`` with all weights = 1). Useful when you
  don't want to hand-tune weights.
- ``worst_case``: takes the max compliance over cases; element sensitivities
  come from the argmax case alone (subgradient at the argmax). Produces
  designs robust against the harshest load.

Mathematical sketch::

    weighted_sum:  c = Σ (w_k / Σw) c_k(ρ)
                   ∂c/∂ρ_e = Σ (w_k / Σw) ∂c_k/∂ρ_e

    average:       c = (1/K) Σ c_k(ρ)
                   ∂c/∂ρ_e = (1/K) Σ ∂c_k/∂ρ_e

    worst_case:    c = max_k c_k(ρ)
                   ∂c/∂ρ_e ≈ ∂c_{k*}/∂ρ_e   where k* = argmax_k c_k

The worst-case "gradient" is a subgradient (non-smooth at argmax ties); in
practice we take the argmax case's element_strain_energy as a proxy for the
descent direction. References: Bendsøe & Sigmund 2003 §1.4 (robust formulation),
Diaz & Bendsøe 1992 (multi-load topology).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig, LoadCaseConfig
from structure_optimizer.core.fem2d import FEMResult, solve_linear_elastic
from structure_optimizer.core.mesh import StructuredMesh

AGGREGATORS: frozenset[str] = frozenset({"weighted_sum", "average", "worst_case"})


@dataclass(frozen=True)
class CaseResult:
    """Solution + metrics for a single load case (raw, pre-aggregation)."""

    name: str
    weight: float
    result: FEMResult


def solve_all_cases(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    load_cases: Sequence[LoadCaseConfig],
) -> list[CaseResult]:
    """Solve every load case independently. Caller chooses how to aggregate."""
    return [
        CaseResult(
            name=lc.name,
            weight=lc.weight,
            result=solve_linear_elastic(config, mesh, densities, loads=lc.loads),
        )
        for lc in load_cases
    ]


def aggregate(aggregator: str, cases: Sequence[CaseResult]) -> FEMResult:
    """Combine per-case ``FEMResult``s into one aggregated ``FEMResult``.

    ``compliance`` and ``element_strain_energy`` reflect the chosen strategy;
    ``max_displacement`` / ``max_stress`` always take the worst over cases;
    ``displacements`` and ``mass`` come from the first case (single
    representative; use ``solve_all_cases`` to inspect per-case fields).
    """
    if not cases:
        raise ValueError("aggregate requires at least one CaseResult")
    if aggregator not in AGGREGATORS:
        raise ValueError(f"unknown aggregator '{aggregator}'; expected one of {sorted(AGGREGATORS)}")

    first = cases[0].result
    max_disp = max(c.result.max_displacement for c in cases)
    max_stress = max(c.result.max_stress for c in cases)

    if aggregator == "worst_case":
        compliances = [c.result.compliance for c in cases]
        argmax_idx = int(np.argmax(compliances))
        argmax_case = cases[argmax_idx]
        return FEMResult(
            displacements=argmax_case.result.displacements,
            compliance=float(argmax_case.result.compliance),
            max_displacement=float(max_disp),
            max_stress=float(max_stress),
            mass=first.mass,
            element_strain_energy=argmax_case.result.element_strain_energy.copy(),
        )

    # weighted_sum or average
    n_elem = first.element_strain_energy.shape[0]
    weighted_energy = np.zeros(n_elem, dtype=float)
    weighted_compliance = 0.0

    if aggregator == "average":
        weights = np.full(len(cases), 1.0 / len(cases))
    else:  # weighted_sum
        total = sum(c.weight for c in cases)
        weights = np.array([c.weight / total for c in cases])

    for w, case in zip(weights, cases, strict=True):
        weighted_energy += w * case.result.element_strain_energy
        weighted_compliance += w * case.result.compliance

    return FEMResult(
        displacements=first.displacements,
        compliance=float(weighted_compliance),
        max_displacement=float(max_disp),
        max_stress=float(max_stress),
        mass=first.mass,
        element_strain_energy=weighted_energy,
    )


def solve_and_aggregate(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    load_cases: Sequence[LoadCaseConfig],
    aggregator: str,
) -> FEMResult:
    """Solve every case + aggregate. Convenience wrapper over solve_all_cases + aggregate."""
    return aggregate(aggregator, solve_all_cases(config, mesh, densities, load_cases))
