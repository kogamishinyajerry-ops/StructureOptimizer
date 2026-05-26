# D111 — multi-family mixture copula in series-system reliability (Wave FFFFFFF, v15)

**Status**: Accepted
**Wave**: FFFFFFF (v15)
**Supersedes**: none (closes D098's reopening; generalises D098 `system_reliability_series_copula`)
**Superseded by**: none

## Context

D098 (v14) wired the `d`-variate **Gumbel** copula into the production series-system
estimator `system_reliability_series_copula(betas, copula)` and recorded as a reopening
criterion:

> *"general Rosenblatt beyond series safety / other families."*

That estimator accepts a **single exchangeable Archimedean** family — Gumbel (upper-tail,
joint-extreme clustering) **or** Clayton (lower-tail, joint-survival) — never both. A real
failure-mode system can exhibit **both** tails at once, which no single one-parameter
Archimedean copula can represent. D111 adds the **multi-family mixture** so the production
estimator covers blended-tail dependence.

## Decision

- **`MixtureCopula`** — a convex combination `C(u) = Σ_k w_k C_k(u)` of `d`-variate
  copulas (`w_k ≥ 0`, `Σ w_k = 1`). Exposes `.dim` and `.cdf(u)`, so it drops **straight
  into the unchanged `system_reliability_series_copula`** (no production function edited —
  pure addition, like D110).
- **`multi_family_copula(components, weights)`** — factory taking a list of copulas (each
  with `.dim`/`.cdf`, equal `dim`) and simplex weights.

**Why it is exact (not numerical)**: because `P_f = 1 − C(u)` and `Σ w_k = 1`,

    P_f(mixture) = 1 − Σ_k w_k C_k(u) = Σ_k w_k (1 − C_k(u)) = Σ_k w_k · P_f(C_k),

so the mixture's series failure probability is the **convex combination of the component
failure probabilities**. A finite convex combination of copulas is itself a copula (the
copula class is convex: each component has uniform margins `C_k(1,…,u_i,…,1)=u_i`, so the
mixture does too), so the result is a valid dependence model that plugs into D098's wiring.

## Verification (quantitative anchors)

`tests/test_multi_family_copula.py` (6 passed; adjacent regression on
`test_series_copula_reliability` + `test_d_gumbel_copula` + `test_gumbel_dvar_copula` +
`test_nested_clayton_copula` + `test_copula_rosenblatt`, 33 pass):

1. **headline — convex-combination identity**: a Gumbel(θ=3)+Clayton(θ=2) blend (w=0.65)
   has `P_f = w·P_f(Gumbel) + (1−w)·P_f(Clayton)` to machine precision (abs 1e-14).
2. **byte-exact opt-in default**: a single-component mixture (w=1) — and a two-component
   mixture with a zero weight — reproduce the pure-family `system_reliability_series_copula`
   path with **exact equality** (the mixture subsumes D098; integration铁律).
3. **binding (changes the answer)**: with 0<w<1 and two genuinely-different families the
   mixture `P_f` lies **strictly between** (and ≠) each pure family's `P_f` — neither
   Gumbel nor Clayton alone gives the mixed-tail answer.
4. **valid copula (uniform margins)**: `C(1,…,u_i,…,1)=u_i` exactly (abs 1e-12) — the
   Sklar margin property survives the convex combination.
5. **≥3 families**: the identity holds for a three-family mixture (Gumbel + two Claytons)
   with simplex weights.
6. **guards**: weight/component count mismatch, negative weight, un-normalised weights,
   mismatched component dims, empty components all raise `SolverError`.

## Honest scope notes

- **CDF-level multi-family, not a mixture Rosenblatt sampler.** The mixture provides
  `.cdf` only — enough for `system_reliability_series_copula` (which uses the CDF), **not**
  the conditional-CDF / inverse transform needed to *sample* from a mixture (that requires
  per-component conditional densities and is genuinely heavier). I scope D111 to the
  multi-family **system-reliability** half of D098's reopening and defer mixture sampling.
- **Normal marginals unchanged.** `system_reliability_series_copula` still maps β→Φ(β)
  (standard-normal safe-probabilities); D111 generalises the **dependence** structure, not
  the **marginals**. General non-normal-marginal Rosenblatt remains a reopening.
- **Convexity is the only mathematical claim**, and it is elementary (Sklar; the copula
  class is convex). The exactness of the `P_f` identity is validated numerically to 1e-14,
  not re-derived symbolically.
- Pure addition: **no existing production function was modified**, so there is no byte-exact
  regression risk to D098's path beyond anchor 2's explicit reproduction.

## Reopening criteria

- **Mixture Rosenblatt sampling** (conditional CDF / inverse of `Σ w_k C_k`) for
  importance-sampling or simulation under blended-tail dependence.
- **General non-normal marginals** through the mixture (full Rosenblatt with per-mode
  arbitrary marginal distributions).
- **Parallel / general system events** (not only series "all safe") under a mixture copula.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
