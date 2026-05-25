# D085 — nested/hierarchical Clayton copula with per-cluster θ (Wave DDDD, v12)

**Status**: Accepted
**Wave**: DDDD (v12)
**Supersedes**: none (extends D077)
**Superseded by**: none

## Context

D077 (v11 Wave VVV) added the `d`-variate **exchangeable** Clayton copula — one
`θ`, so every pair has identical dependence. Its recorded reopening criterion:

> *"nested / hierarchical & non-Clayton d-dim copulas."*

Real reliability systems cluster: variables inside a sub-system are tightly
coupled, sub-systems loosely. One `θ` cannot express that. v12 Wave DDDD adds the
two-level **nested (hierarchical) Clayton** copula with a **per-cluster**
parameter.

## Decision

- **`reliability.NestedClaytonCopula(dim, clusters, theta_outer, thetas_inner)`** —
  with the Clayton generator `φ_θ(u)=u^{-θ}−1`, inverse `ψ_θ(s)=(1+s)^{-1/θ}`, a
  partition of `{0..d-1}` into groups `g` with inner parameters `θ_g` and an outer
  `θ₀`,

      C(u)      = ψ_{θ₀}( Σ_g φ_{θ₀}( C_g(u_g) ) )
      C_g(u_g)  = ψ_{θ_g}( Σ_{i∈g} φ_{θ_g}(u_i) )

  Provides `cdf`, `bivariate_margin_cdf(i,j,·,·)`, `kendall_tau_within(g)`,
  `kendall_tau_between()`. Factory `nested_clayton_copula(...)`.

- **Nesting condition** `θ_g ≥ θ₀ > 0` for every group (Joe/McNeil — *sufficient*
  for a valid copula: within-cluster dependence at least as strong as between)
  enforced in `__post_init__`, alongside a partition check.

- The **bivariate margins are exact** (set the other arguments to 1, using
  `ψ_{θ₀}(φ_{θ₀}(x))=x`): same-group pair `(i,j∈g)` → Clayton(`θ_g`); cross-group →
  Clayton(`θ₀`). Hence pairwise Kendall's τ = `θ_g/(θ_g+2)` within group `g`,
  `θ₀/(θ₀+2)` between. All `θ_g=θ₀` reduces **exactly** to
  `ExchangeableClaytonCopula`.

- **`tests/test_nested_clayton_copula.py`** — six closed-form anchors.

## Verification (quantitative anchors)

`tests/test_nested_clayton_copula.py` (6 passed; adjacent regression on
test_gumbel_dvar_copula + test_copula_rosenblatt = 15 passed):

1. **degeneration**: with all θ equal, `cdf` matches `ExchangeableClaytonCopula.cdf`
   to ≤ 1e-12 on 20 random points.
2. **bivariate-margin structure** (the per-cluster + hierarchy payoff): same-group
   margins match Clayton(6) / Clayton(4), cross-group margins match Clayton(2) — to
   ≤ 1e-12 against the bivariate `ArchimedeanCopula`.
3. **per-cluster Kendall's τ**: within-group 6/8 and 4/6, between-group 2/4, with
   `τ_g0 > τ_g1 > τ_between` (clusters genuinely differ; within > between).
4. **valid copula**: `C(1,…,1)=1`, a near-zero argument grounds `C→0`, uniform
   margins `C(u_i,1,1,1)=u_i`.
5. **density ≥ 0** (the 4th mixed partial) on a 16-point grid under the enforced
   nesting condition.
6. **guards**: nesting-condition violation / non-partition clusters / cluster-θ
   count mismatch / non-positive outer θ raise `SolverError`.

## Honest scope notes

- **No nested Rosenblatt transform / sampler this wave — the exchangeable D077
  transform remains the FORM workhorse.** `ClaytonRosenblattTransform` (D077) gives
  a fully-analytic `d`-dim Rosenblatt map for the *exchangeable* case. The nested
  copula's sequential conditional CDFs need derivatives through *two* generator
  layers (Faà di Bruno), and exact sampling needs the Marshall-Olkin
  tilted/inner-frailty construction (a tilted-stable draw — **not** numpy-trivial,
  and pulling a special-function sampler would brush the numpy-only red line).
  Rather than fake a transform, this wave ships the copula's **structure** (CDF +
  exact bivariate margins + per-cluster τ) and **reopens** the nested transform.
- **Nesting condition is *sufficient*, not necessary, and I do not claim to detect
  its violation by a negative density.** A probe with `θ_inner < θ_outer` did *not*
  produce a negative density on the tested grid — the invalidity, when it bites,
  appears at other arguments / more extreme parameters. I enforce `θ_g ≥ θ₀` as the
  standard guard and make **no** claim to demonstrate non-validity; the density
  anchor only confirms validity *holds* under the guard.
- **Two levels only, single family (Clayton).** Deeper hierarchies (clusters of
  clusters) and mixed families (e.g. Gumbel outer, Clayton inner) are not
  implemented; "non-Clayton d-dim" from D077's criterion is only partially
  addressed (Gumbel exists bivariately from D077, not yet `d`-dim nested).
- **`bivariate_margin_cdf` builds the full `d`-vector** (others = 1) and calls
  `cdf` — `O(d)` per call, fine at these dimensions; no separate fast path.

## Reopening criteria

- **Nested Rosenblatt transform + sampler**: the sequential conditional CDFs
  through nested generators (for `form_hlrf`), and a numpy-only Marshall-Olkin
  sampler if a tilted-stable draw can be done without a special-function
  dependency.
- **Deeper / partially-nested hierarchies** (clusters of clusters) with the nesting
  condition applied level-by-level.
- **Mixed-family nesting** (e.g. Gumbel outer + Clayton inner) and a `d`-dim
  exchangeable Gumbel to round out "non-Clayton d-dim".

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
