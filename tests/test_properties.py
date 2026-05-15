"""Property-style tests: random inputs satisfying preconditions must satisfy
key invariants. No hypothesis dependency — uses stdlib ``random`` with fixed
seeds so failures are reproducible.

Properties exercised:

- **SIMP density bounds**: after a SIMP loop, every cell ∈ [min_density, 1].
- **SIMP volume target**: ``active_volume_fraction ≈ target`` (within tol).
- **Pareto non-dominance**: every rank-1 candidate is dominated by no other
  rank-1 candidate (mutually non-dominated).
- **Pareto monotonicity**: candidates in rank N+1 are dominated by at least
  one in rank N.
- **Symmetry projection idempotence**: applying symmetry twice = once.
- **Extrusion projection idempotence**: applying extrusion twice = once.
- **Symmetry residual zero after projection**.
- **Format helpers**: format_metric_value never returns the empty string.
"""

from __future__ import annotations

import random

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import (
    ExtrusionConstraintConfig,
    SymmetryConstraintConfig,
    parse_config,
    validate_config,
)
from structure_optimizer.core.manufacturing import (
    apply_extrusion_projection,
    apply_symmetry_projection,
    extrusion_residual,
    symmetry_residual,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.review_package import format_metric_value
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.study import DEFAULT_OBJECTIVES, _assign_pareto_ranks, _dominates

PROPERTY_SEEDS = [0, 1, 7, 42, 123]


# --- SIMP density invariants ------------------------------------------


def test_simp_densities_stay_within_bounds_across_random_volume_fractions():
    """For any volume_fraction in (0.1, 0.9), the final density field must lie in
    [min_density, 1] elementwise. This is the bedrock SIMP contract."""
    rng = random.Random(0)
    for _ in range(5):
        target = rng.uniform(0.1, 0.9)
        raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
        raw["optimization"]["volume_fraction"] = target
        config = parse_config(raw)
        validate_config(config)
        mesh = create_structured_mesh(config)
        result = run_simp(config, mesh)
        min_density = config.optimization.min_density
        assert float(result.densities.min()) >= min_density - 1e-12
        assert float(result.densities.max()) <= 1.0 + 1e-12


def test_simp_volume_target_approximately_satisfied():
    """Active volume fraction must converge near the target (within 5% absolute)."""
    rng = random.Random(1)
    for _ in range(5):
        target = rng.uniform(0.2, 0.7)
        raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
        raw["optimization"]["volume_fraction"] = target
        config = parse_config(raw)
        validate_config(config)
        mesh = create_structured_mesh(config)
        result = run_simp(config, mesh)
        active = float(result.densities[mesh.design_mask].mean())
        assert abs(active - target) < 0.05, f"target={target} but achieved={active}"


# --- Pareto invariants ------------------------------------------------


def _random_candidates(rng: random.Random, n: int) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "candidate_id": f"cand_{i:03d}",
                "mass": rng.uniform(0.1, 10.0),
                "compliance": rng.uniform(0.1, 100.0),
                "verification_status": "passed",
            }
        )
    return rows


def test_pareto_front_members_are_mutually_non_dominated():
    """Every pair of rank-1 candidates must be mutually non-dominated."""
    for seed in PROPERTY_SEEDS:
        rng = random.Random(seed)
        rows = _random_candidates(rng, n=15)
        _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
        front = [r for r in rows if r.get("pareto_rank") == 1]
        for a in front:
            for b in front:
                if a is b:
                    continue
                a_vec = [a["mass"], a["compliance"]]
                b_vec = [b["mass"], b["compliance"]]
                assert not _dominates(a_vec, b_vec, DEFAULT_OBJECTIVES), (
                    f"seed={seed}: {a['candidate_id']} dominates {b['candidate_id']} but both in front"
                )


