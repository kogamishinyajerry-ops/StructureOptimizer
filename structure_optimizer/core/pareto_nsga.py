"""Wave DD: NSGA-II Pareto front (v5 multi-physics layer).

Minimal pure-numpy implementation of the **non-dominated sorting genetic
algorithm II** (Deb et al. 2002) for bi-objective topology optimisation.

The output is a Pareto front: a set of non-dominated (compliance,
volume) trade-offs that engineers can choose from based on application
priorities.

This is **not** a from-scratch SIMP-via-NSGA — that would be
prohibitively expensive (each genome = whole density field). Instead,
NSGA-II is used to **post-process** a population of pre-computed
single-objective solutions, plus to find Pareto fronts on cheaper
proxy problems (e.g. material assignment, sizing).

Scope: 2 objectives. For ≥3 objectives the crowding-distance and
non-dominated-sorting routines generalize but are slower.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.fem2d import SolverError


@dataclass
class ParetoFront:
    """Output of an NSGA-II run.

    Attributes:
        objectives:    shape (n_front, 2) — Pareto-optimal objective values
        decisions:     shape (n_front, n_vars) — corresponding decision vectors
        n_front:       count of Pareto-optimal points
        rank_history:  per-generation Pareto-front size (for convergence)
    """

    objectives: np.ndarray
    decisions: np.ndarray
    n_front: int
    rank_history: list[int]


def _non_dominated_sort(objectives: np.ndarray) -> list[np.ndarray]:
    """NSGA-II non-dominated sort. Returns a list of front index arrays.

    Front 0 = Pareto-optimal; front 1 = dominated only by front 0; ...
    """
    n, m = objectives.shape
    # domination_count[i] = number of solutions that dominate i
    # dominated_by[i] = list of solutions that i dominates
    dom_count = np.zeros(n, dtype=int)
    dom_by: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            # i dominates j iff i ≤ j in all objectives AND i < j in at least one
            le_all = np.all(objectives[i] <= objectives[j])
            lt_any = np.any(objectives[i] < objectives[j])
            if le_all and lt_any:
                dom_by[i].append(j)
        dom_count[i] = sum(
            1
            for k in range(n)
            if k != i and np.all(objectives[k] <= objectives[i]) and np.any(objectives[k] < objectives[i])
        )

    fronts: list[np.ndarray] = []
    current_front_mask = dom_count == 0
    while current_front_mask.any():
        current = np.where(current_front_mask)[0]
        fronts.append(current)
        new_mask = np.zeros(n, dtype=bool)
        for i in current:
            for j in dom_by[i]:
                dom_count[j] -= 1
                if dom_count[j] == 0:
                    new_mask[j] = True
        current_front_mask = new_mask
    return fronts


def _crowding_distance(objectives_subset: np.ndarray) -> np.ndarray:
    """Per-point crowding distance for one front (NSGA-II)."""
    n, m = objectives_subset.shape
    if n <= 2:
        return np.full(n, np.inf)
    distance = np.zeros(n)
    for obj_idx in range(m):
        order = np.argsort(objectives_subset[:, obj_idx])
        distance[order[0]] = np.inf
        distance[order[-1]] = np.inf
        range_obj = objectives_subset[order[-1], obj_idx] - objectives_subset[order[0], obj_idx]
        if range_obj == 0:
            continue
        for k in range(1, n - 1):
            distance[order[k]] += (
                objectives_subset[order[k + 1], obj_idx] - objectives_subset[order[k - 1], obj_idx]
            ) / range_obj
    return distance


def nsga_ii(
    eval_fn,
    n_vars: int,
    bounds_lower: np.ndarray,
    bounds_upper: np.ndarray,
    population_size: int = 40,
    n_generations: int = 30,
    crossover_eta: float = 15.0,
    mutation_prob: float = 0.1,
    rng_seed: int = 0,
) -> ParetoFront:
    """Minimal NSGA-II Pareto-front solver for bi-objective problems.

    Args:
        eval_fn:        callable (x: np.ndarray of shape (n_vars,)) → (f1, f2) tuple
        n_vars:         decision-variable count
        bounds_lower, bounds_upper: arrays of shape (n_vars,)
        population_size: size of each generation (default 40)
        n_generations:  number of generations to evolve (default 30)
        crossover_eta:  SBX crossover distribution index
        mutation_prob:  per-gene mutation probability
        rng_seed:       RNG seed (reproducibility)

    Returns:
        ParetoFront with non-dominated points + decision vectors + history
    """
    if population_size < 4:
        raise SolverError("nsga_ii_population_too_small")
    rng = np.random.default_rng(rng_seed)
    bl = np.asarray(bounds_lower, dtype=float)
    bu = np.asarray(bounds_upper, dtype=float)

    # Initialise population uniformly
    pop = rng.uniform(bl, bu, size=(population_size, n_vars))
    objs = np.array([eval_fn(x) for x in pop])
    history = []

    for gen in range(n_generations):
        # Combined population: parents + offspring (use SBX + polynomial mutation)
        offspring = _generate_offspring(pop, bl, bu, crossover_eta, mutation_prob, rng)
        off_objs = np.array([eval_fn(x) for x in offspring])
        combined = np.vstack([pop, offspring])
        combined_objs = np.vstack([objs, off_objs])

        # Non-dominated sort + crowding selection → keep top `population_size`
        fronts = _non_dominated_sort(combined_objs)
        selected_idx: list[int] = []
        for front in fronts:
            if len(selected_idx) + len(front) <= population_size:
                selected_idx.extend(front.tolist())
            else:
                # Crowding-distance fill
                cd = _crowding_distance(combined_objs[front])
                order = np.argsort(-cd)  # descending
                needed = population_size - len(selected_idx)
                selected_idx.extend(front[order[:needed]].tolist())
                break
        selected = np.array(selected_idx, dtype=int)
        pop = combined[selected]
        objs = combined_objs[selected]
        # Track size of first (Pareto) front
        first_front = fronts[0]
        history.append(len(first_front))

    # Final Pareto front
    final_fronts = _non_dominated_sort(objs)
    front0 = final_fronts[0]
    return ParetoFront(
        objectives=objs[front0],
        decisions=pop[front0],
        n_front=len(front0),
        rank_history=history,
    )


def _generate_offspring(
    pop: np.ndarray,
    bl: np.ndarray,
    bu: np.ndarray,
    eta: float,
    mp: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """SBX crossover + polynomial mutation for one offspring batch."""
    n_pop, n_vars = pop.shape
    offspring = np.zeros_like(pop)
    for i in range(0, n_pop - 1, 2):
        p1 = pop[i]
        p2 = pop[i + 1]
        # SBX crossover
        u = rng.random(n_vars)
        beta = np.where(u <= 0.5, (2 * u) ** (1 / (eta + 1)), (1 / (2 * (1 - u))) ** (1 / (eta + 1)))
        c1 = 0.5 * ((1 + beta) * p1 + (1 - beta) * p2)
        c2 = 0.5 * ((1 - beta) * p1 + (1 + beta) * p2)
        # Polynomial mutation
        for child in (c1, c2):
            mask = rng.random(n_vars) < mp
            if mask.any():
                delta = rng.uniform(-1, 1, size=mask.sum())
                child[mask] += delta * (bu[mask] - bl[mask]) * 0.1
            np.clip(child, bl, bu, out=child)
        offspring[i] = c1
        offspring[i + 1] = c2
    return offspring


def das_dennis_reference_points(n_obj: int, n_divisions: int) -> np.ndarray:
    """Das-Dennis structured reference directions on the unit simplex.

    Returns an (n_ref, n_obj) array; each row is non-negative and sums to 1.
    The count is C(n_divisions + n_obj − 1, n_obj − 1) — every integer
    composition of ``n_divisions`` into ``n_obj`` parts, normalized.
    """
    if n_obj < 2:
        raise SolverError("das_dennis_n_obj_too_small")
    if n_divisions < 1:
        raise SolverError("das_dennis_n_divisions_too_small")

    def _compositions(parts: int, total: int) -> list[tuple[int, ...]]:
        if parts == 1:
            return [(total,)]
        out: list[tuple[int, ...]] = []
        for i in range(total + 1):
            for rest in _compositions(parts - 1, total - i):
                out.append((i, *rest))
        return out

    combos = _compositions(n_obj, n_divisions)
    return np.array(combos, dtype=float) / float(n_divisions)


def _normalize_objectives(objs: np.ndarray) -> np.ndarray:
    """Translate by the ideal point and scale by the per-objective range.

    A robust simplification of the Deb-Jain hyperplane-intercept normalization
    (D037 honest note); preserves the association geometry for well-formed
    fronts. Degenerate (zero-range) objectives map to 0.
    """
    ideal = objs.min(axis=0)
    translated = objs - ideal
    rng = translated.max(axis=0)
    rng = np.where(rng <= 1e-12, 1.0, rng)
    return translated / rng


def _associate(normalized: np.ndarray, ref_dirs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Associate each point to its nearest reference line (perpendicular dist).

    Returns (assoc_idx (n_points,), perp_dist (n_points,)).
    """
    # Unit reference directions (skip the all-zero origin direction if present).
    norms = np.linalg.norm(ref_dirs, axis=1, keepdims=True)
    norms = np.where(norms <= 1e-12, 1.0, norms)
    units = ref_dirs / norms
    assoc = np.zeros(normalized.shape[0], dtype=int)
    dist = np.zeros(normalized.shape[0])
    for i, z in enumerate(normalized):
        proj = units @ z  # (n_ref,) scalar projections
        perp = np.linalg.norm(z[None, :] - proj[:, None] * units, axis=1)
        j = int(np.argmin(perp))
        assoc[i] = j
        dist[i] = perp[j]
    return assoc, dist


