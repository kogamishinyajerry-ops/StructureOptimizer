"""Wave QQ (v7, D046): NSGA-III directly on the density field.

v5 Wave DD (``pareto_nsga``) deliberately ran NSGA on **proxy** problems
(material assignment, sizing) or as a **post-processor** of pre-computed
single-objective solutions, because "each genome = whole density field" was
flagged as prohibitively expensive. D037 + D023's reopening criterion named the
upgrade: a genetic multi-objective driver whose decision vector *is* the density
field. v7 Wave QQ delivers that driver for the (compliance, volume) trade-off.

It is honestly a *gradient-free* search: it does not beat gradient SIMP (verified
— the gradient-SIMP point is never dominated by the evolved front). Its value is
a verifiable Pareto front of real FEM-evaluated density fields, with a
monotonically improving hypervolume archive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.pareto_nsga import (
    _generate_offspring,
    _niching_select,
    _non_dominated_sort,
    das_dennis_reference_points,
)


@dataclass
class MultiObjectiveTOResult:
    """Output of a density-field NSGA-III run.

    Attributes:
        front_objectives: (n_front, n_obj) Pareto-optimal objective values
        front_densities:  (n_front, n_elem) full density fields (void floor applied)
        hv_history:       per-generation dominated hypervolume of the cumulative
                          non-dominated archive (non-decreasing by construction)
        reference_point:  (n_obj,) fixed reference used for the hypervolume
        n_front:          count of Pareto-optimal points
    """

    front_objectives: np.ndarray
    front_densities: np.ndarray
    hv_history: list[float]
    reference_point: np.ndarray
    n_front: int


def hypervolume_2d(points: np.ndarray, reference: np.ndarray) -> float:
    """Exact dominated hypervolume (area) of a 2-objective **minimisation** set.

    Only points strictly dominating ``reference`` contribute. The dominated
    region is the union of rectangles [fᵢ, ref]; for a 2-D front it equals

        Σ_i (ref₀ − f1_i) · (prev_f2 − f2_i)

    where points are swept in ascending f1 (so f2 descends along the
    non-dominated staircase) and ``prev_f2`` starts at ref₁.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    ref = np.asarray(reference, dtype=float).reshape(2)
    inside = pts[(pts[:, 0] < ref[0]) & (pts[:, 1] < ref[1])]
    if inside.shape[0] == 0:
        return 0.0
    # Keep the non-dominated staircase, sorted by f1 ascending.
    order = np.lexsort((inside[:, 1], inside[:, 0]))
    inside = inside[order]
    staircase = []
    best_f2 = np.inf
    for f1, f2 in inside:
        if f2 < best_f2:
            staircase.append((f1, f2))
            best_f2 = f2
    hv = 0.0
    prev_f2 = ref[1]
    for f1, f2 in staircase:
        hv += (ref[0] - f1) * (prev_f2 - f2)
        prev_f2 = f2
    return float(hv)


def _nondominated(objs: np.ndarray) -> np.ndarray:
    """Boolean mask of the non-dominated rows of a minimisation objective set."""
    n = objs.shape[0]
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        for j in range(n):
            if i == j:
                continue
            # j dominates i?
            if np.all(objs[j] <= objs[i]) and np.any(objs[j] < objs[i]):
                keep[i] = False
                break
    return keep


