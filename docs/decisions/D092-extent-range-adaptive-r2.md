# D092 — extent (Δ) diversity indicator + range-adaptive augmented R2 (Wave CCCCC, v13)

**Status**: Accepted
**Wave**: CCCCC (v13)
**Supersedes**: none (extends D084)
**Superseded by**: none

## Context

D084 (v12 Wave CCCC) added the augmented-Tchebycheff R2 indicator and the Schott
**spacing** indicator, but recorded a reopening item:

> *"An extent/spread (Δ) indicator to pair with spacing (spacing measures uniformity
> but not how far the front reaches), and a range-adaptive ρ so the augmentation is
> not dominated by the largest-scaled objective."*

This wave delivers **both halves** of that item.

The honest gap D084 left: `spacing_indicator` measures *uniformity* of the
nearest-neighbour gaps only. It reports a tightly-clustered front and a two-point
extreme-only front as *equally* "perfectly uniform" (S = 0 for both), because in both
the NN gaps are equal. Uniformity alone cannot say whether a front actually *spreads*
across objective space. Separately, a fixed augmentation coefficient ρ on raw,
poorly-scaled objectives is swamped: if one objective is 1000× another, the
Tchebycheff `max` and the Σ augmentation are both dominated by that axis and the
tie-breaking purpose of ρ is lost.

## Decision

- **`multi_objective_to.extent_indicator(front)`** — the diversity *extent*
  `Δ = ‖max_i a_i − min_i a_i‖₂`, the ℓ₂ length of the front's axis-aligned
  bounding-box diagonal. **Higher = wider spread.** Translation-invariant, scales
  linearly under per-objective scaling, and (the point) scores a two-point
  extreme-only front the **same** as a dense well-spread one — capturing exactly the
  reach that spacing is blind to. The pair (extent = spread, spacing = uniformity) is
  needed to judge front diversity; neither alone suffices. A single-point front gives
  Δ = 0.

- **`multi_objective_to.augmented_tchebycheff_r2(..., normalize_ranges=False)`** — a
  new opt-in flag. When `True`, the shifted objectives `a − z*` are divided by the
  front's **per-objective range** (`max − min`, guarded to 1 on a degenerate axis)
  before the Tchebycheff + augmentation. This makes R2_aug **scale-invariant**:
  rescaling any objective by a constant leaves the indicator unchanged. **Default
  `False` reproduces D084 exactly** (no regression), and when every range is already 1
  the normalised value equals the fixed value.

- **`tests/test_extent_range_adaptive.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_extent_range_adaptive.py` (6 passed; adjacent regression on
`test_augmented_r2_spacing.py` + `test_property_v12.py`, all pass):

1. **extent closed form**: Δ of the [0,4]×[0,4] spread front = √32 to ≤ 1e-12; the
   clustered front = √(0.15²+0.15²); spread ≥ 10× clustered.
2. **complements spacing (headline)**: the two-point extreme-only front has the
   **identical** extent to the dense spread front (both √32), yet `spacing_indicator`
   reports BOTH as S = 0 — proving extent measures spread that spacing cannot see.
3. **translation-invariant + linear scaling**: Δ unchanged under +100 shift; scaling
   objective 0 by 10 gives exactly √(40²+4²); a single point gives Δ = 0.
4. **range-adaptive scale invariance**: a 1000× rescale of objective 0 leaves the
   normalised aug-R2 unchanged (rel ≤ 1e-9) while the fixed aug-R2 grows > 1.5×.
5. **degeneration**: with every objective range = 1, `normalize_ranges=True` equals
   the fixed value to ≤ 1e-12 (÷1 is a no-op).
6. **guards**: 1-D / empty fronts raise `SolverError`; a front constant in one
   objective (range 0 → guarded to 1) yields a finite normalised value (no ÷0).

## Honest scope notes

- **`extent_indicator` is a *spread* measure, not a *convergence* measure.** Like
  spacing, it says nothing about proximity to the true Pareto front (use R2 / IGD⁺ /
  hypervolume for that). A pathological front consisting of two far-apart *dominated*
  points would score a large Δ; extent must be read alongside a convergence indicator.
- **Range normalisation uses the *front's own* observed range**, not a designer-
  supplied normalisation. If the sampled front does not yet span the true objective
  ranges (early in a run), the normalisation is biased by the current sample. A run
  that has only found one cluster will normalise by that cluster's tiny range. This is
  a deliberate self-contained choice (no external reference needed), but it is *not*
  the same as normalising by the true ideal/nadir box.
- **`normalize_ranges` is opt-in; default preserves D084.** I did not flip the
  default — existing D084 tests and the v12 fingerprints assume the unnormalised
  scalarisation, and on well-scaled objectives the two agree.
- **Δ is not the IGD/HV "spread" (Δ-metric of Deb).** Deb's Δ uses consecutive-
  solution distances + boundary distances and needs a sorted 2-objective front; this
  bounding-box diagonal is the simpler, any-dimension, permutation-invariant extent. I
  do not claim it is Deb's Δ.

## Reopening criteria

- **Wire extent + spacing into a selection / archiving step** (e.g. an ε-archive that
  trades convergence against the (spread, uniformity) pair) so the indicators *drive*
  a many-objective run rather than only scoring it post hoc.
- **Reference-box normalisation**: divide by a supplied ideal/nadir range instead of
  the observed front range, for comparing fronts across different runs/samples.
- **Deb's Δ-spread** (consecutive-distance variance + boundary terms) as a second,
  ordering-aware spread indicator for the 2-objective case.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