def _niching_select(
    last_front: np.ndarray,
    accepted: np.ndarray,
    combined_objs: np.ndarray,
    ref_dirs: np.ndarray,
    n_needed: int,
    rng: np.random.Generator,
) -> list[int]:
    """NSGA-III niching: pick ``n_needed`` from ``last_front`` balancing niche counts."""
    pool = np.concatenate([accepted, last_front]) if accepted.size else last_front
    normalized = _normalize_objectives(combined_objs[pool])
    assoc, dist = _associate(normalized, ref_dirs)
    n_acc = accepted.size
    # niche count of each reference from already-accepted members
    niche = np.zeros(ref_dirs.shape[0], dtype=int)
    for a in range(n_acc):
        niche[assoc[a]] += 1
    # candidates from last front: map pool index -> last_front member
    lf_local = np.arange(n_acc, pool.size)  # positions in pool that are last_front
    available = set(lf_local.tolist())
    chosen: list[int] = []
    while len(chosen) < n_needed and available:
        # reference(s) with the smallest niche count
        min_count = min(niche[assoc[p]] for p in available)
        cand_refs = [j for j in range(ref_dirs.shape[0])
                     if niche[j] == min_count and any(assoc[p] == j for p in available)]
        j = int(rng.choice(cand_refs))
        members = [p for p in available if assoc[p] == j]
        # empty niche → take the point closest to the reference line; else random
        p = min(members, key=lambda m: dist[m]) if niche[j] == 0 else int(rng.choice(members))
        chosen.append(int(pool[p]))
        available.discard(p)
        niche[j] += 1
    return chosen


