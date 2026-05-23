# D038 — FORM / SORM + importance sampling (Wave II)

**Status**: Accepted
**Wave**: II (v6)
**Supersedes**: none (complements D029's Monte Carlo UQ; addresses its rare-event note)
**Superseded by**: none

## Context

v5 Wave CC (D029) shipped `monte_carlo_uq` (stochastic.py): crude Monte Carlo
over compliance under load/material uncertainty. D029's honest scope note flagged
the fatal weakness for **reliability** work — crude MC needs O(1/P_f) samples to
observe a single tail event, so estimating a failure probability of ~1e-4 needs
tens of thousands of FEM solves and still has a large coefficient of variation.
The structural-reliability literature solves this with FORM/SORM (analytical
reliability index) and importance sampling (variance reduction). v6 adds them.

## Decision

Add to `core/reliability.py`, all operating in standard-normal U-space with
failure = {g(u) ≤ 0} (the Hasofer-Lind formulation; origin assumed safe):

- `form_hlrf(limit_state, n_vars, ...)` — HL-RF iteration to the most-probable
  point (MPP). Returns `ReliabilityResult` with β = sign(g(0))·‖u*‖ and
  P_f = Φ(−β). Central-difference gradient (numpy-only). For a linear limit
  state it is exact and converges in one step.
- `sorm_breitung(limit_state, form_result, ...)` — Breitung's second-order
  correction: P_f ≈ Φ(−β)·∏(1+βκᵢ)^(−1/2), where κᵢ are eigenvalues of the
  tangent-projected finite-difference Hessian scaled by ‖∇g‖. Reduces exactly
  to FORM for a linear (zero-curvature) limit state.
- `importance_sampling(limit_state, n_vars, design_point, ...)` — samples
  N(u*, I) and weights by the likelihood ratio φ(u)/h(u) = exp(½‖u*‖² − u*ᵀu).
  Returns P_f, std error, coefficient of variation, failure count.
- `standardize_gaussian(x, mean, std)` — maps physical independent Gaussians to
  U-space. `_standard_normal_cdf` uses `math.erf` (no scipy).

`monte_carlo_uq`, `worst_case_simp` and all v5 callers are untouched.

## Verification (quantitative)

- **FORM exact on linear** (`test_form_linear_exact_beta`,
  `test_form_linear_converges_in_one_step`): g(u)=β₀−aᵀu gives β=β₀/‖a‖ and
  P_f=Φ(−β) to ≤1e-7, MPP=(β₀,0,…) to ≤1e-6, in ≤2 iterations. The analytical
  anchor.
- **Origin-unsafe sign** (`test_form_origin_unsafe_negative_beta`): β₀<0 →
  β<0, P_f>0.5, matching Φ(+|β₀|).
- **SORM ≡ FORM for linear** (`test_sorm_reduces_to_form_for_linear`): rel 1e-6.
- **SORM curvature direction** (`test_sorm_parabola_bends_pf_down`): a parabola
  curving away from the origin (convex safe domain) gives P_f < FORM and matches
  the closed-form Breitung value Φ(−β)(1+βκ)^(−1/2) to rel 5%. This validates
  the curvature sign + formula.
- **Importance sampling** (`test_importance_sampling_matches_analytical`,
  `..._beats_crude_mc_variance`): at the rare event β=3 (P_f≈1.35e-3), IS
  recovers the analytical P_f to rel 12% and has a coefficient of variation
  below 0.10 and below ¼ of the analytical crude-MC cov sqrt((1−P_f)/(N·P_f))
  at the same N. The variance-reduction anchor.
- Contract errors (bad dimension / sample count / std). 10 tests, all green.
  Adjacent `test_robust` + `test_stochastic` (26) unchanged.

## Honest scope notes

- The methods operate on a user-supplied limit state in U-space. A FEM-coupled
  limit state — g(X) = C_allow − compliance(X) with X mapped via
  `standardize_gaussian` — plugs into the same callable, but is **not** bundled
  as a driver here (each evaluation is a full FEM solve; reliability-based TO is
  a future driver).
- SORM uses Breitung's asymptotic (large-β) formula; the more accurate
  Tvedt three-term or exact-integral corrections are out of scope.
- The HL-RF gradient/Hessian are finite-difference; analytic sensitivities for
  smooth limit states would be faster but the FD path keeps the interface
  black-box.
- Assumes independent standard-normal variables; correlated / non-Gaussian
  variables need a Nataf/Rosenblatt transform (future).

## Reopening criteria

- A reliability-based TO driver → wrap a compliance limit state + sensitivities.
- Correlated or non-Gaussian uncertainty → add the Nataf transform.
- Highly nonlinear limit states where Breitung is inaccurate → add Tvedt/SORM-IS.

## Red lines

numpy + stdlib `math` only (Φ via `erf`), 2D-proxy, single-line stderr — all held.