def multi_objective_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    n_generations: int = 12,
    population_size: int = 16,
    n_divisions: int = 8,
    crossover_eta: float = 15.0,
    mutation_prob: float | None = None,
    rng_seed: int = 0,
    seed_genomes: list[np.ndarray] | None = None,
) -> MultiObjectiveTOResult:
    """NSGA-III over density fields, minimising (compliance, volume fraction).

    Each genome is the density of the design elements in [0, 1]; the void floor
    is applied before the FEM solve. Returns the final Pareto front plus the
    per-generation hypervolume of the cumulative non-dominated archive.

    ``seed_genomes`` (Wave WW) optionally warm-starts the initial population:
    each provided design-element genome replaces a random member, so
    gradient-SIMP optima can be injected (see ``gradient_seeded_multi_objective_to``).
    """
    if n_generations < 1:
        raise SolverError("mo_to_n_generations_must_be_positive")
    if population_size < 4:
        raise SolverError("mo_to_population_too_small")

    design = mesh.design_mask
    n_design = int(np.count_nonzero(design))
    if n_design < 1:
        raise SolverError("mo_to_no_design_elements")
    n_elem = mesh.elements.shape[0]
    n_obj = 2
    if mutation_prob is None:
        mutation_prob = 1.0 / n_design

    def _full_density(genome: np.ndarray) -> np.ndarray:
        rho = np.zeros(n_elem)
        rho[design] = np.clip(genome, 0.0, 1.0)
        return rho

    def eval_fn(genome: np.ndarray) -> tuple[float, float]:
        rho = _full_density(genome)
        c = float(solve_linear_elastic(config, mesh, rho).compliance)
        v = float(np.mean(np.clip(genome, 0.0, 1.0)))
        return (c, v)

    rng = np.random.default_rng(rng_seed)
    bl = np.zeros(n_design)
    bu = np.ones(n_design)
    pop = rng.uniform(bl, bu, size=(population_size, n_design))
    if seed_genomes:
        for k, g in enumerate(seed_genomes[:population_size]):
            g = np.asarray(g, dtype=float).reshape(-1)
            if g.size != n_design:
                raise SolverError("mo_to_seed_genome_shape_mismatch")
            pop[k] = np.clip(g, 0.0, 1.0)
    objs = np.array([eval_fn(x) for x in pop])

    # Fixed hypervolume reference: worst stiffness (all-min-density) + full volume,
    # with a small margin so every encountered point strictly dominates it.
    c_worst = float(solve_linear_elastic(config, mesh, _full_density(np.zeros(n_design))).compliance)
    reference = np.array([c_worst * 1.05, 1.05])

    ref_dirs = das_dennis_reference_points(n_obj, n_divisions)
    archive_objs = objs[_nondominated(objs)]
    hv_history = [hypervolume_2d(archive_objs, reference)]

    for _gen in range(n_generations):
        offspring = _generate_offspring(pop, bl, bu, crossover_eta, mutation_prob, rng)
        off_objs = np.array([eval_fn(x) for x in offspring])
        combined = np.vstack([pop, offspring])
        combined_objs = np.vstack([objs, off_objs])

        fronts = _non_dominated_sort(combined_objs)
        selected: list[int] = []
        for front in fronts:
            if len(selected) + len(front) <= population_size:
                selected.extend(front.tolist())
                continue
            n_needed = population_size - len(selected)
            picked = _niching_select(
                front, np.array(selected, dtype=int), combined_objs, ref_dirs, n_needed, rng
            )
            selected.extend(picked)
            break
        sel = np.array(selected, dtype=int)
        pop = combined[sel]
        objs = combined_objs[sel]

        # Cumulative archive → monotone hypervolume.
        merged = np.vstack([archive_objs, objs])
        archive_objs = merged[_nondominated(merged)]
        hv_history.append(hypervolume_2d(archive_objs, reference))

    final_mask = _non_dominated_sort(objs)[0]
    front_obj = objs[final_mask]
    order = np.argsort(front_obj[:, 0])
    front_obj = front_obj[order]
    front_dec = pop[final_mask][order]
    front_dens = np.array([_full_density(g) for g in front_dec])
    return MultiObjectiveTOResult(
        front_objectives=front_obj,
        front_densities=front_dens,
        hv_history=hv_history,
        reference_point=reference,
        n_front=front_obj.shape[0],
    )


def gradient_seeded_multi_objective_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    seed_volume_fractions=(0.2, 0.35, 0.5, 0.65, 0.8),
    **kwargs,
) -> MultiObjectiveTOResult:
    """NSGA-III warm-started with gradient-SIMP optima (Wave WW, D052).

    Runs `run_simp` at each volume fraction in ``seed_volume_fractions`` and
    injects those (gradient-optimal) density fields into the initial population
    via ``seed_genomes``. D046's reopening criterion: a gradient-seeded initial
    population for a sharper front than random initialisation at the same budget.
    """
    from dataclasses import replace

    from structure_optimizer.core.simp import run_simp

    design = mesh.design_mask
    seeds: list[np.ndarray] = []
    for vf in seed_volume_fractions:
        cfg = replace(config, optimization=replace(config.optimization, volume_fraction=float(vf)))
        seeds.append(run_simp(cfg, mesh).densities[design])
    return multi_objective_to(config, mesh, seed_genomes=seeds, **kwargs)