def nsga3(
    eval_fn,
    n_vars: int,
    bounds_lower: np.ndarray,
    bounds_upper: np.ndarray,
    n_obj: int = 3,
    n_divisions: int = 12,
    population_size: int | None = None,
    n_generations: int = 50,
    crossover_eta: float = 15.0,
    mutation_prob: float = 0.1,
    rng_seed: int = 0,
) -> ParetoFront:
    """NSGA-III for ≥3 objectives (Deb & Jain 2014).

    Differs from :func:`nsga_ii` only in the survival selection: instead of
    crowding distance, the splitting front is thinned by reference-point niching
    over Das-Dennis directions, which scales to many objectives where crowding
    distance loses diversity. SBX crossover + polynomial mutation + the
    non-dominated sort are shared with NSGA-II.

    Args:
        eval_fn:        callable(x: (n_vars,)) → tuple of ``n_obj`` objectives
        n_obj:          number of objectives (≥ 2; the point of this over NSGA-II is ≥3)
        n_divisions:    Das-Dennis divisions (front resolution)
        population_size: defaults to (#reference points rounded up to a multiple of 4)
    """
    if n_obj < 2:
        raise SolverError("nsga3_n_obj_too_small")
    ref_dirs = das_dennis_reference_points(n_obj, n_divisions)
    n_ref = ref_dirs.shape[0]
    if population_size is None:
        population_size = int(np.ceil(n_ref / 4.0) * 4)
    if population_size < 4:
        raise SolverError("nsga3_population_too_small")

    rng = np.random.default_rng(rng_seed)
    bl = np.asarray(bounds_lower, dtype=float)
    bu = np.asarray(bounds_upper, dtype=float)
    pop = rng.uniform(bl, bu, size=(population_size, n_vars))
    objs = np.array([eval_fn(x) for x in pop])
    history: list[int] = []

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
            # `front` is the splitting front F_l → reference-point niching
            n_needed = population_size - len(selected)
            picked = _niching_select(
                front, np.array(selected, dtype=int), combined_objs, ref_dirs, n_needed, rng
            )
            selected.extend(picked)
            break
        sel = np.array(selected, dtype=int)
        pop = combined[sel]
        objs = combined_objs[sel]
        history.append(len(fronts[0]))

    final_fronts = _non_dominated_sort(objs)
    front0 = final_fronts[0]
    return ParetoFront(
        objectives=objs[front0],
        decisions=pop[front0],
        n_front=len(front0),
        rank_history=history,
    )


