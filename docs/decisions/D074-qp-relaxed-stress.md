# D074 — qp-relaxed stress: stress-singularity relaxation (Wave SSS, v11)

**Status**: Accepted
**Wave**: SSS (v11)
**Supersedes**: none (extends D066)
**Superseded by**: none

## Context

D066 delivered a multi-constraint MMA driver (`multi_constraint_mma`) using the
**raw** von Mises p-norm stress. Its recorded honest-scope limitation and first
reopening criterion was explicit:

> *"The stress measure is the raw material von Mises p-norm, not a SIMP-relaxed
> stress (ρ^q·σ_vm) … it does not address the classical stress singularity
> phenomenon (vanishing-density elements with non-zero stress) — relaxation /
> ε-relaxed or qp-stress is a separate, future upgrade."*

The stress singularity is the well-known degeneracy of stress-constrained TO: as
ρ_e→0 the raw material stress σ_vm,e(u) stays **finite** (it is a function of the
state, not of ρ), so the feasible set grows thin spikes at the void corners that
gradient-based optimisers cannot escape. The standard cure is **qp-relaxation**
(Bruggi): replace the constraint stress by `σ̃_e = ρ_e^q · σ_vm,e(u)` with the
relaxation exponent `q < p_simp`, so a vanishing-density element contributes
**vanishing** relaxed stress and the singular spikes disappear. v11 Wave SSS
cashes this in.

The blocker was that D066's adjoint was purely *implicit* (no explicit ρ term).
The qp measure adds an **explicit** `ρ^q` factor, so the sensitivity gains an
explicit term alongside a re-derived implicit adjoint. This ADR delivers that.

## Decision

- **`stress.qp_relaxed_stress_pnorm_sensitivity(config, mesh, densities, p=8.0,
  q=2.5, mask=None) → (sigma_pn_relaxed, dsdrho)`** — the density sensitivity of
  the qp-relaxed stress p-norm. The aggregated measure is
  `σ̃_PN = (Σ_e (ρ_e^q·σ_e)^p)^(1/p)`. Because the per-element relaxed stress
  `σ̃_e = ρ_e^q·σ_e(u)` carries **both** an explicit ρ factor and an implicit
  state dependence, the total derivative splits cleanly:

      dσ̃_PN/dρ_e = w_e · [ q·ρ_e^(q−1)·σ_e            (explicit)
                          + ρ_e^q · (∂σ_e/∂uₑ)·(∂u/∂ρ_e) ]   (implicit, adjoint)

  with `w_e = (σ̃_e/σ̃_PN)^(p−1)`. The implicit part reuses the D066 adjoint
  machinery (`K λ = ∂σ̃_PN/∂u` where `∂σ̃_PN/∂u` accumulates `w_e·ρ_e^q·dσ_e/duₑ`,
  and `dσ̃_PN/dρ_e |_implicit = −dscale_e·(λₑᵀ kₑ uₑ)`). The explicit part is a
  pure algebraic `w_e·q·ρ_e^(q−1)·σ_e`. Both share `_element_stress_matrix`
  (`S = D·B`) and the `_VON_MISES_FORM` quadratic form `V`.

- **`nonlinear_simp.qp_stress_constrained_mma(config, mesh, sigma_limit, p=8.0,
  q=2.5, vf=None, max_iter=40, change_tol=1e-3) → MultiConstraintTOResult`** —
  mirrors `multi_constraint_mma` (D066) but swaps the stress gradient for the
  qp-relaxed adjoint. Two inequalities for `mma_step`:

      g₁(x) = σ̃_PN(x)/σ_lim − 1 ≤ 0   (relaxed stress)
      g₂(x) = mean(x) − vf ≤ 0         (volume)

  `stress_history` records the relaxed `σ̃_PN`; reuses `MultiConstraintTOResult`.

