"""Wave CCCCC (v13, D092) — extent/spread diversity indicator + range-adaptive ρ.

Quantitative analytical anchors (closed form / scale-invariance), never qualitative
trends. Traces D084's reopening criterion: "extent/spread indicator + range-adaptive ρ".

- ``extent_indicator`` = ℓ₂ length of the front's bounding-box diagonal:
  it is *higher* for a wider-spread front, **translation-invariant**, and **scales
  linearly** when one objective is scaled. Crucially it scores a two-point
  extreme-only front the SAME as a dense well-spread one — exactly the spread that
  ``spacing_indicator`` (uniformity) is blind to (both give S=0 there).
- ``augmented_tchebycheff_r2(..., normalize_ranges=True)`` divides shifted objectives
  by the per-objective range, making R2_aug **scale-invariant** (a 1000× rescale of
  one objective leaves it unchanged) where the fixed version is dominated by the
  largest-scaled axis; it **degenerates** to the unnormalised value when every range
  is 1.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.multi_objective_to import (
    augmented_tchebycheff_r2,
    extent_indicator,
    spacing_indicator,
)

# An evenly-spread linear front and a tight cluster (same centroid region).
SPREAD = np.array([[0.0, 4.0], [1.0, 3.0], [2.0, 2.0], [3.0, 1.0], [4.0, 0.0]])
CLUSTERED = np.array([[1.9, 2.0], [2.0, 2.1], [2.05, 1.95], [1.95, 2.05]])
TWO_EXTREME = np.array([[0.0, 4.0], [4.0, 0.0]])


def test_extent_closed_form_diagonal():
    """Δ equals the exact ℓ₂ bounding-box diagonal, and a wide front beats a cluster."""
    # SPREAD box = [0,4]×[0,4] ⟹ diagonal = √(4²+4²) = √32.
    assert extent_indicator(SPREAD) == pytest.approx(np.sqrt(32.0), rel=1e-12)
    # CLUSTERED box ≈ [1.9,2.05]×[1.95,2.1] ⟹ diagonal = √(0.15²+0.15²).
    assert extent_indicator(CLUSTERED) == pytest.approx(np.hypot(0.15, 0.15), rel=1e-9)
    assert extent_indicator(SPREAD) > 10.0 * extent_indicator(CLUSTERED)


def test_extent_complements_spacing_on_two_extreme():
    """The headline: extent sees what spacing cannot.

    A two-point extreme-only front spans the SAME box as the dense spread front, so
    its extent is identical (√32). Yet ``spacing_indicator`` reports BOTH as perfectly
    uniform (S=0) — it cannot tell a 2-point gap-front from a dense even one. Extent is
    therefore the necessary diversity *partner*, not a substitute.
    """
    assert extent_indicator(TWO_EXTREME) == pytest.approx(
        extent_indicator(SPREAD), rel=1e-12
    )
    # spacing is blind to the difference: both are "uniform" (NN gaps all equal ⟹ S=0)
    assert spacing_indicator(SPREAD) == pytest.approx(0.0, abs=1e-12)
    assert spacing_indicator(TWO_EXTREME) == pytest.approx(0.0, abs=1e-12)


def test_extent_translation_invariant_and_linear_scaling():
    """Δ is invariant to a constant shift and scales linearly under axis scaling."""
    shifted = SPREAD + 100.0
    assert extent_indicator(shifted) == pytest.approx(extent_indicator(SPREAD), rel=1e-12)
    scaled = SPREAD.copy()
    scaled[:, 0] *= 10.0  # box becomes [0,40]×[0,4] ⟹ diagonal √(40²+4²)
    assert extent_indicator(scaled) == pytest.approx(np.hypot(40.0, 4.0), rel=1e-12)
    # a single point spans nothing
    assert extent_indicator(np.array([[1.0, 2.0]])) == pytest.approx(0.0, abs=1e-15)


def test_range_adaptive_r2_is_scale_invariant():
    """Range-normalised aug-R2 is unchanged by a 1000× rescale; the fixed one is not."""
    w = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])
    scaled = SPREAD.copy()
    scaled[:, 0] *= 1000.0

    base_norm = augmented_tchebycheff_r2(SPREAD, weights=w, rho=0.05, normalize_ranges=True)
    sc_norm = augmented_tchebycheff_r2(scaled, weights=w, rho=0.05, normalize_ranges=True)
    assert sc_norm == pytest.approx(base_norm, rel=1e-9)  # invariant

    base_fixed = augmented_tchebycheff_r2(SPREAD, weights=w, rho=0.05)
    sc_fixed = augmented_tchebycheff_r2(scaled, weights=w, rho=0.05)
    # the unnormalised indicator is dominated by the 1000×-scaled axis and blows up
    assert sc_fixed > 1.5 * base_fixed


def test_range_adaptive_degenerates_to_fixed_when_ranges_unit():
    """When every objective range is exactly 1, normalisation is a no-op (÷1)."""
    unit = np.array([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]])  # each objective range = 1
    w = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])
    fixed = augmented_tchebycheff_r2(unit, weights=w, rho=0.05)
    norm = augmented_tchebycheff_r2(unit, weights=w, rho=0.05, normalize_ranges=True)
    assert norm == pytest.approx(fixed, rel=1e-12)


def test_extent_and_range_guards():
    """Shape/empty guards raise SolverError; a degenerate range axis is divided by 1."""
    with pytest.raises(SolverError, match="extent_expects_2d_front"):
        extent_indicator(np.array([1.0, 2.0, 3.0]))
    with pytest.raises(SolverError, match="extent_empty_front"):
        extent_indicator(np.empty((0, 2)))
    # a front constant in objective 1 (range 0 ⟹ guarded to 1) must not divide by zero
    flat = np.array([[0.0, 5.0], [1.0, 5.0], [2.0, 5.0]])
    val = augmented_tchebycheff_r2(flat, normalize_ranges=True)
    assert np.isfinite(val)