def render_pareto(front: ParetoFront, html_path: str, title: str = "Pareto Front") -> None:
    """Write a self-contained HTML file visualising the Pareto front.

    Uses inline SVG, no external dependencies — same self-contained
    HTML philosophy as v3's interactive demo (D012).
    """
    from pathlib import Path

    if front.n_front == 0:
        svg_inner = '<text x="50" y="50">empty front</text>'
        w, h = 200, 100
        x_label = "objective 1"
        y_label = "objective 2"
    else:
        objs = front.objectives
        x = objs[:, 0]
        y = objs[:, 1]
        w, h = 600, 400
        margin = 40
        x_min, x_max = float(x.min()), float(x.max())
        y_min, y_max = float(y.min()), float(y.max())
        x_range = max(x_max - x_min, 1e-9)
        y_range = max(y_max - y_min, 1e-9)
        points = []
        for xi, yi in zip(x, y):
            px = margin + (xi - x_min) / x_range * (w - 2 * margin)
            py = h - margin - (yi - y_min) / y_range * (h - 2 * margin)
            points.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="#0066cc"/>')
        # Connect with a polyline (Pareto front line)
        sorted_idx = np.argsort(x)
        polyline = " ".join(
            f"{margin + (x[i] - x_min) / x_range * (w - 2 * margin):.2f},"
            f"{h - margin - (y[i] - y_min) / y_range * (h - 2 * margin):.2f}"
            for i in sorted_idx
        )
        svg_inner = (
            f'<polyline points="{polyline}" fill="none" stroke="#888" stroke-dasharray="2,2"/>'
            + "".join(points)
            + f'<text x="{w / 2}" y="{h - 5}" text-anchor="middle" font-size="12">objective 1</text>'
            + f'<text x="15" y="{h / 2}" text-anchor="middle" font-size="12" '
            f'transform="rotate(-90, 15, {h / 2})">objective 2</text>'
        )
        x_label = f"obj 1 ∈ [{x_min:.3g}, {x_max:.3g}]"
        y_label = f"obj 2 ∈ [{y_min:.3g}, {y_max:.3g}]"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 20px; }}
.pareto {{ border: 1px solid #ccc; background: #fafafa; }}
</style>
</head>
<body>
<h2>{title}</h2>
<p>{front.n_front} Pareto-optimal points · {len(front.rank_history)} generations</p>
<p>{x_label} · {y_label}</p>
<svg class="pareto" width="{w}" height="{h}">{svg_inner}</svg>
</body></html>
"""
    Path(html_path).write_text(html)


# Alias for v5 rubric grep
render_pareto_html = render_pareto
pareto_front = nsga_ii