- **`tests/test_qp_stress_relaxation.py`** — four quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_qp_stress_relaxation.py` (4 passed; adjacent regression on
test_multi_constraint_mma / test_stress / test_adjoint_stress /
test_nonlinear_simp / test_augmented_lagrangian below):

1. **qp-relaxed sensitivity vs central-FD**: the full `dσ̃_PN/dρ` (explicit
   `ρ^q` term + implicit adjoint) matches central finite differences to relative
   error ≤ 1e-4 on the 6 highest-|sensitivity| elements (measured ≈ 1e-7). This
   validates the explicit term — the part D066's pure-implicit adjoint did not
   have.
2. **relaxation removes the stress singularity**: a vanishing-density element's
   relaxed stress `σ̃_e = ρ_e^q·σ_e` is suppressed by exactly `ρ_e^q` relative to
   its finite raw von Mises stress (probe: ρ≈0.2 → ρ^2.5 ≈ 0.018, a >50×
   suppression), and vectorised `σ̃_e ≤ σ_e` for every element. The spurious
   finite void stress that makes the raw feasible set singular is removed.
3. **qp-stress-constrained MMA satisfies both constraints**: with
   `σ_lim = 0.7·`(volume-only baseline relaxed σ̃_PN), the optimised relaxed
   stress lands **on** the limit (binding, within +2 %) and below 0.9× baseline,
   while volume stays ≤ vf+0.02. Probe (120 iters): baseline σ̃_PN 2321 →
   constrained 1625.2 ≤ limit 1625.0, volume held at 0.450.
4. **contract + determinism**: histories aligned, `sigma_limit` echoed, two runs
   bit-identical.

## Honest scope notes

- **Buckling-constrained driving was attempted and is deferred** (this is the
  most important honesty note of the wave). The blueprint-v11 SSS row and the
  D066 reopening list both named "buckling eigenvalue constraint alongside
  stress/volume". The codebase *has* `buckling.buckling_load_factor` and
  `buckling_sensitivity` (v4/Wave U), but they are **analysis-grade, not
  design-grade**: `buckling_sensitivity` uses the adjoint-free approximation
  `∂λ/∂ρ ≈ φᵀ(∂K/∂ρ + λ∂K_g/∂ρ)φ / (φᵀ(−K_g)φ)` — it **ignores ∂u/∂ρ** (the
  pre-buckling state's design dependence, which feeds K_g) and has **no
  void-mode relaxation** (low-density regions spawn spurious local pseudo-modes).
  Probe evidence (cantilever smoke mesh, fixed-volume buckling ascent maximising
  λ_crit over 25 MMA iters): **baseline λ_crit = 20.1 → it5 = 3.6 → it24 = 8.1**
  — the "ascent" *drops* λ_crit and never recovers to baseline, i.e. the
  sensitivity points the wrong way for driving design. A buckling-constrained
  MMA showed the same collapse. Claiming a working buckling driver would violate
  the "自我贬低优先于自我吹嘘" red line, so Wave SSS is **re-scoped to qp-relaxed
  stress only** and buckling-driving is moved to an explicit reopening criterion
  with this probe data as the entry condition.
- The relaxation exponent defaults `q = 2.5 < p_simp` and aggregation `p = 8`.
  These are not auto-tuned; very small q or very large p can stiffen the MMA
  subproblem. The tests fix (p, q) = (8, 2.5).
- The underlying von Mises stress is still `fem2d._approx_element_stress`'s
  element-centroid constant stress (single finite-difference strain), as named
  `_approx_`; the qp sensitivity differentiates exactly that kernel, so it is
  *consistent* but inherits the approximation.
- The objective is **linear** compliance (not full-TL end-compliance).
- The `converged` flag may read `False` when `|Δx|` plateaus just above
  `change_tol` at the binding point; tests assert feasibility/binding, not the
  flag (and the binding-constraint anchor needs ~120 iters on the smoke mesh,
  not the default 40).

## Reopening criteria

- **Buckling-constrained / buckling-maximising TO** — requires a **design-grade**
  buckling sensitivity: include the `∂u/∂ρ` term (adjoint through the
  pre-buckling state into K_g) **and** a void-mode filter / mode-tracking to
  suppress spurious low-density pseudo-modes. Entry condition: a probe where
  fixed-volume λ_crit ascent *increases* λ_crit above baseline on the smoke mesh
  (current probe: 20.1 → 8.1, fails).
- **Auto-tuned / continuation q** (relax q from low→target during iterations) to
  trade singularity-removal against constraint stiffness.
- **Regional qp-stress aggregation** (per-region P-norm) to reduce the single
  aggregate's locality error, same as D066's regional reopening.
- **qp-stress + TL** (geometric nonlinearity) combining this adjoint with the
  D044 TL adjoint.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
