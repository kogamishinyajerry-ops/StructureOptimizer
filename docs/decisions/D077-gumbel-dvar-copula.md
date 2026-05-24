# D077 — Gumbel copula + d-dimensional exchangeable Clayton (Wave VVV, v11)

**Status**: Accepted
**Wave**: VVV (v11)
**Supersedes**: none (extends D069)
**Superseded by**: none

## Context

D069 added bivariate **Clayton** and **Frank** Archimedean copulas with a
closed-form Rosenblatt transform (`CopulaRosenblattTransform`). Two limitations,
recorded as its reopening criterion:

> *"d-dimensional / Gumbel copulas."*

Clayton and Frank cover lower-tail and tail-free dependence but **not upper-tail**
dependence — the **Gumbel** family. And the transform was hard-wired to exactly
**two** variables (`build_copula_rosenblatt` raises for any other count), while
real reliability problems have d ≥ 3 correlated inputs. v11 Wave VVV adds both.

## Decision

- **Gumbel added to `ArchimedeanCopula`** (`family="gumbel"`, `θ ≥ 1`):
  generator `φ(t)=(−ln t)^θ`, CDF `C=exp(−((−ln u₁)^θ+(−ln u₂)^θ)^{1/θ})`,
  conditional `C_{2|1}=∂C/∂u₁ = C·A^{1/θ−1}·(−ln u₁)^{θ−1}/u₁` with
  `A=(−ln u₁)^θ+(−ln u₂)^θ`, conditional inverse by **bisection** (no closed
  form; the conditional is monotone in u₂), and Kendall's τ = `1 − 1/θ`. Factory
  `gumbel_copula(theta)`.

- **`ExchangeableClaytonCopula(dim, theta)`** + `clayton_d_copula(dim, theta)` —
  the d-variate exchangeable Clayton copula. Because the generator inverse
  `ψ(s)=(1+s)^{-1/θ}` has derivatives `ψ^{(j)}(s)=(−1)^j[Π_{l<j}(1/θ+l)](1+s)^{-1/θ-j}`,
  the constant Π and sign **cancel in the conditional ratio**, giving the closed
  forms

      C_{k|1..k-1}(u_k | u_{<k}) = (T_k/T_{k-1})^{-(1/θ + k − 1)},
      T_j = Σ_{i≤j} u_i^{-θ} − (j−1),
      u_k = [ T_{k-1}·(w^{-1/(1/θ+k-1)} − 1) + 1 ]^{-1/θ}   (inverse).

  `cdf`, `conditional_cdf`, `conditional_ppf`, `kendall_tau` (= θ/(θ+2)).

- **`ClaytonRosenblattTransform(marginals, copula)`** + `build_clayton_rosenblatt(
  marginals, theta)` — a **d-dim** sequential Rosenblatt transform
  (`u_i=F_i(x_i)`; `w_1=u_1`, `w_k=C_{k|1..k-1}`; `z=Φ⁻¹(w)`, and the inverse),
  mirroring D069's `CopulaRosenblattTransform` interface (`wrap_limit_state`) so
  `form_hlrf` runs unchanged at any dimension.

- **`tests/test_gumbel_dvar_copula.py`** — six quantitative anchors.

## Verification (quantitative anchors)

`tests/test_gumbel_dvar_copula.py` (6 passed; adjacent regression on
test_archimedean_copula / test_copula_rosenblatt / test_reliability /
test_correlated_system_rbto / test_nataf_correlation / test_form below — 78
passed, 4 slow skipped):

1. **Gumbel conditional = numerical ∂C/∂u₁** to ≤ 1e-6; its bisection inverse
   round-trips `conditional_ppf(u₁, C_{2|1})=u₂` to ≤ 1e-9; Kendall's τ = 1−1/θ
   (1e-12).
2. **Gumbel θ < 1 raises** `SolverError`.
3. **d-dim Clayton conditional = true Rosenblatt conditional**: the closed-form
   `C_{3|1,2}` equals the numerical ratio of mixed partials
   `∂²C₃/∂u₁∂u₂ / ∂²C₂/∂u₁∂u₂` to relative error ≤ 1e-5 (measured ≈ 4e-7).
4. **d-dim Rosenblatt round-trip** `z → x → z` to ≤ 1e-9 for d = 3 and d = 4.
5. **correct dependence**: `kendall_tau` = θ/(θ+2) in closed form, and the
   empirical pairwise Kendall's τ of 3000 samples generated through the transform
   matches it to ≤ 0.04 (sampling noise) for all three pairs at d = 3.
6. **error handling**: dim < 2, non-positive θ, CDF dim mismatch, too-few
   marginals all raise `SolverError`.

## Honest scope notes

- **Gumbel's conditional inverse is bisection, not closed form** (100 iterations,
  ~1e-15 interval). The forward conditional CDF is exact; only the inverse is
  numerical. This makes the Gumbel `u_to_x` mildly more expensive than
  Clayton/Frank, and the inverse accuracy is the bisection tolerance, not machine
  epsilon.
- **The d-dim copula is exchangeable Clayton only** — a *single* θ, *symmetric*
  dependence across all pairs (same τ for every pair). It is **not** a nested /
  hierarchical Archimedean copula (different θ per cluster) and **not** d-dim
  Gumbel or Frank (whose generator derivatives need Bell-polynomial / Faà di Bruno
  expansions or numerical differentiation — deferred). The class name says
  "Exchangeable" to be honest about this.
- **Marginals route through the normal map.** `_marginal_cdf`/`_marginal_ppf`
  compose with `to_standard_normal`/`from_standard_normal`, so the copula couples
  the *uniforms*, but each marginal's tail fidelity is the D043/D045 `Marginal`
  map's, not improved here.
- **No tail-dependence parameter exposed.** Gumbel's upper-tail coefficient
  `λ_U = 2 − 2^{1/θ}` and Clayton's lower-tail `λ_L = 2^{-1/θ}` are implied by θ
  but not surfaced as helpers.
- The d-dim conditional CDF is validated at one interior point against mixed
  partials; it is exact by construction (the generator-derivative ratio), the
  numerical check guards the algebra, not a sampled region.

## Reopening criteria

- **Nested / hierarchical Archimedean copulas** (per-cluster θ) for partially
  exchangeable dependence.
- **d-dim Gumbel / Frank** via Bell-polynomial generator derivatives (or numerical
  ψ^{(j)}), to lift the d-dim path beyond Clayton.
- **Closed-form Gumbel conditional inverse** (e.g. via the Gumbel frailty /
  positive-stable representation) to remove the bisection.
- **Tail-dependence helpers** (`λ_U`, `λ_L`) and a Kendall-τ → θ inverse so users
  can specify dependence by τ directly.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
