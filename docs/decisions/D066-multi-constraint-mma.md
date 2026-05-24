# D066 — multi-constraint MMA: stress p-norm + volume (Wave KKK, v10)

**Status**: Accepted
**Wave**: KKK (v10)
**Supersedes**: none (extends D058)
**Superseded by**: none

## Context

D058 delivered an MMA-driven topology optimiser (`mma_nonlinear_to`) but used
it with a **single** inequality constraint (volume), so on a compliance-only
problem MMA only matched OC — the honest D058 claim was *"MMA's payoff over OC is
additional constraints (stress, buckling), not beating OC on compliance"*. That
is precisely D058's recorded reopening criterion: **multi-constraint MMA-TL
(stress/buckling alongside volume)**. v10 Wave KKK cashes it in for the stress
case.

The blocker was that the codebase had the *forward* p-norm von Mises stress
(`stress.p_norm_stress`, `element_von_mises_stresses`) but **no density
sensitivity** — the v1.6 stress module explicitly deferred "full
stress-constrained SIMP (gradient via adjoint method)" to a later ADR. This is
that ADR.

## Decision

- **`stress.stress_pnorm_sensitivity(config, mesh, densities, p=8, mask=None)`**
  — the p-norm stress density sensitivity via the **adjoint method**. The
  aggregated measure is `σ_PN = (Σ_e σ_e^p)^(1/p)` (the smax-normalised
  `p_norm_stress` equals this exactly: the normalisation cancels). Each element
  von Mises stress is the norm of a quantity **linear in the element
  displacement**, `σ_e² = (S uₑ)ᵀ V (S uₑ)` with `S = D·B` the constant
  per-element stress-displacement operator (`_element_stress_matrix`, derived by
  differentiating the same edge-difference plane-stress kernel as
  `fem2d._approx_element_stress`) and `V` the von Mises quadratic form. The raw
  material stress has **no explicit ρ dependence**, so `σ_PN` depends on the
  design only through the state `u(ρ)`, giving the pure adjoint term

      dσ_PN/dρ_e = − dscale_e · (λₑᵀ kₑ uₑ),   K λ = ∂σ_PN/∂u

  where `dscale_e = pen·ρ_e^(pen−1)·(1−ρ_min)` is the SIMP scaling derivative
  (0 on void cells) and `∂σ_PN/∂σ_e = (σ_e/σ_PN)^(p−1)`,
  `∂σ_e/∂uₑ = (V s)ᵀ S / σ_e`. The adjoint reuses the FEM backend
  (dense/sparse) and `get_linear_solver`.

- **`nonlinear_simp.multi_constraint_mma(config, mesh, sigma_limit, p=8, vf=None,
  max_iter=40, change_tol=1e-3)`** — minimise linear compliance subject to **two**
  inequalities handled by `mma_step`:

      g₁(x) = σ_PN(x)/σ_lim − 1 ≤ 0   (stress)
      g₂(x) = mean(x) − vf ≤ 0        (volume)

  Objective gradient = standard SIMP `dc/dρ_e = −dscale_e·(uₑᵀ kₑ uₑ)`;
  stress-constraint gradient = the adjoint above; both density-filtered. Returns
  `MultiConstraintTOResult` (densities + compliance/volume/stress histories +
  `sigma_limit` + converged + mesh_shape).

- **`tests/test_multi_constraint_mma.py`** — four quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_multi_constraint_mma.py` (all pass; adjacent regression on
test_mma_nonlinear_to / test_nonlinear_simp / test_nonlinear_to_oc /
test_nonlinear_to_adjoint / test_stress / test_adjoint_stress /
test_augmented_lagrangian / test_stress_constrained_simp_auglag = 76 passed):

1. **stress sensitivity vs central-FD**: adjoint `dσ_PN/dρ` matches central
   finite differences to relative error ≤ 1e-4 on the 6 highest-|sensitivity|
   elements (measured ≈ 1e-7).
2. **both constraints satisfied**: at convergence `σ_PN ≤ σ_lim·1.02` **and**
   `mean(ρ) ≤ vf+0.02` simultaneously.
3. **stress constraint binds & changes the design**: with `σ_lim = 0.7·`(the
   volume-only `run_simp` design's stress), the optimised `σ_PN` is driven
   strictly below the unconstrained baseline and to within 5 % of the limit
   (active, not slack). Probe: baseline σ_PN 6.56e3 → constrained 4.59e3 ≤ limit
   4.60e3, volume held at 0.450.
4. **contract + determinism**: histories aligned, `sigma_limit` echoed, two runs
   identical.

## Honest scope notes

- The stress measure is the **raw material von Mises p-norm**, *not* a
  SIMP-relaxed stress (`ρ^q·σ_vm`). That keeps the sensitivity purely implicit
  (no explicit ρ term) and exactly FD-validatable, but it means this driver does
  **not** address the classical stress *singularity* phenomenon (vanishing-density
  elements with non-zero stress) — relaxation/ε-relaxed or qp-stress is a
  separate, future upgrade.
- The von Mises stress reuses `fem2d._approx_element_stress`, a **single
  finite-difference strain per element** (element-centroid constant stress), not
  a Gauss-point B-matrix integral. The sensitivity differentiates exactly that
  kernel, so it is consistent — but the underlying stress is itself an
  approximation (as named: `_approx_`).
- The objective is **linear** compliance (not the full-TL end-compliance of
  `mma_nonlinear_to`); combining the stress adjoint with the TL adjoint is a
  further extension, not done here.
- MMA on this problem reliably reaches feasibility but the `converged` flag may
  read `False` when `|Δx|` plateaus just above `change_tol` at the binding point;
  the tests assert feasibility/binding, not the flag.
- The §5 demo rubric greps `**/*.py` and self-matches `test_agent.py`'s own check
  source; the v10 demos are still built genuinely at closure (RRR).

## Reopening criteria

- **SIMP-relaxed / qp-stress** to handle the stress singularity (vanishing
  density elements) — enables true minimum-volume-under-stress designs.
- **Stress + TL** (geometric nonlinearity) by combining this adjoint with the
  D044 TL adjoint.
- **Buckling constraint** alongside stress/volume (linear-buckling eigenvalue
  sensitivity → third `mma_step` inequality).
- **Regional / clustered stress aggregation** (P-norm per region) to reduce the
  single-aggregate's locality error.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
