# D093 — d-dimensional exchangeable Gumbel copula with closed-form conditional CDF (Wave DDDDD, v13)

**Status**: Accepted
**Wave**: DDDDD (v13)
**Supersedes**: none (extends D085 + the bivariate Gumbel of D069)
**Superseded by**: none

## Context

D085 (v12 Wave EEEE) added a **nested Clayton** copula and recorded a reopening item:

> *"A non-Clayton d-dim copula — e.g. an exchangeable Gumbel — with a closed-form
> conditional CDF, so upper-tail-dependent systems can use the Rosenblatt transform
> without falling back to bivariate-only Gumbel (D069)."*

Clayton (D077 `ExchangeableClaytonCopula`) captures **lower**-tail dependence; Gumbel
captures **upper**-tail dependence (joint extremes / simultaneous failures), which is
the relevant regime for series-system reliability. The bivariate Gumbel already exists
(D069 `ArchimedeanCopula`), but there was no d-variate Gumbel with an analytic
conditional CDF for the sequential Rosenblatt transform.

The obstacle: unlike Clayton, the Gumbel inverse generator ``ψ(s) = exp(−s^{1/θ})``
has **no one-line k-th derivative** — the derivatives are degree-growing polynomials
in ``s^{1/θ}`` (Faà di Bruno). This wave supplies them via an exact recursion.

## Decision

- **`reliability._gumbel_psi_derivative_terms(order, alpha)`** — the exact monomial
  terms ``(c, p)`` of ``g_order`` where ``ψ^{(order)}(s) = exp(−s^α)·Σ c·s^p``. From
  ``ψ′ = −α s^{α−1} ψ`` write ``ψ^{(k)} = ψ·g_k`` with ``g_0 = 1`` and the recursion
  ``g_{k+1} = g_k′ − α s^{α−1} g_k``; differentiation maps ``c·s^p → c·p·s^{p−1}`` and
  the ``−α s^{α−1}`` factor maps ``c·s^p → −α c·s^{p+α−1}``. No quadrature, no finite
  differences — a finite, exact symbolic recursion evaluated at the point.

- **`reliability.ExchangeableGumbelCopula(dim, theta)`** + factory
  **`gumbel_d_copula(dim, theta)`** (``θ ≥ 1``): `cdf`, `conditional_cdf`
  (= ``ψ^{(k−1)}(S_k)/ψ^{(k−1)}(S_{k−1})``, the shared ``Π φ′(u_i)`` cancelling in the
  ratio), `conditional_ppf` (bisection on the monotone conditional — Gumbel has no
  closed-form inverse), and `kendall_tau` = ``1 − 1/θ``. ``dim = 2`` reproduces the
  bivariate `ArchimedeanCopula` Gumbel exactly.

- **`tests/test_d_gumbel_copula.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_d_gumbel_copula.py` (6 passed; adjacent regression on
`test_nested_clayton_copula` + `test_archimedean_copula_rosenblatt` clean):

1. **CDF closed form + d=2 degeneration**: d=2 CDF = bivariate Gumbel CDF (rel 1e-12);
   d=3 = the explicit ``exp(−(Σ(−ln u_i)^θ)^{1/θ})``.
2. **conditional CDF vs numerical mixed partials (headline)**: equals the
   finite-difference ``∂^{k−1}C`` ratio to abs 1e-7 at d=3 (the recursion is exact; FD
   is the approximation) and 1e-4 at d=4 (4th-order FD noise).
3. **conditional CDF d=2 degeneration**: matches the bivariate Gumbel h-function to
   abs 1e-12 across four (u₁,u₂).
4. **Kendall τ = 1 − 1/θ**: exact (rel 1e-14) for θ ∈ {1, 1.5, 2.2, 5} and equal to the
   bivariate copula's τ.
5. **conditional_ppf round-trip + monotonicity**: `conditional_cdf(append(u_prev,
   conditional_ppf(u_prev, w, k))) = w` to abs 1e-9 for several w; conditional strictly
   increasing in u_k (invertible).
6. **guards**: dim < 2 / θ < 1 / dim mismatch / bad-k raise single-string `SolverError`.

## Honest scope notes

- **The conditional inverse is bisection, not closed form.** Only the conditional CDF
  is analytic; Gumbel has no closed-form quantile, so `conditional_ppf` is 100-step
  bisection (exact to ~1e-12 in u_k, monotone-guaranteed). I do not claim a closed-form
  inverse.
- **Exchangeable only — a single θ for all pairs.** This is not a nested/hierarchical
  Gumbel (no per-cluster θ_g like D085's nested Clayton). Mixed-strength upper-tail
  structure is a reopening item, not delivered here.
- **The g_k recursion merges like powers at 12 dp.** Powers are ``mα − j`` floats;
  merging rounds to 12 decimals to keep the term count bounded. For the moderate d
  (≤ ~6) used in 2.5-D series-system reliability this is exact to working precision;
  very large d would grow the term list and could accumulate round-off — not pursued
  (out of the 2.5-D regime).
- **No Marshall–Olkin frailty sampler.** Sampling, if needed, goes through the
  sequential Rosenblatt `conditional_ppf`; I did not add the positive-stable frailty
  sampler (would be faster for large-batch sampling but is unnecessary here).
- **Not yet wired into `system_reliability_series`.** This wave delivers the copula +
  transform primitive; substituting it for the Gaussian/Clayton dependence in the
  series-system estimator is a separate integration step (reopening).

## Reopening criteria

- **Nested / hierarchical Gumbel** (per-cluster θ_g ≥ θ_outer) mirroring D085's nested
  Clayton, for mixed upper-tail-dependence clusters.
- **Wire `gumbel_d_copula` into `system_reliability_series`** so a series system with
  joint-extreme (upper-tail) dependence uses Gumbel instead of Gaussian/Clayton.
- **Positive-stable frailty sampler** for large-batch Monte-Carlo sampling of the
  d-Gumbel (faster than per-sample bisection Rosenblatt).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
