# D099 — Genz reordering wired into system_reliability_series_exact (Wave BBBBBB, v14)

**Status**: Accepted
**Wave**: BBBBBB (v14)
**Supersedes**: none (extends D094 Genz reordering + D078 Genz-exact series)
**Superseded by**: none

## Context

D094 (v13 Wave EEEEE) added Genz–Bretz variable reordering but recorded:

> *"Wire reordering into `genz_mvn_cdf_lattice` and `system_reliability_series_exact`
> so the production reliability path benefits from the variance reduction."*

D078's `system_reliability_series_exact` is the production exact series-system
estimator (`P_f = 1 − Φ_m(β; R)` via plain Genz MC). On a poorly-ordered limit-state
set its variance is several-fold larger than necessary. v14 wires the D094 reordering
into it.

## Decision

- **`reliability.system_reliability_series_exact(..., reorder=False)`** — new opt-in
  flag. `reorder=True` routes through `genz_mvn_cdf_reordered` (D094) instead of
  `genz_mvn_cdf` (D078); same estimand, lower variance at the same `n_samples`.
  **Default `reorder=False` reproduces D078 bit-for-bit.**

- **`reliability.system_reliability_series_exact_reordered(...)`** — convenience alias
  for `reorder=True`.

- **`tests/test_series_exact_reordered.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_series_exact_reordered.py` (6 passed; adjacent regression on
`test_genz_reordering` + `test_system_reliability` + `test_series_copula_reliability`,
18 pass):

1. **backward-compat bit-exact (integration铁律)**: `reorder=False` is identical
   (`==`) to `1 − genz_mvn_cdf(...)` (the D078 path) and to the default-arg call.
2. **same estimand**: high-N reordered == unordered (abs 3e-3) and == the exact
   equicorrelation 1-D reference.
3. **fixed-N variance reduction in the production fn (headline)**: on a wide-β,
   ρ=0.5 problem, fixed N=400 mean |error| over 60 seeds with `reorder=True` is < ½
   the `reorder=False` error (measured ratio ≈ 0.11, ≈9× reduction).
4. **convenience wrapper**: `system_reliability_series_exact_reordered(...)` is `==`
   to `...exact(reorder=True)`.
5. **independence**: at R=I both paths give `1 − Π Φ(β_k)` (abs 2e-4).
6. **guards**: shape / empty-modes raise single-string `SolverError` on both the param
   form and the wrapper.

## Honest scope notes

- **Reorder changes convergence, not the estimand.** Anchor 3 is a variance result,
  not a bias/accuracy improvement — the high-N value is the same as D078. Reordering is
  worth it only when `n_samples` is modest and the limit-state set is poorly ordered.
- **Lattice path (D086) still not reordered.** D094's reopening named *both*
  `genz_mvn_cdf_lattice` and the series estimator; this wave wires only the series
  estimator. Reordering + Korobov lattice (the strongest published combination) remains
  a reopening item.
- **The exact reference is equicorrelation-only.** The fixed-N variance anchor uses a
  1-factor equicorrelation reference (exact); a full-matrix reference would itself be a
  Genz-MC estimate (no closed form), so the variance contrast is shown on the
  equicorrelation case.
- **No automatic reorder.** `reorder` defaults off — D078 callers are untouched, and
  the caller opts in. Auto-enabling it (always reorder) is safe in principle but I keep
  the default for strict backward-compat per the v14 integration铁律.

## Reopening criteria

- **Wire reordering into `genz_mvn_cdf_lattice`** (D094's other named target) and
  combine reordering + Korobov lattice.
- **Default `reorder=True`** once a milestone is willing to change the default (it only
  reduces variance), retiring the opt-in.
- **Reorder inside `system_reliability_series_copula`** (D098) if a Genz-based copula
  evaluation is ever added (the Gumbel/Clayton CDFs there are closed-form, so no Genz
  reordering applies today).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