def test_pareto_rank_N_dominated_by_at_least_one_in_rank_N_minus_one():
    """Engineering meaning of rank: if you are rank N>1, somebody in rank N-1
    beat you on all objectives. Verify this holds for a random population."""
    for seed in PROPERTY_SEEDS:
        rng = random.Random(seed)
        rows = _random_candidates(rng, n=20)
        _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
        max_rank = max((r["pareto_rank"] for r in rows if isinstance(r["pareto_rank"], int)), default=1)
        for current_rank in range(2, max_rank + 1):
            prev_rank_candidates = [r for r in rows if r.get("pareto_rank") == current_rank - 1]
            current_rank_candidates = [r for r in rows if r.get("pareto_rank") == current_rank]
            for cand in current_rank_candidates:
                cand_vec = [cand["mass"], cand["compliance"]]
                dominated = False
                for prev in prev_rank_candidates:
                    prev_vec = [prev["mass"], prev["compliance"]]
                    if _dominates(prev_vec, cand_vec, DEFAULT_OBJECTIVES):
                        dominated = True
                        break
                assert dominated, (
                    f"seed={seed}: rank-{current_rank} candidate {cand['candidate_id']} "
                    f"not dominated by any rank-{current_rank - 1} candidate"
                )


# --- Manufacturing projection idempotence -----------------------------


def test_symmetry_projection_is_idempotent():
    """Applying symmetry twice = once (projection is a fixed-point op)."""
    rng = random.Random(0)
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    for _ in range(5):
        densities = np.array([rng.uniform(0.001, 1.0) for _ in range(mesh.elements.shape[0])])
        sym = SymmetryConstraintConfig(axis="y", position=0.5)
        once = apply_symmetry_projection(mesh, densities, sym)
        twice = apply_symmetry_projection(mesh, once, sym)
        np.testing.assert_array_almost_equal(once, twice, decimal=12)


def test_extrusion_projection_is_idempotent():
    rng = random.Random(0)
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    for axis in ("x", "y"):
        for _ in range(3):
            densities = np.array([rng.uniform(0.001, 1.0) for _ in range(mesh.elements.shape[0])])
            ext = ExtrusionConstraintConfig(axis=axis)
            once = apply_extrusion_projection(mesh, densities, ext)
            twice = apply_extrusion_projection(mesh, once, ext)
            np.testing.assert_array_almost_equal(once, twice, decimal=12)


def test_symmetry_residual_zero_after_projection():
    rng = random.Random(0)
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    sym = SymmetryConstraintConfig(axis="y", position=0.5)
    for _ in range(5):
        densities = np.array([rng.uniform(0.001, 1.0) for _ in range(mesh.elements.shape[0])])
        projected = apply_symmetry_projection(mesh, densities, sym)
        assert symmetry_residual(mesh, projected, sym) < 1e-12


def test_extrusion_residual_zero_after_projection():
    rng = random.Random(0)
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    for axis in ("x", "y"):
        ext = ExtrusionConstraintConfig(axis=axis)
        for _ in range(3):
            densities = np.array([rng.uniform(0.001, 1.0) for _ in range(mesh.elements.shape[0])])
            projected = apply_extrusion_projection(mesh, densities, ext)
            assert extrusion_residual(mesh, projected, ext) < 1e-12


# --- format_metric_value invariants -----------------------------------


def test_format_metric_value_never_returns_empty_string():
    """Output must always be non-empty so HTML cells never collapse to ''."""
    rng = random.Random(0)
    samples = [None, True, False, "text", "", 0, 0.0, 1, -1, 1e-100, 1e100]
    samples += [rng.uniform(-1e6, 1e6) for _ in range(50)]
    samples += [rng.uniform(-1e-8, 1e-8) for _ in range(50)]
    for value in samples:
        formatted = format_metric_value(value)
        assert formatted != "", f"empty formatting for {value!r}"


def test_format_metric_value_is_stable_across_calls():
    """Same input → same output (no hidden state)."""
    rng = random.Random(42)
    for _ in range(50):
        value = rng.uniform(-1e6, 1e6)
        assert format_metric_value(value) == format_metric_value(value)
