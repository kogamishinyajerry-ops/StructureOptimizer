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


def hypervolume_nd(points: np.ndarray, reference: np.ndarray) -> float:
    """Exact dominated hypervolume of an n-objective **minimisation** set, via
    Hypervolume by Slicing Objectives (HSO).

    Reduces to ``hypervolume_2d`` at n=2 and to ``ref₀ − min`` at n=1. Only points
    strictly dominating ``reference`` contribute. HSO slices along the last
    objective: in each slab between consecutive slice levels, the points reaching
    that depth contribute the (n−1)-D hypervolume of their projection times the
    slab thickness — recursing until the 2-D base case (Wave EEE, D060).
    """
    ref = np.asarray(reference, dtype=float).reshape(-1)
    d = ref.shape[0]
    pts = np.asarray(points, dtype=float).reshape(-1, d)
    if pts.shape[0] == 0:
        return 0.0
    inside = pts[np.all(pts < ref, axis=1)]
    if inside.shape[0] == 0:
        return 0.0
    if d == 1:
        return float(ref[0] - inside[:, 0].min())
    if d == 2:
        return hypervolume_2d(inside, ref)
    inside = inside[_nondominated(inside)]
    inside = inside[np.argsort(inside[:, -1])]
    levels = [*inside[:, -1].tolist(), float(ref[-1])]
    vol = 0.0
    for j in range(inside.shape[0]):
        depth = levels[j + 1] - levels[j]
        if depth <= 0:
            continue
        vol += depth * hypervolume_nd(inside[: j + 1, :-1], ref[:-1])
    return float(vol)


def igd_plus(front: np.ndarray, reference_front: np.ndarray) -> float:
    """Inverted Generational Distance **plus** (IGD⁺) of an obtained front
    against a reference Pareto front, for **minimisation** (Wave MMM, D068).

    For each reference point ``z`` the modified distance to an obtained point
    ``a`` counts only the objectives where ``a`` is *worse* than ``z``::

        d⁺(z, a) = sqrt( Σ_i max(a_i − z_i, 0)² )

    and ``IGD⁺ = mean_z min_a d⁺(z, a)``. Unlike plain IGD this is weakly
    Pareto-compliant: a front that dominates the reference scores 0, and IGD⁺ is
    non-increasing as the obtained front improves. Lower is better; 0 ⇔ the
    obtained front weakly dominates every reference point.
    """
    a = np.asarray(front, dtype=float)
    z = np.asarray(reference_front, dtype=float)
    if a.ndim != 2 or z.ndim != 2:
        raise SolverError("igd_plus_expects_2d_arrays")
    if a.shape[0] == 0:
        raise SolverError("igd_plus_empty_front")
    if a.shape[1] != z.shape[1]:
        raise SolverError("igd_plus_dim_mismatch")
    total = 0.0
    for zi in z:
        # d⁺ from every obtained point a to this reference point zi
        excess = np.maximum(a - zi, 0.0)
        d_plus = np.sqrt(np.sum(excess**2, axis=1))
        total += float(d_plus.min())
    return total / z.shape[0]


