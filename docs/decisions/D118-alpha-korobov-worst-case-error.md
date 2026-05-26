# D118 — α≥2 higher-smoothness weighted-Korobov worst-case error (Wave EEEEEEEE, v16)

**Status**: Accepted
**Wave**: EEEEEEEE (v16)
**Supersedes**: none (closes D112's "higher smoothness α≥2" reopening; extends `korobov_worst_case_error`)
**Superseded by**: none

## Context

D112 (v15) built the deterministic worst-case error `korobov_worst_case_error` for the
**smoothness α=1** weighted-Korobov space (the `B₂` kernel `ω(x)=2π²B₂({x})`), and recorded
as a reopening:

> *"Higher smoothness (α≥2, `B_{2α}` kernels)."*

Smoother integrands live in higher-α spaces, where good lattice rules converge faster
(`O(N^{−α+δ})`). D118 generalises the certificate to α≥2.

## Decision

- **`_korobov_kernel_omega_alpha(x, alpha)`** — the higher-smoothness kernel piece
  `ω_α(x) = (−1)^{α+1}(2π)^{2α}/(2α)! · B_{2α}({x})` for α∈{1,2,3} (closed-form Bernoulli
  polynomials `B₂,B₄,B₆`; numpy-only, no special-function dependency). The kernel
  `K(x,y)=Π_j(1+γ_j ω_α({x_j−y_j}))` is positive-definite (Fourier coefficients
  `γ_j/|h|^{2α}≥0`) with `∫₀¹ω_α=0`.
- **`korobov_worst_case_error(z, n_points, weights, smoothness=1)`** — `smoothness=α`
  selects the space. **α=1 (default) uses the exact same `_korobov_kernel_omega` code path**
  (byte-exact with D112); α≥2 certifies the smoother space.

## Verification (quantitative anchors)

`tests/test_alpha_korobov.py` (6 passed; adjacent regression on `test_deterministic_qmc` +
`test_genz_cbc`, 12 pass):

1. **byte-exact α=1**: `smoothness=1` reproduces the D112 default bit-exactly (same code
   path).
2. **spatial ≡ general (α=2)**: the O(N) spatial `e²` equals the O(N²) general RKHS
   double-sum form with the `B₄` kernel to machine precision (abs 1e-12), and `e²≥0`.
3. **higher α decays faster**: the mean error ratio per N-doubling strictly increases with
   α (probe: α=1 ≈1.68×, α=2 ≈2.94×, α=3 ≈5.21× per doubling) — the smoother-space payoff.
4. **α=3 finite & non-negative** (`B₆` kernel).
5. **kernel closed forms**: `ω_1` equals the D112 `2π²B₂`; `ω_2` equals `−(2π)⁴/4!·B₄` at a
   sample point (abs 1e-12).
6. **guards**: `smoothness < 1` and unsupported α (≥4) raise `SolverError`.

## Honest scope notes

- **α ∈ {1,2,3} only** — the closed-form Bernoulli polynomials `B₂,B₄,B₆` are hard-coded to
  stay numpy-only (no `scipy.special.bernoulli`). α≥4 raises `korobov_smoothness_unsupported`
  rather than silently degrading; a general Bernoulli recurrence is a reopening.
- **Certificate is for the lattice rule's worst-case quality** in the α-smooth space
  (same RKHS interpretation as D112) — not a tight bound on a specific integrand.
- **`O(N^{−α+δ})` is the asymptotic rate**; the test asserts the *measured* decay ratio
  increases with α on a finite N-ladder (61–521), a concrete quantitative claim, not the
  asymptotic constant.
- **`cbc_korobov_generating_vector` is unchanged** (still α=1); a smoothness-aware CBC that
  optimises `z` for α≥2 is a natural follow-up, not done here.

## Reopening criteria

- **Smoothness-aware CBC** (`cbc_korobov_generating_vector(..., smoothness=α)`) optimising
  the generating vector for the α-smooth space.
- **General α** via a Bernoulli-polynomial recurrence (drop the α∈{1,2,3} cap).
- **Wire α≥2 into `genz_mvn_cdf_cbc`** for smoother MVN integrands.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
