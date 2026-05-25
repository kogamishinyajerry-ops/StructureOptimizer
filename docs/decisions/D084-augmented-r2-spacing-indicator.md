# D084 — augmented-Tchebycheff R2 + Schott spacing indicator (Wave CCCC, v12)

**Status**: Accepted
**Wave**: CCCC (v12)
**Supersedes**: none (extends D076)
**Superseded by**: none

## Context

D076 (v11 Wave UUU) added the reference-free **R2** indicator (plain Tchebycheff)
and a reference-free hypervolume. Its recorded reopening criterion:

> *"augmented Tchebycheff R2 + diversity/spacing indicator."*

Two honest gaps in D076:

1. **Plain Tchebycheff is blind to non-binding objectives.** Its utility
   `max_j λ_j(a_j − z*_j)` is set entirely by the binding coordinate, so two points
   equal there score identically even when one strictly dominates the other in the
   remaining objectives. R2 built on it therefore cannot distinguish a *weakly*
   efficient point from the *properly* efficient one that dominates it.
2. **R2 / IGD⁺ / hypervolume all measure convergence, none measures
   *distribution*.** A front could converge well yet be badly clustered, and D076
   had no indicator that would say so.

v12 Wave CCCC closes both.

## Decision

- **`multi_objective_to.augmented_tchebycheff_r2(front, weights=None, ideal=None,
  n_divisions=10, rho=0.05)`** — the augmented scalarisation adds a small ℓ₁ term:

      g_aug(a; λ, z*) = max_j λ_j(a_j − z*_j) + ρ · Σ_j λ_j(a_j − z*_j)
      R2_aug(A)       = (1/|W|) · Σ_{λ∈W} min_{a∈A} g_aug(a; λ, z*)

  The ℓ₁ term breaks the max-term's ties toward the dominating point. Closed-form
  properties: **`ρ = 0` recovers `r2_indicator` exactly**; for `ρ > 0` and a front
  at/above the utopia, `g_aug ≥ g_plain` pointwise so **`R2_aug ≥ R2`** always.
  Reference-free (weights + utopia only), lower is better.

- **`multi_objective_to.spacing_indicator(front)`** — Schott spacing, the standard
  deviation of the ℓ₁ nearest-neighbour gaps:

      S = sqrt( (1/(m−1)) · Σ_i (d̄ − d_i)² ),   d_i = min_{j≠i} ‖a_i − a_j‖₁

  **Lower is more uniform**; `S = 0` for an evenly-spaced front. A pure
  *distribution* measure (says nothing about proximity to the true front), so it
  **complements** R2/IGD⁺/HV rather than replacing them. Permutation-invariant,
  any objective count, needs `m ≥ 2`.

- **`tests/test_augmented_r2_spacing.py`** — six closed-form anchors.

## Verification (quantitative anchors)

`tests/test_augmented_r2_spacing.py` (6 passed; adjacent regression on
test_reference_free_indicators + test_multi_objective_to = 11 passed):

1. **ρ=0 degeneration**: `augmented_tchebycheff_r2(F, rho=0)` equals
   `r2_indicator(F)` to ≤ 1e-12 on a random front.
2. **augmented ≥ plain** for ρ>0 on a random front above the utopia.
3. **weak-vs-proper discrimination** (the decisive D076-reopening anchor): under
   λ=(0.5,0.5), z*=0, the weakly-efficient (0.5,0.5) and the dominating (0.5,0.3)
   have **identical** plain R2 (0.25, the max binds on f₁), while augmented R2
   strictly prefers the dominating point — exact closed-form 0.30 vs 0.29.
4. **spacing S=0** for an evenly-spaced collinear front (ℓ₁ nn = 2 everywhere).
5. **spacing S>0** for a clustered front, **permutation-invariant**, and strictly
   larger than the even front's S.
6. **guards**: negative ρ / empty front / single point / 1-D input raise
   `SolverError`.

## Honest scope notes

- **`rho=0.05` is a fixed default, not auto-scaled to the objective ranges.** The
  augmentation magnitude that actually breaks ties depends on the scale of
  `λ_j(a_j − z*_j)`; on a poorly-normalised front a fixed ρ can be too weak (no
  discrimination) or too strong (it starts to *re-order* genuinely-incomparable
  points). The recommended practice is normalised objectives; range-adaptive ρ is
  a reopening item.
- **Spacing measures distribution only — it can be gamed.** A front of two extreme
  points has `S=0` (perfectly "uniform") despite covering the objective space
  terribly. Spacing must be read alongside an *extent/spread* measure and a
  convergence indicator; on its own it is not a quality verdict. No extent metric
  is shipped here.
- **ℓ₁ nearest-neighbour, dense pairwise distance.** `O(m²·n_obj)` — fine for the
  modest fronts these drivers produce; no spatial index. ℓ₁ (not ℓ₂) is Schott's
  original choice and keeps the `S=0` collinear-front anchor exact.
- **Neither indicator is wired into a *driver* yet.** They are diagnostics over a
  supplied front (as D076's were); using augmented R2 as the NSGA-III environmental
  selection key, or spacing as a niche-preservation term, is not done here.

## Reopening criteria

- **Range-adaptive ρ** (scale the augmentation by per-objective ranges or set it
  from a target proper-efficiency tolerance) so discrimination is scale-robust.
- **An extent/spread indicator** (e.g. Deb's Δ, or the bounding-box diagonal) to
  pair with spacing so "uniformity" cannot be gamed by a degenerate two-point front.
- **Indicator-driven selection**: augmented-R2 as an NSGA-III selection criterion,
  or a spacing/niching term in the survival operator, to *act* on these diagnostics
  rather than only report them.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