def nsga3_density_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    load_cases: list[list[dict]],
    n_generations: int = 12,
    population_size: int = 16,
    n_divisions: int = 8,
    crossover_eta: float = 15.0,
    mutation_prob: float | None = None,
    rng_seed: int = 0,
    seed_genomes: list[np.ndarray] | None = None,
) -> MultiObjectiveTOResult:
    """The single generalised NSGA-III density-field driver (Wave MMM, D068).

    Minimises ``(C_1, …, C_L, volume)`` where ``C_j`` is the compliance under
    load case ``load_cases[j]`` and ``L = len(load_cases)`` (so ``n_obj = L+1``).
    This **subsumes** both :func:`multi_objective_to` (a single load case → 2
    objectives) and :func:`multi_load_case_to` (≥2 load cases → ≥3 objectives),
    which now delegate here — D060's reopening criterion was *one generalised
    nsga3_density_to* rather than two parallel loops.

    The per-generation cumulative-archive hypervolume uses the exact 2-D
    :func:`hypervolume_2d` when ``n_obj == 2`` and the n-D :func:`hypervolume_nd`
    otherwise, so the refactor is **bit-identical** to the two pre-refactor
    drivers (verified by golden test). All RNG consumption (uniform init →
    per-generation offspring → niching) is unchanged.
    """
    from dataclasses import replace

    if n_generations < 1:
        raise SolverError("mo_to_n_generations_must_be_positive")
    if population_size < 4:
        raise SolverError("mo_to_population_too_small")
    if len(load_cases) < 1:
        raise SolverError("mlc_to_no_load_cases")

    design = mesh.design_mask
    n_design = int(np.count_nonzero(design))
    if n_design < 1:
        raise SolverError("mo_to_no_design_elements")
    n_elem = mesh.elements.shape[0]
    n_obj = len(load_cases) + 1
    if mutation_prob is None:
        mutation_prob = 1.0 / n_design
    configs = [replace(config, loads=lc) for lc in load_cases]
    hv = hypervolume_2d if n_obj == 2 else hypervolume_nd

    def _full_density(genome: np.ndarray) -> np.ndarray:
        rho = np.zeros(n_elem)
        rho[design] = np.clip(genome, 0.0, 1.0)
        return rho

    def eval_fn(genome: np.ndarray) -> tuple[float, ...]:
        rho = _full_density(genome)
        comps = [float(solve_linear_elastic(cfg, mesh, rho).compliance) for cfg in configs]
        vol = float(np.mean(np.clip(genome, 0.0, 1.0)))
        return (*comps, vol)

    rng = np.random.default_rng(rng_seed)
    bl, bu = np.zeros(n_design), np.ones(n_design)
    pop = rng.uniform(bl, bu, size=(population_size, n_design))
    if seed_genomes:
        for k, g in enumerate(seed_genomes[:population_size]):
            g = np.asarray(g, dtype=float).reshape(-1)
            if g.size != n_design:
                raise SolverError("mo_to_seed_genome_shape_mismatch")
            pop[k] = np.clip(g, 0.0, 1.0)
    objs = np.array([eval_fn(x) for x in pop])

    worst = _full_density(np.zeros(n_design))
    c_worst = [float(solve_linear_elastic(cfg, mesh, worst).compliance) for cfg in configs]
    reference = np.array([*[c * 1.05 for c in c_worst], 1.05])

    ref_dirs = das_dennis_reference_points(n_obj, n_divisions)
    archive_objs = objs[_nondominated(objs)]
    hv_history = [hv(archive_objs, reference)]

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
            picked = _niching_select(front, np.array(selected, dtype=int), combined_objs, ref_dirs, n_needed, rng)
            selected.extend(picked)
            break
        sel = np.array(selected, dtype=int)
        pop = combined[sel]
        objs = combined_objs[sel]

        merged = np.vstack([archive_objs, objs])
        archive_objs = merged[_nondominated(merged)]
        hv_history.append(hv(archive_objs, reference))

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

    Since Wave MMM (D068) this is a thin wrapper over the generalised
    :func:`nsga3_density_to` with the single load case ``config.loads`` (→ 2
    objectives); the output is bit-identical to the pre-refactor loop.
    """
    return nsga3_density_to(
        config,
        mesh,
        load_cases=[list(config.loads)],
        n_generations=n_generations,
        population_size=population_size,
        n_divisions=n_divisions,
        crossover_eta=crossover_eta,
        mutation_prob=mutation_prob,
        rng_seed=rng_seed,
        seed_genomes=seed_genomes,
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


def multi_load_case_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    load_cases: list[list[dict]] | None = None,
    n_generations: int = 12,
    population_size: int = 16,
    n_divisions: int = 8,
    crossover_eta: float = 15.0,
    mutation_prob: float | None = None,
    rng_seed: int = 0,
    seed_genomes: list[np.ndarray] | None = None,
) -> MultiObjectiveTOResult:
    """≥3-objective NSGA-III over density fields: minimise compliance under each
    of several **load cases** plus the volume fraction (Wave EEE, D060).

    D052's reopening criterion named "≥3 objectives (multi-load-case) with seeded
    warm-start". With ``L`` load cases the objective is
    ``(C_1, …, C_L, volume)`` (``n_obj = L + 1``). ``load_cases`` is a list of
    ``config.loads``-style lists; the default is the original loads plus a
    horizontal variant (fx/fy swapped), which genuinely conflict — a design tuned
    for one load is sub-optimal for the other. Reuses the same NSGA-III machinery
    (Das-Dennis reference directions, non-dominated sort, niching) as
    ``multi_objective_to`` and the exact n-D ``hypervolume_nd`` archive.

    Since Wave MMM (D068) this resolves the default load cases and delegates to
    the generalised :func:`nsga3_density_to`; the output is bit-identical to the
    pre-refactor loop.
    """
    if load_cases is None:
        load_cases = [
            list(config.loads),
            [{**ld, "fx": ld.get("fy", 0.0), "fy": ld.get("fx", 0.0)} for ld in config.loads],
        ]
    return nsga3_density_to(
        config,
        mesh,
        load_cases=load_cases,
        n_generations=n_generations,
        population_size=population_size,
        n_divisions=n_divisions,
        crossover_eta=crossover_eta,
        mutation_prob=mutation_prob,
        rng_seed=rng_seed,
        seed_genomes=seed_genomes,
    )
